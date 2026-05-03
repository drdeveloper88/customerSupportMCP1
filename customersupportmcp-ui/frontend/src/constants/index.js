/**
 * constants/index.js
 * Application-wide constants.
 *
 * Single source of truth — import from here rather than scattering
 * magic strings throughout components.
 */

// ── Customer identifiers available in the demo UI ─────────────────────────────

export const CUSTOMERS = ['CUST-001', 'CUST-002', 'CUST-003']

// ── Chat quick-suggestion pills ───────────────────────────────────────────────

export const CHAT_SUGGESTIONS = [
  "What's the status of my orders?",
  'What is your return policy?',
  "My package hasn't arrived yet",
  'I need help with a refund',
]

// ── Order status → badge colour ───────────────────────────────────────────────

export const ORDER_STATUS_COLORS = {
  delivered:  '#22c55e',
  shipped:    '#3b82f6',
  processing: '#f59e0b',
  cancelled:  '#ef4444',
}

// ── Ticket priority options ───────────────────────────────────────────────────

export const TICKET_PRIORITIES = ['low', 'medium', 'high', 'critical']

// ── WebSocket reconnect settings ─────────────────────────────────────────────

export const WS_STREAM_DELAY_MS = 25   // ms between streamed words

// ── API base URL (kept here for documentation — Vite proxy handles routing) ───

export const API_BASE_URL = '/api'
