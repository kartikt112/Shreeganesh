import os
import sys
import json
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(".env")

from ai.drawing_parser import parse_drawing, pdf_to_png
from ai.feasibility_engine import process_features
from ai.balloon_generator import generate_ballooned_image
from ai.report_generator import generate_report

# Paths
active_pdf = "/Users/prakashtupe/Shreeganesh/rfq-agent/backend/uploads/drawings/2d47a73c.pdf"
output_dir = "/tmp/verify_output"
os.makedirs(output_dir, exist_ok=True)

img_path = os.path.join(output_dir, "drawing.png")
balloon_path = os.path.join(output_dir, "ballooned.png")
report_path = os.path.join(output_dir, "report.xlsx")

def main():
    print(f"--- Starting Verification for {os.path.basename(active_pdf)} ---")
    
    # 1. Convert PDF to PNG
    print("Step 1: Converting PDF to PNG...")
    pdf_to_png(active_pdf, img_path)
    
    # 2. Parse Drawing
    print("Step 2: Parsing Drawing...")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    features = parse_drawing(drawing_image_path=img_path, api_key=api_key, original_path=active_pdf)
    print(f"Extracted {len(features)} features.")
    
    # 3. Process Feasibility
    print("Step 3: Processing Feasibility...")
    processed_features = process_features(features)
    
    # 4. Generate Ballooned Image
    print("Step 4: Generating Ballooned Image...")
    generate_ballooned_image(img_path, processed_features, balloon_path)
    
    # 5. Generate Report
    print("Step 5: Generating Excel Report...")
    rfq_data = {
        "part_name": "Test Part 2d47a73c",
        "part_no": "2d47a73c",
        "customer_name": "Internal Test",
        "drg_rev": "A / 2026",
        "quantity": 1000
    }
    generate_report(rfq_data, processed_features, report_path)
    
    print("\n--- Verification Complete ---")
    print(f"Results saved in {output_dir}")

if __name__ == "__main__":
    main()
