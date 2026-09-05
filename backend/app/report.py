"""US affiliate-report parsing + portal-user matching for the automated earnings
importer (feature "auto-report-0.1", US-only for 0.1).

Pure module: no DB, no network, no clock — fully offline-testable. The report is
the Amazon Associates "Earnings by Tracking ID" summary CSV (see PORTAL-PLAN.md):
one row per tracking ID, the same 12 columns in the same ORDER in every locale,
so we read by POSITION and use only the 5 columns the feature needs. Amounts are
USD; `-` means null; the `others` catch-all row is skipped.
"""

import csv
import io
from dataclasses import dataclass, field

# Column positions in the report (identical order in every locale):
# 0 Tracking Id | 1 Clicks | 2 Items Ordered | 3 Ordered Revenue |
# 4 Items Shipped | 5 Items Returned | 6 Shipped Revenue | 7 Returned Revenue |
# 8 Total Earnings | 9 Bonus | 10 Shipped Earnings | 11 Returned Earnings.
COL_TAG, COL_ORDERED, COL_SHIPPED, COL_RETURNED, COL_TOTAL = 0, 2, 4, 5, 8
MIN_COLS = 9


@dataclass
class ReportRow:
    tag: str
    ordered: int
    shipped: int
    returned: int
    earnings_usd_cents: int  # Total Earnings x 100, as integer cents (no floats)


def _num(cell: str) -> float:
    cell = (cell or "").strip()
    if cell in ("", "-", "--"):
        return 0.0
    try:
        return float(cell.replace(",", ""))
    except ValueError:
        return 0.0


def parse_report(text: str) -> list[ReportRow]:
    """Rows from a report CSV. The header row, the `others` catch-all, blanks
    and any short/garbage lines are skipped; `-` cells read as zero. Amounts are
    kept in integer cents so no floating-point rounding creeps into money."""
    rows: list[ReportRow] = []
    for i, cells in enumerate(csv.reader(io.StringIO(text))):
        if i == 0 or len(cells) < MIN_COLS:
            continue  # header row (always first), or a short/garbage line
        tag = (cells[COL_TAG] or "").strip()
        # Real tracking IDs have no spaces; "others" is Amazon's catch-all.
        if not tag or " " in tag or tag.lower() == "others":
            continue
        rows.append(
            ReportRow(
                tag=tag,
                ordered=int(round(_num(cells[COL_ORDERED]))),
                shipped=int(round(_num(cells[COL_SHIPPED]))),
                returned=int(round(_num(cells[COL_RETURNED]))),
                earnings_usd_cents=int(round(_num(cells[COL_TOTAL]) * 100)),
            )
        )
    return rows


@dataclass
class MatchResult:
    # (ReportRow, account_id) for tags owned by exactly one portal user.
    matched: list = field(default_factory=list)
    # (tag, [account_ids]) for tags shared by >1 portal user — AMBIGUOUS, never
    # auto-assigned; surfaced as the "duplicate tracking IDs" alert.
    duplicate_tags: list = field(default_factory=list)
    # tags in the report that belong to no portal user (non-portal users, or the
    # report's own tags for people without a dashboard) — informational only.
    unmatched: list = field(default_factory=list)


def match_portal(
    rows: list[ReportRow], tag_to_accounts: dict[str, list[int]]
) -> MatchResult:
    """Match report rows to portal accounts by tracking ID.

    `tag_to_accounts` maps a US tracking ID to the portal account_ids that hold
    it (built on the bot side from tracking_ids intersected with portal
    accounts). A tag on exactly one portal account is matched; a tag on more
    than one is a duplicate (ambiguous → alert, not assigned); a tag on none is
    unmatched. Only ONE report row per tag is expected (Amazon aggregates by
    tag), but if a tag repeats the rows are merged so nothing is lost."""
    merged: dict[str, ReportRow] = {}
    for r in rows:
        if r.tag in merged:
            m = merged[r.tag]
            merged[r.tag] = ReportRow(
                r.tag,
                m.ordered + r.ordered,
                m.shipped + r.shipped,
                m.returned + r.returned,
                m.earnings_usd_cents + r.earnings_usd_cents,
            )
        else:
            merged[r.tag] = r

    result = MatchResult()
    for tag, row in merged.items():
        accounts = tag_to_accounts.get(tag, [])
        if len(accounts) == 1:
            result.matched.append((row, accounts[0]))
        elif len(accounts) > 1:
            result.duplicate_tags.append((tag, sorted(set(accounts))))
        else:
            result.unmatched.append(tag)
    return result
