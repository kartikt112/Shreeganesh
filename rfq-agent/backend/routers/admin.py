import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import RFQ, PipelineRun

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _serialize_rfq_summary(rfq: RFQ, last_run: Optional[PipelineRun]) -> Dict[str, Any]:
    return {
        "id": rfq.id,
        "customer_name": rfq.customer_name,
        "part_name": rfq.part_name,
        "part_no": rfq.part_no,
        "status": rfq.status,
        "received_at": rfq.received_at,
        "ballooned_image_path": rfq.ballooned_image_path,
        "last_run": {
            "id": last_run.id,
            "started_at": last_run.started_at,
            "completed_at": last_run.completed_at,
            "status": last_run.status,
            "total_ms": last_run.total_ms,
            "failure_stage": last_run.failure_stage,
        }
        if last_run
        else None,
    }


@router.get("/rfqs")
def list_rfq_summaries(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: Optional[str] = Query(None),
    customer: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Paginated RFQ summaries for the admin dashboard.
    """
    query = db.query(RFQ)

    if status:
        query = query.filter(RFQ.status == status)
    if customer:
        query = query.filter(RFQ.customer_name.ilike(f"%{customer}%"))

    total = query.count()
    items: List[RFQ] = (
        query.order_by(RFQ.received_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Fetch last pipeline run per RFQ (simple N+1 – fine for dashboard scale)
    summaries: List[Dict[str, Any]] = []
    for rfq in items:
        last_run = (
            db.query(PipelineRun)
            .filter(PipelineRun.rfq_id == rfq.id)
            .order_by(PipelineRun.started_at.desc())
            .first()
        )
        summaries.append(_serialize_rfq_summary(rfq, last_run))

    return {
        "items": summaries,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/rfqs/{rfq_id}/runs")
def get_rfq_runs(
    rfq_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return all pipeline runs for a given RFQ (for timeline visualization).
    """
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    runs: List[PipelineRun] = (
        db.query(PipelineRun)
        .filter(PipelineRun.rfq_id == rfq_id)
        .order_by(PipelineRun.started_at.desc())
        .all()
    )

    def serialize_run(run: PipelineRun) -> Dict[str, Any]:
        return {
            "id": run.id,
            "rfq_id": run.rfq_id,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "status": run.status,
            "engine": run.engine,
            "total_ms": run.total_ms,
            "failure_stage": run.failure_stage,
            "failure_message": run.failure_message,
            "stages": run.stages_json,
        }

    return {
        "rfq_id": rfq_id,
        "runs": [serialize_run(r) for r in runs],
    }


@router.get("/metrics")
def get_metrics(
    db: Session = Depends(get_db),
    days: int = Query(7, ge=1, le=90),
) -> Dict[str, Any]:
    """
    High-level operational metrics for the dashboard.
    """
    now = datetime.datetime.utcnow()
    since = now - datetime.timedelta(days=days)

    base_q = db.query(PipelineRun).filter(PipelineRun.started_at >= since)

    total_runs = base_q.count()
    successful_runs = base_q.filter(PipelineRun.status == "SUCCESS").count()

    avg_duration = (
        db.query(func.avg(PipelineRun.total_ms))
        .filter(PipelineRun.started_at >= since, PipelineRun.total_ms.isnot(None))
        .scalar()
    )

    # SQLite does not have percentile_cont; compute p95 in Python.
    duration_rows = (
        db.query(PipelineRun.total_ms)
        .filter(PipelineRun.started_at >= since, PipelineRun.total_ms.isnot(None))
        .all()
    )
    p95_duration = None
    if duration_rows:
        vals = sorted(int(r[0]) for r in duration_rows if r[0] is not None)
        if vals:
            idx = max(0, int(round(0.95 * (len(vals) - 1))))
            p95_duration = vals[idx]

    # Failures by stage
    failure_rows = (
        db.query(PipelineRun.failure_stage, func.count(PipelineRun.id))
        .filter(
            PipelineRun.started_at >= since,
            PipelineRun.status == "FAILED",
            PipelineRun.failure_stage.isnot(None),
        )
        .group_by(PipelineRun.failure_stage)
        .all()
    )
    failures_by_stage = {stage or "UNKNOWN": count for stage, count in failure_rows}

    # RFQs processed in window
    rfqs_processed = (
        db.query(func.count(func.distinct(PipelineRun.rfq_id)))
        .filter(PipelineRun.started_at >= since)
        .scalar()
    )

    return {
        "window_days": days,
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "success_rate": (successful_runs / total_runs) if total_runs else None,
        "avg_duration_ms": avg_duration,
        "p95_duration_ms": p95_duration,
        "rfqs_processed": rfqs_processed,
        "failures_by_stage": failures_by_stage,
    }

