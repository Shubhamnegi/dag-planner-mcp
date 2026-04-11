"""DAG Planner MCP — Streamlit Dashboard entry point.

Launch with:
    streamlit run dashboard/app.py
"""

import os
import streamlit as st

st.set_page_config(
    page_title="DAG Planner Dashboard",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── DB connection warning ────────────────────────────────────────────────────

if not os.environ.get("DATABASE_URL"):
    st.warning(
        "⚠️ **DATABASE_URL is not set.** "
        "The dashboard will use the default `sqlite:///dag_planner.db` in the "
        "current working directory. "
        "Set the environment variable to point at your database:\n\n"
        "```bash\n"
        "export DATABASE_URL=sqlite:///path/to/dag_planner.db\n"
        "# or for PostgreSQL:\n"
        "export DATABASE_URL=postgresql://user:pass@host:5432/dag_planner\n"
        "```",
        icon="⚠️",
    )

# ── Sidebar navigation ───────────────────────────────────────────────────────

st.sidebar.title("🗺️ DAG Planner")
st.sidebar.markdown("**Read-only dashboard**")
st.sidebar.divider()

pages = {
    "📊 Overview": "pages/overview.py",
    "📋 Workflows": "pages/workflows.py",
}

st.sidebar.markdown(
    """
**Navigation**

Use the pages in the sidebar (Streamlit's built-in multi-page nav) or the
links below to jump directly to a run or task.
"""
)

st.sidebar.divider()
st.sidebar.caption(
    f"DB: `{os.environ.get('DATABASE_URL', 'sqlite:///dag_planner.db')}`"
)

# ── Landing page content ─────────────────────────────────────────────────────

st.title("🗺️ DAG Planner MCP Dashboard")
st.markdown(
    """
Welcome to the **read-only** DAG Planner dashboard.

Use the **sidebar** to navigate between pages:

| Page | Description |
|------|-------------|
| 📊 **Overview** | Summary metrics and recent activity |
| 📋 **Workflows** | Paginated & searchable list of all workflow runs |
| 🔍 **Run Detail** | Deep-dive into a single run: tasks, DAG graph, events, approvals |
| 🔬 **Task Detail** | Full task state including all JSON payloads |

> **Tip:** From the *Workflows* page, click **View →** on any row to open its
> Run Detail page. From the task table on *Run Detail*, click a task key to
> open *Task Detail*.
"""
)
