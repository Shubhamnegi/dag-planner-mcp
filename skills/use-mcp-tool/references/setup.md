# Setup Guide

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

**With dev/test dependencies:**

```bash
pip install -e ".[dev]"
```

---

## Database Configuration

Controlled by the `DATABASE_URL` environment variable. Tables are auto-created on first start.

### SQLite (default)

```bash
# Default — creates dag_planner.db in the current directory
export DATABASE_URL="sqlite:///dag_planner.db"

# Absolute path
export DATABASE_URL="sqlite:////home/user/data/dag_planner.db"

# In-memory (testing only — data lost on exit)
export DATABASE_URL="sqlite:///:memory:"
```

### PostgreSQL

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/dag_planner"
```

Create the database first:

```sql
CREATE DATABASE dag_planner;
```

Then start the server — SQLAlchemy creates all tables automatically.

For SSL/connection pooling:

```bash
export DATABASE_URL="postgresql://user:password@host:5432/dag_planner?sslmode=require"
```

---

## Running the Server

### stdio mode (Claude Desktop, most MCP clients)

```bash
dag-planner-mcp
# or
python -m dag_planner_mcp.server
```

Reads from stdin, writes to stdout. No port is opened.

### Streamable HTTP mode

```bash
dag-planner-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

MCP endpoint: `http://localhost:8000/mcp`

---

## Integrating with Clients

### Claude Desktop (stdio)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

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

Run `which dag-planner-mcp` after installation to get the correct path.

### Cursor IDE (HTTP)

```json
{
  "mcpServers": {
    "dag-planner-mcp": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Python client (HTTP)

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client("http://localhost:8000/mcp") as (r, w, _):
    async with ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool("create_workflow_run", {"goal": "My goal"})
```
