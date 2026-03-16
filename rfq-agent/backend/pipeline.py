import os
import time
import json
from typing import Dict, Any

from ai.drawing_normalizer import normalize_drawing
from ai.vision_detector import detect_dimensions
from ai.geometry_refiner import refine_geometry
from ai.feature_graph import construct_feature_graph
from ai.view_segmenter import segment_views
from ai.view_assigner import assign_features_to_views
from ai.anchor_clusterer import cluster_anchors
from ai.occupancy_grid import create_occupancy_bitmap
from ai.balloon_layout import compute_balloon_layout
from ai.numbering_logic import assign_balloon_numbers
from ai.renderer import render_balloons
from ai.qa_validator import validate_balloons

def run_pipeline(pdf_path: str, output_dir: str, api_key: str) -> Dict[str, Any]:
    """
    Step 14: Orchestrator
    Executes the 13-stage Automatic Ballooning System pipeline.
    """
    start_time = time.time()
    
    basename = os.path.splitext(os.path.basename(pdf_path))[0].lower().replace(" ", "_")
    png_path = os.path.join(output_dir, f"{basename}_drawing.png")
    final_png_path = os.path.join(output_dir, f"{basename}_ballooned.png")
    features_json_path = os.path.join(output_dir, f"{basename}_features.json")
    
    print("\n" + "="*60)
    print("  AUTOMATIC BALLOONING SYSTEM PIPELINE")
    print("="*60)

    # 1. Normalization
    t0 = time.time()
    meta = normalize_drawing(pdf_path, png_path, target_dpi=300)
    img_w, img_h = meta["width"], meta["height"]
    print(f"  [1] Normalization complete: {img_w}x{img_h} ({time.time() - t0:.2f}s)")

    # 2. Vision Detection
    t0 = time.time()
    raw_features = detect_dimensions(png_path, api_key)
    print(f"  [2] AI Detection complete: {len(raw_features)} features ({time.time() - t0:.2f}s)")

    if not raw_features:
        print("  ⚠️  Pipeline aborted: No features detected.")
        return {}

    # 3. Geometry Refinement
    t0 = time.time()
    refined_features = refine_geometry(png_path, raw_features)
    print(f"  [3] Geometry Refinement complete ({time.time() - t0:.2f}s)")

    # 4. Feature Graph
    t0 = time.time()
    graph = construct_feature_graph(refined_features)
    print(f"  [4] Feature Graph built ({time.time() - t0:.2f}s)")

    # 5. View Segmentation
    t0 = time.time()
    views = segment_views(png_path)
    print(f"  [5] Views Segmented: {len(views)} views found ({time.time() - t0:.2f}s)")

    # 6. Assign Views
    t0 = time.time()
    graph = assign_features_to_views(graph, views)
    print(f"  [6] Feature-to-View Assignment complete ({time.time() - t0:.2f}s)")

    # 7. Clustering
    t0 = time.time()
    graph = cluster_anchors(graph, eps=100.0)
    print(f"  [7] Anchor Clustering complete ({time.time() - t0:.2f}s)")

    # 8. Numbering Logic (Before layout to enforce layout consistency with IDs)
    t0 = time.time()
    graph = assign_balloon_numbers(graph)
    print(f"  [8] Numbering Logic complete ({time.time() - t0:.2f}s)")

    # 9, 10, 11 Occupancy & Layout Algorithms
    t0 = time.time()
    radius = min(30, max(18, min(img_w, img_h) // 100))
    grid = create_occupancy_bitmap(png_path, graph)
    graph = compute_balloon_layout(grid, graph, radius)
    print(f"  [9] Layout Engine Placed {len(graph)} balloons ({time.time() - t0:.2f}s)")

    # 12. Renderer
    t0 = time.time()
    render_balloons(png_path, graph, final_png_path)
    print(f"  [10] Rendering complete: {final_png_path} ({time.time() - t0:.2f}s)")

    # 13. QA Validation
    t0 = time.time()
    graph = validate_balloons(final_png_path, graph, api_key)
    print(f"  [11] QA Validation complete ({time.time() - t0:.2f}s)")

    # 14. Structured Output
    output_data = {"features": graph}
    with open(features_json_path, 'w') as f:
        json.dump(output_data, f, indent=2)
        
    total_time = time.time() - start_time
    print("\n" + "="*60)
    print(f"  ✅ PIPELINE SUCCESS ({total_time:.2f}s)")
    print(f"  Output saved to: {final_png_path}")
    print("="*60 + "\n")

    return output_data

if __name__ == "__main__":
    import argparse
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    parser = argparse.ArgumentParser("Production-Grade Ballooning Pipeline")
    parser.add_argument("--pdf", required=True, help="Path to PDF")
    parser.add_argument("--out", default="/tmp", help="Output directory")
    args = parser.parse_args()
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY not found in environment.")
        sys.exit(1)
        
    run_pipeline(args.pdf, args.out, api_key)
