import os
import time
import json
import argparse
import sys

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai"))

from dotenv import load_dotenv
load_dotenv(override=True)

DEFAULT_PDF = "/Users/prakashtupe/Shreeganesh/Swivel_tube.pdf"
OUTPUT_DIR = "/tmp"

def run_dxf_pipeline(pdf_path: str):
    """
    Test the PDF -> DXF -> Parser -> Ballooning pipeline.
    """
    from drawing_parser import pdf_to_png
    from vision_extractor import extract_from_image
    from pdf_to_dxf import extract_pdf_to_dxf
    from ai.dxf_reconstructor import reconstruct_dxf_dimensions
    from ai.balloon_layout_engine import compute_balloon_layout
    from ai.balloon_generator import generate_ballooned_image
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ⚠️  SKIP: ANTHROPIC_API_KEY not set. Set it in backend/.env")
        return False

    basename = os.path.splitext(os.path.basename(pdf_path))[0].lower().replace(" ", "_")
    png_path = os.path.join(OUTPUT_DIR, f"{basename}_drawing.png")
    dxf_path = os.path.join(OUTPUT_DIR, f"{basename}.dxf")
    balloon_path = os.path.join(OUTPUT_DIR, f"{basename}_dxf_balloons.png")
    
    print("\n" + "=" * 60)
    print("  END-TO-END RECONSTRUCTED DXF PIPELINE TEST")
    print("=" * 60)
    
    # 1. PDF -> PNG
    start = time.time()
    pdf_to_png(pdf_path, png_path, dpi=200)
    print(f"  ✅ PDF -> PNG saved: {png_path} ({time.time() - start:.2f}s)")
    
    import cv2
    img = cv2.imread(png_path)
    img_h, img_w = img.shape[:2]
    
    # 2. PDF -> DXF
    start = time.time()
    success = extract_pdf_to_dxf(pdf_path, dxf_path)
    if not success:
        return False
    print(f"  ✅ PDF -> DXF saved: {dxf_path} ({time.time() - start:.2f}s)")
    
    # 3. Vision Extraction
    start = time.time()
    extraction_result = extract_from_image(png_path, api_key)
    features = extraction_result.get("features", [])
    print(f"  ✅ Vision Extraction complete: {len(features)} features ({time.time() - start:.2f}s)")
    
    # 4. DXF Dimension Reconstruction
    start = time.time()
    features = reconstruct_dxf_dimensions(pdf_path, dxf_path, features, img_w, img_h)
    
    # Print out results to see if the matched coordinates look sane
    for f in features:
        anchor = f.get('anchor_point')
        print(f"    #{f.get('balloon_no'):2d} {f.get('specification'):15s} matched={f.get('dxf_matched')} anchor={anchor}")
    
    print(f"  ✅ DXF Parser complete ({time.time() - start:.2f}s)")
    
    # 5. Balloon Layout
    start = time.time()
    features = compute_balloon_layout(png_path, features)
    print(f"  ✅ Layout Engine complete ({time.time() - start:.2f}s)")
    
    # 6. Generator
    start = time.time()
    generate_ballooned_image(png_path, features, balloon_path, api_key)
    print(f"  ✅ DXF Balloons generated: {balloon_path} ({time.time() - start:.2f}s)")

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", default=DEFAULT_PDF, help="Path to PDF")
    args = parser.parse_args()
    run_dxf_pipeline(args.pdf)
