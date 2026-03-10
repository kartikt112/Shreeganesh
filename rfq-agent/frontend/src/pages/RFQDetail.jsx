import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, RefreshCw, Download, FileSpreadsheet } from 'lucide-react';
import api from '../api/client';
import BallooningReview from '../components/BallooningReview';
import FeasibilityReview from '../components/FeasibilityReview';

export default function RFQDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [rfq, setRfq] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchRFQ();
        const interval = setInterval(fetchRFQ, 3000);
        return () => clearInterval(interval);
    }, [id]);

    const fetchRFQ = async () => {
        try {
            const res = await api.get(`/rfq/${id}`);
            setRfq(res.data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return <div className="p-8 text-center text-secondary">Loading RFQ Data...</div>;
    if (!rfq) return <div className="p-8 text-center text-accent-red">RFQ not found.</div>;

    return (
        <div>
            <div className="flex justify-between items-center mb-6">
                <button className="btn btn-outline text-secondary" onClick={() => navigate('/')}>
                    <ArrowLeft size={16} /> Back
                </button>
                <div className="flex items-center gap-3">
                    <span className="badge badge-parsing">{rfq.status}</span>
                </div>
            </div>

            <div className="card mb-6">
                <div className="flex justify-between">
                    <div>
                        <h1>{rfq.part_name}</h1>
                        <p className="text-secondary">{rfq.customer_name} • Part #{rfq.part_no || 'N/A'}</p>
                    </div>
                    <div className="text-right">
                        <p className="text-sm text-muted">Received</p>
                        <p className="font-medium">{new Date(rfq.received_at).toLocaleDateString()}</p>
                    </div>
                </div>
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
