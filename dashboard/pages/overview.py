"""Overview page — summary metrics and recent activity."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
from db_utils import get_run_stats, list_workflow_runs

st.set_page_config(page_title="Overview — DAG Planner", page_icon="📊", layout="wide")
st.title("📊 Overview")

# ── Fetch data ───────────────────────────────────────────────────────────────

stats = get_run_stats()
run_counts = stats["by_status"]
task_counts = stats["task_by_status"]

# ── Run metric cards ─────────────────────────────────────────────────────────

st.subheader("Workflow Runs")
cols = st.columns(6)
metric_labels = [
    ("Total", stats["total"]),
    ("Draft", run_counts.get("draft", 0)),
    ("Running", run_counts.get("running", 0)),
    ("Completed", run_counts.get("completed", 0)),
    ("Failed", run_counts.get("failed", 0)),
    ("Cancelled", run_counts.get("cancelled", 0)),
]
for col, (label, value) in zip(cols, metric_labels):
    col.metric(label, value)

st.divider()

# ── Task status distribution ─────────────────────────────────────────────────

st.subheader("Task Status Distribution (all runs)")
if task_counts:
    task_df = pd.DataFrame(
        [{"Status": k, "Count": v} for k, v in sorted(task_counts.items())]
    ).set_index("Status")
    st.bar_chart(task_df)
else:
    st.info("No tasks found in the database yet.")

st.divider()

# ── Recent runs ──────────────────────────────────────────────────────────────

st.subheader("Most Recently Updated Runs")
recent_rows, _ = list_workflow_runs(page=1, page_size=10)

if recent_rows:
    df = pd.DataFrame(recent_rows)
    df["goal"] = df["goal"].str[:80]
    st.dataframe(
        df[["run_id", "goal", "status", "user_id", "plan_version", "updated_at"]],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No workflow runs found. Start the MCP server and create a run to get started.")
