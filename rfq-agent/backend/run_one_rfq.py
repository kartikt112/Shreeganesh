"""Run the full production pipeline on a single PDF.

Creates an RFQ row, invokes routers.analyze.run_pipeline, and prints
the final state: timings, feature count, feasibility outcomes, ballooned image.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

# Ensure backend is importable (same trick main.py uses)
_BE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BE)
sys.path.insert(0, os.path.join(_BE, "ai"))

from dotenv import load_dotenv

load_dotenv(override=True)

from database import SessionLocal, init_db
from models import RFQ, RFQStatus, DrawingFeature, PipelineRun
from routers.analyze import run_pipeline
from seed_data import seed


def main():
    pdf = Path(sys.argv[1] if len(sys.argv) > 1 else "/Users/prakashtupe/Shreeganesh/Swivel_tube.pdf")
    if not pdf.exists():
        print(f"PDF not found: {pdf}")
        sys.exit(1)

    print(f"Initializing DB + seed…")
    init_db()
    seed()

    uploads = Path(_BE) / "uploads" / "drawings"
    uploads.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        rfq = RFQ(
            customer_name="BAKEOFF",
            part_name=pdf.stem,
            part_no="SWIVEL-001",
            drg_rev="A",
            quantity=1,
            material="Steel",
            status=RFQStatus.NEW.value,
            drawing_path="",
        )
        db.add(rfq)
        db.commit()
        db.refresh(rfq)

        dest = uploads / f"{rfq.id}{pdf.suffix.lower()}"
        shutil.copy(pdf, dest)
        rfq.drawing_path = str(dest)
        db.commit()
        rfq_id = rfq.id
        print(f"Created RFQ {rfq_id} with drawing at {dest}")
    finally:
        db.close()

    t0 = time.time()
    print(f"\n{'=' * 70}\n  RUNNING FULL PIPELINE\n{'=' * 70}\n")
    # Non-interactive = full feasibility path
    run_pipeline(rfq_id, interactive=False)
    total = time.time() - t0

    # Read back final state
    db = SessionLocal()
    try:
        rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
        feats = db.query(DrawingFeature).filter(DrawingFeature.rfq_id == rfq_id).all()
        run = (
            db.query(PipelineRun)
            .filter(PipelineRun.rfq_id == rfq_id)
            .order_by(PipelineRun.id.desc())
            .first()
        )

        print(f"\n{'=' * 70}\n  PIPELINE RESULT\n{'=' * 70}")
        print(f"  total wall-clock:   {total:.1f}s")
        print(f"  RFQ id:             {rfq.id}")
        print(f"  status:             {rfq.status}")
        print(f"  ballooned image:    {rfq.ballooned_image_path or '(none)'}")
        print(f"  notes:              {rfq.notes or ''}")

        if run:
            print(f"\n  pipeline run status: {run.status}")
            if run.failure_message:
                print(f"  failure:             {run.failure_message}")
            if run.stages_json:
                try:
                    stages = json.loads(run.stages_json)
                    print(f"\n  stage timings:")
                    for name, sec in stages.items():
                        print(f"    {name:<25} {sec:>6.2f}s")
                except Exception:
                    pass

        print(f"\n  features saved to DB: {len(feats)}")
        if feats:
            feasible_yes = sum(1 for f in feats if (f.feasible or "").lower() == "yes")
            feasible_no = sum(1 for f in feats if (f.feasible or "").lower() == "no")
            inhouse = sum(1 for f in feats if (f.inhouse_outsource or "").lower() == "inhouse")
            outsource = sum(1 for f in feats if (f.inhouse_outsource or "").lower() == "outsource")
            print(f"  feasibility:         {feasible_yes} Yes / {feasible_no} No")
            print(f"  routing:             {inhouse} Inhouse / {outsource} Outsource")

            print(f"\n  features table:")
            print(
                f"    {'#':>3} {'type':<10} {'desc':<20} {'spec':<22} {'machine':<20} {'feasible':<8} {'instrument':<20}"
            )
            for f in feats[:40]:
                bno = f.balloon_no or 0
                ft = (f.feature_type or "")[:10]
                desc = (f.description or "")[:20]
                spec = (f.specification or "")[:22]
                mach = (f.proposed_machine or "")[:20]
                feas = (f.feasible or "")[:8]
                inst = (f.measuring_instrument or "")[:20]
                print(f"    {bno:>3} {ft:<10} {desc:<20} {spec:<22} {mach:<20} {feas:<8} {inst:<20}")

        print(f"\n  full ballooned image:  {os.path.join(_BE, (rfq.ballooned_image_path or '').lstrip('/'))}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
