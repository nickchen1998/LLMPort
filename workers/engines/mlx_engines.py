"""MLX 引擎（Apple Silicon）：mlx-lm（文字、決策）、mlx-vlm（看圖）、mlx-embeddings（嵌入）。

需要 `poetry install --with mlx`，模型檔要先下載到本機；worker 啟動時設了 HF_HUB_OFFLINE=1，
所以這裡只讀本機資料夾，不會自動去 Hugging Face 下載。

注意：這三個引擎依各套件公開的 API 撰寫，還沒有用真的模型跑過；第一次在 Mac mini 上載入時請留意 worker log。
"""
import base64
import binascii
import tempfile
from collections.abc import Iterator
from pathlib import Path

from workers.engines.base import LETTERS, Engine, EngineError, StopBuffer, decision_messages, normalize


def _text_only(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            if any(isinstance(p, dict) and p.get("type") == "image_url" for p in content):
                raise EngineError("This model does not support image input.")
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        out.append({"role": m.get("role", "user"), "content": content or ""})
    return out


def _mx_memory() -> tuple[float, float]:
    import mlx.core as mx

    get_active = getattr(mx, "get_active_memory", None) or mx.metal.get_active_memory
    get_peak = getattr(mx, "get_peak_memory", None) or mx.metal.get_peak_memory
    return get_active() / 2 ** 20, get_peak() / 2 ** 20


class MLXLMEngine(Engine):
    name = "mlx-lm"

    def load(self, progress) -> None:
        if not self.path.exists():
            raise EngineError(f"找不到模型資料夾 {self.path}")
        progress("讀取權重到統一記憶體")
        from mlx_lm import load

        self.model, self.tokenizer = load(str(self.path))

    def warmup(self) -> None:
        for _ in self.chat_stream([{"role": "user", "content": "hi"}], max_tokens=1, temperature=0, top_p=None,
                                  stop=[], seed=None):
            pass

    def memory_mb(self) -> tuple[float, float]:
        return _mx_memory()

    def _prompt(self, messages: list[dict]) -> str:
        return self.tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def chat_stream(self, messages, *, max_tokens, temperature, top_p, stop, seed) -> Iterator[dict]:
        import mlx.core as mx
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        if seed is not None:
            mx.random.seed(seed)
        prompt = self._prompt(_text_only(messages))
        sampler = make_sampler(temp=temperature, top_p=top_p or 0.0)
        stopper = StopBuffer(stop)
        prompt_tokens = completion = 0
        finish = "stop"
        for resp in stream_generate(self.model, self.tokenizer, prompt, max_tokens=max_tokens, sampler=sampler):
            prompt_tokens = getattr(resp, "prompt_tokens", prompt_tokens)
            completion = getattr(resp, "generation_tokens", completion + 1)
            piece = stopper.push(resp.text)
            if piece:
                yield {"delta": piece}
            if stopper.stopped:
                break
            if getattr(resp, "finish_reason", None):
                finish = "length" if resp.finish_reason == "length" else "stop"
        tail = stopper.flush()
        if tail:
            yield {"delta": tail}
        yield {"done": True, "finish_reason": finish, "prompt_tokens": prompt_tokens, "completion_tokens": completion}

    def option_probs(self, input_text, instructions, options) -> tuple[list[float], int]:
        import mlx.core as mx

        prompt = self._prompt(decision_messages(input_text, instructions, options))
        ids = self.tokenizer.encode(prompt, add_special_tokens=False)
        logits = self.model(mx.array(ids)[None])[0, -1]
        letter_ids = [self.tokenizer.encode(LETTERS[i], add_special_tokens=False)[0] for i in range(len(options))]
        probs = mx.softmax(logits[mx.array(letter_ids)].astype(mx.float32))
        return probs.tolist(), len(ids)


class MLXVLMEngine(Engine):
    """對話＋看圖。決策暫時只走 mlx-lm 的模型。"""
    name = "mlx-vlm"

    def load(self, progress) -> None:
        if not self.path.exists():
            raise EngineError(f"找不到模型資料夾 {self.path}")
        progress("讀取權重到統一記憶體")
        from mlx_vlm import load
        from mlx_vlm.utils import load_config

        self.model, self.processor = load(str(self.path))
        self.config = load_config(str(self.path))
        self._tmp = tempfile.TemporaryDirectory(prefix="llmport-img-")

    def memory_mb(self) -> tuple[float, float]:
        return _mx_memory()

    def _image_ref(self, url: str) -> str:
        """data URL 存成暫存檔；http(s) 網址直接交給 mlx-vlm。"""
        if not url.startswith("data:"):
            return url
        try:
            header, data = url.split(",", 1)
            raw = base64.b64decode(data)
        except (ValueError, binascii.Error):
            raise EngineError("Invalid image data URL.")
        ext = "png" if "png" in header else "jpg"
        path = Path(self._tmp.name) / f"{len(list(Path(self._tmp.name).iterdir()))}.{ext}"
        path.write_bytes(raw)
        return str(path)

    def chat_stream(self, messages, *, max_tokens, temperature, top_p, stop, seed) -> Iterator[dict]:
        from mlx_vlm import stream_generate
        from mlx_vlm.prompt_utils import apply_chat_template

        images, chat = [], []
        for m in messages:
            content = m.get("content")
            if isinstance(content, list):
                text = []
                for p in content:
                    if not isinstance(p, dict):
                        continue
                    if p.get("type") == "image_url":
                        url = p.get("image_url", {}).get("url") if isinstance(p.get("image_url"), dict) else p.get("image_url")
                        images.append(self._image_ref(url or ""))
                    elif p.get("type") == "text":
                        text.append(p.get("text", ""))
                content = "".join(text)
            chat.append({"role": m.get("role", "user"), "content": content or ""})
        prompt = apply_chat_template(self.processor, self.config, chat, num_images=len(images))
        stopper = StopBuffer(stop)
        prompt_tokens = completion = 0
        for resp in stream_generate(self.model, self.processor, prompt, image=images or None,
                                    max_tokens=max_tokens, temperature=temperature):
            text = resp if isinstance(resp, str) else getattr(resp, "text", "")
            prompt_tokens = getattr(resp, "prompt_tokens", prompt_tokens)
            completion = getattr(resp, "generation_tokens", completion + 1)
            piece = stopper.push(text)
            if piece:
                yield {"delta": piece}
            if stopper.stopped:
                break
        tail = stopper.flush()
        if tail:
            yield {"delta": tail}
        finish = "length" if completion >= max_tokens else "stop"
        yield {"done": True, "finish_reason": finish, "prompt_tokens": prompt_tokens, "completion_tokens": completion}


class MLXEmbeddingsEngine(Engine):
    name = "mlx-embeddings"

    def load(self, progress) -> None:
        if not self.path.exists():
            raise EngineError(f"找不到模型資料夾 {self.path}")
        progress("讀取權重到統一記憶體")
        from mlx_embeddings.utils import load

        self.model, self.tokenizer = load(str(self.path))

    def memory_mb(self) -> tuple[float, float]:
        return _mx_memory()

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        import mlx.core as mx

        tok = getattr(self.tokenizer, "_tokenizer", self.tokenizer)
        enc = tok(texts, return_tensors="np", padding=True, truncation=True, max_length=self.context_length)
        input_ids, mask = mx.array(enc["input_ids"]), mx.array(enc["attention_mask"])
        out = self.model(input_ids, attention_mask=mask)
        emb = getattr(out, "text_embeds", None)
        if emb is None:
            # 沒有現成的句向量時取最後一個有效 token（Qwen3-Embedding 的做法）
            hidden = out.last_hidden_state
            last = mask.sum(axis=1) - 1
            emb = hidden[mx.arange(hidden.shape[0]), last]
        vectors = [normalize(v) for v in emb.astype(mx.float32).tolist()]
        return vectors, int(mask.sum().item())
