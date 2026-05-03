# ── CustomerSupportMCP — React Frontend ──────────────────────────────────────
# Multi-stage build:
#   Stage 1 (builder) – Node 20 installs deps and builds the Vite bundle.
#   Stage 2 (runner)  – nginx:alpine serves the static bundle.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (cached unless package.json changes)
COPY customersupportmcp-ui/frontend/package.json customersupportmcp-ui/frontend/package-lock.json* ./
RUN npm ci --frozen-lockfile

# Copy source and build
COPY customersupportmcp-ui/frontend/ .

# VITE_API_URL is injected at build time so the bundle knows the backend URL.
# Pass it via docker-compose build args or --build-arg.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# ── Stage 2: Serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runner

# Remove default nginx static content
RUN rm -rf /usr/share/nginx/html/*

# Copy the Vite build output
COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx config: all routes fall back to index.html for React Router
COPY customersupportmcp-ui/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
