from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

class RFQStatus(str, enum.Enum):
    NEW = "NEW"
    PARSING = "PARSING"
    BALLOONING = "BALLOONING"
    BALLOONING_REVIEW = "BALLOONING_REVIEW"
    FEASIBILITY_GENERATION = "FEASIBILITY_GENERATION"
    FEASIBILITY_REVIEW = "FEASIBILITY_REVIEW"
    COSTING = "COSTING"
    QUOTE_SENT = "QUOTE_SENT"

class ReviewStage(str, enum.Enum):
    BALLOONING = "BALLOONING"
    FEASIBILITY = "FEASIBILITY"

class ReviewAction(str, enum.Enum):
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"

class RFQ(Base):
    __tablename__ = "rfqs"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, nullable=False)
    part_name = Column(String, nullable=False)
    part_no = Column(String, nullable=True)
    drg_rev = Column(String, nullable=True)
    quantity = Column(Integer, nullable=True)
    material = Column(String, nullable=True)
    status = Column(String, default=RFQStatus.NEW)
    received_at = Column(DateTime, default=datetime.utcnow)
    drawing_path = Column(String, nullable=True)
    drawing_image_path = Column(String, nullable=True)   # PNG of the drawing
    template_path = Column(String, nullable=True)
    ballooned_image_path = Column(String, nullable=True) # Nano Banana output
    notes = Column(Text, nullable=True)
    features = relationship("DrawingFeature", back_populates="rfq", cascade="all, delete-orphan")
    reviews = relationship("ReviewRecord", back_populates="rfq", cascade="all, delete-orphan")

class DrawingFeature(Base):
    __tablename__ = "drawing_features"
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False)
    balloon_no = Column(Integer, nullable=False)
    description = Column(String, nullable=True)           # e.g. "Total Length", "OD", "ID"
    specification = Column(String, nullable=True)         # e.g. "87 ±0.5", "Ø11.8 ±0.05"
    criticality = Column(String, nullable=True)           # I / SC / CR / ""
    feature_type = Column(String, nullable=True)          # OD/ID/Thread/Length/etc.
    proposed_machine = Column(String, nullable=True)
    inhouse_outsource = Column(String, default="Inhouse") # Inhouse / Outsource
    feasible = Column(String, default="Yes")              # Yes / No
    reason_not_feasible = Column(String, nullable=True)
    deviation_required = Column(String, nullable=True)
    box_2d = Column(String, nullable=True)                # e.g. "[ymin, xmin, ymax, xmax]"
    measuring_instrument = Column(String, nullable=True)
    inspection_inhouse = Column(String, default="Inhouse")
    inspection_frequency = Column(String, nullable=True)
    gauge_required = Column(String, nullable=True)
    remarks = Column(Text, nullable=True)
    rfq = relationship("RFQ", back_populates="features")

class ReviewRecord(Base):
    __tablename__ = "review_records"
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False)
    stage = Column(String, nullable=False)    # BALLOONING / FEASIBILITY
    action = Column(String, nullable=False)   # approved / revision_requested
    comment = Column(Text, nullable=True)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, default=datetime.utcnow)
    rfq = relationship("RFQ", back_populates="reviews")

class Machine(Base):
    __tablename__ = "machines"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    working_limit = Column(String, nullable=True)
    parameter = Column(String, nullable=True)
    operation_name = Column(String, nullable=False)
    achievable_tolerance = Column(String, nullable=True)
    measuring_instrument = Column(String, nullable=True)
    available = Column(Boolean, default=True)

class Instrument(Base):
    __tablename__ = "instruments"
    id = Column(Integer, primary_key=True, index=True)
    parameter = Column(String, nullable=False)
    tolerance = Column(String, nullable=True)
    name = Column(String, nullable=False)
    instrument_range = Column(String, nullable=True)
    available = Column(Boolean, default=True)

class OutsourcedProcess(Base):
    __tablename__ = "outsourced_processes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class MachineRate(Base):
    """Configurable machine hourly rates for costing."""
    __tablename__ = "machine_rates"
    id = Column(Integer, primary_key=True, index=True)
    machine_name = Column(String, nullable=False, unique=True)
    rate_per_hour = Column(Float, nullable=False)
    currency = Column(String, default="INR")

class MaterialPrice(Base):
    """Configurable material prices and densities for costing."""
    __tablename__ = "material_prices"
    id = Column(Integer, primary_key=True, index=True)
    grade = Column(String, nullable=False, unique=True)     # e.g. "EN8", "C45", "E250"
    aliases = Column(String, nullable=True)                 # comma-separated aliases e.g. "Fe410,E250(Fe410)"
    density_g_cm3 = Column(Float, default=7.86)
    rate_per_kg = Column(Float, nullable=False)
    currency = Column(String, default="INR")

class CostingConfig(Base):
    """Configurable overhead percentages and defaults for costing."""
    __tablename__ = "costing_config"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True)
    value = Column(Float, nullable=False)
    description = Column(String, nullable=True)

class CostingDraft(Base):
    """Stores draft costing data for user review/edit before final generation."""
    __tablename__ = "costing_drafts"
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)
    costing_json = Column(Text, nullable=True)  # full costing breakdown as JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    rfq = relationship("RFQ")


class PipelineRunStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class PipelineRun(Base):
    """
    Stores one execution of the RFQ AI pipeline for dashboard/metrics.
    """

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    status = Column(String, default=PipelineRunStatus.SUCCESS.value)
    engine = Column(String, default="gemini")  # e.g. gemini / claude

    total_ms = Column(Integer, nullable=True)
    failure_stage = Column(String, nullable=True)
    failure_message = Column(Text, nullable=True)

    # JSON text with per-stage timings / metadata for visualization
    stages_json = Column(Text, nullable=True)

    rfq = relationship("RFQ")

