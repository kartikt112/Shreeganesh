"""
Features Router - Adding/Deleting features manually during review
Triggers an immediate redraw of the ballooned image.
"""
import os
import json
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
from models import RFQ, DrawingFeature
from schemas import DrawingFeatureCreate, DrawingFeatureOut
from ai.balloon_generator import generate_ballooned_image

router = APIRouter(prefix="/api/rfq/{rfq_id}/features", tags=["features"])
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

class ManualFeatureCreate(BaseModel):
    box_2d: str   # Expected to be a JSON string like "[ymin, xmin, ymax, xmax]"
    description: Optional[str] = "Manual Add"
    specification: Optional[str] = "Manual Add"
    criticality: Optional[str] = "normal"
    feature_type: Optional[str] = "NOTE"
    balloon_no: Optional[int] = None

class ManualFeatureUpdate(BaseModel):
    balloon_no: Optional[int] = None
    description: Optional[str] = None
    specification: Optional[str] = None
    feature_type: Optional[str] = None

class BulkFeature(BaseModel):
    balloon_no: int
    specification: Optional[str] = ""
    description: Optional[str] = ""
    feature_type: Optional[str] = "OTHER"
    box_2d: Optional[List] = None

class BulkSaveRequest(BaseModel):
    features: List[BulkFeature]

def redraw_balloons(rfq: RFQ, db: Session):
    # Get all features currently in DB for this RFQ (preserve their custom numbers!)
    features = db.query(DrawingFeature).filter(DrawingFeature.rfq_id == rfq.id).order_by(DrawingFeature.balloon_no.asc()).all()

    # Re-fetch after sorting
    features = db.query(DrawingFeature).filter(DrawingFeature.rfq_id == rfq.id).order_by(DrawingFeature.balloon_no.asc()).all()
    
    # Prepare list for balloon generator
    feat_dicts = []
    for f in features:
        d = {
            "balloon_no": f.balloon_no,
            "description": f.description,
            "specification": f.specification,
            "box_2d": json.loads(f.box_2d) if f.box_2d else None
        }
        feat_dicts.append(d)
        
    # Redraw image
    if rfq.drawing_image_path:
        # absolute physical filename
        png_path = os.path.join(UPLOAD_DIR, "drawings", f"{rfq.id}_drawing.png")
        balloon_path = os.path.join(UPLOAD_DIR, "ballooned", f"{rfq.id}_ballooned.png")
        if os.path.exists(png_path):
            generate_ballooned_image(png_path, feat_dicts, balloon_path)


@router.post("", response_model=DrawingFeatureOut)
def add_feature(rfq_id: int, manual_feat: ManualFeatureCreate, db: Session = Depends(get_db)):
    """
    Manually add a balloon/feature. Recalculates balloon numbers and redraws the image.
    """
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
        
    next_num = manual_feat.balloon_no
    if next_num is None:
        max_feat = db.query(DrawingFeature).filter(DrawingFeature.rfq_id == rfq_id).order_by(DrawingFeature.balloon_no.desc()).first()
        next_num = (max_feat.balloon_no + 1) if max_feat else 1
    
    new_feat = DrawingFeature(
        rfq_id=rfq_id,
        balloon_no=next_num,
        box_2d=manual_feat.box_2d,
        description=manual_feat.description,
        specification=manual_feat.specification,
        criticality=manual_feat.criticality,
        feature_type=manual_feat.feature_type,
        proposed_machine="MANUAL REVIEW",
        inhouse_outsource="Inhouse",
        feasible="Yes",
    )
    db.add(new_feat)
    db.commit()
    db.refresh(new_feat)
    
    # Trigger redraw
    redraw_balloons(rfq, db)
    db.refresh(new_feat)
    return new_feat

@router.delete("/{feat_id}")
def delete_feature(rfq_id: int, feat_id: int, db: Session = Depends(get_db)):
    """
    Manually delete a feature. Recalculates numbering and redraws the image.
    """
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
        
    feat = db.query(DrawingFeature).filter(DrawingFeature.id == feat_id, DrawingFeature.rfq_id == rfq_id).first()
    if not feat:
        raise HTTPException(status_code=404, detail="Feature not found")
        
    db.delete(feat)
    db.commit()
    
    # Re-number and trigger redraw
    redraw_balloons(rfq, db)
    
    return {"ok": True, "message": "Deleted and image redrawn."}


@router.patch("/{feat_id}", response_model=DrawingFeatureOut)
def update_feature(rfq_id: int, feat_id: int, update_data: ManualFeatureUpdate, db: Session = Depends(get_db)):
    """
    Update a specific feature's details (e.g. change its balloon number or specification).
    """
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
        
    feat = db.query(DrawingFeature).filter(DrawingFeature.id == feat_id, DrawingFeature.rfq_id == rfq_id).first()
    if not feat:
        raise HTTPException(status_code=404, detail="Feature not found")

    if update_data.balloon_no is not None:
        feat.balloon_no = update_data.balloon_no
    if update_data.specification is not None:
        feat.specification = update_data.specification
    if update_data.description is not None:
        feat.description = update_data.description
        
    db.commit()
    db.refresh(feat)
    
    # Redraw standard balloon image if number changed
    if update_data.balloon_no is not None or update_data.specification is not None:
        redraw_balloons(rfq, db)

    return feat


@router.put("/bulk")
def bulk_save_features(rfq_id: int, payload: BulkSaveRequest, db: Session = Depends(get_db)):
    """
    Replace all features for an RFQ with the editor's current state.
    Called when the user exits the balloon editor to sync changes back.
    """
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    # Delete existing features
    db.query(DrawingFeature).filter(DrawingFeature.rfq_id == rfq_id).delete()

    # Insert new features from editor
    for f in payload.features:
        box_2d_str = json.dumps(f.box_2d) if f.box_2d else None
        db.add(DrawingFeature(
            rfq_id=rfq_id,
            balloon_no=f.balloon_no,
            specification=f.specification or "",
            description=f.description or "",
            feature_type=f.feature_type or "OTHER",
            box_2d=box_2d_str,
            criticality="normal",
            proposed_machine="PENDING REVIEW",
            inhouse_outsource="Inhouse",
            feasible="Yes",
        ))

    db.commit()

    # Redraw ballooned image
    redraw_balloons(rfq, db)

    return {"ok": True, "message": f"Saved {len(payload.features)} features from editor"}
