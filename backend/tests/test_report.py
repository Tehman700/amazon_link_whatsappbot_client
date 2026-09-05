"""Offline tests for the US report parser + portal matcher (auto-report-0.1).

No DB, no network. Fixture mirrors the real Amazon "Earnings by Tracking ID"
US report (header row, an `others` catch-all, and `-` null cells).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app.report import parse_report, match_portal  # noqa: E402

CSV = (
    "Tracking Id,Clicks,Items Ordered,Ordered Revenue,Items Shipped,Items Returned,"
    "Items Shipped Revenue,Items Returned Revenue,Total Earnings,Bonus,"
    "Items Shipped Earnings,Items Returned Earnings\n"
    "pz0da-20,537,15,371.95,15,0,388.95,0.00,11.62,0.00,11.62,0.00\n"
    "beast06a-20,127,21,991.89,21,4,991.89,170.87,26.80,0.00,32.64,5.84\n"
    "beastbot01d-20,53,-,-,4,5,283.46,77.95,6.00,0.00,8.51,2.51\n"
    "others,180,19,1061.22,18,6,846.41,356.65,18.31,0.00,29.77,11.46\n"
)

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


rows = parse_report(CSV)
by = {r.tag: r for r in rows}
check("header + others + blanks skipped -> 3 rows", len(rows) == 3, [r.tag for r in rows])
check("Total Earnings parsed as integer cents", by["pz0da-20"].earnings_usd_cents == 1162)
check("orders/shipped/returned parsed", (by["beast06a-20"].ordered, by["beast06a-20"].shipped,
      by["beast06a-20"].returned) == (21, 21, 4))
check("'-' null cells read as zero", by["beastbot01d-20"].ordered == 0 and by["beastbot01d-20"].shipped == 4)
check("earnings 26.80 -> 2680 cents", by["beast06a-20"].earnings_usd_cents == 2680)

# --- matching ---
tag_to_accounts = {"pz0da-20": [10], "beast06a-20": [20, 21]}  # beastbot01d-20 -> none
mr = match_portal(rows, tag_to_accounts)
check("a tag on exactly one portal user is matched",
      len(mr.matched) == 1 and mr.matched[0][1] == 10 and mr.matched[0][0].tag == "pz0da-20")
check("a tag on >1 portal user is flagged duplicate, not matched",
      mr.duplicate_tags == [("beast06a-20", [20, 21])], mr.duplicate_tags)
check("a tag on no portal user is unmatched",
      mr.unmatched == ["beastbot01d-20"], mr.unmatched)

# repeated tag rows are merged (defensive; Amazon aggregates by tag anyway)
dup_rows = parse_report(CSV + "pz0da-20,1,5,10,5,0,10,0,1.00,0,1.00,0\n")
mr2 = match_portal(dup_rows, {"pz0da-20": [10]})
merged = next(r for r, a in mr2.matched if r.tag == "pz0da-20")
check("repeated tag rows merge (15+5 ordered, 1162+100 cents)",
      merged.ordered == 20 and merged.earnings_usd_cents == 1262, merged)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
