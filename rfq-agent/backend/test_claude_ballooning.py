"""Test: can Claude place balloons via JSON coordinates?

Loads the 28 features from the last pipeline run, calls ai_place_balloons
(Claude-based), renders via generate_ballooned_image, reports timing + output.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_BE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BE)
sys.path.insert(0, os.path.join(_BE, "ai"))

from dotenv import load_dotenv

load_dotenv(override=True)

from balloon_generator import ai_place_balloons, generate_ballooned_image


def main():
    rfq_id = sys.argv[1] if len(sys.argv) > 1 else "33"
    uploads = Path(_BE) / "uploads"

    png_path = uploads / "drawings" / f"{rfq_id}_drawing.png"
    features_path = uploads / "drawings" / f"{rfq_id}_features.json"
    out_path = uploads / "ballooned" / f"{rfq_id}_claude_ballooned.png"

    if not png_path.exists() or not features_path.exists():
        print(f"Missing inputs: {png_path} / {features_path}")
        print("Run `python3 run_one_rfq.py <pdf>` first.")
        sys.exit(1)

    features = json.loads(features_path.read_text())
    print(f"Loaded {len(features)} features from last pipeline run")

    # The features have 'spec'/'type' keys from geometry_correction —
    # rename so ai_place_balloons can read spec. box_2d already present.
    for f in features:
        if "specification" not in f and "spec" in f:
            f["specification"] = f["spec"]
        if "box_2d" not in f and "corrected_box" in f:
            f["box_2d"] = f["corrected_box"]

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set")
        sys.exit(1)

    print(f"\nAsking Claude to place {len(features)} balloons on {png_path.name}…")
    t0 = time.time()
    placed = ai_place_balloons(str(png_path), features, api_key)
    elapsed = time.time() - t0
    print(f"Claude returned balloon positions in {elapsed:.1f}s")

    # Count how many got real coordinates
    has_pos = [f for f in placed if f.get("balloon_position")]
    print(f"  features with balloon_position: {len(has_pos)}/{len(placed)}")

    # Show first few
    print("\n  sample placements:")
    for f in has_pos[:8]:
        bno = f.get("balloon_no")
        pos = f.get("balloon_position")
        spec = (f.get("specification") or f.get("spec") or "")[:28]
        print(f"    balloon #{bno:>2}: ({pos[0]:>5}, {pos[1]:>5})   spec={spec!r}")

    # Render the balloons locally
    print(f"\nRendering {len(has_pos)} balloons → {out_path}…")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    generate_ballooned_image(str(png_path), placed, str(out_path))

    if out_path.exists():
        size = out_path.stat().st_size
        print(f"  ✅ image written: {out_path} ({size // 1024} KB)")
    else:
        print(f"  ❌ image NOT written")

    # Check for overlaps
    positions = [(f["balloon_no"], f["balloon_position"]) for f in has_pos]
    overlaps = 0
    MIN_DIST = 40
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            bx1, by1 = positions[i][1]
            bx2, by2 = positions[j][1]
            d = ((bx1 - bx2) ** 2 + (by1 - by2) ** 2) ** 0.5
            if d < MIN_DIST:
                overlaps += 1
    print(f"\n  overlap check: {overlaps} balloon pairs within {MIN_DIST}px")


if __name__ == "__main__":
    main()
