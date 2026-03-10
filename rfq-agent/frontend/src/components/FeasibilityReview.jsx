import React, { useState } from 'react';
import { CheckCircle, XCircle, Save, Check } from 'lucide-react';
import api from '../api/client';

export default function FeasibilityReview({ rfq, onRefresh }) {
    const [loading, setLoading] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState({});

    const startEdit = (feat) => {
        setEditingId(feat.id);
        setEditForm({
            proposed_machine: feat.proposed_machine || '',
            feasible: feat.feasible || 'Yes',
            measuring_instrument: feat.measuring_instrument || '',
            remarks: feat.remarks || ''
        });
    };

    const handleSaveRow = async (featId) => {
        setLoading(true);
        try {
            await api.patch(`/rfq/${rfq.id}/features/${featId}`, editForm);
            setEditingId(null);
            onRefresh(); // Refresh parent to get updated data
        } catch (err) {
            console.error(err);
            alert("Failed to save row");
        } finally {
            setLoading(false);
        }
    };

    const handleApprove = async () => {
        if (!confirm("Are you sure you want to approve this Feasibility Study and proceed to the Costing stage?")) return;
        setLoading(true);
        try {
            await api.post(`/rfq/${rfq.id}/review`, {
                stage: 'FEASIBILITY',
                action: 'approved',
                comment: '',
                reviewed_by: 'Dev Head'
            });
            onRefresh();
        } catch (err) {
            console.error(err);
            alert("Failed to approve feasibility");
            setLoading(false);
        }
    };

    return (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '24px' }}>

            {/* Left: Sticky Image Viewer */}
            <div style={{ position: 'sticky', top: '80px', maxHeight: 'calc(100vh - 100px)', overflowY: 'auto' }}>
                <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
                    <div className="p-4 border-b bg-elevated" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
                        <h3 style={{ margin: 0 }}>Reference Drawing</h3>
                    </div>
                    {rfq.ballooned_image_path ? (
                        <img
                            src={`http://localhost:8000${rfq.ballooned_image_path}`}
                            alt="Ballooned Drawing"
                            style={{ display: 'block', maxWidth: '100%', height: 'auto' }}
                        />
                    ) : (
                        <div className="p-8 text-center text-muted">No image available.</div>
                    )}
                </div>
            </div>

            {/* Right: Feasibility Grid */}
            <div className="flex flex-col gap-6">
                <div className="card">
                    <div className="flex justify-between items-center mb-4">
                        <h3>Feasibility Analysis</h3>
                        <button
                            className="btn btn-primary"
                            onClick={handleApprove}
                            disabled={loading || editingId !== null}
                        >
                            <CheckCircle size={16} /> Finalize Report & Send to Costing
                        </button>
                    </div>

                    <div className="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th style={{ width: '50px' }}>No.</th>
                                    <th>Feature & Spec</th>
                                    <th>Assigned Machine</th>
                                    <th>Instrument</th>
                                    <th>Feasible?</th>
                                    <th>Remarks (Deviation)</th>
                                    <th style={{ width: '80px' }}>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rfq.features.map(feat => (
                                    <tr key={feat.id}>
                                        <td><span className="badge badge-ballooning">#{feat.balloon_no}</span></td>

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
                                                        onChange={(e) => setEditForm({ ...editForm, proposed_machine: e.target.value })}
                                                    />
                                                </td>
                                                <td>
                                                    <input
                                                        className="form-input text-sm px-2 py-1"
                                                        value={editForm.measuring_instrument}
                                                        onChange={(e) => setEditForm({ ...editForm, measuring_instrument: e.target.value })}
                                                    />
                                                </td>
                                                <td>
                                                    <select
                                                        className="form-input text-sm px-2 py-1"
                                                        value={editForm.feasible}
                                                        onChange={(e) => setEditForm({ ...editForm, feasible: e.target.value })}
                                                    >
                                                        <option value="Yes">Yes</option>
                                                        <option value="No">No</option>
                                                    </select>
                                                </td>
                                                <td>
                                                    <input
                                                        className="form-input text-sm px-2 py-1"
                                                        value={editForm.remarks}
                                                        onChange={(e) => setEditForm({ ...editForm, remarks: e.target.value })}
                                                        placeholder="Reason/Deviation..."
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
                                                    {feat.proposed_machine || '-'}
                                                </td>
                                                <td className={feat.measuring_instrument === 'N/A' ? 'text-muted' : ''}>
                                                    {feat.measuring_instrument || '-'}
                                                </td>
                                                <td>
                                                    {feat.feasible === 'Yes'
                                                        ? <span className="text-accent-green flex items-center gap-1"><Check size={14} /> Yes</span>
                                                        : <span className="text-accent-red font-medium">No</span>
                                                    }
                                                </td>
                                                <td className="text-muted text-sm">{feat.remarks || '-'}</td>
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
                        {rfq.features.length === 0 && <p className="p-4 text-center text-muted">No features to review.</p>}
                    </div>
                </div>
            </div>
        </div>
    );
}
