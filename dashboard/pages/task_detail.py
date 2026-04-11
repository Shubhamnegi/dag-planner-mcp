"""Task Detail page — full task state with expandable JSON viewers."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from db_utils import get_task

st.set_page_config(page_title="Task Detail — DAG Planner", page_icon="🔬", layout="wide")

# ── Status badge helper ───────────────────────────────────────────────────────

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


# ── Task ID input ─────────────────────────────────────────────────────────────

params = st.query_params
task_id_param = params.get("task_id", "")

st.title("🔬 Task Detail")

task_id = st.text_input("Task ID", value=task_id_param, placeholder="task_xxxxxxxx")

if not task_id:
    st.info("Enter a **task_id** above or navigate here from the Run Detail page.")
    st.stop()

# ── Fetch task ────────────────────────────────────────────────────────────────

task = get_task(task_id)
if task is None:
    st.error(f"Task `{task_id}` not found.")
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(f"### {task['title']}")
st.markdown(f"**Status:** {_badge(task['status'])}", unsafe_allow_html=True)
st.link_button("← Back to Run Detail", f"run_detail?run_id={task['run_id']}")

st.divider()

# ── Core fields ───────────────────────────────────────────────────────────────

col1, col2 = st.columns(2)

with col1:
    st.markdown(f"**Task ID:** `{task['task_id']}`")
    st.markdown(f"**Run ID:** `{task['run_id']}`")
    st.markdown(f"**Task key:** `{task['task_key']}`")
    st.markdown(f"**Owner agent:** `{task['owner_agent'] or '—'}`")
    st.markdown(f"**Priority:** `{task['priority']}`")

with col2:
    st.markdown(f"**Retries:** `{task['retry_count']} / {task['max_retries']}`")
    st.markdown(f"**Plan version:** `{task['plan_version']}`")
    st.markdown(f"**Claimed by:** `{task['claimed_by'] or '—'}`")
    st.markdown(f"**Claimed until:** `{task['claimed_until'] or '—'}`")

st.markdown(f"**Description:**")
st.markdown(task["description"] or "_No description_")

ts_col1, ts_col2 = st.columns(2)
ts_col1.metric("Created", task["created_at"] or "—")
ts_col2.metric("Updated", task["updated_at"] or "—")

st.divider()

# ── JSON viewers ──────────────────────────────────────────────────────────────

st.subheader("Payloads")

_json_fields = [
    ("input_json", "📥 Input"),
    ("final_output_json", "✅ Final Output"),
    ("working_output_json", "🔄 Working Output"),
    ("output_contract_json", "📜 Output Contract (JSON Schema)"),
    ("checkpoint_json", "💾 Checkpoint"),
]

for field, label in _json_fields:
    value = task.get(field)
    with st.expander(label, expanded=(field == "final_output_json" and bool(value))):
        if value:
            st.json(value)
        else:
            st.caption("_(empty)_")
