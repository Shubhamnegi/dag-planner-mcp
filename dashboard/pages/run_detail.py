"""Run Detail page — deep-dive into a single workflow run."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import streamlit as st
import pandas as pd
from db_utils import get_workflow_run, list_events, list_approvals

st.set_page_config(page_title="Run Detail — DAG Planner", page_icon="🔍", layout="wide")

# ── Status badge helpers ──────────────────────────────────────────────────────

_STATUS_COLORS = {
    "completed": "#28a745",
    "running": "#007bff",
    "ready": "#17a2b8",
    "failed": "#dc3545",
    "cancelled": "#6c757d",
    "draft": "#ffc107",
    "blocked_human": "#fd7e14",
    "blocked_dependency": "#fd7e14",
    "created": "#adb5bd",
    "validating": "#6f42c1",
}


def _badge(status: str) -> str:
    color = _STATUS_COLORS.get(status, "#6c757d")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em">{status}</span>'
    )


# ── Run ID input ──────────────────────────────────────────────────────────────

params = st.query_params
run_id_param = params.get("run_id", "")

st.title("🔍 Run Detail")

run_id = st.text_input("Run ID", value=run_id_param, placeholder="run_xxxxxxxx")

if not run_id:
    st.info("Enter a **run_id** above or navigate here from the Workflows page.")
    st.stop()

# ── Fetch run ─────────────────────────────────────────────────────────────────

run = get_workflow_run(run_id)
if run is None:
    st.error(f"Run `{run_id}` not found.")
    st.stop()

# ── Section 1 — Run Summary ───────────────────────────────────────────────────

st.subheader("Run Summary")
sum_col1, sum_col2 = st.columns(2)

with sum_col1:
    st.markdown(f"**Goal:** {run['goal']}")
    st.markdown(f"**Status:** {_badge(run['status'])}", unsafe_allow_html=True)
    st.markdown(f"**Plan version:** {run['plan_version']}")

with sum_col2:
    st.markdown(f"**Run ID:** `{run['run_id']}`")
    st.markdown(f"**Session ID:** `{run['session_id'] or '—'}`")
    st.markdown(f"**User ID:** `{run['user_id'] or '—'}`")

ts_col1, ts_col2, ts_col3 = st.columns(3)
ts_col1.metric("Created", run["created_at"] or "—")
ts_col2.metric("Updated", run["updated_at"] or "—")
ts_col3.metric("Completed", run["completed_at"] or "—")

if run["metadata_json"]:
    with st.expander("Metadata JSON"):
        st.json(run["metadata_json"])

st.divider()

# ── Section 2 — Task Table ────────────────────────────────────────────────────

st.subheader("Tasks")
tasks = run["tasks"]

if tasks:
    # Filters
    all_statuses = sorted({t["status"] for t in tasks})
    all_agents = sorted({t["owner_agent"] for t in tasks if t["owner_agent"]})

    flt_col1, flt_col2 = st.columns(2)
    with flt_col1:
        selected_status = st.selectbox("Filter by status", ["all"] + all_statuses, key="task_status_filter")
    with flt_col2:
        selected_agent = st.selectbox("Filter by owner agent", ["all"] + all_agents, key="task_agent_filter")

    filtered = tasks
    if selected_status != "all":
        filtered = [t for t in filtered if t["status"] == selected_status]
    if selected_agent != "all":
        filtered = [t for t in filtered if t["owner_agent"] == selected_agent]

    if filtered:
        df = pd.DataFrame(
            [
                {
                    "task_key": t["task_key"],
                    "title": t["title"],
                    "status": t["status"],
                    "owner_agent": t["owner_agent"],
                    "priority": t["priority"],
                    "retries": f"{t['retry_count']}/{t['max_retries']}",
                    "updated_at": t["updated_at"],
                    "task_id": t["task_id"],
                }
                for t in filtered
            ]
        )
        st.dataframe(
            df[["task_key", "title", "status", "owner_agent", "priority", "retries", "updated_at"]],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("**Open a task →** click a quick-link below")
        link_cols = st.columns(min(len(filtered), 4))
        for i, t in enumerate(filtered):
            col = link_cols[i % len(link_cols)]
            col.link_button(
                f"🔬 {t['task_key']} ({t['status']})",
                f"task_detail?task_id={t['task_id']}",
            )
    else:
        st.info("No tasks match the selected filters.")
else:
    st.info("No tasks found for this run.")

st.divider()

# ── Section 3 — DAG Visualization ─────────────────────────────────────────────

st.subheader("DAG Visualization")

edges = run["edges"]
task_map = {t["task_id"]: t for t in tasks}

_NODE_COLORS = {
    "completed": "#28a745",
    "running": "#007bff",
    "ready": "#17a2b8",
    "failed": "#dc3545",
    "cancelled": "#6c757d",
    "draft": "#ffc107",
    "blocked_human": "#fd7e14",
    "blocked_dependency": "#fd7e14",
    "created": "#adb5bd",
    "validating": "#6f42c1",
}

if tasks:
    try:
        import graphviz

        dot = graphviz.Digraph(
            graph_attr={"rankdir": "LR", "bgcolor": "transparent", "fontname": "Helvetica"},
            node_attr={"shape": "box", "style": "filled,rounded", "fontname": "Helvetica", "fontsize": "11"},
            edge_attr={"fontname": "Helvetica", "fontsize": "9"},
        )
        for t in tasks:
            color = _NODE_COLORS.get(t["status"], "#adb5bd")
            label = f"{t['task_key']}\n({t['status']})"
            dot.node(t["task_id"], label=label, fillcolor=color, fontcolor="#fff" if t["status"] not in ("draft", "created", "cancelled") else "#333")

        for e in edges:
            dot.edge(e["parent_task_id"], e["child_task_id"])

        st.graphviz_chart(dot.source)

        # Colour legend
        legend_items = list(_NODE_COLORS.items())
        leg_cols = st.columns(len(legend_items))
        for col, (status, color) in zip(leg_cols, legend_items):
            col.markdown(
                f'<span style="background:{color};color:#fff;padding:2px 6px;border-radius:3px;font-size:0.75em">{status}</span>',
                unsafe_allow_html=True,
            )

    except ImportError:
        st.warning(
            "The `graphviz` Python package is not installed. "
            "Install it with `pip install graphviz` (and the Graphviz system package) "
            "to see the DAG visualisation. Showing adjacency table instead."
        )
        if edges:
            edge_df = pd.DataFrame(
                [
                    {
                        "parent": task_map.get(e["parent_task_id"], {}).get("task_key", e["parent_task_id"]),
                        "child": task_map.get(e["child_task_id"], {}).get("task_key", e["child_task_id"]),
                        "edge_type": e["edge_type"],
                    }
                    for e in edges
                ]
            )
            st.dataframe(edge_df, use_container_width=True, hide_index=True)
        else:
            st.info("No edges defined for this run.")
else:
    st.info("No tasks — DAG is empty.")

st.divider()

# ── Section 4 — Event Log ─────────────────────────────────────────────────────

st.subheader("Event Log")
events = list_events(run_id)

if events:
    ev_df = pd.DataFrame(
        [
            {
                "created_at": e["created_at"],
                "event_type": e["event_type"],
                "task_id": e["task_id"],
                "created_by": e["created_by"],
                "payload": json.dumps(e["payload_json"], separators=(",", ":"))[:120],
            }
            for e in events
        ]
    )
    st.dataframe(ev_df, use_container_width=True, hide_index=True)
else:
    st.info("No events recorded for this run.")

st.divider()

# ── Section 5 — Human Approvals ───────────────────────────────────────────────

st.subheader("Human Approvals")
approvals = list_approvals(run_id)

if approvals:
    appr_df = pd.DataFrame(
        [
            {
                "status": a["status"],
                "question": a["question"][:80],
                "requested_by": a["requested_by"],
                "decided_by": a["decided_by"],
                "decision": json.dumps(a["decision_json"], separators=(",", ":"))[:80] if a["decision_json"] else "—",
                "requested_at": a["requested_at"],
                "decided_at": a["decided_at"],
            }
            for a in approvals
        ]
    )
    st.dataframe(appr_df, use_container_width=True, hide_index=True)
else:
    st.info("No human approvals for this run.")
