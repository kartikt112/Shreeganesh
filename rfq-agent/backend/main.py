import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ai"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv(override=True)

from database import init_db
from routers import rfq, analyze, review, report, features, admin, costing
from seed_data import seed

app = FastAPI(title="RFQ Feasibility Agent", version="1.0.0")

# CORS – local dev defaults plus any ALLOWED_ORIGINS (comma-separated) set in env.
# For Railway: set ALLOWED_ORIGINS=https://your-frontend.up.railway.app
# Use ALLOWED_ORIGINS=* to allow any origin (disables credentials automatically).
_default_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
]
_env_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
_allow_any = "*" in _env_origins
_origins = ["*"] if _allow_any else list(dict.fromkeys(_default_origins + _env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=None if _allow_any else r"https://.*\.up\.railway\.app",
    allow_credentials=not _allow_any,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files (drawings, ballooned images).
# On Railway, attach a Volume mounted at the container path that resolves here (default: /app/uploads)
# so PDFs/PNGs/reports persist across deploys. All router code uses this same path.
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
for _sub in ("drawings", "ballooned", "reports", "templates"):
    os.makedirs(os.path.join(UPLOAD_DIR, _sub), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Register routers
app.include_router(rfq.router)
app.include_router(analyze.router)
app.include_router(review.router)
app.include_router(report.router)
app.include_router(features.router)
app.include_router(admin.router)
app.include_router(costing.router)
app.include_router(costing.config_router)

@app.on_event("startup")
def startup():
    init_db()
    seed()
    print(f"RFQ Agent API started (port={os.getenv('PORT', '8000')})")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "RFQ Feasibility Agent"}

@app.get("/api/machines")
def list_machines():
    from database import SessionLocal
    from models import Machine
    db = SessionLocal()
    try:
        machines = db.query(Machine).all()
        return [{"id": m.id, "name": m.name, "operation": m.operation_name,
                 "tolerance": m.achievable_tolerance, "instrument": m.measuring_instrument} for m in machines]
    finally:
        db.close()

@app.get("/api/instruments")
def list_instruments():
    from database import SessionLocal
    from models import Instrument
    db = SessionLocal()
    try:
        instruments = db.query(Instrument).all()
        return [{"id": i.id, "parameter": i.parameter, "name": i.name,
                 "tolerance": i.tolerance, "range": i.instrument_range} for i in instruments]
    finally:
        db.close()
