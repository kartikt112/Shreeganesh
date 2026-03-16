"""
Review Router - Two-stage dev team review gates:
Stage 1 (BALLOONING_REVIEW): approve balloon → trigger feasibility → FEASIBILITY_REVIEW
                              revision → re-run balloon
Stage 2 (FEASIBILITY_REVIEW): approve → COSTING
                               revision → re-run feasibility
"""
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "ai"))

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import RFQ, ReviewRecord, RFQStatus, DrawingFeature
from schemas import ReviewCreate, ReviewOut

router = APIRouter(prefix="/api/rfq", tags=["review"])


def _get_api_key():
    from dotenv import load_dotenv
    load_dotenv()
    return os.getenv("ANTHROPIC_API_KEY", "")


def _load_manufacturing_metadata(rfq_id: int) -> dict:
    """Load saved manufacturing_metadata JSON for an RFQ (if available)."""
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    metadata_path = os.path.join(upload_dir, "drawings", f"{rfq_id}_metadata.json")
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            return json.load(f)
    return {}


@router.post("/{rfq_id}/review", response_model=ReviewOut)
async def submit_review(
    rfq_id: int,
    review: ReviewCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    # Save review record
    record = ReviewRecord(
        rfq_id=rfq_id,
        stage=review.stage,
        action=review.action,
        comment=review.comment,
        reviewed_by=review.reviewed_by,
        reviewed_at=datetime.utcnow()
    )
    db.add(record)

    # ── BALLOONING REVIEW ─────────────────────────────────────────────────────
    if review.stage == "BALLOONING":
        if review.action == "approved":
            rfq.status = RFQStatus.FEASIBILITY_REVIEW
            db.commit()
            db.refresh(record)
            return record
        elif review.action == "revision_requested":
            rfq.status = RFQStatus.BALLOONING
            rfq.notes = f"Balloon revision requested: {review.comment}"
            db.commit()
            db.refresh(record)
            # Re-run pipeline from balloon step
            background_tasks.add_task(_rerun_balloon, rfq_id, review.comment)
            return record

    # ── FEASIBILITY REVIEW ────────────────────────────────────────────────────
    elif review.stage == "FEASIBILITY":
        if review.action == "approved":
            rfq.status = RFQStatus.COSTING
            db.commit()
            db.refresh(record)
            return record
        elif review.action == "revision_requested":
            rfq.status = RFQStatus.FEASIBILITY_GENERATION
            rfq.notes = f"Feasibility revision requested: {review.comment}"
            db.commit()
            db.refresh(record)
            background_tasks.add_task(_rerun_feasibility, rfq_id, review.comment)
            return record

    db.commit()
    db.refresh(record)
    return record


async def _rerun_balloon(rfq_id: int, notes: str = ""):
    """Re-run the balloon step for a revision."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
        if not rfq or not rfq.drawing_image_path:
            return

        api_key = _get_api_key()
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
        png_path = os.path.join(upload_dir, "drawings", f"{rfq_id}_drawing.png")
        ballooned_path = os.path.join(upload_dir, "ballooned", f"{rfq_id}_ballooned.png")

        features = []
        for f in db.query(DrawingFeature).filter(DrawingFeature.rfq_id == rfq_id).all():
            feat = {
                "balloon_no": f.balloon_no,
                "description": f.description,
                "specification": f.specification,
                "feature_type": f.feature_type,
            }
            if f.box_2d:
                try:
                    feat["box_2d"] = json.loads(f.box_2d)
                except json.JSONDecodeError:
                    pass
            features.append(feat)

        from balloon_generator import generate_ballooned_image
        generate_ballooned_image(png_path, features, ballooned_path, api_key)

        rfq.ballooned_image_path = f"/uploads/ballooned/{rfq_id}_ballooned.png"
        rfq.status = RFQStatus.BALLOONING_REVIEW
        db.commit()
    except Exception as e:
        print(f"[RerunBalloon] Error: {e}")
    finally:
        db.close()


async def _rerun_feasibility(rfq_id: int, notes: str = ""):
    """Re-run feasibility engine with reviewer notes and manufacturing_metadata."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
        if not rfq:
            return

        # Load manufacturing_metadata from disk (saved during initial extraction)
        manufacturing_metadata = _load_manufacturing_metadata(rfq_id)

        features = db.query(DrawingFeature).filter(DrawingFeature.rfq_id == rfq_id).all()
        raw = []
        for f in features:
            feat = {
                "balloon_no": f.balloon_no,
                "description": f.description,
                "specification": f.specification,
                "feature_type": f.feature_type,
                "criticality_hint": "normal",
            }
            if f.box_2d:
                try:
                    feat["box_2d"] = json.loads(f.box_2d)
                except json.JSONDecodeError:
                    pass
            raw.append(feat)

        from feasibility_engine import process_features
        processed = process_features(raw, db, manufacturing_metadata=manufacturing_metadata)

        db.query(DrawingFeature).filter(DrawingFeature.rfq_id == rfq_id).delete()
        for feat in processed:
            if "box_2d" in feat and isinstance(feat["box_2d"], list):
                feat["box_2d"] = json.dumps(feat["box_2d"])
            elif "box_2d" not in feat:
                feat["box_2d"] = None
            keys_to_remove = ["criticality_hint"]
            cleaned = {k: v for k, v in feat.items() if k not in keys_to_remove}
            db.add(DrawingFeature(rfq_id=rfq_id, **cleaned))

        rfq.status = RFQStatus.FEASIBILITY_REVIEW
        db.commit()
    except Exception as e:
        print(f"[RerunFeasibility] Error: {e}")
    finally:
        db.close()
