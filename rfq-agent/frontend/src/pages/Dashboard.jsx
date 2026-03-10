import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, ArrowRight, FileText, Clock, Settings, FileCheck, CheckCircle2 } from 'lucide-react';
import api from '../api/client';

const PIPELINE_STAGES = [
    { id: 'NEW', label: 'Inbox', icon: <FileText size={16} /> },
    { id: 'PARSING', label: 'AI Extraction', icon: <Settings size={16} /> },
    { id: 'BALLOONING', label: 'AI Ballooning', icon: <Settings size={16} /> },
    { id: 'BALLOONING_REVIEW', label: 'Drawing Review', icon: <FileCheck size={16} className="text-purple-400" /> },
    { id: 'FEASIBILITY_GENERATION', label: 'Engine Running', icon: <Settings size={16} /> },
    { id: 'FEASIBILITY_REVIEW', label: 'Feasibility Review', icon: <FileCheck size={16} className="text-purple-400" /> },
    { id: 'COSTING', label: 'Costing', icon: <Clock size={16} /> },
    { id: 'QUOTE_SENT', label: 'Quote Sent', icon: <CheckCircle2 size={16} className="text-emerald-400" /> }
];

function RFQCard({ rfq }) {
    const navigate = useNavigate();
    return (
        <div
            className="card mb-4"
            style={{ cursor: 'pointer', padding: '16px' }}
            onClick={() => navigate(`/rfq/${rfq.id}`)}
        >
            <div className="flex justify-between items-start mb-2">
                <h4 style={{ fontSize: '1rem', margin: 0 }}>{rfq.part_name}</h4>
                <span className="text-xs text-muted">#{rfq.id}</span>
            </div>
            <p className="text-sm text-secondary mb-4">{rfq.customer_name}</p>

            <div className="flex items-center justify-between mt-4 border-t pt-3" style={{ borderColor: 'var(--border-color)' }}>
                <div className="text-xs text-muted flex items-center gap-1">
                    <Clock size={12} /> {new Date(rfq.received_at).toLocaleDateString()}
                </div>
                <ArrowRight size={14} className="text-secondary" />
            </div>
        </div>
    );
}

export default function Dashboard() {
    const [rfqs, setRfqs] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchRFQs();
        // Auto-refresh dashboard every 5 seconds for smooth pipeline monitoring
        const interval = setInterval(fetchRFQs, 5000);
        return () => clearInterval(interval);
    }, []);

    const fetchRFQs = async () => {
        try {
            const res = await api.get('/rfq');
            setRfqs(res.data);
        } catch (err) {
            console.error("Failed to load RFQs", err);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return <div className="text-center mt-12 text-secondary">Loading Pipeline...</div>;

    return (
        <div>
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1>RFQ Pipeline Status</h1>
                    <p className="text-secondary">Track jobs from drawing abstraction through final costing.</p>
                </div>
                <Link to="/new" className="btn btn-primary">
                    <Plus size={18} /> New RFQ
                </Link>
            </div>

            <div className="kanban-board" style={{
                display: 'flex',
                gap: '24px',
                overflowX: 'auto',
                paddingBottom: '24px',
                minHeight: '600px'
            }}>
                {PIPELINE_STAGES.map(stage => {
                    const stageRfqs = rfqs.filter(r => r.status === stage.id);

                    return (
                        <div key={stage.id} style={{ minWidth: '320px', flex: '0 0 auto' }}>
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="flex items-center gap-2 text-sm" style={{ margin: 0 }}>
                                    <span style={{ color: 'var(--text-secondary)' }}>{stage.icon}</span>
                                    {stage.label}
                                </h3>
                                <span className="badge" style={{ backgroundColor: 'var(--bg-elevated)' }}>
                                    {stageRfqs.length}
                                </span>
                            </div>

                            <div
                                style={{
                                    backgroundColor: 'rgba(26, 29, 36, 0.5)',
                                    borderRadius: 'var(--radius-lg)',
                                    padding: '16px',
                                    minHeight: '100px',
                                    border: '1px dashed var(--border-color)'
                                }}
                            >
                                {stageRfqs.length === 0 ? (
                                    <div className="text-center text-muted text-sm py-8">No RFQs</div>
                                ) : (
                                    stageRfqs.map(rfq => <RFQCard key={rfq.id} rfq={rfq} />)
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
