from workers.decision import answer, confidence, round_probs
from workers.engines.base import StopBuffer, decision_messages


def test_round_probs_sums_to_one():
    for probs in ([.333, .333, .334], [.811, .17, .019], [1, 1, 1, 1, 1, 1, 1]):
        assert abs(sum(round_probs(probs)) - 1) < 1e-9


def test_confidence_range():
    assert confidence([1, 0]) == 1
    assert confidence([.5, .5]) == 0


def test_score_answer_is_probability_weighted():
    q = {"type": "score", "name": "urgency", "levels": [{"label": "低"}, {"label": "中"}, {"label": "高"}, {"label": "緊急"}]}
    a = answer(q, [.01, .08, .5, .41])
    assert a["score"] == 2.31 and a["probabilities"][3] == {"value": 3, "label": "緊急", "probability": .41}


def test_choice_keeps_original_value_type():
    q = {"type": "choice", "name": None, "choices": [{"value": True}, {"value": False}]}
    a = answer(q, [.2, .8])
    assert a["choice"] is False and a["name"] is None


def test_decision_prompt_uses_letters():
    msgs = decision_messages("輸入", "問題", ["甲", "乙", "丙"])
    assert "A. 甲\nB. 乙\nC. 丙" in msgs[1]["content"]


def test_stop_buffer_holds_back_partial_stop():
    s = StopBuffer(["END"])
    out = s.push("hello E") + s.push("N") + s.push("D tail")
    assert out == "hello " and s.stopped and s.flush() == ""
    s = StopBuffer(["END"])
    assert s.push("abcEN") == "abc" and s.flush() == "EN"
