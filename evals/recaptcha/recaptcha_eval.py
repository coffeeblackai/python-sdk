"""
Evaluate CAPTCHA solving capabilities using the CoffeeBlack SDK.

This script:
1. Takes each image in the recaptcha folder
2. Runs it through the solve_captcha function
3. Overlays the solution coordinates on the image
4. Saves the result in the results folder for evaluation
"""

import asyncio
import os
from PIL import Image, ImageDraw, ImageFont
import json
from typing import Dict, Any, List, Tuple
from coffeeblack import CoffeeBlackSDK

# Configuration
INPUT_DIR = "evals/recaptcha"
OUTPUT_DIR = "evals/recaptcha/results"
SUPPORTED_FORMATS = ['.png', '.jpg', '.jpeg', '.webp']
DEV_SERVER = "http://localhost:3000"  # Development server URL

def draw_solution_on_image(image_path: str, coordinates: List[Dict[str, int]], output_path: str) -> None:
    """
    Draw the solution coordinates on the image with numbered points and grid.
    
    Args:
        image_path: Path to the original image
        coordinates: List of coordinate dictionaries with 'x' and 'y' keys
        output_path: Path to save the annotated image
    """
    # Open and convert image to RGBA
    img = Image.open(image_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Create a drawing context
    draw = ImageDraw.Draw(img)
    
    # Draw grid lines (every 50 pixels)
    grid_spacing = 50
    grid_color = (0, 0, 255, 64)  # Semi-transparent blue
    
    for x in range(0, img.width, grid_spacing):
        draw.line([(x, 0), (x, img.height)], fill=grid_color, width=1)
    for y in range(0, img.height, grid_spacing):
        draw.line([(0, y), (img.width, y)], fill=grid_color, width=1)
    
    # Draw coordinates with numbers
    dot_radius = 5
    for i, coord in enumerate(coordinates):
        x, y = coord['x'], coord['y']
        
        # Draw red circle
        draw.ellipse(
            [(x - dot_radius, y - dot_radius), (x + dot_radius, y + dot_radius)],
            fill=(255, 0, 0, 180)  # Semi-transparent red
        )
        
        # Draw number
        draw.text(
            (x + dot_radius + 2, y - dot_radius - 2),
            str(i + 1),
            fill=(255, 0, 0, 255)  # Solid red
        )
    
    # Save the result
    img.save(output_path)

async def evaluate_image(sdk: CoffeeBlackSDK, image_path: str) -> Dict[str, Any]:
    """
    Evaluate a single CAPTCHA image using the SDK.
    
    Args:
        sdk: CoffeeBlack SDK instance
        image_path: Path to the image to evaluate
        
    Returns:
        Dictionary containing evaluation results
    """
    try:
        # Read the image file
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        # Get base filename without extension
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        
        # Use the SDK's solve_captcha method
        result = await sdk.solve_captcha(
            screenshot_data=image_data,
            click_checkbox_first=False,  # Don't try to click since this is just an image
            apply_solution=False  # Don't try to apply the solution
        )
        
        # If solution was found, draw it on the image
        if result.get('status') == 'success' and 'solution' in result:
            solution = result['solution']
            if 'coordinates' in solution:
                output_path = os.path.join(OUTPUT_DIR, f"{base_name}_solved.png")
                draw_solution_on_image(image_path, solution['coordinates'], output_path)
                result['output_image'] = output_path
        
        return result
    
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'image': image_path
        }

async def main():
    """Main function to run the evaluation"""
    # Initialize SDK
    api_key = os.environ.get('COFFEEBLACK_API_KEY')
    if not api_key:
        print("Error: COFFEEBLACK_API_KEY environment variable not set")
        return
    
    sdk = CoffeeBlackSDK(
        api_key=api_key,
        base_url=DEV_SERVER,  # Use local development server
        verbose=True,
        debug_enabled=True,
        elements_conf=0.2,
        rows_conf=0.3,
        container_conf=0.3,
        model="ui-detect"
    )
    
    # Get list of images to evaluate
    images = []
    for filename in os.listdir(INPUT_DIR):
        if any(filename.lower().endswith(ext) for ext in SUPPORTED_FORMATS):
            images.append(os.path.join(INPUT_DIR, filename))
    
    if not images:
        print(f"No supported images found in {INPUT_DIR}")
        return
    
    print(f"Found {len(images)} images to evaluate")
    
    # Create results directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Evaluate each image
    results = []
    for image_path in images:
        print(f"\nEvaluating {os.path.basename(image_path)}...")
        result = await evaluate_image(sdk, image_path)
        results.append({
            'image': os.path.basename(image_path),
            'result': result
        })
        
        # Print result summary
        if result.get('status') == 'success':
            print("✓ Success!")
            if 'solution' in result and 'coordinates' in result['solution']:
                coords = result['solution']['coordinates']
                print(f"  Found {len(coords)} click points")
                if 'output_image' in result:
                    print(f"  Saved annotated image to: {os.path.basename(result['output_image'])}")
        else:
            print(f"✗ Failed: {result.get('error', 'Unknown error')}")
    
    # Save full results to JSON
    results_path = os.path.join(OUTPUT_DIR, 'evaluation_results.json')
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nEvaluation complete! Full results saved to {results_path}")

if __name__ == "__main__":
    asyncio.run(main()) 