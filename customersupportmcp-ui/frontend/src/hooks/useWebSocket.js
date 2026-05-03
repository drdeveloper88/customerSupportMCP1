/**
 * useWebSocket.js
 * Custom hook that manages a WebSocket connection to the chat endpoint.
 *
 * Encapsulates:
 *  - Connection lifecycle (open / close / reconnect on customer change)
 *  - Incoming message parsing and state updates
 *  - Graceful cleanup on unmount
 *  - JWT token passed as ?token= query param (browsers cannot set
 *    custom headers on WebSocket upgrade requests)
 *
 * @param {string} customerId - Active customer ID
 * @param {function} onMessage - Callback(data) invoked for each server message
 * @returns {{ connected: boolean, sendMessage: function(string): void }}
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { getStoredToken } from '../api/apiClient'

export function useWebSocket(customerId, onMessage) {
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)

  // Build the WebSocket URL respecting https / wss and attaching the JWT
  const buildUrl = useCallback(
    (id) => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const token = getStoredToken()
      const base = `${protocol}//${window.location.host}/api/v1/ws/chat/${id}`
      return token ? `${base}?token=${encodeURIComponent(token)}` : base
    },
    [],
  )

  // (Re-)connect whenever the customerId changes
  useEffect(() => {
    const ws = new WebSocket(buildUrl(customerId))
    wsRef.current = ws

    ws.onopen  = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
      } catch {
        // Malformed message — ignore
      }
    }

    return () => {
      ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null
      ws.close()
    }
  }, [customerId, buildUrl, onMessage])

  /** Send a plain-text message to the server. */
  const sendMessage = useCallback((text) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ message: text }))
  }, [])

  return { connected, sendMessage }
}
