import os
import requests
import json
import base64

def test_gemini_layout():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("GEMINI_API_KEY not set — skipping")
        return
    model = "gemini-3.1-flash-image-preview" # Using the exact model requested
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    # Load the image
    image_path = "/tmp/swivel_tube_drawing.png"
    with open(image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode("utf-8")
        
    prompt = """Add numbered inspection balloons to this engineering drawing.
Rules:
- each dimension gets one balloon
- place balloons in nearby whitespace
- avoid overlapping balloons
- connect balloons with leader lines
- they should be numbered according to mechanical engineering."""

    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": img_data
                    }
                }
            ]
        }]
    }
    
    print(f"Sending request to {model}...")
    response = requests.post(url, headers=headers, json=payload)
    
    print(f"Status Code: {response.status_code}")
    try:
        data = response.json()
        print("Response JSON length:", len(json.dumps(data)))
        
        # Check if there's an image part in the response
        if 'candidates' in data and len(data['candidates']) > 0:
            parts = data['candidates'][0].get('content', {}).get('parts', [])
            has_image = False
            for part in parts:
                if 'inlineData' in part or 'executableCode' in part:
                    print(f"Found non-text part: {part.keys()}")
                    has_image = True
                elif 'text' in part:
                    print("Text returned:", part['text'][:500] + "...")
            
            if not has_image:
                print("No image data found in the response parts.")
        else:
            print("Response:", json.dumps(data, indent=2))
            
    except Exception as e:
        print(f"Failed to parse response: {e}")
        print(response.text[:1000])

if __name__ == "__main__":
    test_gemini_layout()
