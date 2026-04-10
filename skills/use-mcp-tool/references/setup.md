# Server Setup Guide

> This guide is for the **human** setting up the server so that an AI agent (Claude, Cursor, etc.) can connect and use the DAG planner tools.
> Once the server is running and registered with your MCP client, the agent can call all tools directly with no additional code.

---

## Requirements

| Dependency | Version |
|---|---|
| Python | ≥ 3.11 |
| mcp[cli] | ≥ 1.6.0 |
| sqlalchemy | ≥ 2.0 |
| pydantic | ≥ 2.0 |
| jsonschema | ≥ 4.0 |
| aiosqlite | ≥ 0.19 |

Optional (PostgreSQL only):

| Dependency | Version |
|---|---|
| asyncpg | ≥ 0.29 |

---

## Installation

### 1. Clone and enter the repository

```bash
git clone https://github.com/Shubhamnegi/dag-planner-mcp.git
cd dag-planner-mcp
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows
```

### 3. Install the package

**SQLite (development — no extra deps):**

```bash
pip install -e .
```

**PostgreSQL (production):**

```bash
pip install -e ".[postgres]"
```

---

## Database Configuration

Controlled by the `DATABASE_URL` environment variable. Tables are auto-created on first start.

### SQLite (default — recommended for single-user / local dev)

```bash
# Default — creates dag_planner.db in the current directory
export DATABASE_URL="sqlite:///dag_planner.db"

# Absolute path (recommended — avoids ambiguity about working directory)
export DATABASE_URL="sqlite:////home/user/data/dag_planner.db"
```

### PostgreSQL (multi-user / production)

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/dag_planner"
```

Create the database first:

```sql
CREATE DATABASE dag_planner;
```

For SSL/connection pooling:

```bash
export DATABASE_URL="postgresql://user:password@host:5432/dag_planner?sslmode=require"
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///dag_planner.db` | SQLAlchemy connection URL |
| `MCP_HOST` | `127.0.0.1` | Bind host (HTTP transport only) |
| `MCP_PORT` | `8000` | Bind port (HTTP transport only) |

---

## Connecting to Your MCP Client

### Claude Desktop (stdio — recommended)

Edit the Claude Desktop config file:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "dag-planner-mcp": {
      "command": "/path/to/.venv/bin/dag-planner-mcp",
      "env": {
        "DATABASE_URL": "sqlite:////home/user/data/dag_planner.db"
      }
    }
  }
}
```

Run `which dag-planner-mcp` (after activating the venv) to find the exact binary path.

Restart Claude Desktop after editing the config. The 22 DAG planner tools will appear in Claude's tool panel.

### Cursor IDE (HTTP transport)

Start the server in HTTP mode:

```bash
DATABASE_URL="sqlite:///dag_planner.db" \
dag-planner-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

Then add to Cursor's MCP config:

```json
{
  "mcpServers": {
    "dag-planner-mcp": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Other MCP-compatible clients

Point any MCP client at the streamable HTTP endpoint:

```
http://localhost:8000/mcp
```

Or use stdio mode with the command `dag-planner-mcp` (binary must be on PATH or use absolute path).

---

## Verifying the Connection

Once connected, ask the agent (or call directly):

Tool: `get_workflow_run`
Input: `{ "run_id": "nonexistent" }`

If the server is connected, you will get a structured error response (not a "tool not found" error). That confirms the tools are live.
