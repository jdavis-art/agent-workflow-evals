"""Scores golden.csv with the real bid-radar rules. Target for the python runner.

Suite-level dependency: the sibling `bid-radar` package, installed editable into the venv
(`pip install -e C:/Users/jdavi/Documents/Claude/Projects/bid-radar`). It is not a harness dependency."""
import csv
import pathlib

from bid_radar.config import load_config
from bid_radar.model import Solicitation
from bid_radar.scoring import Rules, score
from awe.metrics import precision_recall

HERE = pathlib.Path(__file__).resolve().parent


def score_golden(golden_csv: str = "golden.csv", threshold: int = 3) -> dict:
    rules = Rules.from_config(load_config()["scoring"])
    rows, violations = [], []
    for r in csv.DictReader(open(HERE / golden_csv, encoding="utf-8", newline="")):
        sol = Solicitation(uid=r["uid"], source="bidnet", source_id=r["uid"].split(":")[1], title=r["title"], agency=r["agency"],
                           location=r["location"], bid_type=r["bid_type"], blurb=r["blurb"])
        s, note = score(sol, rules)
        rows.append({**r, "score": s, "note": note})
        if r["label"] == "ignore" and note.startswith("excluded:") and s != 0:
            violations.append({"uid": r["uid"], "title": r["title"], "score": s})
    out = precision_recall(rows, threshold)
    out["exclusion_violations"] = violations
    out["n"] = len(rows)
    return out
