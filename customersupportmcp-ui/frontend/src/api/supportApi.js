/**
 * supportApi.js
 * Domain-specific API calls for the Customer Support MCP application.
 * All functions return Promises; components should use the useSupportApi hook
 * rather than calling these directly.
 */

import { apiClient } from './apiClient'

// ── Orders ────────────────────────────────────────────────────────────────────

/**
 * Fetch all orders for a customer.
 * @param {string} customerId
 * @returns {Promise<Array>}
 */
export async function fetchOrders(customerId) {
  const data = await apiClient.get(`/orders/${encodeURIComponent(customerId)}`)
  return Array.isArray(data) ? data : []
}

/**
 * Fetch a single order by order ID.
 * @param {string} orderId
 * @returns {Promise<object>}
 */
export async function fetchOrder(orderId) {
  return apiClient.get(`/orders/detail/${encodeURIComponent(orderId)}`)
}

// ── FAQ / Knowledge base ──────────────────────────────────────────────────────

/**
 * Search the knowledge base.
 * @param {string} query
 * @returns {Promise<Array>}
 */
export async function searchFaq(query) {
  if (!query.trim()) return []
  const data = await apiClient.get(`/faq?q=${encodeURIComponent(query)}`)
  return Array.isArray(data) ? data : []
}

// ── Support tickets ───────────────────────────────────────────────────────────

/**
 * Create a new support ticket.
 * @param {{ customer_id: string, subject: string, description: string, priority?: string }} payload
 * @returns {Promise<object>}
 */
export async function createTicket(payload) {
  return apiClient.post('/tickets', payload)
}

/**
 * Fetch a support ticket by its ID.
 * @param {string} ticketId
 * @returns {Promise<object>}
 */
export async function fetchTicket(ticketId) {
  return apiClient.get(`/tickets/${encodeURIComponent(ticketId)}`)
}

// ── Server tools ──────────────────────────────────────────────────────────────

/**
 * List all tools registered on the MCP server.
 * @returns {Promise<Array>}
 */
export async function fetchTools() {
  const data = await apiClient.get('/tools')
  return data?.tools ?? []
}

// ── Analytics ─────────────────────────────────────────────────────────────────

/**
 * Fetch aggregated analytics for the dashboard.
 * @returns {Promise<object>}
 */
export async function fetchAnalytics() {
  return apiClient.get('/analytics')
}
