import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Activity, CheckCircle2, AlertTriangle, Clock,
    RefreshCw, ChevronRight, Cpu, Zap,
} from 'lucide-react';
import api from '../api/client';
import { relativeTime, duration } from '../utils/formatters';

// Stage color lookup — keyed by status string, used for the stage badge
const STAGE_COLORS = {
    NEW:                    { color: '#64748b', bg: 'rgba(100,116,139,0.12)' },
    PARSING:                { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
    BALLOONING:             { color: '#3b82f6', bg: 'rgba(59,130,246,0.12)' },
    BALLOONING_REVIEW:      { color: '#8b5cf6', bg: 'rgba(139,92,246,0.12)' },
    FEASIBILITY_GENERATION: { color: '#6366f1', bg: 'rgba(99,102,241,0.12)' },
    FEASIBILITY_REVIEW:     { color: '#a855f7', bg: 'rgba(168,85,247,0.12)' },
    COSTING:                { color: '#10b981', bg: 'rgba(16,185,129,0.12)' },
    QUOTE_SENT:             { color: '#06b6d4', bg: 'rgba(6,182,212,0.12)' },
};
const FALLBACK_COLOR = { color: '#64748b', bg: 'rgba(100,116,139,0.12)' };

function stageColor(status) {
    return STAGE_COLORS[status] ?? FALLBACK_COLOR;
}

export default function PipelineActivity() {
    const navigate = useNavigate();
    const [rfqs, setRfqs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [lastRefresh, setLastRefresh] = useState(new Date());
    const [metrics, setMetrics] = useState(null);

    const fetchAll = useCallback(async (showLoading = false) => {
        if (showLoading) setLoading(true);
        setIsRefreshing(true);
        try {
            const [rfqRes, metRes] = await Promise.all([
                api.get('/admin/rfqs', { params: { page: 1, page_size: 200 } }),
                api.get('/admin/metrics', { params: { days: 30 } }),
            ]);
            setRfqs(rfqRes.data.items || []);
            setMetrics(metRes.data);
            setLastRefresh(new Date());
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
            setIsRefreshing(false);
        }
    }, []);

    useEffect(() => {
        fetchAll(true);
        const interval = setInterval(() => fetchAll(false), 8000);
        return () => clearInterval(interval);
    }, [fetchAll]);

    // Sorted + sliced once per rfqs change, not on every render
    const activityItems = useMemo(() =>
        [...rfqs]
            .sort((a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime())
            .slice(0, 50),
        [rfqs]
    );

    if (loading) {
        return (
            <div className="loading-container" style={{ minHeight: '60vh' }}>
                <div className="enterprise-spinner">
                    <div className="enterprise-spinner-ring" />
                    <Cpu size={16} className="enterprise-spinner-icon" />
                </div>
                <div className="text-secondary text-sm" style={{ marginTop: 16 }}>Loading activity…</div>
            </div>
        );
    }

    return (
        <div className="dashboard-root">

            {/* Header */}
            <div className="dashboard-header">
                <div className="dashboard-header-left">
                    <div className="dashboard-title-row">
                        <h1 className="dashboard-title">Pipeline Activity</h1>
                        <div className="live-indicator">
                            <span className="live-dot" />
                            <span>Live</span>
                        </div>
                    </div>
                    <p className="dashboard-subtitle">
                        Real-time status of all RFQ pipeline runs · Last 30 days
                    </p>
                </div>
                <div className="dashboard-header-right">
                    <span className="refresh-time">
                        Updated {relativeTime(lastRefresh)}
                        {isRefreshing && <RefreshCw size={11} className="spin-icon" />}
                    </span>
                </div>
            </div>

            {/* Metrics strip */}
            {metrics && (
                <div className="activity-metrics-strip">
                    <div className="activity-metric">
                        <Zap size={14} className="activity-metric-icon blue" />
                        <div>
                            <div className="activity-metric-val">{metrics.total_runs ?? 0}</div>
                            <div className="activity-metric-lbl">Total runs</div>
                        </div>
                    </div>
                    <div className="activity-metric-sep" />
                    <div className="activity-metric">
                        <CheckCircle2 size={14} className="activity-metric-icon green" />
                        <div>
                            <div className="activity-metric-val">{metrics.successful_runs ?? 0}</div>
                            <div className="activity-metric-lbl">Successful</div>
                        </div>
                    </div>
                    <div className="activity-metric-sep" />
                    <div className="activity-metric">
                        <AlertTriangle size={14} className="activity-metric-icon amber" />
                        <div>
                            <div className="activity-metric-val">
                                {(metrics.total_runs ?? 0) - (metrics.successful_runs ?? 0)}
                            </div>
                            <div className="activity-metric-lbl">Failed</div>
                        </div>
                    </div>
                    <div className="activity-metric-sep" />
                    <div className="activity-metric">
                        <Clock size={14} className="activity-metric-icon purple" />
                        <div>
                            <div className="activity-metric-val">
                                {duration(metrics.avg_duration_ms)}
                            </div>
                            <div className="activity-metric-lbl">Avg duration</div>
                        </div>
                    </div>
                    <div className="activity-metric-sep" />
                    <div className="activity-metric">
                        <Activity size={14} className="activity-metric-icon cyan" />
                        <div>
                            <div className="activity-metric-val">
                                {metrics.success_rate != null ? `${Math.round(metrics.success_rate * 100)}%` : '—'}
                            </div>
                            <div className="activity-metric-lbl">Success rate</div>
                        </div>
                    </div>
                </div>
            )}

            {/* Activity table */}
            <div>
                <div className="section-header">
                    <div className="section-title">
                        <Activity size={15} />
                        <span>All RFQ Activity</span>
                        <span className="section-badge">{activityItems.length}</span>
                    </div>
                </div>

                <div className="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th style={{ width: 40 }}>#</th>
                                <th>Part / Customer</th>
                                <th>Current Stage</th>
                                <th>Last Run</th>
                                <th>Duration</th>
                                <th>Received</th>
                                <th style={{ width: 70 }}></th>
                            </tr>
                        </thead>
                        <tbody>
                            {activityItems.length === 0 ? (
                                <tr>
                                    <td colSpan={7}>
                                        <div className="empty-state">
                                            <div className="empty-state-icon">
                                                <Activity size={20} className="text-muted" />
                                            </div>
                                            <div className="text-sm text-muted">No activity yet.</div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                activityItems.map(rfq => {
                                    const sc = stageColor(rfq.status);
                                    const run = rfq.last_run;
                                    return (
                                        <tr
                                            key={rfq.id}
                                            style={{ cursor: 'pointer' }}
                                            onClick={() => navigate(`/rfq/${rfq.id}`)}
                                            className="recent-row"
                                        >
                                            <td>
                                                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                                    {rfq.id}
                                                </span>
                                            </td>
                                            <td>
                                                <div className="recent-part">{rfq.part_name}</div>
                                                <div className="recent-customer">{rfq.customer_name}</div>
                                            </td>
                                            <td>
                                                <span className="stage-badge" style={{
                                                    color: sc.color, background: sc.bg,
                                                    border: `1px solid ${sc.color}30`,
                                                }}>
                                                    <span className="stage-badge-dot" style={{ background: sc.color }} />
                                                    {rfq.status.replace(/_/g, ' ')}
                                                </span>
                                            </td>
                                            <td>
                                                {run ? (
                                                    run.status === 'SUCCESS'
                                                        ? <span className="run-success"><CheckCircle2 size={12} /> Success</span>
                                                        : <span className="run-fail"><AlertTriangle size={12} /> {run.failure_stage || 'Failed'}</span>
                                                ) : (
                                                    <span className="text-muted" style={{ fontSize: '0.72rem' }}>No runs</span>
                                                )}
                                            </td>
                                            <td>
                                                <span className="run-dur">{run ? duration(run.total_ms) : '—'}</span>
                                            </td>
                                            <td className="recent-date">
                                                {new Date(rfq.received_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}
                                            </td>
                                            <td>
                                                <button className="recent-action-btn">
                                                    View <ChevronRight size={12} />
                                                </button>
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
