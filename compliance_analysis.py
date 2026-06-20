"""
Section 2: Compliance Analysis
SDA Metadata Platform (Uttar Pradesh)- Assignment

Builds the department-level compliance table (2.1), issue type analysis (2.2),
and DPDP compliance flag table (2.3). Saves data/processed/compliance_report.csv (2.4).

Reference date for "days since follow-up" calculations: 2026-04-25, matching the
"as of" date used in the Section 4 monthly progress report, so the dashboard,
report and email all align with the same date.
"""

import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

REFERENCE_DATE = pd.Timestamp("2026-04-25")


def load_data():
    meta = pd.read_csv(DATA_DIR / "metadata_submissions.csv", dtype=str)
    tracker = pd.read_csv(DATA_DIR / "compliance_tracker.csv", dtype=str)
    tracker["final_status"] = tracker["final_status"].str.strip()
    tracker["is_approved"] = tracker["final_status"].str.startswith("Approved")
    tracker["is_pending"] = ~tracker["is_approved"]
    tracker["follow_up_date_dt"] = pd.to_datetime(tracker["follow_up_date"], errors="coerce")
    tracker["days_since_followup"] = (REFERENCE_DATE - tracker["follow_up_date_dt"]).dt.days
    tracker["no_response_7plus"] = (
        tracker["is_pending"]
        & (tracker["department_responded"].str.strip().str.lower() == "no")
        & (tracker["days_since_followup"] >= 7)
    )
    return meta, tracker


def department_table(tracker: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dept, g in tracker.groupby("department"):
        submitted = len(g)
        approved = int(g["is_approved"].sum())
        pending = int(g["is_pending"].sum())
        pct_approved = approved / submitted if submitted else 0

        pending_rows = g[g["is_pending"]]
        if len(pending_rows) == 0:
            followup_status = "N/A"
        else:
            sent = (pending_rows["follow_up_sent"].str.strip().str.lower() == "yes").sum()
            if sent == 0:
                followup_status = "No"
            elif sent == len(pending_rows):
                followup_status = "Yes"
            else:
                followup_status = "Partial"

        no_response_flag = "Yes" if pending_rows["no_response_7plus"].any() else "No"

        rows.append(
            {
                "department": dept,
                "datasets_submitted": submitted,
                "approved": approved,
                "pending": pending,
                "pct_approved": round(pct_approved * 100, 1),
                "followup_sent_for_all_pending": followup_status,
                "pending_no_response_7plus_days": no_response_flag,
            }
        )

    out = pd.DataFrame(rows).sort_values("pct_approved", ascending=True).reset_index(drop=True)
    return out


def issue_type_analysis(tracker: pd.DataFrame):
    """Parse the free-text final_status of pending rows into issue categories,
    matching the labels used in quality_review.py so the two scripts agree."""
    pending = tracker[tracker["is_pending"]].copy()

    label_map = {
        "missing data owner name": "Data owner missing",
        "data owner name missing": "Data owner missing",
        "description missing": "Description missing or too short (<20 chars)",
        "record count missing": "Record count missing (not a live API dataset)",
        "classified public; should be restricted": "DPDP flag inconsistent with classification",
        "classification blank": "Classification missing or invalid",
        "dpdp flag missing": "DPDP flag inconsistent with classification",
        "date format invalid": "Invalid date format",
        "dpdp flag not confirmed": "DPDP flag inconsistent with classification",
        "steward not assigned": "Data Steward not assigned",
    }

    def extract_issues(text: str) -> list:
        text_lower = text.lower()
        found = set()
        for key, label in label_map.items():
            if key in text_lower:
                found.add(label)
        return sorted(found) if found else ["Other / unspecified"]

    pending["issue_labels"] = pending["final_status"].apply(extract_issues)
    all_labels = [lab for labs in pending["issue_labels"] for lab in labs]
    issue_counts = pd.Series(all_labels).value_counts()

    rows = []
    for label in issue_counts.index:
        subset = pending[pending["issue_labels"].apply(lambda labs: label in labs)]
        n = len(subset)
        no_response = (subset["department_responded"].str.strip().str.lower() == "no").sum()
        rows.append({"issue_type": label, "n_pending": n, "n_no_response": no_response,
                      "non_response_rate_pct": round(100 * no_response / n, 1) if n else 0})
    non_response_table = pd.DataFrame(rows).sort_values("non_response_rate_pct", ascending=False)

    return issue_counts, non_response_table


def dpdp_compliance_table(meta: pd.DataFrame) -> pd.DataFrame:
    personal = meta[meta["dpdp_personal_data"].str.strip().str.lower() == "yes"].copy()
    personal["classification_ok"] = personal["data_classification"].isin(["Restricted", "Confidential"])
    personal["steward_assigned"] = personal["data_steward_assigned"].str.strip().str.lower() == "yes"
    personal["fully_compliant"] = personal["classification_ok"] & personal["steward_assigned"]

    cols = ["submission_id", "department", "dataset_title", "data_classification",
            "classification_ok", "steward_assigned", "fully_compliant"]
    return personal[cols].reset_index(drop=True)


def main():
    meta, tracker = load_data()

    dept_table = department_table(tracker)
    dept_table.to_csv(PROCESSED_DIR / "compliance_report.csv", index=False)

    issue_counts, non_response_table = issue_type_analysis(tracker)
    dpdp_table = dpdp_compliance_table(meta)

    # Save DPDP table too - the dashboard needs it as a processed file, not hardcoded.
    dpdp_table.to_csv(PROCESSED_DIR / "dpdp_compliance.csv", index=False)
    issue_counts.rename_axis("issue_type").reset_index(name="count").to_csv(
        PROCESSED_DIR / "issue_type_counts.csv", index=False
    )

    print("=== 2.1 Department-level compliance table (sorted by approval rate, ascending) ===")
    print(dept_table.to_string(index=False))

    print("\n=== 2.2 Issue type analysis: counts across pending submissions ===")
    print(issue_counts.to_string())

    print("\n=== 2.2 Non-response rate by issue type ===")
    print(non_response_table.to_string(index=False))

    print("\n=== 2.3 DPDP compliance table (all submissions with personal data) ===")
    print(dpdp_table.to_string(index=False))

    non_compliant = dpdp_table[~dpdp_table["fully_compliant"]]
    print(f"\nDatasets with personal data that are NOT fully compliant: {len(non_compliant)}")
    print(non_compliant[["submission_id", "department", "dataset_title"]].to_string(index=False))

    print("\nSaved: data/processed/compliance_report.csv, dpdp_compliance.csv, issue_type_counts.csv")


if __name__ == "__main__":
    main()
