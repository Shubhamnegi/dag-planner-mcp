"""Shared UI helpers for the DAG Planner dashboard pages."""

STATUS_COLORS = {
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

# Statuses where white text is legible on the badge background
_DARK_BG_STATUSES = frozenset(STATUS_COLORS) - {"draft", "created", "cancelled"}


def status_badge(status: str) -> str:
    """Return an HTML inline badge for the given status string."""
    color = STATUS_COLORS.get(status, "#6c757d")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em">{status}</span>'
    )


def node_font_color(status: str) -> str:
    """Return a legible font colour for a Graphviz node filled with STATUS_COLORS[status]."""
    return "#fff" if status in _DARK_BG_STATUSES else "#333"
