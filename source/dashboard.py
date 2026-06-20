"""
Section 3: Compliance Dashboard
SDA Metadata Platform (Uttar Pradesh)

Run locally with:  streamlit run src/dashboard.py
(run from the project root so the relative data/ path resolves)

All values are loaded live from data/processed/*.csv - nothing is hardcoded.

"""

import pandas as pd
import streamlit as st
import altair as alt
from pathlib import Path

st.set_page_config(page_title="UP SDA Metadata Registry - Compliance Dashboard", layout="wide")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"


@st.cache_data
def load_data():
    meta = pd.read_csv(DATA_DIR / "metadata_submissions.csv")
    tracker = pd.read_csv(DATA_DIR / "compliance_tracker.csv")
    tracker["final_status"] = tracker["final_status"].astype(str).str.strip()
    tracker["is_approved"] = tracker["final_status"].str.startswith("Approved")
    dept_report = pd.read_csv(PROCESSED_DIR / "compliance_report.csv")
    issue_counts = pd.read_csv(PROCESSED_DIR / "issue_type_counts.csv")
    dpdp = pd.read_csv(PROCESSED_DIR / "dpdp_compliance.csv")
    quality_flags = pd.read_csv(PROCESSED_DIR / "quality_flags.csv")
    return meta, tracker, dept_report, issue_counts, dpdp, quality_flags


meta, tracker, dept_report, issue_counts, dpdp, quality_flags = load_data()

st.title("UP SDA Metadata Registry — Compliance Dashboard")
st.caption("Tracks the review status of department metadata submissions to the State Data Authority.")

# ---------------------------------------------------------------------------
# Panel 1: Overview
# ---------------------------------------------------------------------------
st.header("Overview")

total_submissions = len(tracker)
n_approved = int(tracker["is_approved"].sum())
n_pending = total_submissions - n_approved
pct_approved = n_approved / total_submissions * 100 if total_submissions else 0
pct_pending = n_pending / total_submissions * 100 if total_submissions else 0
n_dpdp_issues = int((~dpdp["fully_compliant"]).sum())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total submissions", total_submissions)
c2.metric("Approved", f"{n_approved} ({pct_approved:.0f}%)")
c3.metric("Pending", f"{n_pending} ({pct_pending:.0f}%)")
c4.metric("DPDP-flagged datasets", n_dpdp_issues, help="Datasets with personal data that are missing correct classification and/or a Data Steward")

st.divider()

# ---------------------------------------------------------------------------
# Panel 2: Department Status
# ---------------------------------------------------------------------------
st.header("Department Status")

status_filter = st.selectbox("Filter by status", ["All", "Has pending items", "Fully approved"])
dept_view = dept_report.copy()
if status_filter == "Has pending items":
    dept_view = dept_view[dept_view["pending"] > 0]
elif status_filter == "Fully approved":
    dept_view = dept_view[dept_view["pending"] == 0]

sort_col = st.selectbox(
    "Sort by",
    ["pct_approved (ascending)", "pct_approved (descending)", "department (A-Z)", "pending (descending)"],
)
if sort_col == "pct_approved (ascending)":
    dept_view = dept_view.sort_values("pct_approved", ascending=True)
elif sort_col == "pct_approved (descending)":
    dept_view = dept_view.sort_values("pct_approved", ascending=False)
elif sort_col == "department (A-Z)":
    dept_view = dept_view.sort_values("department")
else:
    dept_view = dept_view.sort_values("pending", ascending=False)

st.dataframe(
    dept_view.rename(columns={
        "department": "Department",
        "datasets_submitted": "Submitted",
        "approved": "Approved",
        "pending": "Pending",
        "pct_approved": "% Approved",
        "followup_sent_for_all_pending": "Follow-up sent for all pending?",
        "pending_no_response_7plus_days": "Pending 7+ days, no response?",
    }),
    use_container_width=True,
    hide_index=True,
)

chart = alt.Chart(dept_report).mark_bar().encode(
    x=alt.X("pct_approved:Q", title="% Approved"),
    y=alt.Y("department:N", sort="x", title=None),
    color=alt.condition(alt.datum.pct_approved < 100, alt.value("#d6604d"), alt.value("#4393c3")),
    tooltip=["department", "datasets_submitted", "approved", "pending", "pct_approved"],
).properties(height=500)
st.altair_chart(chart, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Panel 3: Issue Breakdown
# ---------------------------------------------------------------------------
st.header("Issue Breakdown")
st.caption("Most common quality issues across pending submissions")

issue_chart = alt.Chart(issue_counts).mark_bar(color="#f4a261").encode(
    x=alt.X("count:Q", title="Number of pending submissions affected"),
    y=alt.Y("issue_type:N", sort="-x", title=None),
    tooltip=["issue_type", "count"],
).properties(height=350)
st.altair_chart(issue_chart, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Panel 4: DPDP Flag Tracker
# ---------------------------------------------------------------------------
st.header("DPDP Flag Tracker")
st.caption("All datasets flagged as containing personal data (dpdp_personal_data = Yes)")


def highlight_noncompliant(row):
    color = "" if row["fully_compliant"] else "background-color: #fde2e1"
    return [color] * len(row)


dpdp_display = dpdp.rename(columns={
    "submission_id": "Submission",
    "department": "Department",
    "dataset_title": "Dataset",
    "data_classification": "Classification",
    "classification_ok": "Classification correct?",
    "steward_assigned": "Steward assigned?",
    "fully_compliant": "fully_compliant",
})

st.dataframe(
    dpdp_display.style.apply(highlight_noncompliant, axis=1),
    use_container_width=True,
    hide_index=True,
)

n_noncompliant = int((~dpdp["fully_compliant"]).sum())
if n_noncompliant:
    st.warning(f"{n_noncompliant} dataset(s) containing personal data are not yet fully compliant (highlighted above).")
else:
    st.success("All datasets containing personal data are fully compliant.")
