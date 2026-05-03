# 🤖 Customer Support MCP — Full-Stack AI Platform

> Build an AI customer support agent for a fictional shop called **ShopEasy** — with real-time chat, order lookup, ticket management, and an analytics dashboard.  
> Everything runs locally. You only need a **free Groq API key** to start. No GPU, no paid subscriptions.

---

## 🗺 What Is This Project?

This is a complete, end-to-end AI customer support platform made of **three packages** that work together:

| Package | What it does |
|---|---|
| `customersupportmcp/` | The **brain** — AI agent, database, tools, security |
| `customersupportmcp-client/` | Terminal chat — talk to the AI in your command line |
| `customersupportmcp-ui/` | Full web app — browser chat, dashboard, order history |

You can use just the CLI client to chat, or spin up the web UI to get a full product experience. All three share the same AI core.

---

## 🏗 How the System Works (Simple Explanation)

```
You (browser or terminal)
       |
       | WebSocket / MCP protocol / HTTP
       v
+------------------------------------------------+
|  React frontend  (nginx, port 3000)            |
|  -> Chat window, orders sidebar, analytics     |
+-------------------+----------------------------+
                    | /api/* and /ws/* reverse-proxy
                    v
+------------------------------------------------+
|  FastAPI backend  (Python, port 8000)          |
|  -> REST + WebSocket endpoints                 |
|  -> Security middleware, request logging       |
+-------------------+----------------------------+
                    | direct Python import (no subprocess)
                    v
+------------------------------------------------+
|  MCP Server  (customersupportmcp)              |
|  -> @gateway decorator (rate limit, injection) |
|  -> LangGraph ReAct agent                      |
|  -> 9 agent tools                              |
+----------+-------------------------------------+
           |                    |
           v                    v
  SQLite database         ChromaDB (vector)
  orders, tickets         FAQ articles
  refunds, notes          Similar tickets
  conversations
           |
           v
  Groq API (cloud LLM)  --> Ollama (local LLM fallback)
  5 free models               llama3.2
  automatic failover
```

**Step by step when you send a message:**

1. Your browser sends the message over a **WebSocket** connection.
2. The **FastAPI backend** receives it and passes it to the AI agent.
3. The **LangGraph ReAct agent** starts reasoning — it decides which tools to call.
4. The agent might call `check_order_status`, `search_knowledge_base`, or `create_ticket_tool` — or all three, in sequence.
5. Each tool reads or writes the **SQLite database**. The knowledge-base search also queries **ChromaDB** for similar questions.
6. The agent synthesizes the results into a human-friendly reply and **streams it back word-by-word**.
7. Your browser shows the reply in a typewriter animation.
8. The frontend UI also shows **"tool chips"** — small badges like `🔍 Searching knowledge base…` that let you see what the AI is doing in real time.

---

## 🚀 Quick Start — One Command

The fastest way to run everything is Docker:

```bash
# Clone the repo
git clone https://github.com/drdeveloper88/customerSupportMCP1.git
cd customerSupportMCP1

# Get a free Groq API key at https://console.groq.com (no credit card)
# Then create .env in the mcp server folder:
echo "GROQ_API_KEY=gsk_your_key_here" > customersupportmcp/.env

# Go to the UI folder (this is where docker-compose.yml lives)
cd customersupportmcp-ui

# Build all images and start
docker compose up --build

# Done! Open these in your browser:
# Chat UI   ->  http://localhost:3000
# API docs  ->  http://localhost:8000/api/docs
```

Three containers will start:

| Container | Port | What it does |
|---|---|---|
| `customersupport-backend` | 8000 | FastAPI + AI agent (Python) |
| `customersupport-frontend` | 3000 | React web UI (nginx serves it) |
| `customersupport-ollama` | 11434 | Local LLM fallback (downloads llama3.2 on first run ~2 GB) |

All three containers have health checks. The backend checks `GET /api/v1/health` every 30 seconds. If the backend crashes, Docker restarts it automatically.

---

## 📦 Package 1 — `customersupportmcp` (The AI Core)

This is the heart of the system. It runs as a **FastMCP server** that exposes AI tools via the **Model Context Protocol (MCP)** — the same protocol used by Claude Desktop and other AI clients.

### What is MCP?

MCP (Model Context Protocol) is a standard way for AI tools to expose capabilities as a structured API. Any MCP client (Claude Desktop, the CLI client, the web backend) can connect and call these tools with typed arguments. The server communicates over **stdio** (standard input/output) using JSON-RPC.

### The 8 MCP Tools

These are the public-facing tools that any MCP client can call:

| Tool | Arguments | What it returns |
|---|---|---|
| `handle_customer_request` | `customer_id`, `message` | Full AI agent response (natural language) |
| `customer_profile` | `customer_id` | All orders + all tickets for this customer |
| `check_order` | `order_id` | Full order details, items, tracking, status |
| `list_orders` | `customer_id` | Array of all orders for this customer |
| `create_ticket` | `customer_id`, `subject`, `description`, `priority` | New ticket object with ID |
| `get_ticket` | `ticket_id` | Ticket status, priority, notes history |
| `search_faqs` | `query` | Top matching FAQ articles |
| `health_check` | *(none)* | Server + database + LLM status |

Every tool is wrapped with the `@gateway(key_arg="customer_id")` decorator **before** `@mcp.tool()`. This means every tool call automatically checks the rate limit, scans for prompt injection, and logs the request.

```python
# Example from main.py — security wrapping comes first
@mcp.tool()
@gateway(key_arg="customer_id")
async def handle_customer_request(customer_id: str, message: str) -> str:
    ...
```

### The LangGraph ReAct Agent

The `handle_customer_request` tool kicks off a **LangGraph ReAct agent**. ReAct stands for *Reason + Act* — the agent alternates between deciding what to do next and calling a tool to do it. The agent has access to 9 internal tools:

| Tool | What it does |
|---|---|
| `get_customer_profile` | Fetches customer info (orders + tickets summary) |
| `search_knowledge_base` | Full-text FAQ search — always checked first |
| `find_similar_tickets_tool` | ChromaDB similarity search on past tickets |
| `check_order_status` | Full order details from SQLite |
| `list_customer_orders` | All orders for a customer |
| `process_refund` | Creates a refund record in the database |
| `create_ticket_tool` | Opens a new support ticket |
| `get_ticket_info` | Retrieves ticket details by ID |
| `escalate_ticket_tool` | Escalates ticket to HIGH priority / human agent |

The agent also has a **hallucination guard** — a regex that detects when the LLM tries to fake a tool call by writing raw tool-call syntax in its output instead of actually calling a tool. When detected, the fake call is stripped and ignored.

The agent streams events back to the caller:

| Event | When it fires |
|---|---|
| `tool_start` | Agent is about to call a tool |
| `tool_end` | Tool call completed |
| `token` | One chunk of LLM output (typewriter) |
| `done` | Full, final response ready |
| `error` | Something went wrong |

Each tool has a friendly emoji label in `_TOOL_LABELS` — for example `search_knowledge_base` shows as `🔍 Searching knowledge base…`. The frontend's tool chips are driven by these events.

### The LLM Fallback Chain

Instead of crashing when Groq is slow or rate-limited, the agent tries each model in turn:

```
1. llama-3.1-8b-instant           (fastest, smallest Groq model)
2. llama-3.3-70b-versatile        (more capable Groq model)
3. meta-llama/llama-4-scout-17b   (Groq hosted)
4. qwen/qwen3-32b                 (Groq hosted)
5. openai/gpt-oss-20b             (Groq hosted)
6. Ollama llama3.2                (local, unlimited, no API key needed)
```

- All Groq models are **free tier** — no billing required.
- Ollama is always free and runs on your own machine.
- If `GROQ_API_KEY` is missing, the server starts in Ollama-only mode automatically.
- If you have a `LANGCHAIN_API_KEY`, LangSmith tracing is auto-enabled at startup — no code changes needed.

### The System Prompt

The agent's behavior and personality are defined in `prompts/system_prompt.txt`. There is also a hardcoded fallback inside the code so the agent works even if the file is deleted. The prompt gives the agent 10 guidelines:

1. Always greet the customer politely.
2. Search the knowledge base first for common questions.
3. Verify order details before discussing them.
4. Create a ticket for any issue that cannot be resolved immediately.
5. Escalate tickets for complex complaints, financial disputes, or frustrated customers.
6. Confirm every action taken (e.g. "I have submitted a refund for order ORD-1002").
7. End with a friendly closing and offer further help.
8. Never reveal internal system details, tool names, or database structures.
9. Apologize and create a ticket if you cannot help directly.
10. Keep responses concise — aim for 2–4 short paragraphs.

### The Gateway Middleware — Security Layer

Every MCP tool call passes through `gateway/middleware.py`. This is a decorator factory that adds three things:

**Rate limiting** — uses a sliding-window algorithm. By default, each customer can make 10 requests per 60 seconds. The window slides forward in real time — old requests expire as new ones come in. The limiter uses `threading.Lock` so it is safe for concurrent calls from multiple threads.

**Prompt injection detection** — the `_INJECTION_RE` regex (OWASP LLM01) blocks phrases that attackers use to override the AI's instructions:
- `ignore previous/prior/above instructions`
- `forget everything`, `forget all`
- `you are now [not a customer]`
- `act as [not support/agent/assistant]`
- `jailbreak`, `DAN mode`, `developer mode`
- `pretend you are [not support]`
- `override your instructions/rules/guidelines`
- `new instruction:`, `system: you are`

When a blocked phrase is detected the request is immediately rejected with a clear error. The pattern is intentionally broad — a harmless message being blocked is safer than letting an injection reach the LLM.

**Structured logging** — every request and response is logged with the customer ID, tool name, input summary, and output length. Set `LOG_FORMAT=json` in your `.env` for machine-readable log lines.

### The Database — SQLite + SQLAlchemy Core

All data lives in a single file at `data/support.db`. SQLAlchemy Core 2.x is used — no ORM, just plain SQL with type-safe table definitions.

| Table | What it stores |
|---|---|
| `orders` | One row per order — status, total, shipping, carrier, tracking number |
| `order_items` | Line items linked to an order by `order_id` |
| `tickets` | Support tickets — subject, description, status, priority |
| `ticket_notes` | Immutable audit trail of notes added to a ticket |
| `refunds` | Refund requests submitted via `process_refund` tool |
| `conversations` | Chat history per customer (enables multi-turn memory) |

The database path is controlled by the `DATA_DIR` environment variable. In Docker this is set to `/app/db_data` — a named volume — so your data survives container restarts.

On first run, `init_db()` creates all tables and seeds them from JSON files (`mock_orders.json`, `tickets.json`).

### The RAG System — ChromaDB + Sentence Transformers

RAG stands for *Retrieval-Augmented Generation* — the AI looks up relevant documents before answering so it gives accurate, factual answers instead of guessing.

The RAG store uses **ChromaDB** as a local vector database and **all-MiniLM-L6-v2** (a small sentence transformer model) to convert text to embeddings. Both run locally — no external API needed.

Two collections are maintained:

| Collection | What it stores | Used for |
|---|---|---|
| `kb_articles` | All FAQ articles from `knowledge_base.json` | Semantic FAQ search |
| `support_tickets` | All past support tickets | Finding similar previous issues |

When a customer asks a question, it is converted to an embedding and the closest articles are found by cosine similarity. This works even when the customer uses different words than the FAQ articles use.

### The Rate Limiter

`core/rate_limiter.py` is a **thread-safe sliding-window rate limiter**. It tracks request timestamps per customer ID. On every call it:
1. Acquires a thread lock.
2. Removes timestamps older than the window.
3. Counts remaining timestamps in the window.
4. If count < max, records the timestamp and allows the request.
5. If count >= max, blocks the request.

Memory usage is proportional to active keys only — expired entries are removed automatically.

---

## 📦 Package 2 — `customersupportmcp-client` (CLI Chat)

A terminal-based chat client that connects to the MCP server via **stdio transport** — it spawns the MCP server as a subprocess and sends tool calls to it over stdin/stdout.

### Three programs inside

**`chat.py` — interactive REPL**

```bash
python chat.py                         # CUST-001 (default customer)
python chat.py --customer CUST-002    # different customer
python chat.py --customer CUST-001 --tools  # list tools before starting chat
```

ANSI colors are enabled automatically on macOS, Linux, Windows Terminal, and any terminal with `WT_SESSION` or `TERM` set. On plain Windows Command Prompt, colors are disabled so you never see garbled characters.

**Chat commands you can type while chatting:**

| Command | What it does |
|---|---|
| `/orders` | Lists all your orders |
| `/order ORD-1001` | Looks up a specific order by ID |
| `/faq how to return` | Searches the FAQ knowledge base |
| `/ticket TKT-XXXXXXXX` | Gets ticket details |
| `/tools` | Shows all MCP tools available on the server |
| `/help` | Shows this command list |
| `/quit` or `/exit` | Exits the chat |

The chat banner looks like this:

```
╔══════════════════════════════════════════════════╗
║      ShopEasy Customer Support Chat              ║
╚══════════════════════════════════════════════════╝
  Customer : CUST-001
  Type your question or a command. Type /help for commands, /quit to exit.

You: Where is my order ORD-1001?

Agent: I checked your order ORD-1001. It was shipped via FedEx
       (tracking: FX123456789) and is expected by Dec 15.
       Is there anything else I can help you with?
```

**`mcp_client.py` — low-level client library**

The engine under `chat.py`. Uses FastMCP's `Client` with a `PythonStdioTransport` to spawn the MCP server and communicate over its stdin/stdout. Exposes async helper functions for each tool:

```python
ask_support_agent(customer_id, message)
check_order(order_id)
list_orders(customer_id)
search_faqs(query)
create_ticket(customer_id, subject, description, priority)
get_ticket(ticket_id)
get_customer_profile(customer_id)
health_check()
list_server_tools()
```

Every call uses `async with get_mcp_client() as client:` so connections are properly closed even if an error occurs.

**`demo.py` — automated demo**

Runs through all tools automatically — no typing required. Good for verifying that setup works, or for showing the project to someone.

```bash
python demo.py
```

It exercises: listing tools, three FAQ searches, three order lookups, customer order histories, a full ticket lifecycle (create → retrieve → escalate), and a natural-language AI chat exchange.

### How to run the CLI client

```bash
cd customersupportmcp-client
pip install -r requirements.txt

# The client auto-finds the MCP server at ../customersupportmcp/main.py
# or you can set MCP_SERVER_PATH in .env
python chat.py
```

---

## 📦 Package 3 — `customersupportmcp-ui` (Web UI)

The full-stack web application. The backend is a **FastAPI** Python server. The frontend is a **React 18** app built with Vite and served by nginx.

### Backend — FastAPI

Built using the **application factory pattern** — a `create_app()` function assembles the FastAPI instance with all middleware and routes, making it easy to test with different configurations.

**Application startup sequence:**
1. Logging is configured first (before any module imports a logger).
2. FastAPI app is created with metadata for the Swagger UI.
3. Four middleware layers are added:
   - `SecurityHeadersMiddleware` — adds OWASP-recommended HTTP security headers.
   - `RequestContextMiddleware` — attaches a unique `X-Request-ID` to each request and measures response time.
   - CORS middleware — allows the React frontend to call the API.
   - Global exception handler — catches unhandled errors and returns clean JSON.
4. The versioned API router is registered under `/api/v1/`.

**Security headers on every response:**

| Header | Value | Protects against |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | MIME-type sniffing attacks |
| `X-Frame-Options` | `DENY` | Clickjacking |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Referrer leakage |
| `X-XSS-Protection` | `1; mode=block` | Reflected XSS (older browsers) |

Every request also gets a short UUID (`X-Request-ID`) in both request and response headers, plus `X-Response-Time` in milliseconds. Every log line for that request includes the same ID — so you can trace one request through the entire system from a single log search.

### REST and WebSocket API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness probe |
| `GET` | `/api/v1/tools` | List all agent tools |
| `GET` | `/api/v1/orders/{customer_id}` | All orders for a customer |
| `GET` | `/api/v1/orders/detail/{order_id}` | Single order with all line items |
| `GET` | `/api/v1/faq?q=your+question` | Knowledge-base search |
| `POST` | `/api/v1/tickets` | Create a ticket |
| `GET` | `/api/v1/tickets/{ticket_id}` | Retrieve ticket details |
| `WS` | `/api/v1/ws/chat/{customer_id}` | Real-time AI chat stream |
| `GET` | `/api/v1/metrics` | Runtime metrics snapshot |
| `GET` | `/api/v1/metrics/stream` | Live metrics via SSE |
| `GET` | `/api/v1/analytics` | Analytics dashboard data |
| `GET` | `/api/docs` | Interactive Swagger UI |

### WebSocket Chat Protocol

**Server → client messages:**

| Type | When sent | Payload |
|---|---|---|
| `connected` | After handshake | *(none)* |
| `typing` | AI starts / stops thinking | `{"status": true/false}` |
| `tool_start` | Agent calls a tool | `{"tool": "name", "label": "emoji text"}` |
| `tool_end` | Tool finishes | `{"tool": "name"}` |
| `token` | One chunk of LLM output | `{"content": "word"}` |
| `done` | Complete final response | `{"content": "full reply"}` |
| `error` | Unrecoverable error | `{"message": "description"}` |

**Client → server message:**
```json
{"message": "Where is my order ORD-1001?"}
```

Before sending the `done` event, the backend sanitizes the response — it strips any raw tool-call artifacts (like `<function=check_order>` or `<tool_call>...</tool_call>`) that might have leaked through the LLM.

### The Direct Import Architecture

Instead of spawning the MCP server as a subprocess, the backend imports its Python functions **directly** — same process, zero IPC latency:

```python
# services/support_service.py
sys.path.insert(0, str(_MCP_SERVER_DIR))

from data.database import init_db, get_analytics_data
from tools.order_tools import get_order_by_id, get_orders_by_customer
from tools.ticket_tools import create_support_ticket, get_ticket_by_id
from tools.kb_tools import search_kb
```

Because database functions use synchronous SQLAlchemy, they are wrapped in `asyncio.to_thread()` so they never block the FastAPI event loop:

```python
async def fetch_orders(customer_id: str) -> list[dict]:
    return await asyncio.to_thread(get_orders_by_customer, customer_id)
```

### Frontend — React 18 + Vite 5

**Chat view (Chat.jsx)**

- **Connection status bar** — green dot when connected, plus live metrics (active sessions, total messages, average latency). Metrics come from SSE so they update every few seconds.
- **Tool activity chips** — while the AI works, badges appear showing which tool is being called with its emoji label. A checkmark appears when the tool finishes.
- **Typewriter text** — `token` events are accumulated character by character so replies appear as if someone is typing.
- **Suggestion pills** — pre-written questions at the bottom of an empty chat. Click one to send it.
- **Message bubbles** — user on the right (blue), AI on the left (with robot avatar).

**Sidebar (Sidebar.jsx)** — three panels:

- **Orders** — expandable order cards showing order ID, status (color-coded), item count, total, and line items. Includes a tracking badge with carrier and tracking number.
- **FAQ** — live search box that queries `GET /api/v1/faq?q=...` and shows matching articles.
- **Tickets** — a form to create tickets with subject, description, and priority (`low` / `medium` / `high` / `critical`). Also includes ticket lookup by ID.

**Dashboard (Dashboard.jsx)** — four charts powered by Recharts:

| Chart | Type | Shows |
|---|---|---|
| Ticket status breakdown | Pie chart | open / pending / resolved / escalated / closed |
| Ticket priority breakdown | Pie chart | critical / high / medium / low |
| Order status breakdown | Bar chart | delivered / shipped / processing / cancelled |
| Recent ticket activity | Area chart | Ticket volume over time |

Four KPI cards at the top show total orders, open tickets, resolved tickets, and total customers.

**`useWebSocket` hook** — manages the WebSocket lifecycle:
- Connects automatically on mount or when the customer ID changes.
- Reconnects if the connection drops.
- Supports both `ws://` (HTTP) and `wss://` (HTTPS) automatically.
- Cleans up on unmount — no memory leaks.

**nginx** serves the static bundle and proxies `/api` and `/ws` to the backend container at `http://backend:8000`. The browser only ever talks to port 3000.

---

## ⚙️ Environment Variables

Create `customersupportmcp/.env` — copy `.env.example` as a starting point:

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | *(none)* | Free key from [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Primary LLM model |
| `OLLAMA_ENABLED` | `true` | Use Ollama as final fallback |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama URL (use `http://ollama:11434` in Docker) |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `LANGCHAIN_API_KEY` | *(none)* | LangSmith key — tracing auto-enables when set |
| `LANGCHAIN_PROJECT` | `customer-support-mcp` | LangSmith project name |
| `RATE_LIMIT_REQUESTS` | `10` | Max requests per customer per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window length in seconds |
| `DATA_DIR` | *(package folder)* | Where `support.db` is stored |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |
| `LOG_FORMAT` | `text` | Set `json` for structured log lines |

---

## 🧪 Running Tests

```bash
cd customersupportmcp
pip install -r requirements.txt

pytest                                    # full suite
pytest tests/unit/                        # unit tests only
pytest tests/integration/                 # integration tests only
pytest --cov=. --cov-report=term-missing  # with coverage
```

| Test file | What it tests |
|---|---|
| `test_rate_limiter.py` | Allow/block logic, window expiry, concurrency |
| `test_kb_tools.py` | Knowledge-base search and fuzzy matching |
| `test_order_tools.py` | Order lookups, invalid IDs, empty results |
| `test_ticket_tools.py` | Create/get/escalate tickets, priority validation |
| `test_agent.py` | Full agent orchestration with mocked LLM responses |

All tests are **hermetic** — no real API calls, no internet, no real database. `conftest.py` patches the database engine to use an in-memory SQLite instance and injects test environment variables.

---

## 🏃 Local Development (Without Docker)

### Step 1 — MCP server

```bash
cd customersupportmcp
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows
# source .venv/bin/activate          # macOS / Linux

pip install -r requirements.txt
cp .env.example .env
# Edit .env and set GROQ_API_KEY

python main.py
# Communicates via stdio — no visible output until a client connects
```

### Step 2 — CLI client

```bash
cd customersupportmcp-client
pip install -r requirements.txt
python chat.py                       # interactive chat
python demo.py                       # automated demo
```

### Step 3 — Web backend

```bash
cd customersupportmcp-ui/backend
pip install -r requirements.txt

# Windows
$env:MCP_SERVER_PATH = "..\..\customersupportmcp\main.py"
# macOS / Linux
export MCP_SERVER_PATH=../../customersupportmcp/main.py

uvicorn main:app --reload --port 8000
# Swagger UI -> http://localhost:8000/api/docs
```

### Step 4 — Web frontend

```bash
cd customersupportmcp-ui/frontend
npm install
npm run dev
# Vite dev server with hot reload -> http://localhost:5173
```

Vite proxies `/api` and `/ws` to `http://localhost:8000` so you do not need to manage CORS during development.

---

## 🐳 Docker Tips

```bash
# Start everything
docker compose up --build

# Run in the background
docker compose up -d

# Watch backend logs
docker compose logs -f backend

# Check container health
docker compose ps

# Pull a better Ollama model
docker compose exec ollama ollama pull llama3.1
# Then set OLLAMA_MODEL=llama3.1 in .env and restart

# Rebuild just the backend after code changes
docker compose build backend && docker compose up -d backend

# Stop everything
docker compose down

# Stop and remove data volumes (WARNING: deletes database)
docker compose down -v
```

---

## 🗂 Full Project Structure

```
customersupportmcp/                       <- MCP server (AI core)
├── main.py                               FastMCP server + 8 MCP tools
├── config.py                             Load .env, define all settings
├── pyproject.toml                        Project metadata, pytest + ruff config
├── Dockerfile
├── requirements.txt
├── .env.example                          <- copy this to .env
│
├── agent/graph.py                        LangGraph ReAct agent, LLM chain, streaming
├── core/
│   ├── logging_config.py                 Structured logging (text + JSON modes)
│   └── rate_limiter.py                   Thread-safe sliding-window rate limiter
├── gateway/middleware.py                 @gateway: rate limit + injection guard + logging
├── model/schemas.py                      Pydantic v2 request/response schemas
├── prompts/system_prompt.txt             Agent personality and support guidelines
├── tools/
│   ├── customer_tools.py                 Aggregate customer profile
│   ├── kb_tools.py                       Knowledge-base full-text search
│   ├── order_tools.py                    get_order_by_id, get_orders_by_customer, process_refund
│   ├── rag_tools.py                      ChromaDB similarity search
│   └── ticket_tools.py                  Create/get/escalate tickets, SQLAlchemy transactions
├── data/
│   ├── database.py                       Tables, seed helpers, conversations
│   ├── rag_store.py                      ChromaDB wrapper (kb_articles + support_tickets)
│   ├── knowledge_base.json               FAQ article seed data
│   ├── mock_orders.json                  Sample orders + line items
│   └── tickets.json                      Sample support tickets
└── tests/
    ├── conftest.py                       In-memory DB fixture, env patching
    ├── unit/                             Unit tests per tool/module
    └── integration/test_agent.py        Agent orchestration with mocked LLM

customersupportmcp-client/                <- CLI chat client
├── chat.py                               Interactive REPL (colors, commands, banner)
├── demo.py                               Automated demo of every MCP tool
├── mcp_client.py                         FastMCP Client over stdio transport
├── config.py                             Client settings
└── requirements.txt

customersupportmcp-ui/                    <- Full-stack web UI
├── docker-compose.yml                    Production stack (backend + frontend + ollama)
├── backend/
│   ├── Dockerfile
│   ├── main.py                           FastAPI application factory + lifespan
│   ├── requirements.txt
│   ├── api/v1/endpoints/
│   │   ├── analytics.py                  GET /analytics
│   │   ├── chat.py                       WebSocket endpoint + response sanitizer
│   │   ├── faq.py                        GET /faq
│   │   ├── health.py                     GET /health
│   │   ├── metrics.py                    GET /metrics + SSE stream
│   │   ├── orders.py                     GET /orders
│   │   └── tickets.py                    POST/GET /tickets
│   ├── core/
│   │   ├── config.py                     Settings (origins, version, paths)
│   │   ├── logging_config.py
│   │   └── middleware.py                 SecurityHeadersMiddleware + RequestContextMiddleware
│   ├── models/schemas.py                 Pydantic schemas
│   └── services/
│       ├── support_service.py            Direct imports from MCP server (zero subprocess)
│       ├── agent_service.py              Wraps LangGraph streaming for WebSocket
│       └── connection_manager.py         WebSocket session tracking + metrics
└── frontend/
    ├── Dockerfile                        Node 20 build -> nginx 1.27 serve
    ├── nginx.conf                        Static serve + /api and /ws proxy
    ├── vite.config.js
    ├── package.json
    └── src/
        ├── App.jsx                       Layout, customer selector, view switcher
        ├── components/
        │   ├── Chat.jsx                  WebSocket chat, tool chips, SSE metrics, typewriter
        │   ├── Dashboard.jsx             KPI cards + 4 Recharts charts
        │   └── Sidebar.jsx              Orders panel, FAQ search, ticket creator
        ├── api/supportApi.js             fetchOrders, searchFaq, createTicket…
        ├── constants/index.js            Customer IDs, suggestion phrases, status colors
        ├── hooks/
        │   ├── useWebSocket.js           Reconnecting WebSocket hook (ws/wss)
        │   └── useApi.js                 Generic async fetch hook with loading/error state
        └── utils/formatHelpers.js        formatCurrency, formatDate helpers
```

---

## 🔌 Connect to Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "customer-support": {
      "command": "python",
      "args": ["C:/projects/dambar projects/customersupportmcp/main.py"]
    }
  }
}
```

Restart Claude Desktop and all 8 tools will appear in the chat interface.

---

## 🛠 Tech Stack Summary

| Layer | Technology | Why |
|---|---|---|
| MCP framework | FastMCP | Simple way to expose Python functions as MCP tools |
| AI agent | LangGraph ReAct | Step-by-step reasoning with tool calling and streaming |
| LLM (cloud) | Groq | Fast inference, free tier, 5-model fallback chain |
| LLM (local) | Ollama llama3.2 | Runs locally — works with no internet or API key |
| Vector search | ChromaDB | Semantic FAQ and ticket similarity search |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 | Local, fast, no API key needed |
| API server | FastAPI + Uvicorn | Async Python web framework |
| Database | SQLAlchemy Core 2.x + SQLite | Lightweight, no server required |
| Frontend | React 18 + Vite 5 | Fast dev builds, hot reload |
| Charts | Recharts | React-native charting library |
| Frontend serving | nginx 1.27 | Static files + API reverse proxy |
| Containers | Docker Compose | Single-command startup for the whole stack |
| Tracing | LangSmith | Optional — auto-enabled with API key |
| Testing | pytest + pytest-asyncio | Hermetic tests, no network calls |

---

## 📄 License

MIT — use freely, modify, redistribute.
