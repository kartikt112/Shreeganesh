import React, { useState, useEffect, useMemo } from 'react';
import {
    CheckCircle, XCircle, Trash2, RefreshCw, PenTool,
    ExternalLink, AlertTriangle, X, Send,
} from 'lucide-react';
import api from '../api/client';

export default function BallooningReview({ rfq, onRefresh }) {
    const [loading, setLoading] = useState(false);
    const [deletingId, setDeletingId] = useState(null); // id of item pending delete confirm
    const [showRejectModal, setShowRejectModal] = useState(false);
    const [rejectNote, setRejectNote] = useState('');
    const [toast, setToast] = useState(null); // { type: 'success'|'error', msg }

    // Listen for "editor-saved" messages from the editor window to auto-refresh
    useEffect(() => {
        const handler = (e) => {
            if (e.data?.type === 'editor-saved' && e.data?.rfqId === rfq.id) {
                onRefresh();
            }
        };
        window.addEventListener('message', handler);
        return () => window.removeEventListener('message', handler);
    }, [rfq.id, onRefresh]);

    // Auto-dismiss toast after 3 s
    useEffect(() => {
        if (!toast) return;
        const t = setTimeout(() => setToast(null), 3000);
        return () => clearTimeout(t);
    }, [toast]);

    // Stable image src — only changes when rfq.ballooned_image_path changes (not on every render)
    const imgSrc = useMemo(() => {
        const path = rfq.ballooned_image_path || rfq.drawing_image_path;
        return path ? `http://localhost:8000${path}?t=${rfq.id}` : null;
    }, [rfq.ballooned_image_path, rfq.drawing_image_path, rfq.id]);

    const showToast = (type, msg) => setToast({ type, msg });

    const confirmDelete = (featId) => setDeletingId(featId);
    const cancelDelete = () => setDeletingId(null);

    const handleDelete = async (featId) => {
        setLoading(true);
        setDeletingId(null);
        try {
            await api.delete(`/rfq/${rfq.id}/features/${featId}`);
            showToast('success', 'Balloon deleted.');
            setTimeout(onRefresh, 800);
        } catch (err) {
            console.error("Delete failed", err);
            showToast('error', 'Delete failed: ' + (err.response?.data?.detail || err.message));
            setLoading(false);
        }
    };

    const handleApprove = async () => {
        setLoading(true);
        try {
            await api.post(`/rfq/${rfq.id}/review`, {
                stage: 'BALLOONING',
                action: 'approved',
                comment: '',
                reviewed_by: 'Dev Head',
            });
            showToast('success', 'Approved — running Feasibility Engine…');
            onRefresh();
        } catch (err) {
            console.error(err);
            showToast('error', 'Approve failed: ' + (err.response?.data?.detail || err.message));
            setLoading(false);
        }
    };

    const handleReject = async () => {
        if (!rejectNote.trim()) return;
        setLoading(true);
        try {
            await api.post(`/rfq/${rfq.id}/review`, {
                stage: 'BALLOONING',
                action: 'rejected',
                comment: rejectNote.trim(),
                reviewed_by: 'Dev Head',
            });
            setShowRejectModal(false);
            setRejectNote('');
            showToast('success', 'Rejection sent — pipeline reset.');
            onRefresh();
        } catch (err) {
            console.error(err);
            showToast('error', 'Rejection failed: ' + (err.response?.data?.detail || err.message));
            setLoading(false);
        }
    };

    return (
        <div className="review-layout">

            {/* ── Toast notification ── */}
            {toast && (
                <div className={`review-toast review-toast-${toast.type}`}>
                    {toast.type === 'success'
                        ? <CheckCircle size={14} />
                        : <AlertTriangle size={14} />}
                    <span>{toast.msg}</span>
                    <button className="review-toast-close" onClick={() => setToast(null)}>
                        <X size={12} />
                    </button>
                </div>
            )}

            {/* ── Rejection modal ── */}
            {showRejectModal && (
                <div className="modal-backdrop" onClick={() => setShowRejectModal(false)}>
                    <div className="modal-card" onClick={e => e.stopPropagation()}>
                        <div className="modal-header">
                            <span className="modal-title">
                                <XCircle size={16} className="text-accent-red" /> Send Rejection
                            </span>
                            <button className="modal-close" onClick={() => setShowRejectModal(false)}>
                                <X size={16} />
                            </button>
                        </div>
                        <p className="modal-body-text">
                            Describe what needs to be corrected. The pipeline will be reset to the BALLOONING stage.
                        </p>
                        <textarea
                            className="modal-textarea"
                            rows={4}
                            placeholder="e.g. Balloon #3 is incorrect — dimension should be 4.5 not 3.5. Missing hole pattern on the right flange."
                            value={rejectNote}
                            onChange={e => setRejectNote(e.target.value)}
                            autoFocus
                        />
                        <div className="modal-actions">
                            <button className="btn btn-outline" onClick={() => setShowRejectModal(false)}>
                                Cancel
                            </button>
                            <button
                                className="btn"
                                style={{
                                    background: 'rgba(239,68,68,0.15)',
                                    color: '#f87171',
                                    border: '1px solid rgba(239,68,68,0.3)',
                                }}
                                onClick={handleReject}
                                disabled={loading || !rejectNote.trim()}
                            >
                                <Send size={14} /> Send Rejection
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Left: Drawing Viewer ── */}
            <div className="card review-image-card">
                <div className="review-image-header">
                    <h3 className="review-image-title">
                        AI Extracted Drawing
                        {loading && <RefreshCw size={13} className="spin-icon" />}
                    </h3>
                    <a
                        href={`http://localhost:5174?rfq_id=${rfq.id}&api=http://localhost:8000`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn btn-primary"
                        style={{ padding: '6px 14px', textDecoration: 'none' }}
                    >
                        <PenTool size={14} /> Open Editor <ExternalLink size={12} />
                    </a>
                </div>
                <div className="review-image-body">
                    {imgSrc ? (
                        <img
                            src={imgSrc}
                            alt="Ballooned Drawing"
                        />
                    ) : (
                        <div className="empty-state" style={{ padding: '48px 0' }}>
                            <div className="text-sm text-muted">No drawing image generated yet.</div>
                        </div>
                    )}
                </div>
            </div>

            {/* ── Right: Feature List + Review Controls ── */}
            <div className="review-sidebar">

                {/* Feature list */}
                <div className="card">
                    <h3 className="mb-4">
                        Extracted Features
                        <span className="section-badge" style={{ marginLeft: 8 }}>{rfq.features.length}</span>
                    </h3>
                    <div className="review-feature-list">
                        {rfq.features.length === 0 ? (
                            <p className="text-sm text-muted">No features extracted.</p>
                        ) : (
                            rfq.features.map(feat => (
                                <div key={feat.id} className="review-feature-row">
                                    <div className="review-feature-info">
                                        <div className="review-feature-top">
                                            <span className="badge badge-ballooning">#{feat.balloon_no}</span>
                                            <strong className="review-feature-spec">{feat.specification}</strong>
                                        </div>
                                        <span className="review-feature-desc">
                                            {feat.description} · <em>{feat.feature_type}</em>
                                        </span>
                                    </div>

                                    {deletingId === feat.id ? (
                                        <div className="review-delete-confirm">
                                            <span className="text-xs text-accent-red">Delete?</span>
                                            <button
                                                className="btn"
                                                style={{ padding: '3px 8px', fontSize: '0.72rem', background: 'rgba(239,68,68,0.15)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)' }}
                                                onClick={() => handleDelete(feat.id)}
                                                disabled={loading}
                                            >
                                                Yes
                                            </button>
                                            <button
                                                className="btn btn-outline"
                                                style={{ padding: '3px 8px', fontSize: '0.72rem' }}
                                                onClick={cancelDelete}
                                            >
                                                No
                                            </button>
                                        </div>
                                    ) : (
                                        <button
                                            className="btn btn-danger"
                                            style={{ padding: '6px', flexShrink: 0 }}
                                            onClick={() => confirmDelete(feat.id)}
                                            disabled={loading}
                                            title="Delete this balloon"
                                        >
                                            <Trash2 size={14} />
                                        </button>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                </div>

                {/* Review action card */}
                <div className="review-action-card">
                    <div className="review-action-header">
                        <h3>Development Head Review</h3>
                    </div>
                    <p className="review-action-desc">
                        Ensure all critical dimensions are captured correctly and there are no hallucinations before sending to the Feasibility Engine.
                    </p>
                    <div className="review-action-btns">
                        <button
                            className="btn btn-primary w-full"
                            style={{ justifyContent: 'center' }}
                            onClick={handleApprove}
                            disabled={loading || rfq.features.length === 0}
                        >
                            <CheckCircle size={16} /> Approve & Run Feasibility Engine
                        </button>
                        <button
                            className="btn w-full"
                            style={{
                                justifyContent: 'center',
                                background: 'rgba(239,68,68,0.08)',
                                color: '#f87171',
                                border: '1px solid rgba(239,68,68,0.25)',
                            }}
                            onClick={() => setShowRejectModal(true)}
                            disabled={loading}
                        >
                            <XCircle size={16} /> Send Rejection / Notes
                        </button>
                    </div>
                </div>

            </div>
        </div>
    );
}
