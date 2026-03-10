import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ai"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from database import init_db
from routers import rfq, analyze, review, report, features
from seed_data import seed

app = FastAPI(title="RFQ Feasibility Agent", version="1.0.0")

# CORS – allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files (drawings, ballooned images)
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Register routers
app.include_router(rfq.router)
app.include_router(analyze.router)
app.include_router(review.router)
app.include_router(report.router)
app.include_router(features.router)

@app.on_event("startup")
def startup():
    init_db()
    seed()
    print("🚀 RFQ Agent API running at http://localhost:8000")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "RFQ Feasibility Agent"}

@app.get("/api/machines")
def list_machines(db=None):
    from database import SessionLocal
    from models import Machine
    db = SessionLocal()
    machines = db.query(Machine).all()
    db.close()
    return [{"id": m.id, "name": m.name, "operation": m.operation_name,
             "tolerance": m.achievable_tolerance, "instrument": m.measuring_instrument} for m in machines]

@app.get("/api/instruments")
def list_instruments():
    from database import SessionLocal
    from models import Instrument
    db = SessionLocal()
    instruments = db.query(Instrument).all()
    db.close()
    return [{"id": i.id, "parameter": i.parameter, "name": i.name,
             "tolerance": i.tolerance, "range": i.instrument_range} for i in instruments]
