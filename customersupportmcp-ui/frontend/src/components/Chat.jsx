import { useState, useCallback, useRef, useEffect } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import { CHAT_SUGGESTIONS } from '../constants'
import './Chat.css'

// ── Live metrics via SSE ──────────────────────────────────────────────────────

function useMetrics() {
  const [metrics, setMetrics] = useState(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'https:' : 'http:'
    const es = new EventSource(`${proto}//${window.location.host}/api/v1/metrics/stream`)
    es.onmessage = (e) => {
      try { setMetrics(JSON.parse(e.data)) } catch { /* ignore */ }
    }
    es.onerror = () => es.close()
    return () => es.close()
  }, [])

  return metrics
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBar({ connected, metrics }) {
  return (
    <div className="chat-statusbar">
      <span className={`status-dot ${connected ? 'on' : 'off'}`} />
      <span>{connected ? 'Connected · real-time streaming' : 'Connecting…'}</span>
      {metrics && (
        <div className="metrics-badge">
          <span className="metric-item">
            <span>Sessions</span>
            <span className="metric-value">{metrics.active_connections}</span>
          </span>
          <span className="metric-item">
            <span>Messages</span>
            <span className="metric-value">{metrics.total_messages}</span>
          </span>
          <span className="metric-item">
            <span>Avg latency</span>
            <span className="metric-value">
              {metrics.avg_response_ms > 0
                ? `${Math.round(metrics.avg_response_ms)}ms`
                : '–'}
            </span>
          </span>
        </div>
      )}
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="message ai">
      <div className="avatar">🤖</div>
      <div className="bubble typing-bubble">
        <span /><span /><span />
      </div>
    </div>
  )
}

/** Inline tool-call activity chips shown while the agent is working */
function ToolActivity({ tools }) {
  if (!tools.length) return null
  return (
    <div className="message ai tool-activity-row">
      <div className="avatar">🤖</div>
      <div className="tool-chips">
        {tools.map((t) => (
          <span key={t.tool} className={`tool-chip ${t.done ? 'done' : 'active'}`}>
            {t.label}
            {t.done && <span className="tool-check">✓</span>}
          </span>
        ))}
      </div>
    </div>
  )
}

function Message({ msg }) {
  return (
    <div className={`message ${msg.role}${msg.error ? ' error-msg' : ''}`}>
      {msg.role === 'ai' && <div className="avatar">🤖</div>}
      <div className="bubble">
        {msg.content}
        {msg.streaming && <span className="cursor">▌</span>}
      </div>
      {msg.role === 'user' && <div className="avatar user-avatar">👤</div>}
    </div>
  )
}

// ── Main Chat component ───────────────────────────────────────────────────────

const STREAM_ID = '__streaming__'

export default function Chat({ customerId }) {
  const [messages,   setMessages]   = useState([])
  const [input,      setInput]      = useState('')
  const [isTyping,   setIsTyping]   = useState(false)
  const [toolEvents, setToolEvents] = useState([])   // [{tool, label, done}]
  const metrics   = useMetrics()
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  // Auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping, toolEvents])

  // Reset when customer changes
  useEffect(() => {
    setMessages([{
      id:      'welcome',
      role:    'ai',
      content: `Hi! I'm your AI support agent for ${customerId}. How can I help you today?`,
    }])
    setIsTyping(false)
    setInput('')
    setToolEvents([])
  }, [customerId])

  // ── WebSocket message handler ───────────────────────────────────────────────
  const handleWsMessage = useCallback((data) => {
    switch (data.type) {

      case 'connected':
        // Channel is ready — nothing visual needed
        break

      case 'typing':
        setIsTyping(data.status)
        if (!data.status) setToolEvents([])  // clear chips when done
        break

      case 'tool_start':
        setToolEvents((prev) => {
          if (prev.find((t) => t.tool === data.tool)) return prev
          return [...prev, { tool: data.tool, label: data.label, done: false }]
        })
        break

      case 'tool_end':
        setToolEvents((prev) =>
          prev.map((t) => t.tool === data.tool ? { ...t, done: true } : t)
        )
        break

      case 'token':
        setMessages((prev) => {
          const exists = prev.find((m) => m.id === STREAM_ID)
          const chunk  = data.content ?? ''
          if (exists) {
            return prev.map((m) =>
              m.id === STREAM_ID
                ? { ...m, content: m.content + chunk, streaming: true }
                : m
            )
          }
          return [...prev, { id: STREAM_ID, role: 'ai', content: chunk, streaming: true }]
        })
        break

      case 'done': {
        const finalText = data.content ?? ''
        setMessages((prev) => {
          const exists = prev.find((m) => m.id === STREAM_ID)
          if (exists) {
            return prev.map((m) =>
              m.id === STREAM_ID
                ? { ...m, id: `ai-${Date.now()}`, content: finalText, streaming: false }
                : m
            )
          }
          if (finalText) {
            return [...prev, { id: `ai-${Date.now()}`, role: 'ai', content: finalText }]
          }
          return prev
        })
        setToolEvents([])
        break
      }

      case 'error':
        setIsTyping(false)
        setToolEvents([])
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== STREAM_ID),
          { id: `err-${Date.now()}`, role: 'ai', content: `⚠️ ${data.message}`, error: true },
        ])
        break

      default:
        break
    }
  }, [])

  const { connected, sendMessage: wsSend } = useWebSocket(customerId, handleWsMessage)

  // ── Send ──────────────────────────────────────────────────────────────────
  const sendMessage = useCallback(
    (text) => {
      const msg = (text ?? input).trim()
      if (!msg || !connected) return
      setMessages((prev) => [...prev, { id: `user-${Date.now()}`, role: 'user', content: msg }])
      setInput('')
      setToolEvents([])
      wsSend(msg)
      inputRef.current?.focus()
    },
    [input, connected, wsSend],
  )

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
    },
    [sendMessage],
  )

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="chat">
      <StatusBar connected={connected} metrics={metrics} />

      {/* Message list */}
      <div className="messages">
        {messages.map((msg) => <Message key={msg.id} msg={msg} />)}
        {toolEvents.length > 0 && <ToolActivity tools={toolEvents} />}
        {isTyping && !toolEvents.length && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Quick suggestion pills */}
      <div className="suggestions">
        {CHAT_SUGGESTIONS.map((s) => (
          <button key={s} className="suggestion-pill" onClick={() => sendMessage(s)}>
            {s}
          </button>
        ))}
      </div>

      {/* Input area */}
      <div className="input-area">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          rows={2}
          disabled={!connected}
        />
        <button
          className="send-btn"
          onClick={() => sendMessage()}
          disabled={!input.trim() || !connected}
          title="Send"
        >
          ➤
        </button>
      </div>
    </div>
  )
}
