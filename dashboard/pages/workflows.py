"""Workflows page — paginated and searchable list of all workflow runs."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
from db_utils import list_workflow_runs

st.set_page_config(page_title="Workflows — DAG Planner", page_icon="📋", layout="wide")
st.title("📋 Workflows")

# ── Filters ──────────────────────────────────────────────────────────────────

col_search, col_status, col_size = st.columns([3, 1, 1])

with col_search:
    search = st.text_input("🔍 Search goal", placeholder="e.g. analyze AWS costs")

with col_status:
    status_options = ["all", "draft", "running", "completed", "failed", "cancelled"]
    status_filter = st.selectbox("Status", status_options, index=0)

with col_size:
    page_size = st.selectbox("Rows per page", [10, 25, 50], index=1)

# ── Pagination state ─────────────────────────────────────────────────────────

if "wf_page" not in st.session_state:
    st.session_state.wf_page = 1

# Reset to page 1 when filters change
filter_key = f"{search}|{status_filter}|{page_size}"
if st.session_state.get("_wf_filter_key") != filter_key:
    st.session_state.wf_page = 1
    st.session_state["_wf_filter_key"] = filter_key

# ── Fetch data ───────────────────────────────────────────────────────────────

rows, total = list_workflow_runs(
    search=search,
    status_filter=status_filter,
    page=st.session_state.wf_page,
    page_size=page_size,
)

total_pages = max(1, (total + page_size - 1) // page_size)

# ── Results table ─────────────────────────────────────────────────────────────

st.caption(f"Showing {len(rows)} of {total} runs — page {st.session_state.wf_page} / {total_pages}")

if rows:
    df = pd.DataFrame(rows)
    df["goal_short"] = df["goal"].str[:80]
    display_df = df[["run_id", "goal_short", "status", "user_id", "plan_version", "created_at", "updated_at"]].copy()
    display_df.columns = ["run_id", "goal", "status", "user_id", "plan_version", "created_at", "updated_at"]

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("**Open a run →** copy a `run_id` from the table and paste it into the *Run Detail* page.")

    # Quick-link buttons (one per row)
    st.markdown("##### Quick links")
    link_cols = st.columns(min(len(rows), 4))
    for i, row in enumerate(rows):
        col = link_cols[i % len(link_cols)]
        label = f"🔍 {row['run_id'][:14]}… ({row['status']})"
        col.link_button(label, f"run_detail?run_id={row['run_id']}")
else:
    st.info("No workflow runs match your filters.")

# ── Pagination controls ───────────────────────────────────────────────────────

st.divider()
prev_col, info_col, next_col = st.columns([1, 2, 1])

with prev_col:
    if st.button("← Previous", disabled=st.session_state.wf_page <= 1):
        st.session_state.wf_page -= 1
        st.rerun()

with info_col:
    st.markdown(
        f"<div style='text-align:center'>Page {st.session_state.wf_page} of {total_pages}</div>",
        unsafe_allow_html=True,
    )

with next_col:
    if st.button("Next →", disabled=st.session_state.wf_page >= total_pages):
        st.session_state.wf_page += 1
        st.rerun()
