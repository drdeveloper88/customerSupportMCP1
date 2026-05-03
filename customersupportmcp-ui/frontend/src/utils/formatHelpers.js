/**
 * utils/formatHelpers.js
 * Pure formatting utility functions — no side effects, no imports.
 */

/**
 * Format a numeric USD amount as a currency string.
 * @param {number} amount
 * @param {string} [currency='USD']
 * @returns {string}  e.g. "$19.99"
 */
export function formatCurrency(amount, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount ?? 0)
}

/**
 * Format an ISO date string to a localised short date.
 * @param {string} isoString
 * @returns {string}  e.g. "Jan 15, 2025"
 */
export function formatDate(isoString) {
  if (!isoString) return '—'
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  }).format(new Date(isoString))
}

/**
 * Capitalise the first letter of a string.
 * @param {string} str
 * @returns {string}
 */
export function capitalise(str) {
  if (!str) return ''
  return str.charAt(0).toUpperCase() + str.slice(1)
}

/**
 * Truncate a string to a maximum length and append an ellipsis.
 * @param {string} str
 * @param {number} [maxLen=100]
 * @returns {string}
 */
export function truncate(str, maxLen = 100) {
  if (!str || str.length <= maxLen) return str
  return `${str.slice(0, maxLen)}…`
}
