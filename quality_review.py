"""
Section 1: Metadata Quality Review
SDA Metadata Platform (Uttar Pradesh)

Reads data/metadata_submissions.csv, applies the SDA quality checklist (1.1),
cross-checks against data/compliance_tracker.csv (1.2), and saves outputs to
data/processed/.

Assumptions are documented in README.md - see "Approach to ambiguous decisions".
"""

import pandas as pd
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_CLASSIFICATIONS = {"Public", "Restricted", "Confidential"}


def is_valid_date(value: str) -> bool:
    """True only for strict YYYY-MM-DD. Anything else (blank, DD-MM-YYYY,
    MM/DD/YYYY, etc.) is invalid for this check."""
    if pd.isna(value) or str(value).strip() == "":
        return False
    value = str(value).strip()
    if not DATE_RE.match(value):
        return False
    try:
        pd.to_datetime(value, format="%Y-%m-%d")
        return True
    except ValueError:
        return False


def is_blank(value) -> bool:
    return pd.isna(value) or str(value).strip() == ""


def check_row(row: pd.Series) -> list[str]:
    """Return list of failed check names for a single submission row."""
    issues = []

    # 1. Data owner present
    if is_blank(row["data_owner_name"]):
        issues.append("Data owner missing")

    # 2. Description adequate (not blank, >= 20 characters)
    desc = "" if is_blank(row["description"]) else str(row["description"]).strip()
    if len(desc) < 20:
        issues.append("Description missing or too short (<20 chars)")

    # 3. Classification present and valid
    classification = None if is_blank(row["data_classification"]) else str(row["data_classification"]).strip()
    if classification not in VALID_CLASSIFICATIONS:
        issues.append("Classification missing or invalid")

    # 4. DPDP flag consistent
    # If personal data = Yes, classification must be Restricted or Confidential.
    # A blank/invalid classification also fails this check when dpdp=Yes,
    # since it cannot be confirmed Restricted/Confidential.
    dpdp = str(row["dpdp_personal_data"]).strip().lower() if not is_blank(row["dpdp_personal_data"]) else "no"
    if dpdp == "yes" and classification not in {"Restricted", "Confidential"}:
        issues.append("DPDP flag inconsistent with classification")

    # 5. last_updated date format valid
    if not is_valid_date(row["last_updated"]):
        issues.append("Invalid last_updated date format")

    # 6. Record count present, unless dataset is delivered as a live API
    formats = "" if is_blank(row["formats"]) else str(row["formats"])
    is_live_api = "API" in [f.strip().upper() for f in formats.split(",")]
    record_count = row["record_count"]
    if is_blank(record_count):
        if not is_live_api:
            issues.append("Record count missing (not a live API dataset)")
    else:
        try:
            rc = float(record_count)
            if rc <= 0 or rc != int(rc):
                issues.append("Record count not a positive integer")
        except (ValueError, TypeError):
            issues.append("Record count not a positive integer")

    # 7. submitted_on date format valid
    if not is_valid_date(row["submitted_on"]):
        issues.append("Invalid submitted_on date format")

    return issues


def main():
    df = pd.read_csv(DATA_DIR / "metadata_submissions.csv", dtype=str)
    df["record_count"] = pd.to_numeric(df["record_count"], errors="coerce")

    df["issues_list"] = df.apply(check_row, axis=1)
    df["issues"] = df["issues_list"].apply(lambda x: "; ".join(x))
    df["n_issues"] = df["issues_list"].apply(len)

    flagged = df[df["n_issues"] > 0].copy()
    clean = df[df["n_issues"] == 0].copy()

    # --- 1.1 outputs ---
    flagged_out = flagged[["submission_id", "department", "dataset_title", "issues"]]
    flagged_out.to_csv(PROCESSED_DIR / "quality_flags.csv", index=False)

    clean_out = clean[["submission_id", "department", "dataset_title"]]
    clean_out.to_csv(PROCESSED_DIR / "clean_submissions.csv", index=False)

    # --- 1.2 cross-check against compliance tracker ---
    tracker = pd.read_csv(DATA_DIR / "compliance_tracker.csv", dtype=str)
    tracker["final_status"] = tracker["final_status"].str.strip()
    tracker["is_approved"] = tracker["final_status"].str.startswith("Approved")

    merged = df[["submission_id", "n_issues", "issues"]].merge(
        tracker[["submission_id", "final_status", "is_approved"]], on="submission_id"
    )

    mis_approved = merged[(merged["n_issues"] > 0) & (merged["is_approved"])]
    ready_to_approve = merged[(merged["n_issues"] == 0) & (~merged["is_approved"])]
    correctly_approved = merged[(merged["n_issues"] == 0) & (merged["is_approved"])]
    correctly_pending = merged[(merged["n_issues"] > 0) & (~merged["is_approved"])]

    crosscheck_summary = pd.DataFrame(
        {
            "category": [
                "Correctly Approved",
                "Correctly Pending",
                "Potentially mis-approved (flagged by us, tracker says Approved)",
                "Potentially ready to approve (passes our checks, tracker says Pending)",
            ],
            "count": [
                len(correctly_approved),
                len(correctly_pending),
                len(mis_approved),
                len(ready_to_approve),
            ],
        }
    )

    # --- 1.3 review_summary.txt ---
    total = len(df)
    n_pass = len(clean)
    n_fail = len(flagged)

    all_issue_types = [issue for sub in flagged["issues_list"] for issue in sub]
    issue_counts = pd.Series(all_issue_types).value_counts()

    lines = []
    lines.append("SDA METADATA QUALITY REVIEW - SUMMARY REPORT")
    lines.append("=" * 50)
    lines.append(f"Total submissions reviewed: {total}")
    lines.append(f"Pass all checks: {n_pass} ({n_pass/total:.0%})")
    lines.append(f"Fail one or more checks: {n_fail} ({n_fail/total:.0%})")
    lines.append("")
    lines.append("Most common issue types:")
    for issue, count in issue_counts.items():
        lines.append(f"  - {issue}: {count}")
    lines.append("")
    lines.append("Cross-check against compliance_tracker.csv:")
    for _, r in crosscheck_summary.iterrows():
        lines.append(f"  - {r['category']}: {r['count']}")
    if len(mis_approved) > 0:
        lines.append("")
        lines.append("  Potentially mis-approved submission IDs: " + ", ".join(mis_approved["submission_id"]))
    if len(ready_to_approve) > 0:
        lines.append("  Potentially ready-to-approve submission IDs: " + ", ".join(ready_to_approve["submission_id"]))

    (PROCESSED_DIR / "review_summary.txt").write_text("\n".join(lines))

    # Console output for the analyst running this interactively
    print("\n".join(lines))
    print("\nSaved: data/processed/quality_flags.csv, clean_submissions.csv, review_summary.txt")


if __name__ == "__main__":
    main()
