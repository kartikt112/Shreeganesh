import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Save, Check, AlertTriangle, X } from 'lucide-react';
import api from '../api/client';

export default function FeasibilityReview({ rfq, onRefresh }) {
    const [loading, setLoading] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState({});
    const [showApproveConfirm, setShowApproveConfirm] = useState(false);
    const [toast, setToast] = useState(null); // { type: 'success'|'error', msg }

    // Auto-dismiss toast
    useEffect(() => {
        if (!toast) return;
        const t = setTimeout(() => setToast(null), 3500);
        return () => clearTimeout(t);
    }, [toast]);

    const showToast = (type, msg) => setToast({ type, msg });

    const startEdit = (feat) => {
        setEditingId(feat.id);
        setEditForm({
            proposed_machine: feat.proposed_machine || '',
            feasible: feat.feasible || 'Yes',
            measuring_instrument: feat.measuring_instrument || '',
            remarks: feat.remarks || '',
        });
    };

    const handleSaveRow = async (featId) => {
        setLoading(true);
        try {
            await api.patch(`/rfq/${rfq.id}/features/${featId}`, editForm);
            setEditingId(null);
            onRefresh();
        } catch (err) {
            console.error(err);
            showToast('error', 'Save failed: ' + (err.response?.data?.detail || err.message));
        } finally {
            setLoading(false);
        }
    };

    const handleApprove = async () => {
        setShowApproveConfirm(false);
        setLoading(true);
        try {
            await api.post(`/rfq/${rfq.id}/review`, {
                stage: 'FEASIBILITY',
                action: 'approved',
                comment: '',
                reviewed_by: 'Dev Head',
            });
            showToast('success', 'Feasibility approved — moving to Costing.');
            onRefresh();
        } catch (err) {
            console.error(err);
            showToast('error', 'Approval failed: ' + (err.response?.data?.detail || err.message));
            setLoading(false);
        }
    };

    return (
        <div className="review-layout">

            {/* ── Toast ── */}
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

            {/* ── Approve confirm modal ── */}
            {showApproveConfirm && (
                <div className="modal-backdrop" onClick={() => setShowApproveConfirm(false)}>
                    <div className="modal-card" onClick={e => e.stopPropagation()}>
                        <div className="modal-header">
                            <span className="modal-title">
                                <CheckCircle size={16} className="text-accent-green" /> Finalize Feasibility Study
                            </span>
                            <button className="modal-close" onClick={() => setShowApproveConfirm(false)}>
                                <X size={16} />
                            </button>
                        </div>
                        <p className="modal-body-text">
                            This will approve the feasibility analysis and advance the RFQ to the <strong>Costing</strong> stage. The Excel report will be generated automatically.
                        </p>
                        <div className="modal-actions">
                            <button className="btn btn-outline" onClick={() => setShowApproveConfirm(false)}>
                                Cancel
                            </button>
                            <button className="btn btn-primary" onClick={handleApprove} disabled={loading}>
                                <CheckCircle size={14} /> Confirm & Send to Costing
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Left: Sticky Image Viewer ── */}
            <div style={{ position: 'sticky', top: '80px', maxHeight: 'calc(100vh - 100px)', overflowY: 'auto' }}>
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <div className="review-image-header">
                        <h3 className="review-image-title">Reference Drawing</h3>
                    </div>
                    <div className="review-image-body">
                        {rfq.ballooned_image_path ? (
                            <img
                                src={`http://localhost:8000${rfq.ballooned_image_path}`}
                                alt="Ballooned Drawing"
                            />
                        ) : (
                            <div className="empty-state" style={{ padding: '48px 0' }}>
                                <div className="text-sm text-muted">No image available.</div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* ── Right: Feasibility Grid ── */}
            <div className="flex flex-col gap-6">
                <div className="card">
                    <div className="flex justify-between items-center mb-4">
                        <h3>Feasibility Analysis</h3>
                        <button
                            className="btn btn-primary"
                            onClick={() => setShowApproveConfirm(true)}
                            disabled={loading || editingId !== null}
                        >
                            <CheckCircle size={16} /> Finalize Report & Send to Costing
                        </button>
                    </div>

                    <div className="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th style={{ width: 50 }}>No.</th>
                                    <th>Feature &amp; Spec</th>
                                    <th>Assigned Machine</th>
                                    <th>Instrument</th>
                                    <th>Feasible?</th>
                                    <th>Remarks</th>
                                    <th style={{ width: 80 }}>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rfq.features.map(feat => (
                                    <tr key={feat.id}>
                                        <td>
                                            <span className="badge badge-ballooning">#{feat.balloon_no}</span>
                                        </td>
                                        <td>
                                            <div className="font-medium">{feat.specification}</div>
                                            <div className="text-xs text-muted">{feat.description}</div>
                                        </td>

                                        {editingId === feat.id ? (
                                            <>
                                                <td>
                                                    <input
                                                        className="form-input text-sm px-2 py-1"
                                                        value={editForm.proposed_machine}
                                                        onChange={e => setEditForm({ ...editForm, proposed_machine: e.target.value })}
                                                    />
                                                </td>
                                                <td>
                                                    <input
                                                        className="form-input text-sm px-2 py-1"
                                                        value={editForm.measuring_instrument}
                                                        onChange={e => setEditForm({ ...editForm, measuring_instrument: e.target.value })}
                                                    />
                                                </td>
                                                <td>
                                                    <select
                                                        className="form-input text-sm px-2 py-1"
                                                        value={editForm.feasible}
                                                        onChange={e => setEditForm({ ...editForm, feasible: e.target.value })}
                                                    >
                                                        <option value="Yes">Yes</option>
                                                        <option value="No">No</option>
                                                    </select>
                                                </td>
                                                <td>
                                                    <input
                                                        className="form-input text-sm px-2 py-1"
                                                        value={editForm.remarks}
                                                        onChange={e => setEditForm({ ...editForm, remarks: e.target.value })}
                                                        placeholder="Reason/Deviation…"
                                                    />
                                                </td>
                                                <td>
                                                    <button
                                                        className="btn btn-primary"
                                                        style={{ padding: '4px 8px' }}
                                                        onClick={() => handleSaveRow(feat.id)}
                                                        disabled={loading}
                                                    >
                                                        <Save size={14} />
                                                    </button>
                                                </td>
                                            </>
                                        ) : (
                                            <>
                                                <td className={feat.proposed_machine === 'N/A' ? 'text-muted' : ''}>
                                                    {feat.proposed_machine || '–'}
                                                </td>
                                                <td className={feat.measuring_instrument === 'N/A' ? 'text-muted' : ''}>
                                                    {feat.measuring_instrument || '–'}
                                                </td>
                                                <td>
                                                    {feat.feasible === 'Yes'
                                                        ? <span className="text-accent-green flex items-center gap-1"><Check size={14} /> Yes</span>
                                                        : <span className="text-accent-red font-medium">No</span>
                                                    }
                                                </td>
                                                <td className="text-muted text-sm">{feat.remarks || '–'}</td>
                                                <td>
                                                    <button
                                                        className="btn btn-outline"
                                                        style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                                                        onClick={() => startEdit(feat)}
                                                        disabled={loading}
                                                    >
                                                        Edit
                                                    </button>
                                                </td>
                                            </>
                                        )}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        {rfq.features.length === 0 && (
                            <p className="p-4 text-center text-muted">No features to review.</p>
                        )}
                    </div>
                </div>
            </div>

        </div>
    );
}
