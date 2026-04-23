#!/usr/bin/env python3
"""
Test sequential balloon placement: feed Gemini's output image back as input for next round.
Usage:
    python3 test_sequential_balloons.py --rfq 32 --batch 1    # 1-at-a-time
    python3 test_sequential_balloons.py --rfq 32 --batch 7    # batch of 7
"""
import argparse, json, os, re, time, sys, io
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

# Force unbuffered output so we see progress in real-time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, write_through=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, write_through=True)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-image-preview")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")


def resize_for_gemini(image_path: str, max_dim: int = 2048):
    """Resize image to fit within max_dim, return (path, (w, h))."""
    img = Image.open(image_path)
    w, h = img.size
    if max(w, h) <= max_dim:
        return image_path, (w, h)
    scale = max_dim / max(w, h)
    nw, nh = int(w * scale), int(h * scale)
    resized = img.resize((nw, nh), Image.LANCZOS)
    out = image_path.replace(".png", "_resized.png")
    resized.save(out, "PNG")
    return out, (nw, nh)


def call_gemini(image_path: str, features: list, placed_nums: list, round_num: int, rfq_id: int = 32):
    """Call Gemini to place balloons on the image. Returns (output_image_path, json_coords)."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    # Resize for Gemini
    resized_path, (input_w, input_h) = resize_for_gemini(image_path)
    with open(resized_path, "rb") as f:
        image_bytes = f.read()

    # Build simple dimension list — no pixel coords, let Gemini find them
    n = len(features)
    nums = ", ".join(str(f["balloon_no"]) for f in features)

    dim_list = ""
    for feat in features:
        spec = feat.get("spec") or feat.get("specification") or ""
        ft = feat.get("type") or feat.get("description") or ""
        dim_list += f"  #{feat['balloon_no']}: {spec} ({ft})\n"

    # Build prompt
    if placed_nums:
        placed_str = ", ".join(str(x) for x in sorted(placed_nums))
        existing_note = f"""NOTE: This image already has balloons numbered {placed_str}. Do NOT touch, move, or redraw them. Only add the NEW balloons listed below."""
    else:
        existing_note = ""

    prompt = f"""Look at this engineering drawing carefully. I need you to find specific dimensions on it and mark each one with a numbered inspection balloon.

{existing_note}

Find these {n} dimensions on the drawing and balloon each one:

{dim_list}
For each dimension:
1. FIND the dimension text on the drawing (read the actual text on the image)
2. Place a small numbered circle (balloon) in clear space near that dimension
3. Draw a thin leader line from the balloon to the dimension it marks

The balloon number must match the # shown above. The leader line connects the balloon circle to the dimension text — this is how inspectors know which balloon goes with which dimension.

After placing all balloons, output a JSON array with each balloon's center position:
[{{"balloon_no": 1, "x": pixel_x, "y": pixel_y}}, ...]

Coordinates should be in the image pixel space ({input_w}x{input_h}).

Important:
- Find and balloon ALL {n} dimensions listed: {nums}
- Each balloon gets a leader line pointing to its dimension
- Don't place balloons on top of drawing lines, text, or other balloons
- Keep the original drawing intact — only add balloons and leader lines
- Use a consistent small circle style with the number centered inside

Output the JSON first, then generate the annotated image."""

    print(f"  [Round {round_num}] Sending {n} features to Gemini ({len(image_bytes)} bytes)...", flush=True)
    t0 = time.time()

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            ),
        )

        output_path = None
        text = ""
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                output_path = os.path.join(UPLOAD_DIR, "drawings", f"seq_round_{round_num:02d}.png")
                with open(output_path, "wb") as f:
                    f.write(part.inline_data.data)
            if hasattr(part, "text") and part.text:
                text += part.text

        # Parse JSON coords
        coords = []
        if text:
            match = re.search(r'\[[\s\S]*?\]', text)
            if match:
                try:
                    raw = json.loads(match.group())
                    for c in raw:
                        if "balloon_no" in c and "x" in c and "y" in c:
                            coords.append({"balloon_no": int(c["balloon_no"]),
                                           "x": float(c["x"]), "y": float(c["y"])})
                except json.JSONDecodeError:
                    pass

        elapsed = time.time() - t0
        img_ok = "YES" if output_path else "NO"
        print(f"  [Round {round_num}] Done in {elapsed:.1f}s — image={img_ok}, coords={len(coords)}", flush=True)

        return output_path, coords

    except Exception as e:
        elapsed = time.time() - t0
        err_str = str(e)
        print(f"  [Round {round_num}] ERROR after {elapsed:.1f}s: {err_str[:120]}", flush=True)
        # For 503/429 errors, return None so outer loop retries with backoff
        return None, []


def run_sequential(rfq_id: int, batch_size: int):
    """Run sequential balloon placement test."""
    # Load features
    feat_path = os.path.join(UPLOAD_DIR, "drawings", f"{rfq_id}_features.json")
    with open(feat_path) as f:
        features = json.load(f)

    drawing_path = os.path.join(UPLOAD_DIR, "drawings", f"{rfq_id}_drawing.png")
    print(f"\n{'='*60}")
    print(f"Sequential Balloon Test — RFQ {rfq_id}")
    print(f"Features: {len(features)}, Batch size: {batch_size}")
    print(f"Drawing: {drawing_path}")
    print(f"{'='*60}\n")

    # Split into batches
    batches = []
    for i in range(0, len(features), batch_size):
        batches.append(features[i:i + batch_size])

    print(f"Rounds: {len(batches)}")
    for i, b in enumerate(batches):
        nums = [f["balloon_no"] for f in b]
        print(f"  Round {i+1}: balloons {nums}")
    print()

    # Run rounds
    current_image = drawing_path
    placed_nums = []
    all_coords = []
    total_start = time.time()

    for round_idx, batch in enumerate(batches):
        round_num = round_idx + 1
        MAX_RETRIES = 5
        success = False

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                wait = min(10 * attempt, 60)  # 20s, 30s, 40s, 50s
                print(f"  -> Retry {attempt}/{MAX_RETRIES} in {wait}s...", flush=True)
                time.sleep(wait)

            output_path, coords = call_gemini(current_image, batch, placed_nums, round_num, rfq_id)

            if output_path:
                current_image = output_path
                new_nums = [f["balloon_no"] for f in batch]
                placed_nums.extend(new_nums)
                all_coords.extend(coords)
                print(f"  ✓ Round {round_num} SUCCESS (attempt {attempt}) — placed: {sorted(placed_nums)}", flush=True)
                success = True
                break
            else:
                print(f"  ✗ Round {round_num} attempt {attempt} FAILED (no image)", flush=True)

        if not success:
            print(f"  !! Round {round_num} FAILED after {MAX_RETRIES} attempts — stopping", flush=True)
            break

        # Small delay between rounds to avoid rate limiting
        if round_idx < len(batches) - 1:
            time.sleep(3)

    total_time = time.time() - total_start

    print(f"\n{'='*60}")
    print(f"RESULTS — Batch size {batch_size}")
    print(f"{'='*60}")
    print(f"Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"Rounds: {len(batches)}")
    print(f"Balloons placed: {len(placed_nums)}/{len(features)}")
    print(f"Final image: {current_image}")
    print(f"All round images saved as seq_round_XX.png in uploads/drawings/")
    print()

    # Copy final image with descriptive name
    final_name = f"seq_final_batch{batch_size}.png"
    final_path = os.path.join(UPLOAD_DIR, "drawings", final_name)
    if current_image != drawing_path:
        Image.open(current_image).save(final_path)
        print(f"Final saved: {final_path}")

    return current_image


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test sequential balloon placement")
    parser.add_argument("--rfq", type=int, default=32, help="RFQ ID")
    parser.add_argument("--batch", type=int, default=1, help="Batch size (1=one-at-a-time, 7=batch)")
    args = parser.parse_args()

    run_sequential(args.rfq, args.batch)
