# Customer Support MCP — Full-Stack Web UI

> **Production-grade AI customer-support platform** with a full authentication system, real-time AI chat, analytics dashboard, and a LangGraph + Groq/Ollama LLM backend.

This package is the **web front-end** of the `customerSupportMCP1` mono-repo.  
It pairs a **FastAPI backend** (port 8000) with a **React + Vite frontend** (port 3000), runs on **PostgreSQL 16** and **Redis 7**, and bundles the MCP server directly into its Docker image.

For the standalone MCP server and CLI client see the sibling packages:

- [`customersupportmcp/`](../customersupportmcp) — FastMCP server (AI core)
- [`customersupportmcp-client/`](../customersupportmcp-client) — CLI chat client

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Browser  :3000                           │
│                  React 18 + Vite  (nginx)                        │
└──────────┬──────────────────────────────────────────────────────┘
           │  REST /api/v1/*   WebSocket /api/v1/ws/*
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend  :8000                          │
│                                                                  │
│  Auth endpoints  ──  JWT (HS256, 8 h) + bcrypt passwords         │
│  Chat endpoint   ──  WebSocket streaming (token-by-token)        │
│  Orders / Tickets / FAQ / Analytics / Metrics  (REST + SSE)      │
│                                                                  │
│  Middleware: CORS · JWT auth · Security headers · Rate limiting  │
│             Request-ID · Structured JSON logging                 │
└────────┬──────────────────┬──────────────────┬───────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
   PostgreSQL 16        Redis 7          MCP Server
   (users, tokens)  (rate limit,      (LangGraph agent,
                     JWT blocklist,    Groq → Ollama,
                     OAuth CSRF)       SQLite, ChromaDB)
```

---

## Features

### Authentication & User Management
| Feature | Details |
|---|---|
| **Registration** | Email + password (bcrypt, work-factor 12 with SHA-256 prehash) |
| **Login** | Email or username + password; issues 8-hour JWT |
| **JWT revocation** | Per-token JTI stored in Redis blocklist on logout |
| **Email verification** | Single-use token emailed on registration (console mode in dev) |
| **Password reset** | Time-limited email link (30 min); OWASP-safe — no user enumeration |
| **Profile management** | Update full name, username, change password |
| **OAuth2 — Google** | One-click sign-in when `GOOGLE_CLIENT_ID` is configured |
| **OAuth2 — Facebook** | One-click sign-in when `FACEBOOK_APP_ID` is configured |
| **Rate limiting** | Auth endpoints: 5 req/min; Reset endpoints: 3 req/min (slowapi) |
| **CSRF protection** | OAuth state tokens stored in Redis (5-min TTL) |

### AI Chat & Support
| Feature | Details |
|---|---|
| **Real-time AI chat** | WebSocket with word-by-word token streaming |
| **LangGraph ReAct agent** | Reasons step-by-step, calls tools, synthesises reply |
| **LLM fallback chain** | Groq (5 models) → Ollama local — never a dead end |
| **RAG search** | ChromaDB + all-MiniLM-L6-v2 embeddings for FAQ |
| **Analytics dashboard** | Live ticket/order metrics via SSE |
| **Injection guard** | Regex prompt-injection detection (OWASP LLM01) |

---

## Quick Start — Docker (Recommended)

```bash
# Clone and enter the UI package
git clone https://github.com/drdeveloper88/customerSupportMCP1.git
cd customerSupportMCP1/customersupportmcp-ui

# (Optional) copy and edit environment overrides
# The defaults work out-of-the-box for local dev:
#   GROQ_API_KEY  ← get one free at https://console.groq.com

# Build images and start all five containers
docker compose up --build

# App is ready at:
#   UI          →  http://localhost:3000
#   API docs    →  http://localhost:8000/api/docs
#   Swagger     →  http://localhost:8000/api/redoc
```

### What `docker compose up --build` starts

| Container | Port | Description |
|---|---|---|
| `customersupport-postgres` | `5432` | PostgreSQL 16 — users, tokens |
| `customersupport-redis` | `6379` | Redis 7 — rate limiting, JWT blocklist, OAuth CSRF |
| `customersupport-backend` | `8000` | FastAPI + MCP server bundled |
| `customersupport-frontend` | `3000` | React/Vite static bundle (nginx) |
| `customersupport-ollama` | `11434` | Local LLM fallback (pulls `llama3.2` on first run) |

---

## Environment Variables

All variables have safe defaults for local development. Set them in `docker-compose.yml` or a `.env` file.

### Backend (`customersupportmcp-ui/backend`)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://support:changeme@postgres:5432/support` | PostgreSQL connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `JWT_SECRET_KEY` | `change-me-in-production` | HS256 signing secret — **change in prod** |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `480` | Token TTL (8 hours) |
| `FRONTEND_URL` | `http://localhost:3000` | Used for OAuth redirects |
| `GOOGLE_CLIENT_ID` | *(empty)* | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | *(empty)* | Google OAuth client secret |
| `FACEBOOK_APP_ID` | *(empty)* | Facebook OAuth app ID |
| `FACEBOOK_APP_SECRET` | *(empty)* | Facebook OAuth app secret |
| `SMTP_HOST` | *(empty)* | SMTP server — leave blank for console-log mode |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | *(empty)* | SMTP username |
| `SMTP_PASSWORD` | *(empty)* | SMTP password |
| `EMAIL_FROM` | `noreply@example.com` | From address for outbound emails |
| `RATE_LIMIT_AUTH` | `5/minute` | Rate limit for auth endpoints |
| `RATE_LIMIT_RESET` | `3/minute` | Rate limit for password reset endpoints |
| `GROQ_API_KEY` | *(empty)* | Free key — [console.groq.com](https://console.groq.com) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama server URL |

### OAuth2 Setup (optional)

**Google**
1. Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Web application)
3. Add `http://localhost:8000/api/v1/auth/oauth/google/callback` to Authorized redirect URIs
4. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `docker-compose.yml`

**Facebook**
1. Go to [developers.facebook.com](https://developers.facebook.com) → My Apps → Add a New App
2. Add Facebook Login → Web; set the redirect URI to `http://localhost:8000/api/v1/auth/oauth/facebook/callback`
3. Set `FACEBOOK_APP_ID` and `FACEBOOK_APP_SECRET` in `docker-compose.yml`

> The UI **automatically hides** OAuth buttons for any provider that is not configured — no code change needed.

---

## REST API Reference

Base URL: `http://localhost:8000`

### Authentication (`/api/v1/auth`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | — | Register new account; returns JWT |
| `POST` | `/auth/token` | — | Login with email/username + password; returns JWT |
| `POST` | `/auth/logout` | Bearer | Revoke current JWT |
| `GET` | `/auth/me` | Bearer | Get current user profile |
| `PATCH` | `/auth/me` | Bearer | Update full name / username |
| `POST` | `/auth/change-password` | Bearer | Change password |
| `GET` | `/auth/verify-email?token=` | — | Consume email verification token |
| `POST` | `/auth/resend-verification` | Bearer | Re-send verification email |
| `POST` | `/auth/forgot-password` | — | Request password reset email |
| `POST` | `/auth/reset-password` | — | Complete password reset |
| `GET` | `/auth/providers` | — | List configured OAuth providers |
| `GET` | `/auth/oauth/{provider}` | — | Initiate OAuth2 flow (google / facebook) |
| `GET` | `/auth/oauth/{provider}/callback` | — | OAuth2 callback handler |

### Support (`/api/v1`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `GET` | `/orders/{customer_id}` | List customer orders |
| `GET` | `/orders/detail/{order_id}` | Single order detail |
| `GET` | `/faq?q=...` | Knowledge-base semantic search |
| `POST` | `/tickets` | Create support ticket |
| `GET` | `/tickets/{ticket_id}` | Retrieve ticket |
| `WS` | `/ws/chat/{customer_id}` | Real-time AI chat stream |
| `GET` | `/metrics` | Runtime metrics snapshot |
| `GET` | `/metrics/stream` | Live metrics (SSE) |
| `GET` | `/analytics` | Analytics dashboard data |
| `GET` | `/docs` | Interactive Swagger UI |

---

## Project Structure

```
customersupportmcp-ui/
├── docker-compose.yml              Five-service production stack
│
├── backend/
│   ├── Dockerfile                  Multi-stage Python 3.11 build
│   ├── main.py                     FastAPI application factory + lifespan
│   ├── requirements.txt
│   │
│   ├── api/v1/
│   │   ├── router.py               Route registration
│   │   └── endpoints/
│   │       ├── auth.py             All auth endpoints (register, login, OAuth, …)
│   │       ├── chat.py             WebSocket streaming AI chat
│   │       ├── analytics.py
│   │       ├── faq.py
│   │       ├── health.py
│   │       ├── metrics.py          SSE metrics stream
│   │       ├── orders.py
│   │       └── tickets.py
│   │
│   ├── core/
│   │   ├── auth.py                 JWT create / verify / revoke (Redis blocklist)
│   │   ├── config.py               All env-var config
│   │   ├── database.py             SQLAlchemy engine + session factory (PostgreSQL)
│   │   ├── limiter.py              Shared slowapi Limiter instance
│   │   ├── logging_config.py       Structured JSON logging
│   │   ├── middleware.py           JWT auth + security headers middleware
│   │   └── security.py            bcrypt hashing + token helpers
│   │
│   ├── models/
│   │   ├── schemas.py              Pydantic v2 request/response schemas
│   │   └── user.py                 SQLAlchemy ORM: User, PasswordResetToken,
│   │                               EmailVerificationToken
│   │
│   └── services/
│       ├── agent_service.py        LangGraph agent loader
│       ├── auth_service.py         Registration, login, OAuth, password reset
│       ├── connection_manager.py   WebSocket session tracking
│       ├── email_service.py        Async SMTP (console-log mode in dev)
│       ├── mcp_service.py          Direct MCP tool imports
│       └── support_service.py      Support data access layer
│
└── frontend/
    ├── Dockerfile                  Node 20 build → nginx 1.27 serve
    ├── nginx.conf                  Reverse proxy /api and /ws to backend
    ├── vite.config.js
    ├── package.json
    └── src/
        ├── App.jsx                 Root component — auth gate, layout, routing
        ├── App.css
        ├── api/
        │   ├── apiClient.js        Fetch wrapper with auto Bearer token injection
        │   └── supportApi.js       Support domain API calls
        ├── components/
        │   ├── Chat.jsx            WebSocket chat + SSE metrics bar
        │   ├── Dashboard.jsx       Analytics charts (Recharts)
        │   ├── EmailVerification.jsx  Email verification flow
        │   ├── ForgotPassword.jsx  Forgot password form
        │   ├── Login.jsx           Login form + OAuth buttons (auto-hidden if unconfigured)
        │   ├── Profile.jsx         Account management slide-in panel
        │   ├── Register.jsx        Registration form
        │   ├── ResetPassword.jsx   Password reset form
        │   └── Sidebar.jsx         Orders, tickets, FAQ panels
        ├── constants/              Customer IDs, suggestions, colour maps
        └── hooks/useWebSocket.js   Reconnecting WebSocket hook
```

---

## Local Development (without Docker)

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 16 running locally (or use `docker compose up postgres redis`)
- Redis 7 running locally

### Backend

```bash
cd customersupportmcp-ui/backend

pip install -r requirements.txt

# Set required env vars (PowerShell example)
$env:DATABASE_URL = "postgresql://support:changeme@localhost:5432/support"
$env:REDIS_URL    = "redis://localhost:6379/0"
$env:JWT_SECRET_KEY = "dev-secret-key"

uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd customersupportmcp-ui/frontend
npm install
npm run dev
# → http://localhost:5173  (Vite proxies /api and /ws to :8000)
```

---

## Docker Tips

```bash
# Build and start all services
docker compose up --build

# Detached mode
docker compose up -d

# Tail backend logs
docker compose logs -f backend

# Rebuild only the backend (after Python/config changes)
docker compose up --build -d backend

# Rebuild only the frontend (after React changes)
docker compose up --build -d frontend

# Stop without deleting data volumes
docker compose down

# Full reset including all data
docker compose down -v
```

---

## Security Notes

- Passwords are hashed with **bcrypt (work-factor 12)** via SHA-256 prehash (handles passwords > 72 bytes).
- JWTs carry a **JTI (unique ID)** — logout stores the JTI in Redis so tokens can be revoked before expiry.
- OAuth CSRF state tokens are stored in Redis with a 5-minute TTL.
- All auth error messages are intentionally generic to prevent user enumeration.
- Rate limiting is enforced on auth and reset endpoints via slowapi.
- `JWT_SECRET_KEY` defaults to a placeholder — **always change this in production**.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API server | [FastAPI](https://fastapi.tiangolo.com) + Uvicorn |
| Auth | JWT (python-jose HS256) + bcrypt (direct) |
| ORM | [SQLAlchemy](https://www.sqlalchemy.org) 2.x (PostgreSQL via psycopg2) |
| Cache / sessions | Redis 7 (redis-py) |
| OAuth2 | [Authlib](https://authlib.org) starlette integration |
| Email | aiosmtplib (async SMTP) |
| Rate limiting | [slowapi](https://github.com/laurentS/slowapi) |
| AI agent | [LangGraph](https://github.com/langchain-ai/langgraph) ReAct |
| LLM (cloud) | [Groq](https://console.groq.com) — free tier |
| LLM (local) | [Ollama](https://ollama.com) — llama3.2 |
| RAG | [ChromaDB](https://www.trychroma.com) + sentence-transformers |
| MCP framework | [FastMCP](https://github.com/jlowin/fastmcp) |
| Frontend | [React 18](https://react.dev) + [Vite 5](https://vitejs.dev) |
| Charts | [Recharts](https://recharts.org) |
| Frontend serve | nginx 1.27 |
| Containers | Docker Compose |

---

## License

MIT
