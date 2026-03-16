import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plus, FileText, Clock, FileCheck,
  CheckCircle2, AlertTriangle, Gauge,
  ArrowRight, RefreshCw, Search, Filter, Layers,
  TrendingUp, TrendingDown, Minus, ChevronRight,
  BarChart3, Cpu, GitMerge,
} from 'lucide-react';
import api from '../api/client';
import { relativeTime, formatDate } from '../utils/formatters';

/* ── Stage configuration ────────────────── */
const STAGES = [
  { id: 'NEW',                    label: 'Inbox',               shortLabel: 'Inbox',    color: '#64748b', bg: 'rgba(100,116,139,0.12)' },
  { id: 'PARSING',                label: 'AI Extraction',       shortLabel: 'Extract',  color: '#f59e0b', bg: 'rgba(245,158,11,0.12)'  },
  { id: 'BALLOONING',             label: 'AI Ballooning',       shortLabel: 'Balloon',  color: '#3b82f6', bg: 'rgba(59,130,246,0.12)'  },
  { id: 'BALLOONING_REVIEW',      label: 'Drawing Review',      shortLabel: 'D.Review', color: '#8b5cf6', bg: 'rgba(139,92,246,0.12)'  },
  { id: 'FEASIBILITY_GENERATION', label: 'Feasibility Engine',  shortLabel: 'Feasib.',  color: '#6366f1', bg: 'rgba(99,102,241,0.12)'  },
  { id: 'FEASIBILITY_REVIEW',     label: 'F. Review',           shortLabel: 'F.Review', color: '#a855f7', bg: 'rgba(168,85,247,0.12)'  },
  { id: 'COSTING',                label: 'Costing',             shortLabel: 'Costing',  color: '#10b981', bg: 'rgba(16,185,129,0.12)'  },
  { id: 'QUOTE_SENT',             label: 'Quote Sent',          shortLabel: 'Quoted',   color: '#06b6d4', bg: 'rgba(6,182,212,0.12)'   },
];

const stageMap = Object.fromEntries(STAGES.map(s => [s.id, s]));

/* ── KPI Card ──────────────────────────────────────────────── */
function KpiCard({ label, value, sub, icon, color, trend, trendLabel }) {
  const trendIcon = trend === 'up' ? <TrendingUp size={12} /> : trend === 'down' ? <TrendingDown size={12} /> : <Minus size={12} />;
  const trendClass = `kpi-trend ${trend === 'up' ? 'up' : trend === 'down' ? 'down' : 'neutral'}`;
  return (
    <div className={`kpi-card kpi-${color}`}>
      <div className="kpi-top">
        <div>
          <div className="kpi-label">{label}</div>
          <div className="kpi-value">{value}</div>
        </div>
        <div className="kpi-icon-wrap">{icon}</div>
      </div>
      <div className="kpi-bottom">
        <span className="kpi-sub">{sub}</span>
        {trendLabel && (
          <span className={trendClass}>
            {trendIcon} {trendLabel}
          </span>
        )}
      </div>
    </div>
  );
}

/* ── Stage Pill (pipeline distribution bar) ─────────────────── */
function StagePill({ stage, count }) {
  return (
    <div className="stage-pill" style={{ '--stage-color': stage.color, '--stage-bg': stage.bg }}>
      <span className="stage-pill-dot" />
      <span className="stage-pill-label">{stage.shortLabel}</span>
      <span className="stage-pill-count">{count}</span>
    </div>
  );
}

/* ── RFQ Kanban Card ─────────────────────── */
function RFQKanbanCard({ rfq, stage }) {
  const navigate = useNavigate();
  const lastRun = rfq.last_run;

  return (
    <div
      className="kanban-card"
      onClick={() => navigate(`/rfq/${rfq.id}`)}
      style={{ '--card-accent': stage.color }}
    >
      <div className="kanban-card-accent" />
      <div className="kanban-card-body">
        <div className="kanban-card-header">
          <span className="kanban-card-title">{rfq.part_name}</span>
          <span className="kanban-card-id">#{rfq.id}</span>
        </div>
        <div className="kanban-card-customer">{rfq.customer_name}</div>
        {rfq.part_no && (
          <div className="kanban-card-partno">PN: {rfq.part_no}</div>
        )}
        <div className="kanban-card-footer">
          <span className="kanban-card-date">
            <Clock size={10} /> {relativeTime(rfq.received_at)}
          </span>
          {lastRun && (
            <span
              className={`kanban-run-dot ${lastRun.status === 'SUCCESS' ? 'success' : 'fail'}`}
              title={`Last run: ${lastRun.status}${lastRun.failure_stage ? ` at ${lastRun.failure_stage}` : ''}`}
            />
          )}
          <ChevronRight size={12} className="kanban-card-arrow" />
        </div>
      </div>
    </div>
  );
}

/* ── Kanban Column ───────────────────────── */
function KanbanColumn({ stage, rfqs }) {
  return (
    <div className="kanban-col">
      <div className="kanban-col-header" style={{ '--col-color': stage.color, '--col-bg': stage.bg }}>
        <div className="kanban-col-title">
          <span className="kanban-col-dot" />
          <span>{stage.label}</span>
        </div>
        <span className="kanban-col-count">{rfqs.length}</span>
      </div>
      <div className="kanban-col-body">
        {rfqs.length === 0 ? (
          <div className="kanban-col-empty">No RFQs</div>
        ) : (
          rfqs.map(rfq => (
            <RFQKanbanCard key={rfq.id} rfq={rfq} stage={stage} />
          ))
        )}
      </div>
    </div>
  );
}

/* ── Recent RFQ Table Row ────────────────── */
function RecentRfqRow({ rfq }) {
  const navigate = useNavigate();
  const stage = stageMap[rfq.status] || STAGES[0];
  const lastRun = rfq.last_run;

  return (
    <tr className="recent-row" onClick={() => navigate(`/rfq/${rfq.id}`)}>
      <td>
        <div className="recent-part">{rfq.part_name}</div>
        <div className="recent-customer">{rfq.customer_name}</div>
      </td>
      <td>
        <span className="stage-badge" style={{ color: stage.color, background: stage.bg, border: `1px solid ${stage.color}30` }}>
          <span className="stage-badge-dot" style={{ background: stage.color }} />
          {stage.shortLabel}
        </span>
      </td>
      <td className="recent-date">{formatDate(rfq.received_at)}</td>
      <td>
        {lastRun ? (
          <div className="recent-run-info">
            {lastRun.status === 'SUCCESS'
              ? <span className="run-success"><CheckCircle2 size={12} /> Success</span>
              : <span className="run-fail"><AlertTriangle size={12} /> Failed {lastRun.failure_stage ? `(${lastRun.failure_stage})` : ''}</span>
            }
            {lastRun.total_ms != null && <span className="run-dur">{Math.round(lastRun.total_ms / 1000)}s</span>}
          </div>
        ) : (
          <span className="text-muted" style={{ fontSize: '0.75rem' }}>No runs</span>
        )}
      </td>
      <td>
        <button className="recent-action-btn">
          View <ArrowRight size={12} />
        </button>
      </td>
    </tr>
  );
}

/* ── Main Dashboard ──────────────────────── */
export default function Dashboard() {
  const navigate = useNavigate();
  const [rfqs, setRfqs] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeStageFilter, setActiveStageFilter] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchAll = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setIsRefreshing(true);
    try {
      const [rfqRes, metricsRes] = await Promise.all([
        api.get('/admin/rfqs', { params: { page: 1, page_size: 200 } }),
        api.get('/admin/metrics', { params: { days: 7 } }),
      ]);
      setRfqs(rfqRes.data.items || []);
      setMetrics(metricsRes.data);
      setLastRefresh(new Date());
    } catch (err) {
      console.error('Dashboard fetch error', err);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchAll(true);
    const interval = setInterval(() => fetchAll(false), 5000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  /* ── Derived state (memoised to avoid redundant filter passes) ── */

  // Single-pass bucket: used for both the distribution bar and Kanban columns
  const rfqsByStage = useMemo(() =>
    rfqs.reduce((acc, rfq) => {
      (acc[rfq.status] ??= []).push(rfq);
      return acc;
    }, {}),
    [rfqs]
  );

  const activeRfqs = useMemo(() =>
    rfqs.filter(r => r.status !== 'QUOTE_SENT'),
    [rfqs]
  );

  const inReviewCount = useMemo(() =>
    (rfqsByStage['BALLOONING_REVIEW']?.length ?? 0) +
    (rfqsByStage['FEASIBILITY_REVIEW']?.length ?? 0),
    [rfqsByStage]
  );

  const filteredRfqs = useMemo(() => {
    if (!activeStageFilter && !searchQuery) return rfqs;
    return rfqs.filter(rfq => {
      if (activeStageFilter && rfq.status !== activeStageFilter) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          rfq.part_name?.toLowerCase().includes(q) ||
          rfq.customer_name?.toLowerCase().includes(q) ||
          rfq.part_no?.toLowerCase().includes(q) ||
          String(rfq.id).includes(q)
        );
      }
      return true;
    });
  }, [rfqs, activeStageFilter, searchQuery]);

  const successRatePct = metrics?.success_rate != null ? Math.round(metrics.success_rate * 100) : null;

  if (loading) {
    return (
      <div className="loading-container" style={{ minHeight: '60vh' }}>
        <div className="enterprise-spinner">
          <div className="enterprise-spinner-ring" />
          <Cpu size={18} className="enterprise-spinner-icon" />
        </div>
        <div className="text-secondary text-sm" style={{ marginTop: 16 }}>Loading RFQ dashboard…</div>
      </div>
    );
  }

  return (
    <div className="dashboard-root">

      {/* ── Page Header ── */}
      <div className="dashboard-header">
        <div className="dashboard-header-left">
          <div className="dashboard-title-row">
            <h1 className="dashboard-title">RFQ Operations</h1>
            <div className="live-indicator">
              <span className="live-dot" />
              <span>Live</span>
            </div>
          </div>
          <p className="dashboard-subtitle">
            AI extraction · Auto-ballooning · Feasibility analysis · {rfqs.length} total RFQs
          </p>
        </div>
        <div className="dashboard-header-right">
          <div className="dashboard-header-meta">
            <span className="refresh-time">
              Updated {relativeTime(lastRefresh)}
              {isRefreshing && <RefreshCw size={11} className="spin-icon" />}
            </span>
          </div>
          <button className="btn btn-primary" onClick={() => navigate('/new')}>
            <Plus size={16} /> New RFQ
          </button>
        </div>
      </div>

      {/* ── KPI Cards ── */}
      <div className="kpi-grid">
        <KpiCard
          label="RFQs Processed"
          value={metrics?.rfqs_processed ?? '—'}
          sub={`Last ${metrics?.window_days ?? 7} days · ${metrics?.total_runs ?? 0} pipeline runs`}
          icon={<BarChart3 size={20} />}
          color="blue"
          trend={metrics?.rfqs_processed > 0 ? 'up' : 'neutral'}
          trendLabel={metrics?.rfqs_processed > 0 ? 'Active' : null}
        />
        <KpiCard
          label="Success Rate"
          value={successRatePct != null ? `${successRatePct}%` : '—'}
          sub={`${metrics?.successful_runs ?? 0} of ${metrics?.total_runs ?? 0} runs succeeded`}
          icon={<CheckCircle2 size={20} />}
          color={successRatePct == null ? 'blue' : successRatePct >= 80 ? 'green' : successRatePct >= 50 ? 'amber' : 'red'}
          trend={successRatePct == null ? 'neutral' : successRatePct >= 80 ? 'up' : successRatePct >= 50 ? 'neutral' : 'down'}
          trendLabel={successRatePct != null ? `${successRatePct}% success` : null}
        />
        <KpiCard
          label="Avg Pipeline Duration"
          value={metrics?.avg_duration_ms != null ? `${Math.round(metrics.avg_duration_ms / 1000)}s` : '—'}
          sub={`p95: ${metrics?.p95_duration_ms != null ? `${Math.round(metrics.p95_duration_ms / 1000)}s` : '—'}`}
          icon={<Gauge size={20} />}
          color="amber"
          trend="neutral"
        />
        <KpiCard
          label="Pending Reviews"
          value={inReviewCount}
          sub={`${activeRfqs.length} RFQs actively in pipeline`}
          icon={<FileCheck size={20} />}
          color={inReviewCount > 0 ? 'purple' : 'green'}
          trend={inReviewCount > 0 ? 'up' : 'neutral'}
          trendLabel={inReviewCount > 0 ? `${inReviewCount} awaiting` : 'All clear'}
        />
      </div>

      {/* ── Stage Distribution Bar ── */}
      <div className="stage-distribution-bar">
        <div className="stage-distribution-label">
          <Layers size={13} />
          <span>Pipeline distribution</span>
        </div>
        <div className="stage-pills">
          {STAGES.map(stage => {
            const count = rfqsByStage[stage.id]?.length ?? 0;
            return (
              <button
                key={stage.id}
                onClick={() => setActiveStageFilter(activeStageFilter === stage.id ? null : stage.id)}
                className={`stage-pill-btn ${activeStageFilter === stage.id ? 'active' : ''}`}
              >
                <StagePill stage={stage} count={count} />
              </button>
            );
          })}
        </div>
        <div className="stage-distribution-total">
          <span>{rfqs.length} total</span>
        </div>
      </div>

      {/* ── Kanban Board ── */}
      <div className="kanban-section">
        <div className="section-header">
          <div className="section-title">
            <GitMerge size={15} />
            <span>Live Pipeline</span>
            <span className="section-badge">{activeRfqs.length} active</span>
          </div>
          <span className="section-sub">Auto-refreshes every 5s</span>
        </div>

        <div className="kanban-board-outer">
          <div className="kanban-board">
            {STAGES.map(stage => (
              <KanbanColumn
                key={stage.id}
                stage={stage}
                rfqs={rfqsByStage[stage.id] ?? []}
              />
            ))}
          </div>
        </div>
      </div>

      {/* ── All RFQs Table ── */}
      <div className="rfq-table-section">
        <div className="section-header">
          <div className="section-title">
            <FileText size={15} />
            <span>All RFQs</span>
            <span className="section-badge">{filteredRfqs.length}</span>
          </div>
          <div className="section-actions">
            <div className="search-box">
              <Search size={13} className="search-icon" />
              <input
                type="text"
                className="search-input"
                placeholder="Search part, customer, ID…"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
            </div>
            {activeStageFilter && (
              <button
                className="filter-clear-btn"
                onClick={() => setActiveStageFilter(null)}
              >
                <Filter size={12} /> {stageMap[activeStageFilter]?.label}
                <span className="filter-clear-x">×</span>
              </button>
            )}
          </div>
        </div>

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Part / Customer</th>
                <th>Stage</th>
                <th>Received</th>
                <th>Last Run</th>
                <th style={{ width: 80 }}></th>
              </tr>
            </thead>
            <tbody>
              {filteredRfqs.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <div className="empty-state" style={{ padding: '32px 0' }}>
                      <div className="empty-state-icon">
                        <FileText size={20} className="text-muted" />
                      </div>
                      <div className="text-sm text-muted">
                        {searchQuery || activeStageFilter ? 'No RFQs match your filter.' : 'No RFQs yet. Submit one to get started.'}
                      </div>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredRfqs.map(rfq => <RecentRfqRow key={rfq.id} rfq={rfq} />)
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}
