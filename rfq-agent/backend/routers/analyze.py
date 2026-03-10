"""
Analyze Router - Triggers the full AI pipeline:
1. PDF → PNG (PyMuPDF)
2. PNG → Gemini features (Drawing Parser)
3. Features → Nano Banana balloon image
4. Features → Feasibility processing
5. Save everything to DB, update status to BALLOONING_REVIEW
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "ai"))

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from database import get_db
from models import RFQ, DrawingFeature, RFQStatus
from schemas import RFQOut

router = APIRouter(prefix="/api/rfq", tags=["analyze"])

def _get_api_key():
    from dotenv import load_dotenv
    load_dotenv()
    return os.getenv("ANTHROPIC_API_KEY", "")


async def run_pipeline(rfq_id: int):
    """Background task: run full AI pipeline for an RFQ."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
        if not rfq:
            return

        api_key = _get_api_key()
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

        # ── Step 1: PDF → PNG ─────────────────────────────────────────────────
        rfq.status = RFQStatus.PARSING
        db.commit()

        drawing_path = rfq.drawing_path
        png_path = os.path.join(upload_dir, "drawings", f"{rfq_id}_drawing.png")

        if drawing_path and drawing_path.lower().endswith(".pdf"):
            from drawing_parser import pdf_to_png
            pdf_to_png(drawing_path, png_path)
        elif drawing_path and os.path.exists(drawing_path):
            # Already an image (jpg/png)
            import shutil
            shutil.copy(drawing_path, png_path)
        else:
            # Create placeholder
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (800, 600), "white")
            d = ImageDraw.Draw(img)
            d.text((100, 280), "No drawing uploaded — Mock Mode", fill="gray")
            img.save(png_path)

        rfq.drawing_image_path = f"/uploads/drawings/{rfq_id}_drawing.png"
        db.commit()

        # ── Step 2: Gemini → Extract features ────────────────────────────────
        from drawing_parser import parse_drawing
        raw_features = parse_drawing(png_path, api_key, original_path=drawing_path)

        # ── Step 3: Nano Banana → Draft Ballooned image ──────────────────────
        ballooned_path = os.path.join(upload_dir, "ballooned", f"{rfq_id}_ballooned.png")
        os.makedirs(os.path.dirname(ballooned_path), exist_ok=True)
        from balloon_generator import generate_ballooned_image
        generate_ballooned_image(png_path, raw_features, ballooned_path, api_key)

        # ── Step 4: AI QA Layer (Self-Correction) ─────────────────────────
        # We pass the draft balloons to the "Best Mechanical Engineer" layer
        from balloon_reviewer import review_balloons
        corrected_features = review_balloons(ballooned_path, raw_features, api_key)

        # ── Step 5: Regenerate Final Balloons (if corrections made) ──────────
        # By drawing again, we ensure any deleted or re-numbered balloons perfectly match the new DB state
        generate_ballooned_image(png_path, corrected_features, ballooned_path, api_key)

        # ── Step 6: Feasibility engine (on corrected data) ───────────────────
        rfq.status = RFQStatus.BALLOONING
        db.commit()

        from feasibility_engine import process_features
        processed = process_features(corrected_features, db)

        # Save finalized features to DB
        import json
        db.query(DrawingFeature).filter(DrawingFeature.rfq_id == rfq_id).delete()
        for feat in processed:
            if "box_2d" in feat and isinstance(feat["box_2d"], list):
                feat["box_2d"] = json.dumps(feat["box_2d"])
            elif "box_2d" not in feat:
                feat["box_2d"] = None
                
            if "criticality_hint" in feat: del feat["criticality_hint"]
            db.add(DrawingFeature(rfq_id=rfq_id, **feat))
        db.commit()

        rfq.ballooned_image_path = f"/uploads/ballooned/{rfq_id}_ballooned.png"
        rfq.status = RFQStatus.BALLOONING_REVIEW
        db.commit()
        print(f"[Pipeline] RFQ {rfq_id} ready for BALLOONING_REVIEW ✅")

    except Exception as e:
        print(f"[Pipeline] Error for RFQ {rfq_id}: {e}")
        try:
            rfq.status = RFQStatus.NEW
            rfq.notes = f"Pipeline error: {str(e)}"
            db.commit()
        except:
            pass
    finally:
        db.close()


@router.post("/{rfq_id}/analyze")
async def trigger_analysis(
    rfq_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if rfq.status not in [RFQStatus.NEW, RFQStatus.PARSING]:
        raise HTTPException(status_code=400, detail=f"Cannot re-analyze RFQ in status {rfq.status}")

    background_tasks.add_task(run_pipeline, rfq_id)
    return {"message": "Analysis started", "rfq_id": rfq_id}
