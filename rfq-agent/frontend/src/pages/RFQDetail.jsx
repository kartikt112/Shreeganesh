import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    ArrowLeft,
    RefreshCw,
    Download,
    FileSpreadsheet,
    Activity,
    Clock,
    AlertTriangle,
    CheckCircle2,
} from 'lucide-react';
import api from '../api/client';
import BallooningReview from '../components/BallooningReview';
import FeasibilityReview from '../components/FeasibilityReview';
import { duration } from '../utils/formatters';

// Static map — defined at module level so it's not recreated on every render
const STATUS_BADGE = {
    NEW:                    'badge-new',
    PARSING:                'badge-parsing',
    BALLOONING:             'badge-ballooning',
    BALLOONING_REVIEW:      'badge-review',
    FEASIBILITY_GENERATION: 'badge-parsing',
    FEASIBILITY_REVIEW:     'badge-review',
    COSTING:                'badge-costing',
    QUOTE_SENT:             'badge-done',
};

export default function RFQDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [rfq, setRfq] = useState(null);
    const [loading, setLoading] = useState(true);
    const [runs, setRuns] = useState([]);
    const [runsLoading, setRunsLoading] = useState(true);

    // Wrapped in useCallback so the interval closure always captures the
    // latest version (avoids stale-closure issues when `id` changes).
    const fetchRFQ = useCallback(async () => {
        try {
            const res = await api.get(`/rfq/${id}`);
            // Only update state if status changed — prevents child components
            // (BallooningReview / FeasibilityReview) from re-rendering every 3s
            // when nothing has actually changed.
            setRfq(prev => {
                if (prev && prev.status === res.data.status && prev.id === res.data.id) return prev;
                return res.data;
            });
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [id]);

    const fetchRuns = useCallback(async () => {
        try {
            setRunsLoading(true);
            const res = await api.get(`/admin/rfqs/${id}/runs`);
            setRuns(res.data.runs || []);
        } catch (err) {
            console.error("Failed to load pipeline runs", err);
        } finally {
            setRunsLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchRFQ();
        fetchRuns();
        // Poll RFQ status quickly (3s); refresh run history less aggressively (15s)
        const rfqInterval  = setInterval(fetchRFQ,  3000);
        const runsInterval = setInterval(fetchRuns, 15000);
        return () => {
            clearInterval(rfqInterval);
            clearInterval(runsInterval);
        };
    }, [fetchRFQ, fetchRuns]);

    if (loading) return (
        <div className="loading-container" style={{ minHeight: '60vh' }}>
            <div className="enterprise-spinner">
                <div className="enterprise-spinner-ring" />
            </div>
            <div className="text-secondary text-sm" style={{ marginTop: 16 }}>Loading RFQ…</div>
        </div>
    );
    if (!rfq) return <div className="p-8 text-center text-accent-red">RFQ not found.</div>;

    const latestRun = runs[0];

    return (
        <div>
            <div className="detail-header">
                <div className="detail-title-section">
                    <button className="btn btn-outline text-secondary mb-2" onClick={() => navigate('/')}>
                        <ArrowLeft size={16} /> Back to Dashboard
                    </button>
                    <h1>{rfq.part_name}</h1>
                    <p className="text-secondary text-sm">
                        {rfq.customer_name} • Part #{rfq.part_no || 'N/A'}
                    </p>
                </div>
                <div className="detail-actions">
                    <span className={`badge ${STATUS_BADGE[rfq.status] || 'badge-new'}`}>{rfq.status.replace(/_/g, ' ')}</span>
                </div>
            </div>

            <div className="detail-grid mb-6">
                <div className="detail-meta-card">
                    <div className="detail-meta-row">
                        <span className="detail-meta-label">RFQ ID</span>
                        <span className="detail-meta-value">#{rfq.id}</span>
                    </div>
                    <div className="detail-meta-row">
                        <span className="detail-meta-label">Received</span>
                        <span className="detail-meta-value">
                            {new Date(rfq.received_at).toLocaleString()}
                        </span>
                    </div>
                    <div className="detail-meta-row">
                        <span className="detail-meta-label">Template</span>
                        <span className="detail-meta-value">
                            {rfq.template_path ? 'Attached' : 'N/A'}
                        </span>
                    </div>
                </div>

                <div className="detail-meta-card">
                    <div className="mb-3 flex items-center gap-2">
                        <Activity size={16} className="text-accent-blue" />
                        <span className="text-sm font-semibold">Latest pipeline run</span>
                    </div>
                    {runsLoading && (
                        <div className="text-sm text-muted">Loading run history...</div>
                    )}
                    {!runsLoading && !latestRun && (
                        <div className="text-sm text-muted">No runs recorded yet.</div>
                    )}
                    {latestRun && (
                        <>
                            <div className="detail-meta-row">
                                <span className="detail-meta-label">Started</span>
                                <span className="detail-meta-value">
                                    {latestRun.started_at
                                        ? new Date(latestRun.started_at).toLocaleString()
                                        : '—'}
                                </span>
                            </div>
                            <div className="detail-meta-row">
                                <span className="detail-meta-label">Completed</span>
                                <span className="detail-meta-value">
                                    {latestRun.completed_at
                                        ? new Date(latestRun.completed_at).toLocaleString()
                                        : 'In progress'}
                                </span>
                            </div>
                            <div className="detail-meta-row">
                                <span className="detail-meta-label">Duration</span>
                                <span className="detail-meta-value">{duration(latestRun.total_ms)}</span>
                            </div>
                            <div className="detail-meta-row">
                                <span className="detail-meta-label">Result</span>
                                <span className="detail-meta-value">
                                    {latestRun.status === 'SUCCESS' ? (
                                        <span className="flex items-center gap-1 text-accent-green text-sm">
                                            <CheckCircle2 size={14} /> Success
                                        </span>
                                    ) : (
                                        <span className="flex items-center gap-1 text-accent-red text-sm">
                                            <AlertTriangle size={14} /> Failed
                                        </span>
                                    )}
                                </span>
                            </div>
                            {latestRun.failure_stage && (
                                <div className="detail-meta-row">
                                    <span className="detail-meta-label">Failure stage</span>
                                    <span className="detail-meta-value">{latestRun.failure_stage}</span>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>

            {/* Pipeline run timeline */}
            <div className="card mb-6">
                <div className="card-header">
                    <span className="card-title flex items-center gap-2">
                        <Clock size={16} /> Pipeline history
                    </span>
                </div>
                {runsLoading ? (
                    <div className="loading-container">
                        <div className="spinner" />
                        <div className="text-secondary text-sm">Loading pipeline runs…</div>
                    </div>
                ) : runs.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-icon">
                            <Activity size={20} className="text-muted" />
                        </div>
                        <div className="text-sm">No pipeline runs recorded for this RFQ yet.</div>
                    </div>
                ) : (
                    <div className="timeline">
                        {runs.map((run) => (
                            <div key={run.id} className="timeline-item">
                                <div className="timeline-dot">
                                    {run.status === 'SUCCESS' ? (
                                        <CheckCircle2 size={16} className="text-accent-green" />
                                    ) : (
                                        <AlertTriangle size={16} className="text-accent-red" />
                                    )}
                                </div>
                                <div className="timeline-content">
                                    <div className="timeline-text">
                                        Run #{run.id} • {run.engine?.toUpperCase() || 'ENGINE'}
                                    </div>
                                    <div className="timeline-time">
                                        {run.started_at
                                            ? new Date(run.started_at).toLocaleString()
                                            : '—'}{" "}
                                        • {duration(run.total_ms)}
                                    </div>
                                    {run.failure_stage && (
                                        <div className="text-xs text-accent-red mt-1">
                                            Failed at {run.failure_stage}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {rfq.status === 'BALLOONING_REVIEW' ? (
                <BallooningReview rfq={rfq} onRefresh={fetchRFQ} />
            ) : rfq.status === 'FEASIBILITY_REVIEW' ? (
                <FeasibilityReview rfq={rfq} onRefresh={fetchRFQ} />
            ) : ['COSTING', 'QUOTE_SENT'].includes(rfq.status) ? (
                <div className="card text-center py-12">
                    <FileSpreadsheet className="mx-auto text-accent-green mb-4" size={48} />
                    <h2 className="mb-2">Feasibility Report Generated</h2>
                    <p className="text-secondary mb-8">The AI engine and Dev Head review are complete. Download the official Excel report for costing.</p>
                    <a href={`http://localhost:8000/api/rfq/${rfq.id}/report`} target="_blank" rel="noreferrer" className="btn btn-primary" style={{ display: 'inline-flex', padding: '12px 24px' }}>
                        <Download size={20} /> Download Feasibility Report (.xlsx)
                    </a>
                </div>
            ) : (
                <div className="card text-center py-12">
                    <RefreshCw className="animate-spin mx-auto text-accent-blue mb-4" size={32} />
                    <h3 className="text-secondary">Pipeline Running</h3>
                    <p className="text-muted text-sm mt-2">
                        The Deep Vision Pipeline is currently processing this drawing. <br />
                        This page will automatically update when the BALLOONING_REVIEW stage is reached.
                    </p>
                </div>
            )}

        </div>
    );
}
