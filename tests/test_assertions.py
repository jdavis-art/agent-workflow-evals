from awe.assertions import check

TXT = "Seed drift: Cedar Row is missing. Northline box count moved from 18 to 20.\nPaste into seed-data.json."


def test_text_assertions():
    assert check({"contains": "Cedar Row"}, TXT).passed
    assert not check({"contains": "matches vault"}, TXT).passed
    assert check({"not_contains": "Seed matches vault"}, TXT).passed
    assert check({"regex": r"seed-data\.json"}, TXT).passed
    assert check({"not_regex": r"TBD|TODO"}, TXT).passed
    assert check({"length_between": [50, 500]}, TXT).passed
    assert not check({"length_between": [500, 900]}, TXT).passed
    r = check({"mentions_all": ["cedar row", "northline", "Pine"]}, TXT)
    assert not r.passed and "Pine" in r.detail
    assert check({"mentions_none": ["Riverbend"]}, TXT).passed


def test_value_assertions():
    assert check({"equals": 4.0}, 4.0).passed
    assert check({"gte": 0.9}, 0.95).passed and not check({"gte": 0.9}, 0.5).passed
    out = {"precision": 0.7, "confusion": [{"title": "x"}]}
    assert check({"json_path": {"path": "precision", "gte": 0.6}}, out).passed
    assert check({"json_path": {"path": "confusion[0].title", "equals": "x"}}, out).passed
    r = check({"json_path": {"path": "nope.deeper", "equals": 1}}, out)
    assert not r.passed and "nope" in r.detail


def test_unknown_kind():
    r = check({"sparkles": True}, "x")
    assert not r.passed and "unknown assertion" in r.detail
