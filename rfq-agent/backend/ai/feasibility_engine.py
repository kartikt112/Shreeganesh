"""
Feasibility Engine — based on MACHINE LIST & INSTRUMENT LIST.xlsx

Machine database, instrument selection, criticality determination,
and feasibility checks all use the exact rules and naming conventions
from the user's real machine/instrument reference data.

All output values are template-ready — no abbreviations.
"""
import re
from typing import Dict, Any, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# Helper: extract tolerance and diameter from specification strings
# ═══════════════════════════════════════════════════════════════════════════

def _extract_tolerance_value(spec: str) -> Optional[float]:
    """Extract absolute tolerance value from spec string.
    Examples: '87 ±0.5' → 0.5, 'Ø11.8 ±0.05' → 0.05, 'Ø13 h9 (0 / -0.043)' → 0.043
    """
    if not spec:
        return None
    # Try ± notation first
    m = re.search(r'±\s*([\d.]+)', spec)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    # Try range notation: (0 / -0.043) or (+0.2 / 0)
    m = re.search(r'\(\s*[+\-]?([\d.]+)\s*/\s*[+\-]?([\d.]+)\s*\)', spec)
    if m:
        try:
            v1, v2 = float(m.group(1)), float(m.group(2))
            return max(v1, v2)
        except ValueError:
            pass
    # Try trailing tolerance: spec ending with a number after ± or +/-
    m = re.search(r'[±+\-]\s*([\d.]+)\s*$', spec)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _extract_diameter(spec: str) -> Optional[float]:
    """Extract diameter from spec string.
    Examples: 'Ø13 h9' → 13.0, 'Ø7.8 ±0.2' → 7.8, 'M10x1.5' → 10.0
    """
    if not spec:
        return None
    # Ø notation
    m = re.search(r'[Øø⌀]\s*([\d.]+)', spec)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    # M-thread notation
    m = re.search(r'M\s*([\d.]+)', spec)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _extract_thread_size(spec: str) -> Optional[float]:
    """Extract metric thread size from spec. 'M10x1.5' → 10.0"""
    m = re.search(r'M\s*([\d.]+)', spec)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _is_internal(spec: str, description: str, feature_type: str) -> bool:
    """Determine if a thread/hole feature is internal."""
    combined = f"{spec} {description}".lower()
    if feature_type == "ID":
        return True
    return any(kw in combined for kw in ["internal", "tapping", "bore", "hole", "plug"])


# ═══════════════════════════════════════════════════════════════════════════
# Machine Database (from MACHINE LIST & INSTRUMENT LIST.xlsx)
#
# Each entry: (machine, working_limit, operations_with_tolerances, inhouse)
# Operations dict: {operation_name: tolerance_mm} (None = no tolerance check)
# ═══════════════════════════════════════════════════════════════════════════

MACHINE_DB = {
    "TRAUB MACHINE": {
        "bar_dia_min": 0,
        "bar_dia_max": 25,
        "inhouse": "Inhouse",
        "operations": {
            "TURNING": 0.1,
            "PARTING": 0.1,
            "DRILLING": 0.1,
            "EXTERNAL GROOVING": 0.1,
        },
    },
    "CNC LATHE": {
        "bar_dia_min": 5,
        "bar_dia_max": 150,
        "inhouse": "Inhouse",
        "operations": {
            "TURNING": 0.03,
            "BORING": 0.1,
            "DRILLING": 0.1,
            "EXTERNAL THREADING": None,
            "INTERNAL THREADING": None,
            "EXTERNAL GROOVING": 0.1,
            "INTERNAL GROOVING": 0.1,
            "DISTANCE": 0.03,
        },
    },
    "TURRET LATHE": {
        "bar_dia_min": 5,
        "bar_dia_max": 30,
        "inhouse": "Inhouse",
        "operations": {
            "DRILLING": 0.1,
        },
    },
    "VMC": {
        "bar_dia_min": 0,
        "bar_dia_max": 9999,
        "inhouse": "Inhouse",
        "operations": {
            "SLOT MILLING": 0.03,
            "PROFILE MILLING": 0.05,
            "DRILLING": 0.05,
            "BORING": 0.02,
            "TAPPING": None,
        },
    },
    "THREAD ROLLING": {
        "bar_dia_min": 8,
        "bar_dia_max": 14,
        "inhouse": "Outsource",
        "operations": {
            "EXTERNAL THREADING": None,
        },
    },
    "TAPPING MACHINE": {
        "bar_dia_min": 6,
        "bar_dia_max": 12,
        "inhouse": "Outsource",
        "operations": {
            "INTERNAL THREADING": None,
            "TAPPING": None,
        },
    },
    "CNC CUTTING": {
        "bar_dia_min": 0,
        "bar_dia_max": 100,
        "inhouse": "Inhouse",
        "operations": {
            "CUTTING": 0.03,
        },
    },
}

# Feature type → candidate operations (ordered by preference)
FEATURE_TO_OPERATIONS = {
    "OD": ["TURNING", "EXTERNAL GROOVING"],
    "ID": ["BORING", "DRILLING"],
    "LENGTH": ["DISTANCE", "TURNING"],
    "THREAD": ["EXTERNAL THREADING", "INTERNAL THREADING"],
    "CHAMFER": ["TURNING"],
    "SURFACE_FINISH": ["TURNING"],
    "SLOT": ["SLOT MILLING"],
    "PROFILE": ["PROFILE MILLING"],
    "RADIUS": ["TURNING"],
    "ANGLE": ["TURNING"],
    "GDT": ["TURNING"],
    "REFERENCE": [],
    "NOTE": [],
    "MATERIAL": [],
}

# Outsourced processes
OUTSOURCED_PROCESSES = {
    "PLATING", "POWDER COATING", "ED COATING",
    "THREAD ROLLING", "TAPPING MACHINE",
}


# ═══════════════════════════════════════════════════════════════════════════
# Instrument Database (from MACHINE LIST & INSTRUMENT LIST.xlsx)
# All names are FULL — no abbreviations
# ═══════════════════════════════════════════════════════════════════════════

INSTRUMENT_DB = {
    # (parameter, tolerance_threshold) → instrument info
    "OD_LOOSE":     {"instrument": "DIGITAL VERNIER CALIPER", "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": ""},
    "OD_TIGHT":     {"instrument": "MICROMETER",              "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": ""},
    "OD_CRITICAL":  {"instrument": "MICROMETER",              "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": "SNAP GAUGE"},
    "ID_LOOSE":     {"instrument": "DIGITAL VERNIER CALIPER", "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": ""},
    "ID_TIGHT":     {"instrument": "PIN GAUGE",               "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": "PIN GAUGE"},
    "ID_GROOVE":    {"instrument": "INSIDE VERNIER CALIPER",  "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": ""},
    "LENGTH":       {"instrument": "HEIGHT GAUGE",            "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": ""},
    "CHAMFER":      {"instrument": "DIGITAL HEIGHT GAUGE",    "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": ""},
    "ANGLE":        {"instrument": "DIGITAL HEIGHT GAUGE",    "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": ""},
    "RADIUS":       {"instrument": "HEIGHT GAUGE",            "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": ""},
    "SLOT":         {"instrument": "SLOT WIDTH GAUGE",        "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": "SLOT WIDTH GAUGE"},
    "THREAD_EXT":   {"instrument": "THREAD RING GAUGE",       "inhouse": "Inhouse", "frequency": "5/Setup", "gauge": "THREAD RING GAUGE"},
    "THREAD_INT":   {"instrument": "THREAD PLUG GAUGE",       "inhouse": "Inhouse", "frequency": "5/Setup", "gauge": "THREAD PLUG GAUGE"},
    "SURFACE":      {"instrument": "RA TESTER",               "inhouse": "Outsource", "frequency": "1/3 Months", "gauge": ""},
    "GDT":          {"instrument": "CMM",                     "inhouse": "Outsource", "frequency": "5/Setup", "gauge": ""},
    "PROFILE":      {"instrument": "CMM",                     "inhouse": "Outsource", "frequency": "5/Setup", "gauge": ""},
    "MATERIAL":     {"instrument": "RM TEST LAB",             "inhouse": "Outsource", "frequency": "Per Lot", "gauge": ""},
    "NA":           {"instrument": "N/A",                     "inhouse": "N/A", "frequency": "N/A", "gauge": "N/A"},
    "DEFAULT":      {"instrument": "DIGITAL VERNIER CALIPER", "inhouse": "Inhouse", "frequency": "1/Hr", "gauge": ""},
}


# ═══════════════════════════════════════════════════════════════════════════
# Criticality Determination
# ═══════════════════════════════════════════════════════════════════════════

def determine_criticality(spec: str, feature_type: str, hint: str) -> str:
    """Determine feature criticality: '' (normal), 'I' (Important), 'SC' (Safety Critical), 'CR' (Critical)."""
    if not spec:
        return ""
    # GD&T symbols → SC
    if any(s in spec for s in ["⌀", "◎", "⊙", "⊿", "⊕", "Ⓜ", "⊛", "GD&T",
                                "concentricity", "position", "⌭", "⌖", "∥", "⊥", "⌒"]):
        return "SC"
    if feature_type == "GDT":
        return "SC"
    # Surface finish Ra ≤ 1.6 → SC
    ra_match = re.search(r'Ra\s*([\d.]+)', spec, re.IGNORECASE)
    if ra_match:
        try:
            if float(ra_match.group(1)) <= 1.6:
                return "SC"
        except ValueError:
            pass
    # h-class fits → SC
    if re.search(r'h[679]\b', spec.lower()):
        return "SC"
    # Tolerance-based
    tol = _extract_tolerance_value(spec)
    if tol is not None:
        if tol <= 0.01:
            return "CR"
        if tol <= 0.05:
            return "SC"
    if hint == "tight":
        return "SC"
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# Machine Selection — per-feature, using machine database
# ═══════════════════════════════════════════════════════════════════════════

def select_machine(
    feature_type: str,
    spec: str,
    db=None,
    manufacturing_metadata: Optional[Dict] = None,
    description: str = "",
) -> Dict[str, str]:
    """Select the best machine for a feature based on its type, diameter, and tolerance."""
    feat = feature_type or ""
    spec_lower = (spec or "").lower()
    desc_lower = (description or "").lower()

    # ── Non-machined features ──
    if feat in ("NOTE", "MASS", "TOLERANCE_STANDARD", "REFERENCE"):
        return {"machine": "N/A", "inhouse": "N/A"}
    if feat == "MATERIAL" or any(kw in spec_lower for kw in ["rm", "tensile", "yield", "din", "astm"]):
        if any(kw in desc_lower for kw in ["material", "raw material", "grade", "steel"]):
            return {"machine": "RM SUPPLIER", "inhouse": "Outsource"}
    if any(kw in spec_lower for kw in ["coating", "plating", "zinc", "treatment", "zniii", "phosphate"]):
        return {"machine": "PLATING", "inhouse": "Outsource"}
    if any(kw in desc_lower for kw in ["coating", "plating", "surface protection", "zinc"]):
        return {"machine": "PLATING", "inhouse": "Outsource"}

    # ── Threading: pick THREAD ROLLING vs TAPPING based on internal/external + size ──
    if feat == "THREAD" or "thread" in spec_lower or "threading" in desc_lower:
        thread_size = _extract_thread_size(spec)
        internal = _is_internal(spec, description, feat)
        if internal:
            if thread_size and 6 <= thread_size <= 12:
                return {"machine": "TAPPING MACHINE", "inhouse": "Outsource"}
            return {"machine": "CNC LATHE", "inhouse": "Inhouse"}
        else:
            if thread_size and 8 <= thread_size <= 14:
                return {"machine": "THREAD ROLLING", "inhouse": "Outsource"}
            return {"machine": "CNC LATHE", "inhouse": "Inhouse"}

    # ── Slot / Profile → VMC ──
    if feat == "SLOT" or "slot" in desc_lower:
        return {"machine": "VMC", "inhouse": "Inhouse"}
    if feat == "PROFILE" or "profile" in desc_lower:
        return {"machine": "VMC", "inhouse": "Inhouse"}

    # ── GDT → CNC LATHE ──
    if feat == "GDT":
        return {"machine": "CNC LATHE", "inhouse": "Inhouse"}

    # ── Turning features (OD, ID, LENGTH, CHAMFER, SURFACE_FINISH, RADIUS, ANGLE) ──
    if feat in ("OD", "ID", "LENGTH", "CHAMFER", "SURFACE_FINISH", "RADIUS", "ANGLE"):
        dia = _extract_diameter(spec)
        tol = _extract_tolerance_value(spec)

        # Get part envelope from metadata for fallback
        max_od = None
        if manufacturing_metadata:
            envelope = manufacturing_metadata.get("part_envelope", {})
            max_od = envelope.get("max_od_mm")

        # Determine effective diameter (feature's own, or part envelope)
        effective_dia = dia or max_od

        # ID boring with tight tolerance → VMC (±0.02 capability)
        if feat == "ID" and tol is not None and tol < 0.05:
            return {"machine": "VMC", "inhouse": "Inhouse"}

        # TRAUB: diameter ≤ 25mm AND tolerance ≥ 0.1 (or no tight tolerance)
        if effective_dia is not None and effective_dia <= 25:
            if tol is None or tol >= 0.1:
                return {"machine": "TRAUB MACHINE", "inhouse": "Inhouse"}

        # CNC LATHE: diameter 5-150mm or tight tolerance
        if effective_dia is None or (5 <= effective_dia <= 150):
            return {"machine": "CNC LATHE", "inhouse": "Inhouse"}

        return {"machine": "CNC LATHE", "inhouse": "Inhouse"}

    return {"machine": "CNC LATHE", "inhouse": "Inhouse"}


# ═══════════════════════════════════════════════════════════════════════════
# Feasibility Check — per-operation tolerance from machine database
# ═══════════════════════════════════════════════════════════════════════════

def _get_operation_tolerance(machine_name: str, feature_type: str, spec: str, description: str) -> Optional[float]:
    """Get the machine tolerance for the specific operation being performed."""
    machine = MACHINE_DB.get(machine_name)
    if not machine:
        return 0.1  # conservative fallback

    operations = machine["operations"]
    feat = feature_type or ""
    desc_lower = (description or "").lower()

    # Map feature type to the specific operation
    if feat == "OD":
        if "groove" in desc_lower or "undercut" in desc_lower:
            return operations.get("EXTERNAL GROOVING", operations.get("TURNING", 0.1))
        return operations.get("TURNING", 0.1)
    if feat == "ID":
        if "bore" in desc_lower or "boring" in desc_lower:
            return operations.get("BORING", operations.get("DRILLING", 0.1))
        if "groove" in desc_lower:
            return operations.get("INTERNAL GROOVING", 0.1)
        return operations.get("DRILLING", operations.get("BORING", 0.1))
    if feat == "LENGTH":
        return operations.get("DISTANCE", operations.get("TURNING", 0.1))
    if feat in ("CHAMFER", "RADIUS", "ANGLE", "SURFACE_FINISH"):
        return operations.get("TURNING", 0.1)
    if feat == "SLOT":
        return operations.get("SLOT MILLING", 0.03)
    if feat == "PROFILE":
        return operations.get("PROFILE MILLING", 0.05)

    # Fallback: smallest tolerance the machine can do
    tols = [t for t in operations.values() if t is not None]
    return min(tols) if tols else 0.1


def check_feasibility(
    feature_type: str,
    spec: str,
    machine_name: str,
    description: str = "",
) -> Dict[str, str]:
    """Compare required tolerance to machine's operation-specific capability."""
    if machine_name in ("N/A", "RM SUPPLIER", "PLATING"):
        return {"feasible": "Yes", "reason": "", "deviation": ""}

    tol = _extract_tolerance_value(spec)
    if tol is None:
        return {"feasible": "Yes", "reason": "", "deviation": ""}

    machine_cap = _get_operation_tolerance(machine_name, feature_type, spec, description)
    if machine_cap is None:
        return {"feasible": "Yes", "reason": "", "deviation": ""}

    if tol >= machine_cap:
        return {"feasible": "Yes", "reason": "", "deviation": ""}

    return {
        "feasible": "No",
        "reason": f"Required tolerance ±{tol}mm tighter than {machine_name} capability ±{machine_cap}mm",
        "deviation": f"Relax tolerance to ±{machine_cap}mm",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Instrument Selection — tolerance-aware, full names, no abbreviations
# ═══════════════════════════════════════════════════════════════════════════

def select_instrument(
    feature_type: str,
    spec: str,
    criticality: str,
    db=None,
    description: str = "",
) -> Dict[str, str]:
    """Select measuring instrument based on feature type and tolerance.
    All returned names are FULL — no abbreviations (DHG, DVC, IN, Out)."""
    spec_lower = (spec or "").lower()
    feat = feature_type or ""
    desc_lower = (description or "").lower()

    # ── Non-inspectable features ──
    if feat in ("REFERENCE", "NOTE", "TOLERANCE_STANDARD"):
        r = INSTRUMENT_DB["NA"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Material testing ──
    if feat == "MATERIAL" or "material" in desc_lower or "rm" in desc_lower:
        r = INSTRUMENT_DB["MATERIAL"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Threading ──
    if feat == "THREAD" or "thread" in spec_lower or "thread" in desc_lower:
        internal = _is_internal(spec, description, feat)
        key = "THREAD_INT" if internal else "THREAD_EXT"
        r = INSTRUMENT_DB[key]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Surface finish ──
    if feat == "SURFACE_FINISH" or "ra" in spec_lower or "surface" in desc_lower:
        r = INSTRUMENT_DB["SURFACE"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── GD&T ──
    if feat == "GDT":
        r = INSTRUMENT_DB["GDT"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Profile ──
    if feat == "PROFILE" or "profile" in desc_lower:
        r = INSTRUMENT_DB["PROFILE"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Slot ──
    if feat == "SLOT" or "slot" in desc_lower:
        r = INSTRUMENT_DB["SLOT"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    tol = _extract_tolerance_value(spec)

    # ── OD (Outer Diameter) ──
    if feat == "OD":
        # h-class fit or tight tolerance → MICROMETER
        if re.search(r'h[679]\b', spec_lower) or (tol is not None and tol < 0.1):
            key = "OD_CRITICAL" if criticality in ("SC", "CR") else "OD_TIGHT"
            r = INSTRUMENT_DB[key]
            return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                    "frequency": r["frequency"], "gauge": r["gauge"]}
        r = INSTRUMENT_DB["OD_LOOSE"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── ID (Inner Diameter) ──
    if feat == "ID":
        if "groove" in desc_lower:
            r = INSTRUMENT_DB["ID_GROOVE"]
            return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                    "frequency": r["frequency"], "gauge": r["gauge"]}
        if tol is not None and tol < 0.1:
            r = INSTRUMENT_DB["ID_TIGHT"]
            return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                    "frequency": r["frequency"], "gauge": r["gauge"]}
        r = INSTRUMENT_DB["ID_LOOSE"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Chamfer ──
    if feat == "CHAMFER" or "chamfer" in desc_lower:
        r = INSTRUMENT_DB["CHAMFER"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Angle ──
    if feat == "ANGLE" or "angle" in desc_lower:
        r = INSTRUMENT_DB["ANGLE"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Radius ──
    if feat == "RADIUS" or "radius" in desc_lower:
        r = INSTRUMENT_DB["RADIUS"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Length / Distance ──
    if feat == "LENGTH" or "length" in desc_lower or "distance" in desc_lower:
        r = INSTRUMENT_DB["LENGTH"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Critical features fallback → CMM ──
    if criticality in ("SC", "CR"):
        r = INSTRUMENT_DB["GDT"]
        return {"instrument": r["instrument"], "inhouse": r["inhouse"],
                "frequency": r["frequency"], "gauge": r["gauge"]}

    # ── Default ──
    r = INSTRUMENT_DB["DEFAULT"]
    return {"instrument": r["instrument"], "inhouse": r["inhouse"],
            "frequency": r["frequency"], "gauge": r["gauge"]}


# ═══════════════════════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════════════════════

def process_features(
    raw_features: List[Dict],
    db=None,
    manufacturing_metadata: Optional[Dict] = None,
) -> List[Dict]:
    """Run the full feasibility pipeline on extracted features.

    Args:
        raw_features: feature dicts from vision extraction
        db: database session (optional, unused currently)
        manufacturing_metadata: metadata from vision extractor (tightest_tolerance,
            part_envelope, material, surface_protection)
    """
    processed = []
    for f in raw_features:
        # Tolerate both the original VLM schema (specification/feature_type)
        # and geometry_correction's rewritten schema (spec/type).
        feat_type = f.get("feature_type") or f.get("type") or ""
        spec = f.get("specification") or f.get("spec") or ""
        hint = f.get("criticality_hint", "normal")
        description = f.get("description", "")

        criticality = determine_criticality(spec, feat_type, hint)
        machine_info = select_machine(
            feat_type, spec, db,
            manufacturing_metadata=manufacturing_metadata,
            description=description,
        )
        feasibility = check_feasibility(
            feat_type, spec, machine_info["machine"],
            description=description,
        )
        instr_info = select_instrument(
            feat_type, spec, criticality, db,
            description=description,
        )

        processed.append({
            "balloon_no": f.get("balloon_no", 0),
            "description": description,
            "specification": spec,
            "criticality": criticality,
            "feature_type": feat_type,
            "proposed_machine": machine_info["machine"],
            "inhouse_outsource": machine_info["inhouse"],
            "feasible": feasibility["feasible"],
            "reason_not_feasible": feasibility["reason"],
            "deviation_required": feasibility["deviation"],
            "box_2d": f.get("box_2d", None),
            "measuring_instrument": instr_info["instrument"],
            "inspection_inhouse": instr_info["inhouse"],
            "inspection_frequency": instr_info["frequency"],
            "gauge_required": instr_info["gauge"],
            "remarks": "",
        })
    return processed
