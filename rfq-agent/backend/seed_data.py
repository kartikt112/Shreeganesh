"""
Seed data taken directly from:
- /Users/prakashtupe/Shreeganesh/MACHINE LIST & INSTRUMENT LIST.xlsx
  Sheets: MACHINE LIST, MEASURING INSTRUMENT LIST, OUTSOURCED PROCESSES
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, init_db
from models import Machine, Instrument, OutsourcedProcess

MACHINES = [
    # (name, working_limit, parameter, operation_name, achievable_tolerance, measuring_instrument)
    ("TRAUB MACHINE", "BAR DIA. 0 TO 25 mm", "PARTING LENGTH", "PARTING", "±0.1", "DIGITAL VERNIER CALIPER"),
    ("TRAUB MACHINE", "BAR DIA. 0 TO 25 mm", "INNER DIAMETER", "DRILLING", "±0.1", "DIGITAL VERNIER CALIPER"),
    ("CNC LATHE", "BAR DIA. 5mm TO 150 mm", "OUTER DIAMETER", "TURNING", "±0.030", "MICROMETER"),
    ("CNC LATHE", "BAR DIA. 5mm TO 150 mm", "INNER DIAMETER", "BORING", "±0.1", "PIN GAUGE"),
    ("CNC LATHE", "BAR DIA. 5mm TO 150 mm", "EXTERNAL THREADING (UNF/UNC/NPT/INCHES)", "EXTERNAL THREADING", "ALL", "THREAD RING GAUGE"),
    ("CNC LATHE", "BAR DIA. 5mm TO 150 mm", "INTERNAL THREADING (M10/M12/M14/M20)", "INTERNAL THREADING", "6g", "THREAD PLUG GAUGE"),
    ("CNC LATHE", "BAR DIA. 5mm TO 150 mm", "GROOVE OD", "EXTERNAL GROOVING", "±0.1", "DIGITAL VERNIER CALIPER"),
    ("CNC LATHE", "BAR DIA. 5mm TO 150 mm", "GROOVE ID", "INTERNAL GROOVING", "±0.1", "INSIDE VERNIER CALIPER"),
    ("CNC LATHE", "BAR DIA. 5mm TO 150 mm", "DISTANCE LENGTH", "TURNING", "±0.03", "HEIGHT GAUGE"),
    ("TURRET LATHE", "ID. 5mm TO 30mm", "INNER DIAMETER", "DRILLING", "±0.1", "DIGITAL VERNIER CALIPER"),
    ("THREAD ROLLING", "THREADING M8 TO M14", "EXTERNAL THREADING (M8/M10/M12/M14)", "THREAD ROLLING", "6g/6h", "THREAD RING GAUGE"),
    ("TAPPING MACHINE", "THREADING M6 TO M12", "INTERNAL THREADING (M6/M8/M10/M12)", "TAPPING", "6g/6h", "THREAD PLUG GAUGE"),
    ("VMC", None, "SLOT", "SLOT MILLING", "±0.03", "SLOT WIDTH GAUGE"),
    ("VMC", None, "PROFILE", "PROFILE MILLING", "±0.05", "CMM"),
    ("VMC", None, "INNER DIAMETER", "DRILLING", "±0.05", "PIN GAUGE"),
    ("VMC", None, "INTERNAL THREADING", "TAPPING", "6g/6h", "THREAD PLUG GAUGE"),
    ("VMC", None, "INNER DIAMETER", "BORING", "±0.02", "PIN GAUGE"),
    ("CNC CUTTING", "BAR DIA. 0 TO 100 mm", "BLANK LENGTH", "CUTTING", "±0.03", "DIGITAL VERNIER CALIPER"),
]

INSTRUMENTS = [
    # (parameter, tolerance, name, range)
    ("OUTER DIAMETER", "±0.1", "DIGITAL VERNIER CALIPER", "0 TO 200 mm"),
    ("INNER DIAMETER", "±0.1", "DIGITAL VERNIER CALIPER", "0 TO 200 mm"),
    ("OUTER DIAMETER", "±0.020", "MICROMETER", "0 TO 100 mm"),
    ("INNER DIAMETER", "+0.1", "PIN GAUGE", "0 TO 12 mm"),
    ("LENGTH", "±0.03", "HEIGHT GAUGE", "0 TO 300 mm"),
    ("RM GRADE", None, "RM TEST LAB", None),
    ("EXTERNAL THREADING", None, "THREAD RING GAUGE", None),
    ("INTERNAL THREADING", None, "THREAD PLUG GAUGE", None),
]

OUTSOURCED = [
    "Plating", "Powder Coating", "ED Coating", "Thread Rolling",
    "Parting on Traub", "CMM Inspection", "Tapping", "Bending"
]

def seed():
    init_db()
    db = SessionLocal()
    try:
        if db.query(Machine).count() == 0:
            for m in MACHINES:
                db.add(Machine(
                    name=m[0], working_limit=m[1], parameter=m[2],
                    operation_name=m[3], achievable_tolerance=m[4], measuring_instrument=m[5]
                ))
            print(f"✅ Seeded {len(MACHINES)} machine records")

        if db.query(Instrument).count() == 0:
            for i in INSTRUMENTS:
                db.add(Instrument(parameter=i[0], tolerance=i[1], name=i[2], instrument_range=i[3]))
            print(f"✅ Seeded {len(INSTRUMENTS)} instrument records")

        if db.query(OutsourcedProcess).count() == 0:
            for op in OUTSOURCED:
                db.add(OutsourcedProcess(name=op))
            print(f"✅ Seeded {len(OUTSOURCED)} outsourced processes")

        db.commit()
        print("🌱 Database seeded successfully!")
    except Exception as e:
        db.rollback()
        print(f"❌ Seed error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
