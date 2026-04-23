"""
Costing API endpoints.
Generates Cost Break-Up Sheets after feasibility report.
"""
import os
import json
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import RFQ, DrawingFeature, MachineRate, MaterialPrice, CostingConfig, CostingDraft

from ai.costing_engine import (
    generate_full_estimate,
    generate_cost_sheet_excel,
    calculate_raw_material,
    calculate_process_cost,
    calculate_overheads,
    calculate_total,
)

router = APIRouter(prefix="/api/rfq", tags=["costing"])
config_router = APIRouter(prefix="/api/config", tags=["costing-config"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
TEMPLATE_PATH = os.path.join(UPLOAD_DIR, "templates", "cost_breakup_template.xlsx")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_machine_rates(db: Session) -> Dict[str, float]:
    rates = db.query(MachineRate).all()
    return {r.machine_name: r.rate_per_hour for r in rates}


def _get_material_prices(db: Session) -> List[Dict[str, Any]]:
    prices = db.query(MaterialPrice).all()
    return [
        {
            "id": p.id, "grade": p.grade, "aliases": p.aliases,
            "density_g_cm3": p.density_g_cm3, "rate_per_kg": p.rate_per_kg,
        }
        for p in prices
    ]


def _get_costing_config(db: Session) -> Dict[str, float]:
    configs = db.query(CostingConfig).all()
    return {c.key: c.value for c in configs}


def _get_features(db: Session, rfq_id: int) -> List[Dict[str, Any]]:
    """Get features from draft JSON first, fall back to DB."""
    # Try draft JSON (has richer data from pipeline)
    draft_path = os.path.join(UPLOAD_DIR, "ballooned", f"{rfq_id}_draft.json")
    if os.path.exists(draft_path):
        with open(draft_path) as f:
            data = json.load(f)
        feats = data.get("features", [])
        if feats:
            return [
                {
                    "balloon_no": f.get("balloon_no"),
                    "specification": f.get("specification") or f.get("spec", ""),
                    "description": f.get("description") or f.get("type", ""),
                    "feature_type": f.get("feature_type") or f.get("type", ""),
                    "proposed_machine": f.get("proposed_machine"),
                    "inhouse_outsource": f.get("inhouse_outsource"),
                }
                for f in feats
            ]

    # Try features JSON
    features_path = os.path.join(UPLOAD_DIR, "drawings", f"{rfq_id}_features.json")
    if os.path.exists(features_path):
        with open(features_path) as f:
            feats = json.load(f)
        return [
            {
                "balloon_no": feat.get("balloon_no"),
                "specification": feat.get("specification") or feat.get("spec", ""),
                "description": feat.get("description") or feat.get("type", ""),
                "feature_type": feat.get("feature_type") or feat.get("type", ""),
                "proposed_machine": feat.get("proposed_machine"),
                "inhouse_outsource": feat.get("inhouse_outsource"),
            }
            for feat in feats
        ]

    # Fall back to DB
    features = db.query(DrawingFeature).filter(
        DrawingFeature.rfq_id == rfq_id
    ).order_by(DrawingFeature.balloon_no).all()
    return [
        {
            "balloon_no": f.balloon_no,
            "specification": f.specification,
            "description": f.description,
            "feature_type": f.feature_type,
            "proposed_machine": f.proposed_machine,
            "inhouse_outsource": f.inhouse_outsource,
        }
        for f in features
    ]


def _get_metadata(rfq_id: int) -> Dict[str, Any]:
    metadata_path = os.path.join(UPLOAD_DIR, "drawings", f"{rfq_id}_metadata.json")
    if os.path.exists(metadata_path):
        with open(metadata_path) as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------------------
# Estimate endpoint — AI suggests, user reviews
# ---------------------------------------------------------------------------

@router.post("/{rfq_id}/estimate-costing")
async def estimate_costing(rfq_id: int, db: Session = Depends(get_db)):
    """
    Generate initial cost estimate from feasibility data.
    AI suggests operations and cycle times. User can edit before final generation.
    """
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    features = _get_features(db, rfq_id)
    if not features:
        raise HTTPException(status_code=400, detail="No features found. Run analysis first.")

    metadata = _get_metadata(rfq_id)
    machine_rates = _get_machine_rates(db)
    material_prices = _get_material_prices(db)
    config = _get_costing_config(db)

    estimate = generate_full_estimate(
        features=features,
        metadata=metadata,
        machine_rates=machine_rates,
        material_prices=material_prices,
        config=config,
        quantity=rfq.quantity or 3000,
    )

    # Save draft
    draft = db.query(CostingDraft).filter(CostingDraft.rfq_id == rfq_id).first()
    if draft:
        draft.costing_json = json.dumps(estimate)
    else:
        draft = CostingDraft(rfq_id=rfq_id, costing_json=json.dumps(estimate))
        db.add(draft)
    db.commit()

    return estimate


# ---------------------------------------------------------------------------
# Get / Update draft
# ---------------------------------------------------------------------------

@router.get("/{rfq_id}/costing-data")
async def get_costing_data(rfq_id: int, db: Session = Depends(get_db)):
    """Get saved costing draft for review/editing."""
    draft = db.query(CostingDraft).filter(CostingDraft.rfq_id == rfq_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="No costing draft found. Run estimate first.")
    return json.loads(draft.costing_json)


class CostingUpdate(BaseModel):
    raw_material: Optional[Dict[str, Any]] = None
    process: Optional[Dict[str, Any]] = None
    overheads: Optional[Dict[str, Any]] = None
    tooling: Optional[Dict[str, float]] = None


@router.put("/{rfq_id}/costing-data")
async def update_costing_data(
    rfq_id: int,
    update: CostingUpdate,
    db: Session = Depends(get_db),
):
    """Update costing draft after user edits (operations, rates, etc.)."""
    draft = db.query(CostingDraft).filter(CostingDraft.rfq_id == rfq_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="No costing draft found.")

    data = json.loads(draft.costing_json)

    # Apply user edits
    if update.raw_material:
        data["raw_material"].update(update.raw_material)
    if update.process:
        data["process"].update(update.process)
    if update.overheads:
        data["overheads"].update(update.overheads)
    if update.tooling:
        data["tooling"] = update.tooling

    # Recalculate totals
    rm = data["raw_material"]
    proc = data["process"]

    # Recalculate process costs
    if update.process and "operations" in update.process:
        total_proc = 0
        for op in proc["operations"]:
            s = op.get("strokes_per_hr", 1)
            r = op.get("rate_per_hr", 0)
            op["cost"] = round(r / s if s > 0 else 0, 4)
            total_proc += op["cost"]
        proc["total_process_cost"] = round(total_proc, 4)

    # Recalculate overheads
    config = _get_costing_config(db)
    oh_config = {
        "rejection_pct": data["overheads"].get("rejection_pct", config.get("rejection_pct", 0.02)),
        "icc_pct": data["overheads"].get("icc_pct", config.get("icc_pct", 0.015)),
        "overheads_pct": data["overheads"].get("overheads_pct", config.get("overheads_pct", 0.065)),
        "profit_pct": data["overheads"].get("profit_pct", config.get("profit_pct", 0.10)),
        "packing_pct": data["overheads"].get("packing_pct", config.get("packing_pct", 0.015)),
        "freight_per_kg": data["overheads"].get("freight_per_kg", config.get("freight_per_kg", 8.0)),
        "inspection_pct": data["overheads"].get("inspection_pct", config.get("inspection_pct", 0.02)),
    }
    new_oh = calculate_overheads(
        rm_cost=rm["part_rm_rate"],
        bop_cost=rm["bop_cost"],
        process_cost=proc["total_process_cost"],
        plating_cost=proc.get("plating_cost", 0),
        annealing_cost=proc.get("annealing_cost", 0),
        net_weight_kg=rm["net_weight_kg"],
        config=oh_config,
    )
    data["overheads"] = new_oh

    # Recalculate total
    data["part_cost_abc"] = round(new_oh["subtotal_rm_process"] + new_oh["overhead_total"], 4)
    tooling = data.get("tooling", {})
    data["tool_cost"] = round(sum(tooling.values()), 4)
    data["total_part_cost"] = round(data["part_cost_abc"] + data["tool_cost"], 4)

    draft.costing_json = json.dumps(data)
    db.commit()

    return data


# ---------------------------------------------------------------------------
# Generate Excel
# ---------------------------------------------------------------------------

@router.post("/{rfq_id}/generate-cost-sheet")
async def generate_cost_sheet(rfq_id: int, db: Session = Depends(get_db)):
    """Generate final Cost Break-Up Sheet Excel from confirmed costing data."""
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    draft = db.query(CostingDraft).filter(CostingDraft.rfq_id == rfq_id).first()
    if not draft:
        raise HTTPException(status_code=400, detail="No costing draft. Run estimate first.")

    costing_data = json.loads(draft.costing_json)

    if not os.path.exists(TEMPLATE_PATH):
        raise HTTPException(status_code=500, detail="Cost breakup template not found")

    # Generate Excel
    part_no = rfq.part_no or rfq.part_name or str(rfq_id)
    customer = rfq.customer_name or "SGE"
    output_name = f"COST_BREAKUP_{part_no}_{customer}.xlsx"
    output_path = os.path.join(UPLOAD_DIR, "reports", output_name)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    generate_cost_sheet_excel(
        costing_data=costing_data,
        template_path=TEMPLATE_PATH,
        output_path=output_path,
    )

    return {
        "message": "Cost sheet generated",
        "file_path": f"/uploads/reports/{output_name}",
        "total_part_cost": costing_data["total_part_cost"],
    }


# ---------------------------------------------------------------------------
# Config endpoints (machine rates, material prices)
# ---------------------------------------------------------------------------

@config_router.get("/machine-rates")
async def get_machine_rates(db: Session = Depends(get_db)):
    rates = db.query(MachineRate).all()
    return [
        {"id": r.id, "machine_name": r.machine_name, "rate_per_hour": r.rate_per_hour}
        for r in rates
    ]


class RateUpdate(BaseModel):
    machine_name: str
    rate_per_hour: float


@config_router.put("/machine-rates")
async def update_machine_rate(update: RateUpdate, db: Session = Depends(get_db)):
    rate = db.query(MachineRate).filter(MachineRate.machine_name == update.machine_name).first()
    if rate:
        rate.rate_per_hour = update.rate_per_hour
    else:
        db.add(MachineRate(machine_name=update.machine_name, rate_per_hour=update.rate_per_hour))
    db.commit()
    return {"message": "Updated", "machine_name": update.machine_name, "rate_per_hour": update.rate_per_hour}


@config_router.get("/material-prices")
async def get_material_prices(db: Session = Depends(get_db)):
    prices = db.query(MaterialPrice).all()
    return [
        {
            "id": p.id, "grade": p.grade, "aliases": p.aliases,
            "density_g_cm3": p.density_g_cm3, "rate_per_kg": p.rate_per_kg,
        }
        for p in prices
    ]


class PriceUpdate(BaseModel):
    grade: str
    rate_per_kg: float
    density_g_cm3: Optional[float] = None
    aliases: Optional[str] = None


@config_router.put("/material-prices")
async def update_material_price(update: PriceUpdate, db: Session = Depends(get_db)):
    price = db.query(MaterialPrice).filter(MaterialPrice.grade == update.grade).first()
    if price:
        price.rate_per_kg = update.rate_per_kg
        if update.density_g_cm3:
            price.density_g_cm3 = update.density_g_cm3
        if update.aliases:
            price.aliases = update.aliases
    else:
        db.add(MaterialPrice(
            grade=update.grade, rate_per_kg=update.rate_per_kg,
            density_g_cm3=update.density_g_cm3 or 7.86, aliases=update.aliases,
        ))
    db.commit()
    return {"message": "Updated", "grade": update.grade}


@config_router.get("/costing-defaults")
async def get_costing_defaults(db: Session = Depends(get_db)):
    configs = db.query(CostingConfig).all()
    return [{"key": c.key, "value": c.value, "description": c.description} for c in configs]
