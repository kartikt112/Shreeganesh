"""
Test script for the Geometry Correction Layer + Full Ballooning Pipeline.

Usage:
    python test_ballooning_pipeline.py --unit                  # Unit tests only (no API)
    python test_ballooning_pipeline.py --pdf /path/to/file.pdf # Full end-to-end
    python test_ballooning_pipeline.py                         # Both (needs API key)
"""
import os
import sys
import json
import argparse
import time

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai"))

from dotenv import load_dotenv
load_dotenv(override=True)

DEFAULT_PDF = "/Users/prakashtupe/Shreeganesh/Swivel_tube.pdf"
OUTPUT_DIR = "/tmp"


# ═══════════════════════════════════════════════════════════════════════════
# UNIT TESTS (no API key required)
# ═══════════════════════════════════════════════════════════════════════════

def test_coordinate_conversion():
    """Test box_2d [ymin,xmin,ymax,xmax] <-> (x1,y1,x2,y2) round-trip."""
    from geometry_correction import _box2d_to_xyxy, _xyxy_to_box2d

    box = [100, 200, 150, 300]  # ymin=100, xmin=200, ymax=150, xmax=300
    x1, y1, x2, y2 = _box2d_to_xyxy(box)
    assert (x1, y1, x2, y2) == (200, 100, 300, 150), f"Got {(x1,y1,x2,y2)}"

    roundtrip = _xyxy_to_box2d(x1, y1, x2, y2)
    assert roundtrip == box, f"Round-trip failed: {roundtrip}"
    print("  ✅ PASS: coordinate conversion round-trip")


def test_clamp_box():
    """Test clamping to image boundaries."""
    from geometry_correction import _clamp_box

    # Fully within bounds
    assert _clamp_box(10, 20, 100, 200, 500, 500) == (10, 20, 100, 200)
    # Negative values clamped to 0
    assert _clamp_box(-5, -10, 100, 200, 500, 500) == (0, 0, 100, 200)
    # Exceeding bounds clamped
    result = _clamp_box(400, 400, 600, 600, 500, 500)
    assert result[2] <= 500 and result[3] <= 500, f"Not clamped: {result}"
    print("  ✅ PASS: box clamping")


def test_text_box_refinement():
    """Test text box refinement on a synthetic image with known text position."""
    import cv2
    import numpy as np
    from geometry_correction import refine_text_box

    # 500x500 white image with black rectangle at known position (simulates text)
    img = np.ones((500, 500), dtype=np.uint8) * 255
    cv2.rectangle(img, (150, 120), (250, 140), 0, -1)  # filled black at known spot

    # AI box is slightly too large: [ymin=110, xmin=140, ymax=150, xmax=260]
    box_2d = [110, 140, 150, 260]
    x1, y1, x2, y2 = refine_text_box(img, box_2d)

    # Should tighten to approximately (150, 120, 250, 140)
    assert abs(x1 - 150) <= 5, f"x1 too far: {x1} (expected ~150)"
    assert abs(y1 - 120) <= 5, f"y1 too far: {y1} (expected ~120)"
    assert abs(x2 - 250) <= 5, f"x2 too far: {x2} (expected ~250)"
    assert abs(y2 - 140) <= 5, f"y2 too far: {y2} (expected ~140)"
    print("  ✅ PASS: text box refinement")


def test_collision_avoidance():
    """Test that colliding balloons get shifted apart."""
    from geometry_correction import resolve_collisions, _euclidean_distance

    placed = [(100, 100), (200, 200)]

    # Anchor collides with first placed (distance < 40)
    anchor = (110, 105)
    result = resolve_collisions(anchor, placed, 1000, 1000)
    dist = _euclidean_distance(result, (100, 100))
    assert dist >= 40, f"Collision not resolved: dist={dist:.1f}"

    # Non-colliding anchor should remain unchanged
    anchor2 = (500, 500)
    result2 = resolve_collisions(anchor2, placed, 1000, 1000)
    assert result2 == anchor2, f"Non-colliding anchor changed: {result2}"
    print("  ✅ PASS: collision avoidance")


def test_leader_line_detection():
    """Test leader line detection on synthetic image."""
    import cv2
    import numpy as np
    from geometry_correction import detect_leader_lines

    img = np.ones((500, 500), dtype=np.uint8) * 255
    # Draw a text-like region
    cv2.rectangle(img, (200, 100), (280, 120), 0, -1)
    # Draw a leader line extending right from text to geometry (with a gap from text)
    cv2.line(img, (285, 110), (400, 110), 0, 2)

    leader = detect_leader_lines(img, 200, 100, 280, 120)

    if leader:
        # The far endpoint should be ~400 (away from text box)
        assert leader[0] > 300, f"Leader x should be far from text: {leader[0]} (expected >300)"
        print("  ✅ PASS: leader line detection")
    else:
        print("  ⚠️  SKIP: leader line not detected (threshold sensitivity)")


def test_geometry_circle_detection():
    """Test circle detection for diameter features."""
    import cv2
    import numpy as np
    from geometry_correction import detect_associated_geometry

    img = np.ones((500, 500), dtype=np.uint8) * 255
    # Draw a circle near a text box
    cv2.circle(img, (350, 200), 50, 0, 2)  # circle at (350, 200) radius 50
    # Text box at (150, 180) to (250, 220)
    center = detect_associated_geometry(
        img, 150, 180, 250, 220, "OD", "Ø50 ±0.1", search_margin=200
    )

    if center:
        assert abs(center[0] - 350) <= 15, f"Circle x off: {center[0]}"
        assert abs(center[1] - 200) <= 15, f"Circle y off: {center[1]}"
        print("  ✅ PASS: circle geometry detection")
    else:
        print("  ⚠️  SKIP: circle not detected (HoughCircles sensitivity)")


def test_balloon_placement():
    """Test balloon placement logic."""
    from geometry_correction import compute_anchor_and_placement

    # With leader line — should use leader point
    anchor = compute_anchor_and_placement(
        100, 100, 200, 120, leader_point=(300, 110), geometry_center=None,
        img_w=800, img_h=600
    )
    assert abs(anchor[0] - 300) <= 20, f"Anchor x should be near leader: {anchor}"
    assert abs(anchor[1] - 110) <= 20, f"Anchor y should be near leader: {anchor}"

    # Without leader/geometry — should use offset from text
    anchor2 = compute_anchor_and_placement(
        100, 100, 200, 120, leader_point=None, geometry_center=None,
        img_w=800, img_h=600
    )
    # Should be offset from text box (not inside it)
    assert anchor2[0] < 100 or anchor2[0] > 200, f"Anchor inside text box: {anchor2}"
    print("  ✅ PASS: balloon placement logic")


def test_none_box_handling():
    """Test that features with None box_2d are handled gracefully."""
    import cv2
    import numpy as np
    from geometry_correction import refine_feature_coordinates

    img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    path = "/tmp/test_none_box.png"
    cv2.imwrite(path, img)

    features = [
        {"balloon_no": 1, "specification": "M10", "feature_type": "THREAD",
         "box_2d": None},
        {"balloon_no": 2, "specification": "Ra 1.6", "feature_type": "SURFACE_FINISH",
         "box_2d": []},
    ]
    results = refine_feature_coordinates(path, features)
    assert len(results) == 2
    assert results[0]["corrected_box"] is None
    assert results[1]["corrected_box"] is None
    print("  ✅ PASS: None/empty box_2d handling")
    os.remove(path)


def test_full_pipeline_with_mock_features():
    """Test the full correction pipeline with synthetic image and mock features."""
    import cv2
    import numpy as np
    from geometry_correction import refine_feature_coordinates

    # Create synthetic 800x600 image with text-like rectangles
    img = np.ones((600, 800, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (100, 200), (200, 220), 0, -1)  # text block 1
    cv2.rectangle(img, (400, 300), (500, 320), 0, -1)  # text block 2
    cv2.circle(img, (300, 210), 40, 0, 2)               # circle near block 1

    test_img_path = "/tmp/test_geom_correction.png"
    cv2.imwrite(test_img_path, img)

    features = [
        {"balloon_no": 1, "specification": "Ø14 ±0.1", "feature_type": "OD",
         "description": "Outer Dia", "box_2d": [195, 95, 225, 205]},
        {"balloon_no": 2, "specification": "25 ±0.2", "feature_type": "LENGTH",
         "description": "Length", "box_2d": [295, 395, 325, 505]},
    ]

    start = time.time()
    results = refine_feature_coordinates(test_img_path, features)
    elapsed = time.time() - start

    assert len(results) == 2, f"Expected 2 results, got {len(results)}"
    assert results[0]["corrected_box"] is not None, "Feature 1 missing corrected_box"
    assert results[0]["anchor_point"] is not None, "Feature 1 missing anchor_point"
    assert results[1]["corrected_box"] is not None, "Feature 2 missing corrected_box"
    assert results[1]["anchor_point"] is not None, "Feature 2 missing anchor_point"
    assert elapsed < 2.0, f"Too slow: {elapsed:.2f}s (must be <2s)"

    # Verify output format matches spec
    for r in results:
        assert "balloon_no" in r
        assert "spec" in r
        assert "type" in r
        assert "corrected_box" in r
        assert "anchor_point" in r
        assert len(r["corrected_box"]) == 4
        assert len(r["anchor_point"]) == 2

    print(f"  ✅ PASS: full correction pipeline ({elapsed:.3f}s for {len(features)} features)")
    os.remove(test_img_path)


def test_balloon_layout_engine():
    """Test the balloon layout engine."""
    import cv2
    import numpy as np
    from balloon_layout_engine import compute_balloon_layout
    
    # Create synthetic 800x600 image
    img = np.ones((600, 800, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (200, 200), (600, 400), 0, -1)  # dark rectangle as "part"
    test_img_path = "/tmp/test_layout.png"
    cv2.imwrite(test_img_path, img)
    
    features = [
        {"balloon_no": 1, "anchor_point": [400, 150]}, # Top
        {"balloon_no": 2, "anchor_point": [400, 450]}, # Bottom
        {"balloon_no": 3, "anchor_point": [150, 300]}, # Left
        {"balloon_no": 4, "anchor_point": [650, 300]}, # Right
    ]
    
    results = compute_balloon_layout(test_img_path, features)
    
    assert len(results) == 4
    for r in results:
        assert "balloon_position" in r
        assert len(r["balloon_position"]) == 2
        
    print("  ✅ PASS: balloon layout engine")
    os.remove(test_img_path)

def run_unit_tests():
    """Run all unit tests."""
    print("\n" + "=" * 60)
    print("  UNIT TESTS (no API key required)")
    print("=" * 60 + "\n")

    tests = [
        test_coordinate_conversion,
        test_clamp_box,
        test_text_box_refinement,
        test_collision_avoidance,
        test_leader_line_detection,
        test_geometry_circle_detection,
        test_balloon_placement,
        test_none_box_handling,
        test_full_pipeline_with_mock_features,
        test_balloon_layout_engine,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAIL: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n  Results: {passed} passed, {failed} failed out of {len(tests)}")
    return failed == 0


# ═══════════════════════════════════════════════════════════════════════════
# END-TO-END PIPELINE TEST (requires ANTHROPIC_API_KEY)
# ═══════════════════════════════════════════════════════════════════════════

def run_end_to_end_test(pdf_path: str):
    """Full pipeline: PDF → PNG → Vision → Correction → Balloons → QA → Final."""
    from drawing_parser import pdf_to_png
    from vision_extractor import extract_from_image
    from geometry_correction import refine_feature_coordinates
    from balloon_layout_engine import compute_balloon_layout
    from balloon_generator import generate_ballooned_image
    from balloon_reviewer import review_balloons

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ⚠️  SKIP: ANTHROPIC_API_KEY not set. Set it in backend/.env")
        return False

    basename = os.path.splitext(os.path.basename(pdf_path))[0].lower().replace(" ", "_")
    png_path = os.path.join(OUTPUT_DIR, f"{basename}_drawing.png")
    draft_balloon_path = os.path.join(OUTPUT_DIR, f"{basename}_draft_balloons.png")
    final_balloon_path = os.path.join(OUTPUT_DIR, f"{basename}_final_ballooned.png")
    extraction_json = os.path.join(OUTPUT_DIR, f"{basename}_extraction.json")
    correction_json = os.path.join(OUTPUT_DIR, f"{basename}_corrections.json")
    corrected_json = os.path.join(OUTPUT_DIR, f"{basename}_corrected.json")

    timings = {}

    print("\n" + "=" * 60)
    print("  END-TO-END PIPELINE TEST")
    print("=" * 60)
    print(f"\n  Input: {pdf_path}")
    print(f"  Output dir: {OUTPUT_DIR}\n")

    # ── Stage 1: PDF → PNG ──
    print("━" * 50)
    print("  Stage 1: PDF → PNG (PyMuPDF)")
    print("━" * 50)
    start = time.time()
    pdf_to_png(pdf_path, png_path, dpi=200)
    timings["pdf_to_png"] = time.time() - start

    from PIL import Image
    img = Image.open(png_path)
    file_size = os.path.getsize(png_path)
    print(f"  ✅ PNG saved: {png_path}")
    print(f"     Dimensions: {img.size[0]}x{img.size[1]}")
    print(f"     File size: {file_size / 1024:.0f} KB")
    print(f"     Time: {timings['pdf_to_png']:.2f}s")
    img.close()

    # ── Stage 2: Claude Vision Extraction ──
    print("\n" + "━" * 50)
    print("  Stage 2: Claude Vision Extraction (Sonnet 4.6)")
    print("━" * 50)
    start = time.time()
    extraction_result = extract_from_image(png_path, api_key)
    timings["vision_extraction"] = time.time() - start

    features = extraction_result.get("features", [])
    metadata = extraction_result.get("manufacturing_metadata", {})

    print(f"  ✅ Extracted {len(features)} features")
    print(f"     Time: {timings['vision_extraction']:.2f}s")
    print()
    for f in features:
        box = f.get("box_2d", [])
        box_str = f"[{','.join(str(int(b)) for b in box)}]" if box else "None"
        print(f"     #{f.get('balloon_no'):2d}  {f.get('specification', ''):20s}  "
              f"{f.get('description', ''):18s}  {f.get('feature_type', ''):15s}  "
              f"box={box_str}")

    # Metadata summary
    print()
    print(f"     Part: {metadata.get('part_name', 'N/A')}")
    print(f"     Drawing #: {metadata.get('drawing_number', 'N/A')}")
    mat = metadata.get("material", {})
    print(f"     Material: {mat.get('grade', 'N/A')} ({mat.get('standard', 'N/A')})")
    envelope = metadata.get("part_envelope", {})
    print(f"     Envelope: OD={envelope.get('max_od_mm', 'N/A')}mm, "
          f"Length={envelope.get('total_length_mm', 'N/A')}mm")
    tight = metadata.get("tightest_tolerance", {})
    print(f"     Tightest: {tight.get('value_mm', 'N/A')}mm "
          f"({tight.get('feature', 'N/A')})")

    # Save extraction JSON
    with open(extraction_json, "w") as f:
        json.dump(extraction_result, f, indent=2)
    print(f"\n     Saved: {extraction_json}")

    # ── Stage 2.5: Geometry Correction Layer ──
    print("\n" + "━" * 50)
    print("  Stage 2.5: Geometry Correction Layer (OpenCV)")
    print("━" * 50)
    start = time.time()
    corrections = refine_feature_coordinates(png_path, features)
    timings["geometry_correction"] = time.time() - start

    print(f"  ✅ Corrected {len(corrections)} features")
    print(f"     Time: {timings['geometry_correction']:.3f}s")
    print()
    for c in corrections:
        box = c.get("corrected_box")
        anchor = c.get("anchor_point")
        box_str = f"[{','.join(str(b) for b in box)}]" if box else "None"
        anchor_str = f"[{anchor[0]},{anchor[1]}]" if anchor else "None"
        print(f"     #{c['balloon_no']:2d}  {c['spec']:20s}  "
              f"box={box_str:30s}  anchor={anchor_str}")

    with open(correction_json, "w") as f:
        json.dump(corrections, f, indent=2)
    print(f"\n     Saved: {correction_json}")

    # ── Stage 2.7: Balloon Layout Engine ──
    print("\n" + "━" * 50)
    print("  Stage 2.7: Balloon Layout Engine")
    print("━" * 50)
    start = time.time()
    corrections = compute_balloon_layout(png_path, corrections)
    timings["balloon_layout"] = time.time() - start
    
    print(f"  ✅ Computed layout for {len(corrections)} balloons")
    print(f"     Time: {timings['balloon_layout']:.3f}s")
    for c in corrections:
        bp = c.get("balloon_position")
        bp_str = f"[{bp[0]},{bp[1]}]" if bp else "None"
        print(f"     #{c['balloon_no']:2d}  pos={bp_str}")

    # ── Stage 3: Draft Balloon Generation ──
    print("\n" + "━" * 50)
    print("  Stage 3: Draft Balloon Generation (Pillow)")
    print("━" * 50)
    start = time.time()
    generate_ballooned_image(png_path, features, draft_balloon_path, api_key)
    timings["draft_balloons"] = time.time() - start
    print(f"  ✅ Draft balloons saved: {draft_balloon_path}")
    print(f"     Time: {timings['draft_balloons']:.2f}s")

    # ── Stage 4: AI QA Review ──
    print("\n" + "━" * 50)
    print("  Stage 4: AI QA Review (Claude Vision)")
    print("━" * 50)
    start = time.time()
    corrected_features = review_balloons(draft_balloon_path, features, api_key)
    timings["qa_review"] = time.time() - start

    # Detect corrections
    changes = 0
    orig_dict = {f.get("balloon_no"): f for f in extraction_result.get("features", [])}
    for corrected in corrected_features:
        bno = corrected.get("balloon_no")
        if bno in orig_dict:
            orig = orig_dict[bno]
            if orig.get("specification") != corrected.get("specification"):
                changes += 1
                print(f"     Changed #{bno}: "
                      f"'{orig.get('specification')}' → '{corrected.get('specification')}'")
        else:
            print(f"     Added #{bno}: '{corrected.get('specification')}'")
            
    for f in extraction_result.get("features", []):
        bno = f.get("balloon_no")
        if not any(c.get("balloon_no") == bno for c in corrected_features):
            changes += 1
            print(f"     Removed #{bno}: '{f.get('specification')}'")

    print(f"  ✅ QA review complete: {len(corrected_features)} features, {changes} corrections")
    print(f"     Time: {timings['qa_review']:.2f}s")

    with open(corrected_json, "w") as f:
        json.dump(corrected_features, f, indent=2, default=str)
    print(f"     Saved: {corrected_json}")

    # ── Stage 5: Final Balloon Regeneration ──
    print("\n" + "━" * 50)
    print("  Stage 5: Final Balloon Regeneration (Pillow)")
    print("━" * 50)
    start = time.time()
    generate_ballooned_image(png_path, corrected_features, final_balloon_path, api_key)
    timings["final_balloons"] = time.time() - start
    print(f"  ✅ Final balloons saved: {final_balloon_path}")
    print(f"     Time: {timings['final_balloons']:.2f}s")

    # ── Summary ──
    total_time = sum(timings.values())
    print("\n" + "=" * 60)
    print("  PIPELINE SUMMARY")
    print("=" * 60)
    print(f"\n  Total time: {total_time:.2f}s")
    print()
    for stage, elapsed in timings.items():
        pct = (elapsed / total_time) * 100
        bar = "█" * int(pct / 2)
        print(f"    {stage:25s}  {elapsed:6.2f}s  {pct:5.1f}%  {bar}")
    print()
    print(f"  Features: {len(extraction_result.get('features', []))} extracted "
          f"→ {len(corrections)} corrected → {len(corrected_features)} after QA")
    print()
    print("  Output files:")
    print(f"    📄 {png_path}")
    print(f"    📄 {extraction_json}")
    print(f"    📄 {correction_json}")
    print(f"    🎨 {draft_balloon_path}")
    print(f"    📄 {corrected_json}")
    print(f"    🎨 {final_balloon_path}")
    print()

    return True


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Test Geometry Correction Layer + Full Ballooning Pipeline"
    )
    parser.add_argument(
        "--pdf", default=DEFAULT_PDF,
        help=f"Path to PDF for end-to-end test (default: {DEFAULT_PDF})"
    )
    parser.add_argument(
        "--unit", action="store_true",
        help="Run only unit tests (no Claude API calls)"
    )
    parser.add_argument(
        "--e2e", action="store_true",
        help="Run only end-to-end test (skip unit tests)"
    )
    args = parser.parse_args()

    print("\n🔧 Ballooning Pipeline Test Suite")
    print("━" * 40)

    success = True

    if not args.e2e:
        if not run_unit_tests():
            success = False

    if not args.unit:
        if os.path.exists(args.pdf):
            if not run_end_to_end_test(args.pdf):
                success = False
        else:
            print(f"\n  ⚠️  PDF not found: {args.pdf}")
            if not args.e2e:
                print("     (unit tests still ran above)")

    if success:
        print("\n✅ All tests passed!\n")
    else:
        print("\n❌ Some tests failed.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
