from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class DrawingFeatureBase(BaseModel):
    balloon_no: int
    description: Optional[str] = None
    specification: Optional[str] = None
    criticality: Optional[str] = None
    feature_type: Optional[str] = None
    proposed_machine: Optional[str] = None
    inhouse_outsource: Optional[str] = "Inhouse"
    feasible: Optional[str] = "Yes"
    reason_not_feasible: Optional[str] = None
    deviation_required: Optional[str] = None
    box_2d: Optional[str] = None
    measuring_instrument: Optional[str] = None
    inspection_inhouse: Optional[str] = "Inhouse"
    inspection_frequency: Optional[str] = None
    gauge_required: Optional[str] = None
    remarks: Optional[str] = None

class DrawingFeatureCreate(DrawingFeatureBase):
    rfq_id: int

class DrawingFeatureUpdate(DrawingFeatureBase):
    pass

class DrawingFeatureOut(DrawingFeatureBase):
    id: int
    rfq_id: int
    class Config:
        from_attributes = True

class RFQCreate(BaseModel):
    customer_name: str
    part_name: str
    part_no: Optional[str] = None
    drg_rev: Optional[str] = None
    quantity: Optional[int] = None
    material: Optional[str] = None

class RFQUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None

class RFQOut(BaseModel):
    id: int
    customer_name: str
    part_name: str
    part_no: Optional[str] = None
    drg_rev: Optional[str] = None
    quantity: Optional[int] = None
    material: Optional[str] = None
    status: str
    received_at: datetime
    drawing_path: Optional[str] = None
    drawing_image_path: Optional[str] = None
    ballooned_image_path: Optional[str] = None
    notes: Optional[str] = None
    features: List[DrawingFeatureOut] = []
    class Config:
        from_attributes = True

class ReviewCreate(BaseModel):
    stage: str
    action: str   # approved / revision_requested
    comment: Optional[str] = None
    reviewed_by: Optional[str] = None

class ReviewOut(BaseModel):
    id: int
    rfq_id: int
    stage: str
    action: str
    comment: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: datetime
    class Config:
        from_attributes = True

class MachineOut(BaseModel):
    id: int
    name: str
    working_limit: Optional[str] = None
    parameter: Optional[str] = None
    operation_name: str
    achievable_tolerance: Optional[str] = None
    measuring_instrument: Optional[str] = None
    available: bool
    class Config:
        from_attributes = True

class InstrumentOut(BaseModel):
    id: int
    parameter: str
    tolerance: Optional[str] = None
    name: str
    instrument_range: Optional[str] = None
    available: bool
    class Config:
        from_attributes = True
