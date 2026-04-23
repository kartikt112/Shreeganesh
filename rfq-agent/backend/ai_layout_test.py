import os
import sys
import base64
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

def generate_ai_ballooned_image(image_path: str, prompt: str, output_path: str):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    client = Anthropic(api_key=api_key)
    
    with open(image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode("utf-8")
        
    print("Sending prompt to Claude to draw balloons (this may not work as VLMs don't typically generate image files directly without a tool)...")
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_data}},
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        print("Response received:")
        print(response.content[0].text)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    prompt = """Add numbered inspection balloons to this engineering drawing.
Rules:
- each dimension gets one balloon
- place balloons in nearby whitespace
- avoid overlapping balloons
- connect balloons with leader lines
- they should be numbered according to mechanical engineering ."""
    
    generate_ai_ballooned_image("/tmp/swivel_tube_drawing.png", prompt, "/tmp/ai_drawn_balloons.png")
