import { useState } from 'react'
import { fetchOrders, searchFaq, createTicket, fetchTicket } from '../api/supportApi'
import { useApi } from '../hooks/useApi'
import { ORDER_STATUS_COLORS, TICKET_PRIORITIES } from '../constants'
import { formatCurrency } from '../utils/formatHelpers'
import './Sidebar.css'

// ── Orders panel ─────────────────────────────────────────────────────────────

function OrderCard({ order }) {
  const [open, setOpen] = useState(false)
  const color = ORDER_STATUS_COLORS[order.status] || '#64748b'

  return (
    <div className="order-card" onClick={() => setOpen((o) => !o)}>
      <div className="order-header">
        <span className="order-id">{order.order_id}</span>
        <span className="order-status" style={{ color }}>● {order.status}</span>
      </div>
      <div className="order-meta">
        {order.items?.length ?? 0} item{(order.items?.length ?? 0) !== 1 ? 's' : ''} ·{' '}
        <strong>{formatCurrency(order.total)}</strong>
      </div>

      {open && (
        <div className="order-detail">
          {order.items?.map((item, i) => (
            <div key={i} className="order-item">
              <span className="item-name">{item.name}</span>
              <span className="item-qty">×{item.quantity}</span>
              <span className="item-price">{formatCurrency(item.price)}</span>
            </div>
          ))}
          {order.tracking_number && (
            <div className="tracking-badge">
              🚚 {order.tracking_number} &nbsp;·&nbsp; {order.carrier}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function OrdersPanel({ customerId }) {
  const { data: orders, loading, error } = useApi(
    () => fetchOrders(customerId),
    [customerId],
  )

  if (loading) return <div className="state-msg">Loading orders…</div>
  if (error)   return <div className="state-msg error">Failed to load orders.</div>
  if (!orders?.length) return <div className="state-msg">No orders found for {customerId}.</div>

  return (
    <div className="list-container">
      {orders.map((o) => <OrderCard key={o.order_id} order={o} />)}
    </div>
  )
}

// ── FAQ panel ────────────────────────────────────────────────────────────────

function FAQPanel() {
  const [query,   setQuery]   = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  const search = async () => {
    if (!query.trim()) return
    setLoading(true)
    setSearched(true)
    try {
      const data = await searchFaq(query)
      setResults(data)
    } catch {
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="faq-panel">
      <div className="search-row">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && search()}
          placeholder="Search knowledge base…"
        />
        <button onClick={search} className="icon-btn">🔍</button>
      </div>

      {loading && <div className="state-msg">Searching…</div>}
      {!loading && searched && !results.length && (
        <div className="state-msg">No results for "{query}".</div>
      )}

      <div className="list-container">
        {results.map((item) => (
          <div key={item.id} className="faq-card">
            <div className="faq-category">{item.category}</div>
            <div className="faq-question">{item.question}</div>
            <div className="faq-answer">{item.answer}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Tickets panel ────────────────────────────────────────────────────────────

const TICKET_STATUS_COLOR = {
  open:      '#3b82f6',
  pending:   '#f59e0b',
  resolved:  '#22c55e',
  escalated: '#ef4444',
}

function TicketsPanel({ customerId }) {
  const [subject,     setSubject]     = useState('')
  const [description, setDescription] = useState('')
  const [priority,    setPriority]    = useState('medium')
  const [newTicket,   setNewTicket]   = useState(null)
  const [creating,    setCreating]    = useState(false)
  const [createError, setCreateError] = useState(null)

  const [ticketId,    setTicketId]    = useState('')
  const [foundTicket, setFoundTicket] = useState(null)
  const [lookupError, setLookupError] = useState(false)

  const subjectTrimmed     = subject.trim()
  const descriptionTrimmed = description.trim()

  const submitTicket = async () => {
    if (!subjectTrimmed) {
      setCreateError('Subject is required.')
      return
    }
    if (subjectTrimmed.length < 3) {
      setCreateError('Subject must be at least 3 characters.')
      return
    }
    if (!descriptionTrimmed) {
      setCreateError('Description is required.')
      return
    }
    if (descriptionTrimmed.length < 5) {
      setCreateError('Description must be at least 5 characters.')
      return
    }
    setCreating(true)
    setCreateError(null)
    setNewTicket(null)
    try {
      const data = await createTicket({ customer_id: customerId, subject, description, priority })
      setNewTicket(data)
      setSubject('')
      setDescription('')
      // Auto-populate the lookup section with the newly created ticket
      setTicketId(data.ticket_id)
      setFoundTicket(data)
      setLookupError(false)
    } catch (err) {
      setCreateError(err?.message ?? 'Failed to create ticket. Please try again.')
    } finally {
      setCreating(false)
    }
  }

  const lookupTicket = async () => {
    if (!ticketId.trim()) return
    setLookupError(false)
    setFoundTicket(null)
    try {
      const data = await fetchTicket(ticketId.trim())
      if (data?.ticket_id) setFoundTicket(data)
      else setLookupError(true)
    } catch {
      setLookupError(true)
    }
  }

  return (
    <div className="tickets-panel">
      {/* ── Create ── */}
      <section className="ticket-section">
        <h3>Create Ticket</h3>
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Subject"
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe your issue…"
          rows={3}
        />
        <select value={priority} onChange={(e) => setPriority(e.target.value)}>
          {TICKET_PRIORITIES.map((p) => (
            <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
          ))}
        </select>
        <button
          onClick={submitTicket}
          disabled={creating}
          className="primary-btn"
        >
          {creating ? 'Creating…' : '+ Create Ticket'}
        </button>
        {createError && (
          <div className="ticket-error">{createError}</div>
        )}
        {newTicket?.ticket_id && (
          <div className="ticket-success">
            ✅ Created <strong>{newTicket.ticket_id}</strong>
            <span
              className="ticket-status-pill"
              style={{ color: TICKET_STATUS_COLOR[newTicket.status] ?? '#64748b' }}
            >
              {newTicket.status}
            </span>
          </div>
        )}
      </section>

      <div className="divider" />

      {/* ── Lookup ── */}
      <section className="ticket-section">
        <h3>Lookup Ticket</h3>
        <div className="lookup-row">
          <input
            value={ticketId}
            onChange={(e) => setTicketId(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && lookupTicket()}
            placeholder="TKT-XXXXXXXX"
          />
          <button onClick={lookupTicket} className="icon-btn">🔎</button>
        </div>
        {lookupError && <div className="state-msg error">Ticket not found.</div>}
        {foundTicket && (
          <div className="ticket-card">
            <div className="ticket-card-header">
              <span className="ticket-card-id">{foundTicket.ticket_id}</span>
              <span
                className="ticket-status-pill"
                style={{ color: TICKET_STATUS_COLOR[foundTicket.status] ?? '#64748b' }}
              >
                {foundTicket.status}
              </span>
            </div>
            <div className="ticket-card-subject">{foundTicket.subject}</div>
            <div className="ticket-card-desc">{foundTicket.description}</div>
            <div className="ticket-card-meta">
              Priority: <strong>{foundTicket.priority}</strong>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

// ── Sidebar shell ─────────────────────────────────────────────────────────────

const TABS = [
  { id: 'orders',  label: '📦 Orders'  },
  { id: 'faq',     label: '🔍 FAQ'     },
  { id: 'tickets', label: '🎫 Tickets' },
]

export default function Sidebar({ customerId }) {
  const [tab, setTab] = useState('orders')

  return (
    <aside className="sidebar">
      <div className="sidebar-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? 'active' : ''}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="sidebar-body">
        {tab === 'orders'  && <OrdersPanel  customerId={customerId} />}
        {tab === 'faq'     && <FAQPanel />}
        {tab === 'tickets' && <TicketsPanel customerId={customerId} />}
      </div>
    </aside>
  )
}
