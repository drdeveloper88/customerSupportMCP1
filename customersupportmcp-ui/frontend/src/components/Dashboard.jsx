import { useState, useEffect, useCallback } from 'react'
import {
  AreaChart, Area,
  BarChart, Bar,
  PieChart, Pie, Cell,
  ResponsiveContainer,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import { fetchAnalytics } from '../api/supportApi'
import './Dashboard.css'

// ── Colour maps ───────────────────────────────────────────────────────────────

const PRIORITY_COLORS = {
  critical: '#dc2626',
  high:     '#f59e0b',
  medium:   '#3b82f6',
  low:      '#22c55e',
}

const STATUS_COLORS = {
  open:      '#3b82f6',
  pending:   '#f59e0b',
  resolved:  '#22c55e',
  escalated: '#ef4444',
  closed:    '#6366f1',
}

const ORDER_STATUS_COLORS = {
  delivered:  '#22c55e',
  shipped:    '#3b82f6',
  processing: '#f59e0b',
  cancelled:  '#ef4444',
}

// ── Sub-components ────────────────────────────────────────────────────────────

function KpiCard({ label, value, icon, color, subtitle }) {
  return (
    <div className="kpi-card" style={{ '--kpi-color': color }}>
      <div className="kpi-icon">{icon}</div>
      <div className="kpi-body">
        <div className="kpi-value">{value ?? '—'}</div>
        <div className="kpi-label">{label}</div>
        {subtitle && <div className="kpi-subtitle">{subtitle}</div>}
      </div>
    </div>
  )
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      {label && <p className="tooltip-label">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color || p.fill || '#fff' }}>
          {p.name}: <strong>{p.value}</strong>
        </p>
      ))}
    </div>
  )
}

const RADIAN = Math.PI / 180
function renderPieLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }) {
  if (percent < 0.07) return null
  const r = innerRadius + (outerRadius - innerRadius) * 0.5
  const x = cx + r * Math.cos(-midAngle * RADIAN)
  const y = cy + r * Math.sin(-midAngle * RADIAN)
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central"
          fontSize={11} fontWeight="700">
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  )
}

function PriorityDonut({ data }) {
  const chartData = Object.entries(data || {}).map(([name, value]) => ({ name, value }))
  if (!chartData.length) return <div className="chart-empty">No data</div>

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={55}
          outerRadius={90}
          paddingAngle={3}
          dataKey="value"
          labelLine={false}
          label={renderPieLabel}
        >
          {chartData.map((entry) => (
            <Cell key={entry.name} fill={PRIORITY_COLORS[entry.name] || '#94a3b8'} />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend
          formatter={(v) => v.charAt(0).toUpperCase() + v.slice(1)}
          iconType="circle"
          iconSize={9}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [data,        setData]        = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [error,       setError]       = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await fetchAnalytics()
      setData(d)
      setLastUpdated(new Date())
    } catch (e) {
      setError(e.message || 'Failed to load analytics')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="dashboard-state">
        <div className="dash-spinner" />
        <p>Loading analytics…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="dashboard-state dashboard-error">
        <span className="error-icon">⚠️</span>
        <p>{error}</p>
        <button className="dash-refresh" onClick={load}>Retry</button>
      </div>
    )
  }

  const { tickets = {}, orders = {}, refunds = {}, server = {} } = data || {}

  const openCount      = tickets.by_status?.open       || 0
  const resolvedCount  = tickets.by_status?.resolved   || 0
  const escalatedCount = tickets.by_status?.escalated  || 0
  const highCritical   = (tickets.by_priority?.high || 0) + (tickets.by_priority?.critical || 0)

  const statusChartData = Object.entries(tickets.by_status || {}).map(([name, value]) => ({
    name:  name.charAt(0).toUpperCase() + name.slice(1),
    value,
    fill:  STATUS_COLORS[name] || '#94a3b8',
  }))

  const orderChartData = Object.entries(orders.by_status || {}).map(([name, value]) => ({
    name:  name.charAt(0).toUpperCase() + name.slice(1),
    value,
    fill:  ORDER_STATUS_COLORS[name] || '#94a3b8',
  }))

  const customerChartData = Object.entries(tickets.by_customer || {})
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }))

  const trendData = (tickets.trend_7d || []).map((d) => ({
    date:    d.date.slice(5),   // show MM-DD
    Tickets: d.count,
  }))

  const uptimeSec = server.uptime_seconds
  const uptimeStr = uptimeSec != null
    ? `${Math.floor(uptimeSec / 60)}m ${Math.round(uptimeSec % 60)}s`
    : '—'

  return (
    <div className="dashboard">

      {/* ── Toolbar ─────────────────────────────────────────────── */}
      <div className="dash-toolbar">
        <div className="dash-toolbar-left">
          <h2>📊 Analytics Dashboard</h2>
          <span className="dash-subtitle">Real-time customer support insights</span>
        </div>
        <div className="dash-toolbar-right">
          {lastUpdated && (
            <span className="dash-updated">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button className="dash-refresh" onClick={load} disabled={loading}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* ── KPI cards ─────────────────────────────────────────── */}
      <div className="kpi-grid">
        <KpiCard label="Total Tickets"    value={tickets.total ?? 0}  icon="🎫" color="#6366f1" />
        <KpiCard label="Open"             value={openCount}            icon="📂" color="#f59e0b" subtitle="Needs attention" />
        <KpiCard label="Resolved"         value={resolvedCount}        icon="✅" color="#22c55e" />
        <KpiCard label="High / Critical"  value={highCritical}         icon="🔴" color="#ef4444" subtitle="Urgent priority" />
        <KpiCard label="Escalated"        value={escalatedCount}       icon="🚨" color="#dc2626" />
        <KpiCard label="Total Orders"     value={orders.total ?? 0}    icon="📦" color="#3b82f6" />
        <KpiCard label="Total Refunds"    value={refunds.total ?? 0}   icon="💳" color="#8b5cf6" />
        <KpiCard label="Active Sessions"  value={server.active_connections ?? 0} icon="🟢" color="#10b981" subtitle="Live now" />
      </div>

      {/* ── Charts row 1: Priority Donut · Status Bar · Trend ─── */}
      <div className="charts-row">
        <div className="chart-card">
          <div className="chart-title">Priority Distribution</div>
          <PriorityDonut data={tickets.by_priority} />
        </div>

        <div className="chart-card">
          <div className="chart-title">Ticket Status</div>
          {statusChartData.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={statusChartData} barSize={36}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]} isAnimationActive>
                  {statusChartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <div className="chart-empty">No data</div>}
        </div>

        <div className="chart-card">
          <div className="chart-title">7-Day Ticket Trend</div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={trendData}>
              <defs>
                <linearGradient id="ticketGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0}    />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="Tickets"
                stroke="#6366f1"
                strokeWidth={2.5}
                fill="url(#ticketGrad)"
                dot={{ r: 4, fill: '#6366f1', strokeWidth: 0 }}
                activeDot={{ r: 6 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Charts row 2: Orders · Customer Breakdown · Server ── */}
      <div className="charts-row">
        <div className="chart-card">
          <div className="chart-title">Order Status Breakdown</div>
          {orderChartData.length ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={orderChartData} layout="vertical" barSize={22}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={86} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                  {orderChartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <div className="chart-empty">No data</div>}
        </div>

        <div className="chart-card">
          <div className="chart-title">Tickets by Customer</div>
          {customerChartData.length ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={customerChartData} barSize={36}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" fill="#6366f1" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <div className="chart-empty">No data</div>}
        </div>

        <div className="chart-card">
          <div className="chart-title">Server Performance</div>
          <div className="stat-list">
            <div className="stat-row">
              <span className="stat-label">Active Connections</span>
              <span className="stat-value stat-blue">{server.active_connections ?? '—'}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">Active Customers</span>
              <span className="stat-value">{server.active_customers?.length ?? 0}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">Messages Served</span>
              <span className="stat-value stat-purple">{server.total_messages ?? '—'}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">Avg Response Time</span>
              <span className="stat-value stat-green">
                {server.avg_response_ms ? `${Math.round(server.avg_response_ms)} ms` : '—'}
              </span>
            </div>
            <div className="stat-row">
              <span className="stat-label">Uptime</span>
              <span className="stat-value">{uptimeStr}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">Total Revenue</span>
              <span className="stat-value stat-green">
                ${(orders.total_revenue || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Recent tickets table ───────────────────────────────── */}
      <div className="table-card">
        <div className="chart-title">Recent Tickets</div>
        <div className="table-wrapper">
          <table className="tickets-table">
            <thead>
              <tr>
                <th>Ticket ID</th>
                <th>Customer</th>
                <th>Subject</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {(tickets.recent || []).map((t) => (
                <tr key={t.ticket_id}>
                  <td><span className="ticket-id-badge">{t.ticket_id}</span></td>
                  <td>{t.customer_id}</td>
                  <td className="subject-cell" title={t.subject}>{t.subject}</td>
                  <td>
                    <span className="priority-badge" data-priority={t.priority}>
                      {t.priority?.toUpperCase()}
                    </span>
                  </td>
                  <td>
                    <span className="status-badge" data-status={t.status}>
                      {t.status?.toUpperCase()}
                    </span>
                  </td>
                  <td className="date-cell">
                    {t.created_at ? new Date(t.created_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
              {!(tickets.recent?.length) && (
                <tr>
                  <td colSpan={6} className="no-data">No tickets found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  )
}
