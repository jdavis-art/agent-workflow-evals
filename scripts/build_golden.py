"""Propose suites/bid-scoring/golden.csv from bid-radar's public regression fixture.
Takes every row scored 3+ and a fixed sample of 60 rows scored 0-2, proposes label = pursue if score >= 3 else ignore,
and writes the CSV for hand correction. Rerun with --keep-labels to preserve labels already edited."""
import argparse
import csv
import json
import pathlib
import random

FIX = pathlib.Path(r"C:\Users\jdavi\Documents\Claude\Projects\bid-radar\tests\fixtures\sweep-2026-09-04-scored.jsonl")
OUT = pathlib.Path(__file__).resolve().parent.parent / "suites" / "bid-scoring" / "golden.csv"
COLS = ["uid", "title", "agency", "location", "bid_type", "blurb", "legacy_score", "label", "note"]

ap = argparse.ArgumentParser(); ap.add_argument("--keep-labels", action="store_true"); a = ap.parse_args()
rows = [json.loads(l) for l in FIX.read_text(encoding="utf-8").splitlines()]
hi = [r for r in rows if r["legacy_score"] >= 3]
lo = [r for r in rows if r["legacy_score"] < 3]
random.Random(20260904).shuffle(lo)
pick = hi + lo[:60]
existing = {}
if a.keep_labels and OUT.exists():
    existing = {r["uid"]: r for r in csv.DictReader(open(OUT, encoding="utf-8", newline=""))}
with open(OUT, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=COLS); w.writeheader()
    for r in pick:
        uid = f"bidnet:{r['id']}"
        prev = existing.get(uid, {})
        w.writerow({"uid": uid, "title": r["title"], "agency": r["agency"], "location": r["location"], "bid_type": r["bid_type"],
                    "blurb": r["blurb"], "legacy_score": r["legacy_score"],
                    "label": prev.get("label") or ("pursue" if r["legacy_score"] >= 3 else "ignore"), "note": prev.get("note", "")})
print(f"wrote {len(pick)} rows to {OUT}; labels are PROPOSALS until reviewed by hand")
