"""
Debug utilities for the CoffeeBlack SDK
"""

import os
import json
import time
from typing import Any, Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont


def create_debug_visualization(
    debug_dir: str,
    screenshot_path: str, 
    boxes: List[Dict], 
    chosen_index: int, 
    timestamp: Optional[int] = None
) -> str:
    """
    Create a debug visualization of the detected UI elements.
    
    Args:
        debug_dir: Directory to save debug files
        screenshot_path: Path to the screenshot
        boxes: List of detected UI elements
        chosen_index: Index of the chosen element (-1 if none)
        timestamp: Optional timestamp for the debug file
        
    Returns:
        Path to the debug visualization
    """
    try:
        # Ensure debug directory exists
        os.makedirs(debug_dir, exist_ok=True)
        
        # Use current timestamp if none provided
        if timestamp is None:
            timestamp = int(time.time())
            
        # Create debug output path
        debug_path = f"{debug_dir}/debug_viz_{timestamp}.png"
        
        # Open the screenshot
        img = Image.open(screenshot_path).convert('RGBA')
        draw = ImageDraw.Draw(img)
        
        # Try to load a font, fall back to default if not available
        try:
            font = ImageFont.truetype("Arial.ttf", 12)
        except:
            font = ImageFont.load_default()
        
        # Draw boxes for all elements
        for i, box in enumerate(boxes):
            # Get coordinates from the bbox field
            if 'bbox' not in box:
                continue
                
            bbox = box['bbox']
            x1, y1 = float(bbox['x1']), float(bbox['y1'])
            x2, y2 = float(bbox['x2']), float(bbox['y2'])
            
            # Determine color based on whether this is the chosen element
            color = (0, 255, 0, 128) if i == chosen_index else (255, 0, 0, 64)
            text_color = (0, 200, 0) if i == chosen_index else (200, 0, 0)
            
            # Draw rectangle
            draw.rectangle([x1, y1, x2, y2], outline=text_color, width=2)
            
            # Add ID and class info
            label = f"{i}: {box.get('class_name', 'unknown')}"
            draw.text((x1, y1-15), label, fill=text_color, font=font)
        
        # Save visualization
        img.save(debug_path)
        return debug_path
        
    except Exception as e:
        print(f"Error creating debug visualization: {e}")
        return ""


def log_debug(debug_dir: str, stage: str, data: Any, suffix: str) -> str:
    """
    Log debug data to a file.
    
    Args:
        debug_dir: Directory to save debug files
        stage: Stage of processing (e.g., "api_request")
        data: Data to log
        suffix: Suffix for the log file name
        
    Returns:
        Path to the log file
    """
    try:
        # Ensure debug directory exists
        os.makedirs(debug_dir, exist_ok=True)
        
        # Create filename with timestamp
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"{debug_dir}/stage{stage}_{suffix}_{timestamp}.json"
        
        # Write the data to the file
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Logged {suffix} to {filename}")
        return filename
    except Exception as e:
        print(f"Error logging debug data: {e}")
        return "" 