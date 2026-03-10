import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, FileText, Settings, ArrowLeft } from 'lucide-react';
import api from '../api/client';

export default function NewRFQ() {
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [formData, setFormData] = useState({
        customer_name: '',
        part_name: '',
        part_no: '',
        material: '',
        quantity: ''
    });
    const [drawing, setDrawing] = useState(null);

    const handleInputChange = (e) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files.length > 0) {
            setDrawing(e.target.files[0]);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!drawing) {
            alert("Please upload an engineering drawing PDF.");
            return;
        }

        setLoading(true);
        try {
            const data = new FormData();
            Object.keys(formData).forEach(key => {
                if (formData[key]) data.append(key, formData[key]);
            });
            data.append('drawing', drawing);

            const res = await api.post('/rfq', data, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });

            const rfqId = res.data.id;

            // Trigger AI Analysis Pipeline immediately after creation
            await api.post(`/rfq/${rfqId}/analyze`);

            // Navigate to dashboard
            navigate('/');

        } catch (err) {
            console.error("Failed to create RFQ", err);
            alert("Error submitting RFQ: " + (err.response?.data?.detail || err.message));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ maxWidth: '800px', margin: '0 auto' }}>
            <button
                className="btn btn-outline mb-6 text-secondary"
                onClick={() => navigate('/')}
                disabled={loading}
            >
                <ArrowLeft size={16} /> Back to Dashboard
            </button>

            <div className="card">
                <h2 className="flex items-center gap-2 mb-6">
                    <Upload className="text-accent-blue" /> Submit New RFQ
                </h2>

                <form onSubmit={handleSubmit}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '24px' }}>
                        <div className="form-group mb-0">
                            <label className="form-label">Customer Name *</label>
                            <input
                                type="text"
                                name="customer_name"
                                required
                                className="form-input"
                                value={formData.customer_name}
                                onChange={handleInputChange}
                                placeholder="e.g. Kongsberg Automotive"
                            />
                        </div>
                        <div className="form-group mb-0">
                            <label className="form-label">Part Name *</label>
                            <input
                                type="text"
                                name="part_name"
                                required
                                className="form-input"
                                value={formData.part_name}
                                onChange={handleInputChange}
                                placeholder="e.g. Ball Stud"
                            />
                        </div>
                        <div className="form-group mb-0">
                            <label className="form-label">Part Number</label>
                            <input
                                type="text"
                                name="part_no"
                                className="form-input"
                                value={formData.part_no}
                                onChange={handleInputChange}
                                placeholder="e.g. 1001540840"
                            />
                        </div>
                        <div className="form-group mb-0">
                            <label className="form-label">Quantity</label>
                            <input
                                type="number"
                                name="quantity"
                                className="form-input"
                                value={formData.quantity}
                                onChange={handleInputChange}
                                placeholder="e.g. 5000"
                            />
                        </div>
                    </div>

                    <div className="form-group">
                        <label className="form-label">Engineering Drawing PDF *</label>
                        <div
                            style={{
                                border: '2px dashed var(--border-color)',
                                padding: '40px',
                                textAlign: 'center',
                                borderRadius: 'var(--radius-md)',
                                backgroundColor: 'rgba(26, 29, 36, 0.4)'
                            }}
                        >
                            <FileText size={48} className="text-secondary mb-4 mx-auto" />
                            <div className="mb-4">
                                {drawing ? (
                                    <span className="text-accent-blue font-medium">{drawing.name}</span>
                                ) : (
                                    <span className="text-muted">No file selected</span>
                                )}
                            </div>
                            <label className="btn btn-outline" style={{ display: 'inline-flex' }}>
                                Browse Files
                                <input
                                    type="file"
                                    accept=".pdf,.png,.jpg,.jpeg"
                                    onChange={handleFileChange}
                                    required
                                    style={{ display: 'none' }}
                                />
                            </label>
                            <p className="text-xs text-muted mt-4">Takes a master PDF or flat image. Max 10MB.</p>
                        </div>
                    </div>

                    <div className="flex justify-end gap-4 mt-8 pt-6 border-t" style={{ borderColor: 'var(--border-color)' }}>
                        <button
                            type="button"
                            className="btn btn-outline"
                            onClick={() => navigate('/')}
                            disabled={loading}
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="btn btn-primary"
                            disabled={loading || !drawing}
                        >
                            {loading ? (
                                <><Settings className="animate-spin" size={16} /> Parsing File & Starting AI...</>
                            ) : (
                                <>Submit & Start Analysis <ArrowLeft style={{ transform: 'rotate(180deg)' }} size={16} /></>
                            )}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
