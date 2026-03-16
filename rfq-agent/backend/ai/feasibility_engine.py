"""
Feasibility Engine:
- Maps feature types to machines (using real machine DB data)
- Determines criticality from tolerance/GD&T hints
- Decides feasibility by comparing tolerance to machine capability
- Generates deviation suggestions
- Selects measuring instrument
- Consumes manufacturing_metadata for enhanced machine assignment decisions
"""
import re
from typing import Dict, Any, List, Optional


# Criticality rules matching the real report (I=Important, SC=Safety Critical, CR=Critical)
def determine_criticality(spec: str, feature_type: str, hint: str) -> str:
    if not spec:
        return ""
    spec_lower = spec.lower()
    # GD&T symbols indicate critical
    if any(s in spec for s in ["⌀", "◎", "⊙", "⊿", "⊕", "Ⓜ", "⊛", "GD&T", "concentricity", "position", "⌭", "⌖", "∥", "⊥", "⌒"]):
        return "SC"
    # GD&T feature type
    if feature_type == "GDT":
        return "SC"
    # Surface finish Ra ≤ 1.6 is critical
    ra_match = re.search(r'Ra\s*([\d.]+)', spec, re.IGNORECASE)
    if ra_match:
        try:
            if float(ra_match.group(1)) <= 1.6:
                return "SC"
        except ValueError:
            pass
    # Tight tolerance
    tol = _extract_tolerance_value(spec)
    if tol is not None and tol <= 0.01:
        return "CR"
    if tol is not None and tol <= 0.05:
        return "SC"
    if hint == "tight":
        return "SC"
    return ""


def _extract_tolerance_value(spec: str) -> Optional[float]:
    """Extract absolute tolerance value from spec string like '87 ±0.5' or 'Ø11.8 ±0.05'"""
    match = re.search(r'[±+\-]?\s*([\d.]+)\s*$', spec.replace("±", "±"))
    if not match:
        match = re.search(r'±\s*([\d.]+)', spec)
    if match:
        try:
            return float(match.group(1))
        except:
            pass
    return None


# Map feature type → preferred machine operation
FEATURE_TO_OPERATION = {
    "OD": ["TURNING", "EXTERNAL GROOVING"],
    "ID": ["BORING", "DRILLING"],
    "LENGTH": ["TURNING"],
    "THREAD": ["EXTERNAL THREADING", "INTERNAL THREADING", "THREAD ROLLING", "TAPPING"],
    "CHAMFER": ["TURNING"],
    "SURFACE_FINISH": ["TURNING"],
    "SLOT": ["SLOT MILLING"],
    "PROFILE": ["PROFILE MILLING"],
    "RADIUS": ["TURNING"],
    "GDT": ["TURNING"],
    "REFERENCE": [],
    "NOTE": [],
    "MATERIAL": [],
}

# Machine tolerance lookup (from real data)
MACHINE_TOLERANCE = {
    "TRAUB MACHINE": 0.1,
    "CNC LATHE": 0.03,
    "TURRET LATHE": 0.1,
    "THREAD ROLLING": None,
    "TAPPING MACHINE": None,
    "VMC": 0.02,
    "CNC CUTTING": 0.03,
}

# Instrument selection rules (from real instrument list)
def select_instrument(feature_type: str, spec: str, criticality: str, db=None, description: str = "") -> Dict[str, str]:
    """
    Returns {instrument, inspection_inhouse, inspection_frequency, gauge_required}
    Matches the real feasibility report naming conventions:
      DVC = Digital Vernier Caliper
      DHG = Digital Height Gauge (for lengths, chamfers, angles)
      Micrometer = for tight OD tolerances (h-class fits)
    """
    spec_lower = (spec or "").lower()
    feat = feature_type or ""
    desc_lower = (description or "").lower()

    # Reference dimensions — no inspection needed
    if feat == "REFERENCE":
        return {"instrument": "N/A", "inhouse": "N/A", "frequency": "N/A", "gauge": "N/A"}

    # Threading → Thread Ring/Plug Gauge
    if "thread" in feat.lower() or "thread" in spec_lower or "threading" in desc_lower:
        if "internal" in spec_lower or feat == "ID":
            return {"instrument": "Thread Plug gauge", "inhouse": "IN", "frequency": "5/Setup", "gauge": "Thread Plug gauge"}
        return {"instrument": "Thread Ring gauge", "inhouse": "IN", "frequency": "5/Setup", "gauge": "Thread Ring gauge"}

    # Surface roughness → RA Tester (Outsourced)
    if "ra" in spec_lower or "surface" in feat.lower() or "surface" in desc_lower:
        return {"instrument": "RA Tester", "inhouse": "Out", "frequency": "1/3 Months", "gauge": ""}

    # GD&T → CMM (Outsourced)
    if feat == "GDT":
        return {"instrument": "CMM", "inhouse": "Out", "frequency": "5/Setup", "gauge": ""}

    # Non-machined features
    if feat in ["NOTE", "MATERIAL", "MASS", "TOLERANCE_STANDARD"]:
        if "material" in desc_lower:
            return {"instrument": "Material Testing Lab", "inhouse": "Out", "frequency": "Per Lot", "gauge": ""}
        return {"instrument": "N/A", "inhouse": "N/A", "frequency": "N/A", "gauge": "N/A"}

    # Angle → DHG
    if feat == "ANGLE" or "angle" in desc_lower:
        return {"instrument": "DHG", "inhouse": "IN", "frequency": "1/Hr", "gauge": ""}

    tol = _extract_tolerance_value(spec)

    # OD (Outer Dia, Slot Dia, Undercut Dia)
    if feat == "OD":
        # h-class fit (tight tolerance) → Micrometer
        if "h9" in spec_lower or "h7" in spec_lower or "h6" in spec_lower:
            return {"instrument": "Micrometer", "inhouse": "IN", "frequency": "1/Hr", "gauge": "SNAP GAUGE" if criticality in ["SC","CR"] else ""}
        if tol is not None and tol <= 0.05:
            return {"instrument": "Micrometer", "inhouse": "IN", "frequency": "1/Hr", "gauge": "SNAP GAUGE" if criticality in ["SC","CR"] else ""}
        return {"instrument": "DVC", "inhouse": "IN", "frequency": "1/Hr", "gauge": ""}

    # ID → DVC or Pin Gauge
    if feat == "ID":
        if tol is not None and tol <= 0.05:
            return {"instrument": "Pin Gauge", "inhouse": "IN", "frequency": "1/Hr", "gauge": "Pin Gauge"}
        return {"instrument": "DVC", "inhouse": "IN", "frequency": "1/Hr", "gauge": ""}

    # Chamfer → DHG
    if feat == "CHAMFER" or "chamfer" in desc_lower:
        return {"instrument": "DHG", "inhouse": "IN", "frequency": "1/Hr", "gauge": ""}

    # Length / Slot width → DHG for regular lengths, DVC for slot/undercut
    if feat == "LENGTH" or "length" in feat.lower():
        if "slot" in desc_lower:
            return {"instrument": "DVC", "inhouse": "IN", "frequency": "1/Hr", "gauge": ""}
        return {"instrument": "DHG", "inhouse": "IN", "frequency": "1/Hr", "gauge": ""}

    if criticality in ["SC", "CR"]:
        return {"instrument": "CMM", "inhouse": "Out", "frequency": "5/Setup", "gauge": ""}

    return {"instrument": "DVC", "inhouse": "IN", "frequency": "5/Setup", "gauge": ""}


def select_machine(feature_type: str, spec: str, db=None, manufacturing_metadata: Dict = None) -> Dict[str, str]:
    """
    Returns {machine, inhouse_outsource}
    Matches feature to best machine from the real machine list.

    When manufacturing_metadata is provided, uses:
    - tightest_tolerance for machine type decision (CNC vs Traub)
    - part_envelope for machine size selection
    - material for bar stock and cutting parameters
    - surface_protection for post-processing requirements
    """
    feat = feature_type or ""
    spec_lower = (spec or "").lower()

    if feat in ["NOTE", "MASS", "TOLERANCE_STANDARD", "REFERENCE"]:
        return {"machine": "N/A", "inhouse": "N/A"}
    if "material" in feat.lower() or "rm" in spec_lower or "tensile" in spec_lower or "yield" in spec_lower:
        return {"machine": "RM SUPPLIER", "inhouse": "Outsource"}
    if "coating" in spec_lower or "plating" in spec_lower or "zinc" in spec_lower or "treatment" in spec_lower:
        return {"machine": "PLATING", "inhouse": "Outsource"}
    if "thread" in feat.lower() or "thread" in spec_lower:
        if "internal" in spec_lower or feat == "ID":
            return {"machine": "TAPPING MACHINE", "inhouse": "Outsource"}
        return {"machine": "THREAD ROLLING", "inhouse": "Outsource"}
    if "slot" in feat.lower():
        return {"machine": "VMC", "inhouse": "Inhouse"}
    if "profile" in feat.lower():
        return {"machine": "VMC", "inhouse": "Inhouse"}
    if feat == "GDT":
        return {"machine": "CNC LATHE", "inhouse": "Inhouse"}

    if feat in ["OD", "ID", "LENGTH", "CHAMFER", "SURFACE_FINISH", "RADIUS", "ANGLE"]:
        # Use manufacturing_metadata for enhanced machine selection
        if manufacturing_metadata:
            tightest = manufacturing_metadata.get("tightest_tolerance", {})
            envelope = manufacturing_metadata.get("part_envelope", {})
            tightest_val = tightest.get("value_mm")
            max_od = envelope.get("max_od_mm")

            # Machine type decision based on tightest tolerance
            # < 0.05mm → CNC Lathe; >= 0.05mm → Traub Machine (if envelope fits)
            if tightest_val is not None and tightest_val >= 0.05:
                # Check if part fits on Traub (max OD ≤ 25mm for Traub)
                if max_od is not None and max_od <= 25:
                    return {"machine": "TRAUB MACHINE", "inhouse": "Inhouse"}

            # If tightest tolerance < 0.05mm, must use CNC Lathe
            if tightest_val is not None and tightest_val < 0.05:
                return {"machine": "CNC LATHE", "inhouse": "Inhouse"}

        # Fallback: per-feature diameter check
        dia_match = re.search(r'Ø?\s*([\d.]+)', spec or "")
        if dia_match and feat == "OD":
            try:
                if float(dia_match.group(1)) <= 25:
                    return {"machine": "TRAUB MACHINE", "inhouse": "Inhouse"}
            except ValueError:
                pass
        return {"machine": "CNC LATHE", "inhouse": "Inhouse"}
    return {"machine": "CNC LATHE", "inhouse": "Inhouse"}


def check_feasibility(feature_type: str, spec: str, machine_name: str) -> Dict[str, str]:
    """
    Compares required tolerance to machine capability.
    Returns {feasible, reason, deviation}
    """
    if machine_name == "N/A" or machine_name == "RM SUPPLIER" or machine_name == "PLATING":
        return {"feasible": "Yes", "reason": "", "deviation": ""}

    tol = _extract_tolerance_value(spec)
    machine_cap = MACHINE_TOLERANCE.get(machine_name.upper(), 0.1)

    if tol is None or machine_cap is None:
        return {"feasible": "Yes", "reason": "", "deviation": ""}

    if tol >= machine_cap:
        return {"feasible": "Yes", "reason": "", "deviation": ""}
    else:
        reason = f"Required tolerance ±{tol}mm tighter than {machine_name} capability ±{machine_cap}mm"
        deviation = f"Relax tolerance to ±{machine_cap}mm"
        return {"feasible": "No", "reason": reason, "deviation": deviation}


def process_features(raw_features: List[Dict], db=None, manufacturing_metadata: Dict = None) -> List[Dict]:
    """
    Run the full feasibility pipeline on extracted AI features.

    Args:
        raw_features: list of feature dicts from drawing_parser or vision_extractor
        db: database session (optional)
        manufacturing_metadata: metadata dict from vision_extractor (optional)
            Contains tightest_tolerance, part_envelope, material, surface_protection
            used for enhanced machine assignment decisions.
    """
    processed = []
    for f in raw_features:
        feat_type = f.get("feature_type", "")
        spec = f.get("specification", "")
        hint = f.get("criticality_hint", "normal")

        criticality = determine_criticality(spec, feat_type, hint)
        machine_info = select_machine(feat_type, spec, db, manufacturing_metadata=manufacturing_metadata)
        feasibility = check_feasibility(feat_type, spec, machine_info["machine"])
        description = f.get("description", "")
        instr_info = select_instrument(feat_type, spec, criticality, db, description=description)

        processed.append({
            "balloon_no": f.get("balloon_no", 0),
            "description": f.get("description", ""),
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
