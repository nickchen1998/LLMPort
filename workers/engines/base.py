"""推論引擎的共同介面。每個 worker 行程只載入一個引擎（一個模型）。"""
import math
from collections.abc import Callable, Iterator
from pathlib import Path

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_OPTIONS = len(LETTERS)


class EngineError(Exception):
    """引擎不支援這個操作，或輸入有問題；訊息會照 OpenAI 錯誤格式回給用戶端。"""


class Engine:
    name = "base"

    def __init__(self, path: str, *, context_length: int = 32768, dims: int | None = None, **_):
        self.path = Path(path)
        self.context_length = context_length
        self.dims = dims

    # ─── 生命週期 ───

    def load(self, progress: Callable[[str], None]) -> None:
        raise NotImplementedError

    def warmup(self) -> None:
        pass

    def memory_mb(self) -> tuple[float, float]:
        """（目前、峰值）MB。"""
        return 0.0, 0.0

    # ─── 推論 ───

    def count_tokens(self, text: str) -> int:
        return max(1, round(len(text) * .75))

    def chat_stream(self, messages: list[dict], *, max_tokens: int, temperature: float, top_p: float | None,
                    stop: list[str], seed: int | None) -> Iterator[dict]:
        """逐段產生 {"delta": str}，最後一筆是 {"done": True, "finish_reason", "prompt_tokens", "completion_tokens"}。"""
        raise EngineError("This model does not support chat completions.")

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """回傳（已正規化的向量, 輸入 token 數）。"""
        raise EngineError("This model does not support embeddings.")

    def option_probs(self, input_text: str, instructions: str, options: list[str]) -> tuple[list[float], int]:
        """決策用：模型下一個 token 落在各選項代號（A、B、C…）的機率，與輸入 token 數。"""
        raise EngineError("This model does not support decisions.")


def decision_messages(input_text: str, instructions: str, options: list[str]) -> list[dict]:
    """把一個決策問題組成提示：選項編成 A、B、C…，要求模型只回一個代號。"""
    lines = "\n".join(f"{LETTERS[i]}. {opt}" for i, opt in enumerate(options))
    return [
        {"role": "system", "content": "You are a precise classifier. Read the input, then answer the question "
                                      "with exactly one option letter and nothing else."},
        {"role": "user", "content": f"Input:\n{input_text}\n\nQuestion: {instructions}\nOptions:\n{lines}\n\n"
                                    f"Answer with one letter ({', '.join(LETTERS[:len(options)])})."},
    ]


def normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class StopBuffer:
    """串流時處理 stop：保留可能是 stop 開頭的尾巴，確定不是才送出。"""

    def __init__(self, stops: list[str]):
        self.stops = [s for s in stops if s]
        self.hold = max((len(s) for s in self.stops), default=1) - 1
        self.buf = ""
        self.stopped = False

    def push(self, text: str) -> str:
        if self.stopped:
            return ""
        self.buf += text
        for s in self.stops:
            idx = self.buf.find(s)
            if idx >= 0:
                out, self.buf, self.stopped = self.buf[:idx], "", True
                return out
        if self.hold <= 0:
            out, self.buf = self.buf, ""
            return out
        out, self.buf = self.buf[:-self.hold], self.buf[-self.hold:]
        return out

    def flush(self) -> str:
        out, self.buf = ("" if self.stopped else self.buf), ""
        return out
