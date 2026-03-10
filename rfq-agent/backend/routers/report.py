"""
Report Router - Generate and download the Excel feasibility report
"""
import os
import sys

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AI_DIR = os.path.join(_BACKEND_DIR, "ai")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
if _AI_DIR not in sys.path:
    sys.path.insert(0, _AI_DIR)

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db
from models import RFQ, DrawingFeature

router = APIRouter(prefix="/api/rfq", tags=["report"])
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "reports")


@router.get("/{rfq_id}/report")
def download_report(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    features = db.query(DrawingFeature).filter(
        DrawingFeature.rfq_id == rfq_id
    ).order_by(DrawingFeature.balloon_no).all()

    rfq_data = {
        "part_name": rfq.part_name,
        "part_no": rfq.part_no or "",
        "customer_name": rfq.customer_name,
        "drg_rev": rfq.drg_rev or "",
        "quantity": rfq.quantity,
    }

    feat_dicts = []
    for f in features:
        feat_dicts.append({
            "balloon_no": f.balloon_no,
            "description": f.description,
            "specification": f.specification,
            "criticality": f.criticality,
            "proposed_machine": f.proposed_machine,
            "inhouse_outsource": f.inhouse_outsource,
            "feasible": f.feasible,
            "reason_not_feasible": f.reason_not_feasible,
            "deviation_required": f.deviation_required,
            "measuring_instrument": f.measuring_instrument,
            "inspection_inhouse": f.inspection_inhouse,
            "inspection_frequency": f.inspection_frequency,
            "gauge_required": f.gauge_required,
            "remarks": f.remarks,
        })

    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"F-DEV-07_FEASIBILITY_{rfq.part_no or rfq_id}_{rfq.customer_name.replace(' ','_')}.xlsx"
    output_path = os.path.join(REPORTS_DIR, filename)

    from report_generator import generate_report
    generate_report(rfq_data, feat_dicts, output_path)

    return FileResponse(
        path=output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
