import React, { useRef, useState } from 'react';
import { CheckCircle, XCircle, Trash2, MousePointerClick, RefreshCw, Pencil } from 'lucide-react';
import api from '../api/client';

export default function BallooningReview({ rfq, onRefresh }) {
    const [loading, setLoading] = useState(false);
    const [clickMode, setClickMode] = useState(false); // If true, next click on image adds a balloon
    const imageRef = useRef(null);

    const [modalOpen, setModalOpen] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [formData, setFormData] = useState({ id: null, balloon_no: "", specification: "", description: "", box_2d: null });

    // Handle clicking on the drawing to manually add a balloon
    const handleImageClick = async (e) => {
        if (!clickMode || !imageRef.current) return;

        // Get coordinate relative to the image
        const rect = imageRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        // Scale to the underlying image's natural dimensions
        const scaleX = imageRef.current.naturalWidth / rect.width;
        const scaleY = imageRef.current.naturalHeight / rect.height;

        // Create a 40x40 pixel bounding box around the click point as the "feature box"
        const absoluteX = x * scaleX;
        const absoluteY = y * scaleY;

        const box_2d = JSON.stringify([
            Math.max(0, absoluteY - 20),
            Math.max(0, absoluteX - 20),
            absoluteY + 20,
            absoluteX + 20
        ]);

        setClickMode(false); // Reset mode

        const max_num = rfq.features.reduce((max, f) => Math.max(max, f.balloon_no), 0);
        setFormData({
            id: null,
            box_2d,
            balloon_no: (max_num + 1).toString(),
            specification: "",
            description: "Outer Dia"
        });
        setIsEditing(false);
        setModalOpen(true);
    };

    const openEditModal = (feat) => {
        setFormData({
            id: feat.id,
            balloon_no: feat.balloon_no?.toString() || "",
            specification: feat.specification || "",
            description: feat.description || "",
            box_2d: null
        });
        setIsEditing(true);
        setModalOpen(true);
    };

    const handleModalSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setModalOpen(false);

        try {
            if (isEditing) {
                await api.patch(`/rfq/${rfq.id}/features/${formData.id}`, {
                    balloon_no: parseInt(formData.balloon_no, 10),
                    specification: formData.specification,
                    description: formData.description
                });
            } else {
                await api.post(`/rfq/${rfq.id}/features`, {
                    box_2d: formData.box_2d,
                    balloon_no: parseInt(formData.balloon_no, 10),
                    specification: formData.specification,
                    description: formData.description,
                });
            }
            setTimeout(onRefresh, 1000);
        } catch (err) {
            console.error(err);
            alert(`Failed to ${isEditing ? 'update' : 'add'} feature`);
            setLoading(false);
        }
    };

    const handleDelete = async (featId) => {
        if (!confirm("Are you sure you want to delete this balloon?")) return;

        setLoading(true);
        try {
            await api.delete(`/rfq/${rfq.id}/features/${featId}`);
            setTimeout(onRefresh, 1000);
        } catch (err) {
            console.error("Delete failed", err);
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
                reviewed_by: 'Dev Head'
            });
            onRefresh();
        } catch (err) {
            console.error(err);
            alert('Failed to approve: ' + (err.response?.data?.detail || err.message));
            setLoading(false);
        }
    };

    return (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2.5fr) minmax(300px, 1fr)', gap: '24px' }}>

            {/* Left Side: Interactive Drawing Viewer */}
            <div className="card" style={{ padding: '0', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                <div className="flex items-center justify-between p-4 border-b" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
                    <h3 style={{ margin: 0 }} className="flex items-center gap-2">
                        AI Extracted Drawing
                        {loading && <RefreshCw size={14} className="animate-spin text-accent-blue" />}
                    </h3>
                    <button
                        className={`btn ${clickMode ? 'btn-primary' : 'btn-outline'}`}
                        onClick={() => setClickMode(!clickMode)}
                        disabled={loading}
                    >
                        <MousePointerClick size={16} />
                        {clickMode ? "Click drawing to add..." : "Draw Missing Balloon"}
                    </button>
                </div>

                <div style={{ flex: 1, backgroundColor: '#000', overflow: 'auto', maxHeight: '800px', cursor: clickMode ? 'crosshair' : 'default' }}>
                    {rfq.ballooned_image_path ? (
                        <img
                            ref={imageRef}
                            src={`http://localhost:8000${rfq.ballooned_image_path}?t=${Date.now()}`} // cache buster for instant redraws
                            alt="Ballooned Drawing"
                            style={{ display: 'block', maxWidth: '100%', height: 'auto' }}
                            onClick={handleImageClick}
                        />
                    ) : (
                        <div className="p-8 text-center text-muted">No image generated.</div>
                    )}
                </div>
            </div>

            {/* Right Side: Feature List & Approval Controls */}
            <div className="flex flex-col gap-6">

                <div className="card">
                    <h3 className="mb-4">Extracted Features ({rfq.features.length})</h3>
                    <div style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: '8px' }}>
                        {rfq.features.map(feat => (
                            <div key={feat.id} className="flex justify-between items-start mb-3 pb-3 border-b" style={{ borderColor: 'var(--border-color)' }}>
                                <div>
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="badge badge-ballooning">#{feat.balloon_no}</span>
                                        <strong className="text-sm">{feat.specification}</strong>
                                    </div>
                                    <span className="text-xs text-muted">{feat.description} • {feat.feature_type}</span>
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        className="btn btn-outline"
                                        style={{ padding: '6px' }}
                                        onClick={() => openEditModal(feat)}
                                        disabled={loading}
                                        title="Edit this dimension"
                                    >
                                        <Pencil size={14} />
                                    </button>
                                    <button
                                        className="btn btn-danger"
                                        style={{ padding: '6px' }}
                                        onClick={() => handleDelete(feat.id)}
                                        disabled={loading}
                                        title="Delete this hallucinated dimension"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            </div>
                        ))}
                        {rfq.features.length === 0 && <p className="text-sm text-muted">No features extracted.</p>}
                    </div>
                </div>

                <div className="card" style={{ backgroundColor: 'rgba(59, 130, 246, 0.05)', borderColor: 'rgba(59, 130, 246, 0.2)' }}>
                    <h3 className="mb-2">Development Head Review</h3>
                    <p className="text-sm text-secondary mb-6">
                        Review the generated balloons. Ensure all critical dimensions are captured correctly and there are no hallucinations before sending to the Feasibility Engine.
                    </p>

                    <div className="flex flex-col gap-3">
                        <button
                            className="btn btn-primary w-full"
                            style={{ justifyContent: 'center' }}
                            onClick={handleApprove}
                            disabled={loading || rfq.features.length === 0}
                        >
                            <CheckCircle size={18} /> Approve & Run Feasibility Engine
                        </button>
                        <button
                            className="btn btn-outline text-accent-red w-full"
                            style={{ justifyContent: 'center', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                            disabled={loading}
                        >
                            <XCircle size={18} /> Send Rejection / Notes
                        </button>
                    </div>
                </div>

            </div>

            {/* Add/Edit Modal */}
            {modalOpen && (
                <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
                    <div className="card" style={{ width: '400px' }}>
                        <h3 className="mb-4">{isEditing ? 'Edit Balloon' : 'Add Manual Balloon'}</h3>
                        <form onSubmit={handleModalSubmit} className="flex flex-col gap-4">
                            <div>
                                <label className="block text-sm mb-1 text-secondary">Balloon Number</label>
                                <input
                                    type="number"
                                    className="form-input w-full"
                                    value={formData.balloon_no}
                                    onChange={e => setFormData({ ...formData, balloon_no: e.target.value })}
                                    required
                                    min="1"
                                />
                            </div>
                            <div>
                                <label className="block text-sm mb-1 text-secondary">Specification (Text)</label>
                                <input
                                    type="text"
                                    className="form-input w-full"
                                    value={formData.specification}
                                    onChange={e => setFormData({ ...formData, specification: e.target.value })}
                                    placeholder="e.g. 10 ±0.1 or M8x1.25"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-sm mb-1 text-secondary">Feature Category</label>
                                <select
                                    className="form-input w-full"
                                    value={formData.description}
                                    onChange={e => setFormData({ ...formData, description: e.target.value })}
                                    required
                                >
                                    <option value="Outer Dia">Outer Dia</option>
                                    <option value="Slot Dia">Slot Dia</option>
                                    <option value="Undercut Dia">Undercut Dia</option>
                                    <option value="Length">Length</option>
                                    <option value="Slot width">Slot width</option>
                                    <option value="Threading">Threading</option>
                                    <option value="Chamfer">Chamfer</option>
                                    <option value="Surface roughness">Surface roughness</option>
                                    <option value="Angle">Angle</option>
                                    <option value="Radius">Radius</option>
                                    <option value="Note">Note/Other</option>
                                </select>
                            </div>

                            <div className="flex justify-end gap-3 mt-4">
                                <button type="button" className="btn btn-outline" onClick={() => setModalOpen(false)}>Cancel</button>
                                <button type="submit" className="btn btn-primary">{isEditing ? 'Save Changes' : 'Add Balloon'}</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
