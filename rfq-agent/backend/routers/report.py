"""
Report Router - Generate and download the Excel feasibility report
Supports two modes:
  1. AI Template Mode: Upload any Excel template → AI understands & fills it
  2. Default Mode: Generate report using built-in format
"""
import os
import sys
import shutil

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AI_DIR = os.path.join(_BACKEND_DIR, "ai")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
if _AI_DIR not in sys.path:
    sys.path.insert(0, _AI_DIR)

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db
from models import RFQ, DrawingFeature

router = APIRouter(prefix="/api/rfq", tags=["report"])
REPORTS_DIR = os.path.join(_BACKEND_DIR, "uploads", "reports")
TEMPLATES_DIR = os.path.join(_BACKEND_DIR, "uploads", "templates")


def _get_rfq_and_features(rfq_id: int, db: Session):
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
        "material": rfq.material or "",
    }

    feat_dicts = []
    for f in features:
        feat_dicts.append({
            "balloon_no": f.balloon_no,
            "description": f.description,
            "specification": f.specification,
            "criticality": f.criticality or "",
            "feature_type": f.feature_type or "",
            "proposed_machine": f.proposed_machine or "",
            "inhouse_outsource": f.inhouse_outsource or "Inhouse",
            "feasible": f.feasible or "Yes",
            "reason_not_feasible": f.reason_not_feasible or "",
            "deviation_required": f.deviation_required or "",
            "measuring_instrument": f.measuring_instrument or "",
            "inspection_inhouse": f.inspection_inhouse or "Inhouse",
            "inspection_frequency": f.inspection_frequency or "",
            "gauge_required": f.gauge_required or "",
            "remarks": f.remarks or "",
        })

    return rfq, rfq_data, feat_dicts


# ── Upload a template for an RFQ ──────────────────────────────────────────
@router.post("/{rfq_id}/template")
async def upload_template(
    rfq_id: int,
    template: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    ext = os.path.splitext(template.filename)[1]
    tpl_path = os.path.join(TEMPLATES_DIR, f"{rfq_id}_template{ext}")
    with open(tpl_path, "wb") as f:
        shutil.copyfileobj(template.file, f)

    rfq.template_path = tpl_path
    db.commit()

    return {"ok": True, "template_path": tpl_path, "message": f"Template uploaded for RFQ {rfq_id}"}


# ── Generate report (AI template or default) ─────────────────────────────
@router.post("/{rfq_id}/generate-report")
async def generate_report_endpoint(
    rfq_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Generate feasibility report. If RFQ has a template, uses AI agent.
    Otherwise uses default built-in format.
    """
    rfq, rfq_data, feat_dicts = _get_rfq_and_features(rfq_id, db)

    if not feat_dicts:
        raise HTTPException(status_code=400, detail="No features found. Run analysis first.")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"F-DEV-07_FEASIBILITY_{rfq.part_no or rfq_id}_{rfq.customer_name.replace(' ', '_')}.xlsx"
    output_path = os.path.join(REPORTS_DIR, filename)

    # Get ballooned image path
    ballooned_path = None
    if rfq.ballooned_image_path:
        bp = os.path.join(_BACKEND_DIR, rfq.ballooned_image_path.lstrip("/"))
        if os.path.exists(bp):
            ballooned_path = bp

    template_path = rfq.template_path

    # Check for a default template if none set
    default_template = os.path.join(_BACKEND_DIR, "feasibility_template.xlsx")
    if not template_path and os.path.exists(default_template):
        template_path = default_template

    if template_path and os.path.exists(template_path):
        # AI Template Mode
        background_tasks.add_task(
            _run_ai_report_generation,
            rfq_id, template_path, rfq_data, feat_dicts, output_path, ballooned_path
        )
        return {
            "ok": True,
            "mode": "ai_template",
            "message": f"AI feasibility report generation started for RFQ {rfq_id}",
            "report_filename": filename,
        }
    else:
        # Default Mode
        from report_generator import generate_report
        generate_report(rfq_data, feat_dicts, output_path)
        return {
            "ok": True,
            "mode": "default",
            "message": f"Report generated for RFQ {rfq_id}",
            "report_filename": filename,
        }


def _run_ai_report_generation(
    rfq_id: int,
    template_path: str,
    rfq_data: dict,
    features: list,
    output_path: str,
    ballooned_image_path: str = None,
):
    """Background task for AI report generation."""
    try:
        from feasibility_report_agent import generate_feasibility_report
        generate_feasibility_report(
            template_path=template_path,
            rfq_data=rfq_data,
            features=features,
            output_path=output_path,
            ballooned_image_path=ballooned_image_path,
        )
        print(f"[Report] AI report generation complete for RFQ {rfq_id}")
    except Exception as e:
        print(f"[Report] ERROR generating AI report for RFQ {rfq_id}: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to default report
        try:
            print(f"[Report] Falling back to default report format...")
            from report_generator import generate_report
            generate_report(rfq_data, features, output_path)
            print(f"[Report] Default report generated as fallback")
        except Exception as e2:
            print(f"[Report] Fallback also failed: {e2}")


# ── Download generated report ─────────────────────────────────────────────
@router.get("/{rfq_id}/report")
def download_report(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    # Check if report already exists
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"F-DEV-07_FEASIBILITY_{rfq.part_no or rfq_id}_{rfq.customer_name.replace(' ', '_')}.xlsx"
    output_path = os.path.join(REPORTS_DIR, filename)

    if os.path.exists(output_path):
        return FileResponse(
            path=output_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # Generate on-the-fly if not exists
    _, rfq_data, feat_dicts = _get_rfq_and_features(rfq_id, db)

    template_path = rfq.template_path
    default_template = os.path.join(_BACKEND_DIR, "feasibility_template.xlsx")
    if not template_path and os.path.exists(default_template):
        template_path = default_template

    if template_path and os.path.exists(template_path):
        from feasibility_report_agent import generate_feasibility_report
        ballooned_path = None
        if rfq.ballooned_image_path:
            bp = os.path.join(_BACKEND_DIR, rfq.ballooned_image_path.lstrip("/"))
            if os.path.exists(bp):
                ballooned_path = bp
        generate_feasibility_report(
            template_path=template_path,
            rfq_data=rfq_data,
            features=feat_dicts,
            output_path=output_path,
            ballooned_image_path=ballooned_path,
        )
    else:
        from report_generator import generate_report
        generate_report(rfq_data, feat_dicts, output_path)

    return FileResponse(
        path=output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
