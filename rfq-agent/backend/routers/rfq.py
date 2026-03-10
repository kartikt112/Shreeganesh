"""
RFQ Router - CRUD operations
"""
import os
import shutil
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
import json

from database import get_db
from models import RFQ, DrawingFeature, RFQStatus
from schemas import RFQCreate, RFQUpdate, RFQOut

router = APIRouter(prefix="/api/rfq", tags=["rfq"])
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")


@router.post("", response_model=RFQOut)
async def create_rfq(
    customer_name: str = Form(...),
    part_name: str = Form(...),
    part_no: Optional[str] = Form(None),
    drg_rev: Optional[str] = Form(None),
    quantity: Optional[int] = Form(None),
    material: Optional[str] = Form(None),
    drawing: UploadFile = File(...),
    template: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    rfq_id = str(uuid.uuid4())[:8]
    # Save drawing
    drawing_dir = os.path.join(UPLOAD_DIR, "drawings")
    os.makedirs(drawing_dir, exist_ok=True)
    ext = os.path.splitext(drawing.filename)[1]
    drawing_path = os.path.join(drawing_dir, f"{rfq_id}{ext}")
    with open(drawing_path, "wb") as f:
        shutil.copyfileobj(drawing.file, f)

    template_path = None
    if template and template.filename:
        tpl_dir = os.path.join(UPLOAD_DIR, "templates")
        os.makedirs(tpl_dir, exist_ok=True)
        tpl_ext = os.path.splitext(template.filename)[1]
        template_path = os.path.join(tpl_dir, f"{rfq_id}{tpl_ext}")
        with open(template_path, "wb") as f:
            shutil.copyfileobj(template.file, f)

    rfq = RFQ(
        customer_name=customer_name,
        part_name=part_name,
        part_no=part_no,
        drg_rev=drg_rev,
        quantity=quantity,
        material=material,
        status=RFQStatus.NEW,
        drawing_path=drawing_path,
        template_path=template_path,
    )
    db.add(rfq)
    db.commit()
    db.refresh(rfq)
    return rfq


@router.get("", response_model=List[RFQOut])
def list_rfqs(db: Session = Depends(get_db)):
    return db.query(RFQ).order_by(RFQ.received_at.desc()).all()


@router.get("/{rfq_id}", response_model=RFQOut)
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return rfq


@router.patch("/{rfq_id}", response_model=RFQOut)
def update_rfq(rfq_id: int, update: RFQUpdate, db: Session = Depends(get_db)):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    for k, v in update.dict(exclude_none=True).items():
        setattr(rfq, k, v)
    db.commit()
    db.refresh(rfq)
    return rfq


@router.patch("/{rfq_id}/features/{feat_id}")
def update_feature(rfq_id: int, feat_id: int, data: dict, db: Session = Depends(get_db)):
    feat = db.query(DrawingFeature).filter(
        DrawingFeature.id == feat_id, DrawingFeature.rfq_id == rfq_id
    ).first()
    if not feat:
        raise HTTPException(status_code=404, detail="Feature not found")
    for k, v in data.items():
        if hasattr(feat, k):
            setattr(feat, k, v)
    db.commit()
    db.refresh(feat)
    return {"ok": True}


@router.delete("/{rfq_id}")
def delete_rfq(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    db.delete(rfq)
    db.commit()
    return {"ok": True}
