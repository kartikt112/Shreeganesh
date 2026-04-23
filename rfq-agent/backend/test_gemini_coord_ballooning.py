"""Focused test: Gemini 2.5 Pro on Vertex → balloon coords → local render."""

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

from routers.analyze import (
    _gemini_balloon_image,
    _build_balloon_positions,
    _validate_balloons,
    _draw_balloons,
    _get_image_size,
    _resize_for_gemini,
)


def main():
    rfq_id = sys.argv[1] if len(sys.argv) > 1 else "33"
    uploads = Path(_BE) / "uploads"
    png_path = uploads / "drawings" / f"{rfq_id}_drawing.png"
    features_path = uploads / "drawings" / f"{rfq_id}_features.json"
    out_path = uploads / "ballooned" / f"{rfq_id}_gemini_vertex_ballooned.png"

    if not png_path.exists():
        print(f"Missing {png_path}. Run `python3 run_one_rfq.py <pdf>` first.")
        sys.exit(1)

    features = json.loads(features_path.read_text())
    # Normalize keys from geometry_correction's rewrite
    for f in features:
        if "specification" not in f and "spec" in f:
            f["specification"] = f["spec"]
        if "box_2d" not in f and "corrected_box" in f:
            f["box_2d"] = f["corrected_box"]

    print(f"Loaded {len(features)} features from RFQ {rfq_id}")
    print(f"Gemini model: {os.getenv('GEMINI_MODEL', '(default)')}")
    print(f"Vertex mode:  {os.getenv('GENAI_USE_VERTEXAI', '(off)')}")

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("GEMINI_API_KEY not set"); sys.exit(1)

    orig_size = _get_image_size(str(png_path))
    _, resized_size = _resize_for_gemini(str(png_path), str(uploads / "drawings"))

    t0 = time.time()
    gemini_path, coords = _gemini_balloon_image(
        str(png_path), features, gemini_key, str(uploads / "drawings")
    )
    elapsed = time.time() - t0
    print(f"\nGemini coord call: {elapsed:.1f}s, returned {len(coords)} coords")
    if coords:
        print("  first 5:")
        for c in coords[:5]:
            print(f"    #{c['balloon_no']:>2}: ({c['x']}, {c['y']})")

    if not coords:
        print("  ❌ no coords returned — can't render")
        sys.exit(1)

    balloons = _build_balloon_positions(
        coords, gemini_path, features, resized_size, orig_size, resized_size
    )
    print(f"\nBuilt {len(balloons)} balloon positions")

    validation = _validate_balloons(balloons, features, orig_size)
    print(f"Validation: {validation['placed']}/{validation['expected']} placed, overlaps={validation['overlaps']}")
    for i in validation.get("issues", [])[:10]:
        print(f"  ! {i}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _draw_balloons(str(png_path), balloons, str(out_path))
    size_kb = out_path.stat().st_size // 1024 if out_path.exists() else 0
    print(f"\n✅ rendered → {out_path} ({size_kb} KB)")


if __name__ == "__main__":
    main()
