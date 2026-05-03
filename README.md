# Customer Support MCP — Full-Stack AI Platform

> **Production-grade AI customer-support platform** built with **FastMCP**, **LangGraph**, **FastAPI**, and **React**.  
> A Groq → Ollama LLM fallback chain powers every customer interaction — no GPU, no credit card required.

This platform simulates a complete e-commerce customer-support system for a fictional shop called **ShopEasy**.  
Customers can ask natural-language questions, check orders, raise support tickets, and search an FAQ knowledge base.  
The AI agent decides which tools to call, in what order, and synthesises a coherent reply — all in real time.

---

## Repository Layout

This workspace contains **three independently deployable packages** that form one coherent system:

```
📦 customersupportmcp/          ← MCP server (AI core — the brain)
📦 customersupportmcp-client/   ← CLI chat client (terminal interface)
📦 customersupportmcp-ui/       ← Full-stack web UI (FastAPI backend + React frontend)
```

Each package can be run standalone.  In production, `customersupportmcp-ui` bundles the MCP server
directly into its Docker image so there is only one container to operate.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     Browser / Claude Desktop                      │
└──────────┬──────────────────────────┬────────────────────────────┘
           │ HTTP / WebSocket          │ MCP protocol (stdio)
           ▼                           ▼
┌──────────────────────┐   ┌──────────────────────────┐
│   React Frontend     │   │   CLI Client             │
│   (Vite + nginx)     │   │   chat.py / demo.py      │
│   port 3000          │   └──────────────────────────┘
└──────────┬───────────┘
           │ REST + WebSocket
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend  (port 8000)                  │
│  /api/v1/{health,orders,tickets,faq,chat,metrics,analytics}       │
│  WS  /api/v1/ws/chat/{customer_id}  — real-time AI streaming      │
│  Middleware: CORS · SecurityHeaders · RequestID · timing          │
└──────────────────────┬───────────────────────────────────────────┘
                       │ direct Python imports (zero subprocess)
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│              FastMCP Server  (customersupportmcp)                 │
│  @gateway middleware → rate limit · injection guard · logging     │
│  LangGraph ReAct Agent                                            │
│  Tools: kb · orders · tickets · customer · rag · health           │
└──────────────────────┬───────────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
  SQLite (SQLAlchemy)         ChromaDB (RAG)
  orders · tickets            all-MiniLM-L6-v2 embeddings
  refunds · notes             kb_articles collection
  conversations               support_tickets collection
          │
          ├── Groq API  (llama-3.1-8b → llama-3.3-70b → llama-4-scout → qwen3-32b → gpt-oss-20b)
          └── Ollama    (llama3.2 — local fallback, unlimited, no API key)
```

### How it all fits together

1. **A user opens** `http://localhost:3000` in a browser.  The React frontend is a static bundle served by nginx.
2. **Nginx reverse-proxies** all `/api` and `/ws` requests to the FastAPI backend on port 8000.
3. **FastAPI** receives the request, runs security middleware (CORS headers, request-ID tagging, response-time measurement), then routes it to the correct endpoint.
4. **The endpoint** calls the **support service** — a thin async layer that imports the MCP server's Python functions *directly* (no subprocess, no JSON-RPC overhead, no extra latency).
5. **For AI chat**, the endpoint upgrades the HTTP connection to a **WebSocket**.  The agent streams tokens back word-by-word so the UI can render a typewriter effect.
6. **The LangGraph ReAct agent** receives the customer's message.  It decides which tools to call (orders? FAQ? ticket?), calls them, reads the results, and continues reasoning until it can write a final answer.
7. **Tools** read/write **SQLite** via SQLAlchemy Core or query **ChromaDB** for semantic search.
8. **LLM calls** go to Groq first.  If Groq is busy or rate-limited, the next model in the fallback chain is tried automatically.  If every cloud model fails, Ollama serves the request locally.

---

## Features

| Category | Details |
|---|---|
| **AI engine** | LangGraph ReAct agent — reasons step-by-step, calls tools, verifies results |
| **LLM chain** | Groq (5-model fallback) → Ollama local — never a dead end |
| **RAG search** | ChromaDB + sentence-transformers all-MiniLM-L6-v2 — no API key needed |
| **Real-time chat** | WebSocket streaming with word-by-word token delivery |
| **Analytics dashboard** | Live ticket/order metrics via Server-Sent Events (SSE) |
| **Rate limiting** | Per-customer sliding-window (10 req / 60 s — fully configurable) |
| **Injection guard** | Regex-based prompt injection detection on every message (OWASP LLM01) |
| **Observability** | LangSmith tracing (optional), structured JSON logs, request-ID headers |
| **Database** | SQLite + SQLAlchemy Core 2.x, auto-seeded on first run |
| **Docker** | Single `docker compose up` starts everything |
| **Tests** | pytest suite — unit + integration, fully hermetic, no real API calls |

---

## Quick Start — Docker (Recommended)

Docker is the easiest path because it wires all three services together automatically and you do not need Python or Node.js installed locally.

```bash
# 1. Clone the repo
git clone <repo-url>

# 2. The main docker-compose.yml lives inside customersupportmcp-ui
cd customersupportmcp-ui

# 3. Create the .env file — only GROQ_API_KEY is required
#    Get a free key at https://console.groq.com  (no credit card needed)
cp ../customersupportmcp/.env.example ../customersupportmcp/.env
# Open the file and paste your GROQ_API_KEY

# 4. Build images and start all containers
docker compose up --build

# That's it.  Open these URLs:
# UI         →  http://localhost:3000
# API docs   →  http://localhost:8000/api/docs
# Swagger    →  http://localhost:8000/api/redoc
```

What happens during `docker compose up --build`:

1. **Backend image** is built from `customersupportmcp-ui/backend/Dockerfile`.  
   It copies the entire `customersupportmcp/` directory into the image at `/app/mcp_server/` and installs all Python dependencies.  
   The FastAPI server + the MCP server share a single Python process.
2. **Frontend image** is built from `customersupportmcp-ui/frontend/Dockerfile`.  
   Vite compiles the React source into static HTML/CSS/JS files, then nginx copies them and serves them on port 3000.  
   nginx also reverse-proxies `/api` and `/ws` to the backend — the browser never needs to know the backend's port.
3. **Ollama** starts and listens on port 11434.  On first run it downloads the `llama3.2` model (~2 GB).  Subsequent starts reuse the cached model.

All three services start automatically:

| Container | Port | Health-check | Description |
|---|---|---|---|
| `customersupport-backend` | `8000` | `GET /api/v1/health` every 30 s | FastAPI + MCP server bundled together |
| `customersupport-frontend` | `3000` | nginx default | React/Vite static bundle served by nginx |
| `customersupport-ollama` | `11434` | `ollama list` every 30 s | Local LLM (pulls llama3.2 on first run) |

---

## Quick Start — Local Dev (without Docker)

Use this if you want to edit code and see changes immediately without rebuilding Docker images.

### Prerequisites

- Python 3.11 or newer (`python --version`)
- Node.js 20 or newer (`node --version`) — only for the frontend
- [Ollama](https://ollama.com/download) installed locally — only if you want the local LLM fallback

### Step 1 — MCP Server (AI core)

```bash
cd customersupportmcp

# Create an isolated virtual environment
python -m venv .venv

# Activate it
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# Install all dependencies
pip install -r requirements.txt

# Copy the example env file and fill in your Groq key
cp .env.example .env
# Open .env in any editor and set GROQ_API_KEY=gsk_...

# Start the MCP server (communicates over stdio — you will see no output until a client connects)
python main.py
```

> **Note:** The MCP server communicates over `stdio` (standard input/output).  
> You will not see an HTTP port.  Run the CLI client or the backend to interact with it.

### Step 2 — Web UI Backend (API server)

Open a new terminal:

```bash
cd customersupportmcp-ui/backend

# Install dependencies (separate from the MCP server venv)
pip install -r requirements.txt

# The backend needs to find the MCP server code.
# Point it to the main.py of the MCP server:
export MCP_SERVER_PATH=../../customersupportmcp/main.py
# Windows PowerShell:
$env:MCP_SERVER_PATH = "..\..\customersupportmcp\main.py"

# Start FastAPI with auto-reload
uvicorn main:app --reload --port 8000

# Swagger UI → http://localhost:8000/api/docs
```

### Step 3 — Web UI Frontend (React)

Open another terminal:

```bash
cd customersupportmcp-ui/frontend
npm install
npm run dev
# Vite dev server → http://localhost:5173
# It auto-proxies /api and /ws to http://localhost:8000
```

### Step 4 — CLI Client (optional)

```bash
cd customersupportmcp-client
pip install -r requirements.txt

# Interactive chat — the client spawns the MCP server itself via stdio
python chat.py                         # uses CUST-001 by default
python chat.py --customer CUST-002    # override to a different customer
python chat.py --customer CUST-001 --tools  # list all server tools first

# Non-interactive demo that exercises every MCP tool
python demo.py
```

---

## Environment Variables

Create `customersupportmcp/.env` (copy from `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | *(empty)* | Free Groq key — [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Primary Groq model |
| `GROQ_FALLBACK_MODELS` | *(see config)* | Comma-separated fallback chain |
| `OLLAMA_ENABLED` | `true` | Enable local Ollama fallback |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `LANGCHAIN_API_KEY` | *(empty)* | LangSmith key — enables tracing when set |
| `LANGCHAIN_PROJECT` | `customer-support-mcp` | LangSmith project name |
| `RATE_LIMIT_REQUESTS` | `10` | Max AI requests per customer per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window in seconds |
| `SERVER_NAME` | `CustomerSupportMCP` | MCP server display name |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG` / `INFO` / `WARNING`) |
| `LOG_FORMAT` | `text` | Set `json` for machine-parseable logs |

---

## MCP Tools

| Tool | Description |
|---|---|
| `handle_customer_request` | Full AI-powered support via LangGraph + Groq/Ollama |
| `customer_profile` | Aggregate orders + tickets in one call |
| `check_order` | Fetch a single order by ID |
| `list_orders` | All orders for a customer |
| `create_ticket` | Open a support ticket |
| `get_ticket` | Retrieve ticket status and details |
| `search_faqs` | RAG-powered knowledge-base search |
| `health_check` | Server / DB / LLM health status |

---

## REST & WebSocket API

Base URL: `http://localhost:8000`

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness probe |
| `GET` | `/api/v1/orders/{customer_id}` | List customer orders |
| `GET` | `/api/v1/orders/detail/{order_id}` | Single order details |
| `GET` | `/api/v1/faq?q=...` | Knowledge-base search |
| `POST` | `/api/v1/tickets` | Create support ticket |
| `GET` | `/api/v1/tickets/{ticket_id}` | Retrieve ticket |
| `WS` | `/api/v1/ws/chat/{customer_id}` | Real-time AI chat stream |
| `GET` | `/api/v1/metrics` | Runtime metrics snapshot |
| `GET` | `/api/v1/metrics/stream` | Live metrics via SSE |
| `GET` | `/api/v1/analytics` | Analytics dashboard data |
| `GET` | `/api/docs` | Interactive Swagger UI |

---

## LLM Provider Chain

Requests are tried in this order with automatic failover:

```
Groq llama-3.1-8b-instant
  → Groq gemma2-9b-it
    → Groq mixtral-8x7b-32768
      → Groq llama-3.3-70b-versatile
        → Ollama llama3.2  (local)
```

- **Rate-limit / 429 / 503** → automatically skip to next provider
- **All providers exhausted** → polite error message returned to user
- **No `GROQ_API_KEY`** → Ollama-only mode (set `OLLAMA_ENABLED=true`)

---

## Connect to Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "customer-support": {
      "command": "python",
      "args": ["/absolute/path/to/customersupportmcp/main.py"]
    }
  }
}
```

---

## Running Tests

```bash
cd customersupportmcp
pip install -r requirements.txt

pytest                                    # full suite
pytest tests/unit/                        # unit tests only
pytest tests/integration/                 # integration tests only
pytest --cov=. --cov-report=term-missing  # with coverage
```

All tests are **hermetic** — no real API calls, no internet required. The database tests use an in-memory SQLite engine injected via `monkeypatch`.

---

## Project Structure

```
customersupportmcp/                   ← MCP server (AI core)
├── main.py                           FastMCP server entry point
├── config.py                         Central configuration (.env loader)
├── pyproject.toml                    Project metadata + pytest/ruff config
├── docker-compose.yml                Standalone MCP + Ollama stack
├── Dockerfile
├── requirements.txt
├── .env.example                      ← copy to .env
│
├── agent/
│   └── graph.py                      LangGraph ReAct agent + LLM fallback chain
├── core/
│   ├── logging_config.py             Structured JSON + console logging
│   └── rate_limiter.py               Sliding-window rate limiter
├── gateway/
│   └── middleware.py                 @gateway decorator (rate limit + logging)
├── model/
│   └── schemas.py                    Pydantic v2 request/response schemas
├── prompts/
│   └── system_prompt.txt             LangGraph agent system prompt
├── tools/
│   ├── customer_tools.py             Customer profile aggregation
│   ├── kb_tools.py                   Knowledge-base / FAQ search
│   ├── order_tools.py                Order management (SQLAlchemy)
│   ├── rag_tools.py                  ChromaDB semantic search
│   └── ticket_tools.py              Support ticket CRUD
├── data/
│   ├── database.py                   SQLAlchemy Core schema + seed helpers
│   ├── rag_store.py                  ChromaDB vector store wrapper
│   ├── knowledge_base.json           FAQ articles seed data
│   ├── mock_orders.json              Seed order data
│   └── tickets.json                  Seed ticket data
└── tests/
    ├── conftest.py                   Shared fixtures (in-memory DB, env patching)
    ├── unit/
    │   ├── test_kb_tools.py
    │   ├── test_order_tools.py
    │   ├── test_ticket_tools.py
    │   └── test_rate_limiter.py
    └── integration/
        └── test_agent.py             Agent orchestration (mocked LLM)

customersupportmcp-client/            ← CLI client
├── chat.py                           Interactive chat REPL
├── demo.py                           Non-interactive tool demo
├── mcp_client.py                     Low-level FastMCP client wrapper
├── config.py                         Client configuration
└── requirements.txt

customersupportmcp-ui/                ← Full-stack web UI
├── docker-compose.yml                Production compose (backend + frontend + ollama)
├── backend/
│   ├── Dockerfile                    Multi-stage Python build
│   ├── main.py                       FastAPI application factory
│   ├── requirements.txt
│   ├── api/v1/
│   │   ├── router.py
│   │   └── endpoints/
│   │       ├── analytics.py
│   │       ├── chat.py               WebSocket streaming endpoint
│   │       ├── faq.py
│   │       ├── health.py
│   │       ├── metrics.py            SSE metrics stream
│   │       ├── orders.py
│   │       └── tickets.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging_config.py
│   │   └── middleware.py             Security headers + request context
│   ├── models/schemas.py
│   └── services/
│       ├── support_service.py        Direct MCP tool imports (zero subprocess)
│       ├── agent_service.py
│       ├── connection_manager.py     WebSocket session tracking
│       └── mcp_service.py
└── frontend/
    ├── Dockerfile                    Node build → nginx serve
    ├── nginx.conf                    Reverse proxy /api and /ws to backend
    ├── vite.config.js
    ├── package.json
    └── src/
        ├── App.jsx                   Layout, customer selector, view switcher
        ├── components/
        │   ├── Chat.jsx              WebSocket chat + SSE metrics bar
        │   ├── Dashboard.jsx         Analytics charts (Recharts)
        │   └── Sidebar.jsx           Orders, tickets, FAQ panels
        ├── api/
        │   ├── apiClient.js
        │   └── supportApi.js
        ├── constants/index.js        Customer IDs, suggestions, colours
        └── hooks/useWebSocket.js     Reconnecting WebSocket hook
```

---

## Docker Tips

```bash
# Start everything (builds on first run)
docker compose up --build

# Detached mode
docker compose up -d

# Tail backend logs
docker compose logs -f backend

# Pull a different Ollama model
docker compose exec ollama ollama pull llama3.1
# Then set OLLAMA_MODEL=llama3.1 in .env and restart

# Stop and remove containers (data volumes preserved)
docker compose down

# Stop and remove everything including volumes
docker compose down -v
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI agent | [LangGraph](https://github.com/langchain-ai/langgraph) ReAct |
| LLM (cloud) | [Groq](https://console.groq.com) — free tier |
| LLM (local) | [Ollama](https://ollama.com) — llama3.2 |
| RAG | [ChromaDB](https://www.trychroma.com) + sentence-transformers |
| MCP framework | [FastMCP](https://github.com/jlowin/fastmcp) |
| API server | [FastAPI](https://fastapi.tiangolo.com) + Uvicorn |
| Database | SQLite + [SQLAlchemy](https://www.sqlalchemy.org) Core 2.x |
| Frontend | [React 18](https://react.dev) + [Vite 5](https://vitejs.dev) |
| Charts | [Recharts](https://recharts.org) |
| Frontend serve | nginx 1.27 |
| Containers | Docker Compose |
| Observability | [LangSmith](https://smith.langchain.com) (optional) |
| Testing | pytest + pytest-asyncio + pytest-mock |

---

## License

MIT
