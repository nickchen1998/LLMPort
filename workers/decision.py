"""決策 API（Jev／OpenAI Decisions 類型）：不產生文字，用模型下一個 token 的機率回答每個問題。

- predicate：選項是「是」「否」，probability 是「是」的機率。
- choice：每個選項的機率，confidence 用 1 減正規化熵。
- score：每個等級的機率，score 是等級索引乘機率的總和，可以落在兩個等級之間。
機率四捨五入到小數兩位，並把誤差補在最大的那一項，讓總和剛好是 1。
"""
import math

from workers.engines.base import MAX_OPTIONS, Engine, EngineError


def round_probs(probs: list[float]) -> list[float]:
    total = sum(probs) or 1.0
    rounded = [round(p / total, 2) for p in probs]
    diff = round(1 - sum(rounded), 2)
    if diff:
        k = rounded.index(max(rounded))
        rounded[k] = round(rounded[k] + diff, 2)
    return rounded


def confidence(probs: list[float]) -> float:
    n = len(probs)
    if n < 2:
        return 1.0
    entropy = -sum(p * math.log(p) for p in probs if p > 0)
    return round(max(0.0, 1 - entropy / math.log(n)), 2)


def _option_texts(q: dict) -> list[str]:
    if q["type"] == "predicate":
        return ["是（Yes）", "否（No）"]
    if q["type"] == "choice":
        return [f"{c['value']}" + (f" — {c['description']}" if c.get("description") else "") for c in q["choices"]]
    return [f"{lv['label']}" + (f" — {lv['description']}" if lv.get("description") else "") for lv in q["levels"]]


def answer(q: dict, probs: list[float]) -> dict:
    name = q.get("name")
    if q["type"] == "predicate":
        p = round_probs(probs)
        return {"type": "predicate", "name": name, "probability": p[0]}
    ps = round_probs(probs)
    if q["type"] == "choice":
        k = ps.index(max(ps))
        return {"type": "choice", "name": name, "choice": q["choices"][k]["value"], "confidence": confidence(ps),
                "probabilities": [{"value": c["value"], "probability": ps[i]} for i, c in enumerate(q["choices"])]}
    return {"type": "score", "name": name, "score": round(sum(i * p for i, p in enumerate(ps)), 2),
            "confidence": confidence(ps),
            "probabilities": [{"value": i, "label": lv["label"], "probability": ps[i]} for i, lv in enumerate(q["levels"])]}


def decide(engine: Engine, input_text: str, questions: list[dict]) -> tuple[list[dict], int]:
    """回傳（answers, 輸入 token 數）。輸入已由 /v1 驗證過格式。"""
    answers, tokens = [], 0
    for q in questions:
        options = _option_texts(q)
        if len(options) > MAX_OPTIONS:
            raise EngineError(f"At most {MAX_OPTIONS} options are supported per question.")
        probs, used = engine.option_probs(input_text, q["instructions"], options)
        tokens += used
        answers.append(answer(q, probs))
    return answers, tokens
