"""假引擎：沒有模型檔時用來把整條流程跑起來（開發、展示、測試）。

回覆、向量與決策機率都是模擬的，記憶體用登記的預估值。
"""
import hashlib
import math
import random
import time
from collections.abc import Iterator

from utils.settings import env_float
from workers.engines.base import Engine, StopBuffer, normalize


def _bigrams(text: str) -> set[str]:
    t = "".join((text or "").split()).lower()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


class FakeEngine(Engine):
    name = "fake"

    def __init__(self, path: str, *, name: str = "model", simulated_mb: float = 0, **kw):
        super().__init__(path, **kw)
        self.model_name = name
        self.simulated_mb = float(simulated_mb or 0)
        self.tps = env_float("FAKE_TPS", 40)
        self.load_seconds = env_float("FAKE_LOAD_SECONDS", 2)
        self.loaded = False

    def load(self, progress) -> None:
        steps = ["讀取權重到統一記憶體", "預熱：跑一次短推論", "健康檢查"]
        for step in steps:
            progress(step)
            time.sleep(self.load_seconds / len(steps))
        self.loaded = True

    def memory_mb(self) -> tuple[float, float]:
        if not self.loaded:
            return 0.0, 0.0
        jitter = 1 + (random.random() - .5) * .02
        return self.simulated_mb * jitter, self.simulated_mb * 1.04

    def chat_stream(self, messages, *, max_tokens, temperature, top_p, stop, seed) -> Iterator[dict]:
        prompt_text = "\n".join(_text_of(m.get("content")) for m in messages)
        last_user = next((_text_of(m.get("content")) for m in reversed(messages) if m.get("role") == "user"), "")
        has_image = any(isinstance(m.get("content"), list) and any(
            isinstance(p, dict) and p.get("type") == "image_url" for p in m["content"]) for m in messages)
        reply = (f"（假 worker：{self.model_name} 沒有模型檔，這是模擬回覆）"
                 + ("我看到你附了一張圖片。" if has_image else "")
                 + f"你剛剛說的是：「{last_user.strip()[:80]}」。換成真的模型後，這裡會是模型實際生成的內容。")
        chunk_chars = 3
        delay = chunk_chars / 1.3 / self.tps if self.tps > 0 else 0
        stopper = StopBuffer(stop)
        sent_tokens, finish = 0, "stop"
        for i in range(0, len(reply), chunk_chars):
            piece = stopper.push(reply[i:i + chunk_chars])
            if piece:
                yield {"delta": piece}
            sent_tokens = self.count_tokens(reply[:i + chunk_chars])
            if stopper.stopped:
                break
            if sent_tokens >= max_tokens:
                finish = "length"
                break
            if delay:
                time.sleep(delay)
        tail = stopper.flush()
        if tail:
            yield {"delta": tail}
        yield {"done": True, "finish_reason": finish, "prompt_tokens": self.count_tokens(prompt_text) + 8 + (1100 if has_image else 0),
               "completion_tokens": min(sent_tokens, max_tokens)}

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        dims = self.dims or 1024
        vectors = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
            rnd = random.Random(seed)
            vectors.append(normalize([rnd.random() - .5 for _ in range(dims)]))
        return vectors, sum(self.count_tokens(t) for t in texts)

    def option_probs(self, input_text: str, instructions: str, options: list[str]) -> tuple[list[float], int]:
        words = _bigrams(input_text)
        rnd = random.Random(hashlib.sha256((input_text + instructions).encode("utf-8")).digest())
        if len(options) == 2 and options[0].startswith("是"):
            hits = len(_bigrams(instructions) & words)
            p = .9 if hits else .1
            scores = [math.log(p), math.log(1 - p)]
        else:
            scores = [len(_bigrams(opt) & words) * 1.5 + rnd.random() * .3 for opt in options]
        exps = [math.exp(s) for s in scores]
        total = sum(exps)
        tokens = self.count_tokens(input_text) + self.count_tokens(instructions) + 20 * len(options)
        return [e / total for e in exps], tokens
