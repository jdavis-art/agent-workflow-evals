from awe.metrics import precision_recall

ROWS = [
    {"uid": "1", "title": "a", "score": 5, "label": "pursue"},
    {"uid": "2", "title": "b", "score": 3, "label": "ignore"},
    {"uid": "3", "title": "c", "score": 1, "label": "pursue"},
    {"uid": "4", "title": "d", "score": 0, "label": "ignore"},
]


def test_precision_recall():
    m = precision_recall(ROWS, 3)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5
    assert [r["uid"] for r in m["confusion"]] == ["2", "3"]


def test_empty():
    m = precision_recall([], 3)
    assert m["precision"] == 0 and m["recall"] == 0
