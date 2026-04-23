import os
import sys
from dotenv import load_dotenv

# Load env to get API Key
load_dotenv()
if not os.getenv("ANTHROPIC_API_KEY"):
    print("ANTHROPIC_API_KEY not found in .env")
    sys.exit(1)

# Import AI modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai.drawing_parser import pdf_to_png, parse_drawing
from ai.balloon_generator import generate_ballooned_image

PDF_PATH = "/Users/prakashtupe/Shreeganesh/1001540840_5DR_000_BALL STUD Sheet.1.pdf"
PNG_PATH = "/tmp/test_drawing.png"
BALLOON_PATH = "/tmp/test_ballooned.png"

print("1️⃣ Converting PDF to PNG...")
pdf_to_png(PDF_PATH, PNG_PATH, dpi=150)
print(f"✅ PNG saved to {PNG_PATH}")

print("\n2️⃣ Extracting features using Claude Vision...")
api_key = os.getenv("ANTHROPIC_API_KEY")
features = parse_drawing(PNG_PATH, api_key=api_key)
print(f"✅ Extracted {len(features)} features!")
for f in features:
    print(f"   🎈 {f.get('balloon_no')}: {f.get('description')} ({f.get('specification')})")

print("\n3️⃣ Generating Ballooned Drawing...")
final_img = generate_ballooned_image(PNG_PATH, features, BALLOON_PATH, api_key=api_key)
print(f"\n🎉 DONE! View the ballooned drawing here:\n➡️ {final_img}")
