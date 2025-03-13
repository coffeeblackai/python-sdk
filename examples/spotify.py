"""
Basic usage example for the Argus SDK with compilation step for visual element storage
"""

import asyncio
import os
import sys
import os.path
import time
import json
import uuid
import io
import base64
from pathlib import Path
from datetime import datetime
from PIL import Image
import requests
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from voyageai import Client as VoyageClient
from coffeeblack import Argus

voyage_api_key = "pa-Kt9snqkuTiF150_2Jh7N_L8Uf6eQIfTBvzR-x5VVUBZ"

# Storage paths for compiled tasks
TASKS_DIR = Path("./compiled_tasks")
TASKS_DIR.mkdir(exist_ok=True)

class TaskCompiler:
    """Helper class to manage the compilation of automation tasks"""
    
    def __init__(self, sdk, task_id=None, voyage_api_key=None, yolo_endpoint=None):
        self.sdk = sdk
        self.task_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        self.voyage_api_key = voyage_api_key
        self.yolo_endpoint = yolo_endpoint or "http://app.coffeeblack.ai/api/yolo"
        self.steps = []
        self.task_dir = TASKS_DIR / self.task_id
        self.task_dir.mkdir(exist_ok=True)
        self.screenshots_dir = self.task_dir / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)
        self.crops_dir = self.task_dir / "crops"
        self.crops_dir.mkdir(exist_ok=True)
        self.task_file = self.task_dir / "task.json"
        
        # Initialize Voyage client if API key is provided
        self.voyage_client = VoyageClient(api_key=voyage_api_key) if voyage_api_key else None
        
        # Load existing steps if present
        self.load_task_metadata()
    
    def load_task_metadata(self):
        """Load task metadata from disk if it exists"""
        if self.task_file.exists():
            try:
                with open(self.task_file, 'r') as f:
                    metadata = json.load(f)
                    self.steps = metadata.get('steps', [])
                    print(f"Loaded {len(self.steps)} steps from existing task: {self.task_id}")
            except Exception as e:
                print(f"Error loading task metadata: {e}")
    
    def save_task_metadata(self):
        """Save task metadata to disk"""
        metadata = {
            "task_id": self.task_id,
            "created_at": datetime.now().isoformat(),
            "modified_at": datetime.now().isoformat(),
            "steps": self.steps
        }
        with open(self.task_file, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    async def get_yolo_detections(self, screenshot, container_conf=0.3, row_conf=0.4, element_conf=0.2):
        """Get UI element detections using YOLO API endpoint"""
        try:
            # Save screenshot to a temporary file
            temp_screenshot_path = self.task_dir / f"temp_screenshot_{int(time.time())}.png"
            with open(temp_screenshot_path, 'wb') as f:
                f.write(base64.b64decode(screenshot))
            
            # Send request to YOLO endpoint
            with open(temp_screenshot_path, 'rb') as f:
                files = {'file': f}
                data = {
                    'container_conf': container_conf,
                    'row_conf': row_conf,
                    'element_conf': element_conf
                }
                response = requests.post(self.yolo_endpoint, files=files, data=data)
            
            # Remove temp file
            temp_screenshot_path.unlink()
            
            if response.status_code != 200:
                print(f"Error from YOLO API: {response.status_code} {response.text}")
                return None
            
            # Parse response
            result = response.json()
            return result
            
        except Exception as e:
            print(f"Error getting YOLO detections: {e}")
            return None
    
    def crop_element_from_screenshot(self, screenshot_image, bbox):
        """Crop an element from a screenshot based on its bounding box"""
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        return screenshot_image.crop((x1, y1, x2, y2))
    
    async def compile_action(self, description, action_type="execute", params=None, confidence_threshold=0.85):
        """Compile an action with user confirmation"""
        params = params or {}
        
        # Ask for user confirmation
        print(f"\n--- Compilation Step ---")
        print(f"Action: {action_type}")
        print(f"Description: {description}")
        confirm = input("Confirm this step? (y/n): ").lower().strip()
        
        if confirm != 'y':
            print("Step skipped.")
            return False
        
        # First, let the SDK handle the action using its natural language capabilities
        try:
            if action_type == "execute":
                # Execute the action first - let the SDK handle element detection and interaction
                # The SDK should return information about the element it interacted with
                result = await self.sdk.execute_action(description, 
                                           elements_conf=params.get("elements_conf", None),
                                           rows_conf=params.get("rows_conf", None))
                                           
                # Extract the element information from the result
                selected_element_info = result.get('chosen_element') if result else None
            elif action_type == "press_key":
                await self.sdk.press_key(params.get("key", ""))
                selected_element_info = None  # No element for key press actions
            
            # Give a short delay for any UI changes to complete
            time.sleep(0.5)
        except Exception as e:
            print(f"Error executing action: {e}")
            return False
        
        # Now capture the screen to record what happened
        screenshot = await self.sdk.capture_screenshot()
        if not screenshot:
            print("Failed to capture screenshot after action")
            return False
            
        # Convert screenshot data to PIL Image
        screenshot_image = Image.open(io.BytesIO(base64.b64decode(screenshot)))
        
        # Save screenshot
        timestamp = int(time.time())
        screenshot_path = self.screenshots_dir / f"step_{len(self.steps)+1}_{timestamp}.png"
        screenshot_image.save(screenshot_path)
        
        element_info = None
        embedding = []
        element_crop_path = None
        
        if action_type == "execute" and selected_element_info:
            # The SDK provided information about the element it interacted with
            print(f"SDK interacted with element: {selected_element_info.get('class_name', 'unknown')}")
            
            # Get the bounding box
            bbox = selected_element_info.get('bbox')
            
            if bbox:
                # Crop the element from the screenshot
                element_crop = self.crop_element_from_screenshot(screenshot_image, bbox)
                element_crop_path = self.crops_dir / f"step_{len(self.steps)+1}_{timestamp}_element.png"
                element_crop.save(element_crop_path)
                
                # Generate embedding using Voyage API
                embedding = self.generate_embedding(element_crop_path)
                
                # Store element information
                element_info = {
                    "bbox": bbox,
                    "class_name": selected_element_info.get("class_name", ""),
                    "confidence": selected_element_info.get("confidence", 0),
                    "type": selected_element_info.get("type", ""),
                    "_uniqueid": selected_element_info.get("_uniqueid", "")
                }
            else:
                print("Element information is missing bounding box")
        
        # If the SDK didn't provide element info or it's a key press action, 
        # check if the user wants to manually identify an element
        if not element_info and action_type == "execute":
            print("\nThe SDK didn't return element information. Would you like to manually identify it?")
            manual_select = input("Identify element manually? (y/n): ").lower().strip()
            
            if manual_select == 'y':
                # Get YOLO detections for the screenshot to see what elements we have
                yolo_result = await self.get_yolo_detections(
                    screenshot, 
                    container_conf=params.get("container_conf", 0.3),
                    row_conf=params.get("row_conf", 0.4), 
                    element_conf=params.get("element_conf", 0.2)
                )
                
                if yolo_result and "boxes" in yolo_result:
                    elements = [box for box in yolo_result["boxes"] if box["type"] == "elements"]
                    
                    if elements:
                        print("\nDetected elements:")
                        for i, element in enumerate(elements):
                            class_name = element.get("class_name", "unknown")
                            confidence = element.get("confidence", 0)
                            print(f"{i+1}. {class_name} (confidence: {confidence:.2f})")
                        
                        try:
                            selection = int(input("Which element was interacted with? (or 0 if none): "))
                            if selection > 0 and selection <= len(elements):
                                selected_element = elements[selection-1]
                                
                                # Crop the element from the screenshot
                                element_crop = self.crop_element_from_screenshot(screenshot_image, selected_element["bbox"])
                                element_crop_path = self.crops_dir / f"step_{len(self.steps)+1}_{timestamp}_element.png"
                                element_crop.save(element_crop_path)
                                
                                # Generate embedding using Voyage API
                                embedding = self.generate_embedding(element_crop_path)
                                
                                # Store element information
                                element_info = {
                                    "bbox": selected_element["bbox"],
                                    "class_name": selected_element.get("class_name", ""),
                                    "confidence": selected_element.get("confidence", 0),
                                    "type": selected_element.get("type", ""),
                                    "_uniqueid": selected_element.get("_uniqueid", "")
                                }
                        except ValueError:
                            print("Invalid selection, no element will be recorded")
        
        if not element_info:
            # No specific element was identified, so we'll use the full screenshot
            print("No specific element identified, using full screenshot for this action.")
            full_path = self.screenshots_dir / f"step_{len(self.steps)+1}_{timestamp}_full.png"
            screenshot_image.save(full_path)
            element_crop_path = full_path
            embedding = self.generate_embedding(full_path)
        
        # Store step information
        step_data = {
            "step_id": len(self.steps) + 1,
            "timestamp": timestamp,
            "action_type": action_type,
            "description": description,
            "screenshot_path": str(screenshot_path.relative_to(TASKS_DIR)),
            "element_crop_path": str(element_crop_path.relative_to(TASKS_DIR)) if element_crop_path else None,
            "element_info": element_info,
            "params": params,
            "embedding": embedding,
            "confidence_threshold": confidence_threshold
        }
        
        self.steps.append(step_data)
        self.save_task_metadata()
        
        print(f"Step {len(self.steps)} compiled successfully.")
        return True
    
    def generate_embedding(self, image_path):
        """Generate multimodal embedding for an image using Voyage API"""
        if not self.voyage_api_key:
            print("Warning: No Voyage API key provided, skipping embedding generation")
            return []
            
        try:
            if self.voyage_client:
                # Generate real embedding using Voyage API
                image = Image.open(image_path)
                inputs = [["", image]]  # Empty text + image
                result = self.voyage_client.multimodal_embed(inputs, model="voyage-multimodal-3")
                return result.embeddings[0]
            else:
                # Simulated embedding for testing
                print(f"Simulating embedding generation for {image_path}")
                return [0.0] * 10  # Simulate a 10-dim embedding
            
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return []
    
    async def execute_compiled_task(self):
        """Execute a previously compiled task using visual similarity matching"""
        if not self.steps:
            print("No steps found in this task")
            return False
            
        print(f"\n=== Executing Compiled Task: {self.task_id} ===")
        print(f"Total steps: {len(self.steps)}")
        
        for i, step in enumerate(self.steps):
            print(f"\nExecuting step {i+1}: {step['action_type']} - {step['description']}")
            
            # Different handling based on action type
            if step["action_type"] == "execute":
                # For execute actions, we can use the visual information to enhance targeting
                if step.get("element_info"):
                    # The action involved a specific element that we have info about
                    # We'll use this info to create a more targeted action
                    
                    # Option 1: Simply use the original description with position information
                    bbox = step["element_info"]["bbox"]
                    center_x = (bbox["x1"] + bbox["x2"]) / 2
                    center_y = (bbox["y1"] + bbox["y2"]) / 2
                    
                    # Create a position-enhanced description
                    targeted_description = f"{step['description']} at position ({int(center_x)}, {int(center_y)})"
                    print(f"Using targeted description: {targeted_description}")
                    
                    await self.sdk.execute_action(targeted_description, 
                                               elements_conf=step['params'].get("elements_conf", None),
                                               rows_conf=step['params'].get("rows_conf", None))
                else:
                    # No specific element info, just use the original description
                    await self.sdk.execute_action(step["description"],
                                               elements_conf=step['params'].get("elements_conf", None),
                                               rows_conf=step['params'].get("rows_conf", None))
            elif step["action_type"] == "press_key":
                # For key press actions, just execute them directly
                await self.sdk.press_key(step["params"].get("key", ""))
            
            print(f"Step {i+1} executed")
            time.sleep(1)  # Add a small delay between steps
            
        print(f"\n=== Task Execution Complete ===")
        return True

async def main():
    # Initialize the SDK with API key for authentication
    api_key = os.environ.get("COFFEEBLACK_API_KEY")
    sdk = Argus(
        api_key=api_key,  # API key for authentication
        verbose=True,
        debug_enabled=True,
        elements_conf=0.2,
        rows_conf=0.2,
        model="ui-detect"  # Set the UI detection model to use (cua, ui-detect, or ui-tars)
    )
    
    # Define the browser name
    browser_name = "Safari" 
    
    # Create a task compiler with a specific task ID for persistence
    task_id = "spotify_login_flow"
    compiler = TaskCompiler(
        sdk=sdk, 
        task_id=task_id, 
        voyage_api_key=voyage_api_key,
        yolo_endpoint="http://app.coffeeblack.ai/api/yolo"
    )
    
    # Flag to determine if we're in compilation mode or execution mode
    # Set to False to run a previously compiled task
    compilation_mode = True
    
    # Check if task already exists, if so suggest execution mode
    if compiler.steps and compilation_mode:
        print(f"Found existing task '{task_id}' with {len(compiler.steps)} steps.")
        run_mode = input("Run in execution mode instead? (y/n): ").lower().strip()
        if run_mode == 'y':
            compilation_mode = False
    
    try:
        # Open and attach to the browser
        await sdk.open_and_attach_to_app(browser_name, wait_time=2.0)

        if compilation_mode:
            # Compilation mode: step through each action with user confirmation
            print("\n=== Starting Compilation Mode ===")
            
            # Keep only the first step for testing
            await compiler.compile_action(
                "Type https://www.spotify.com into the url bar",
                action_type="execute",
                params={}
            )
            
            # Comment out all other steps for now
            """
            # Compile the enter key press
            await compiler.compile_action(
                "Press enter key",
                action_type="press_key",
                params={"key": "enter"}
            )
            
            # Wait for the Spotify page to load and verify
            see_result = await sdk.see(
                description="The spotify home page with their logo",
                wait=True,
                timeout=10.0,
                interval=2
            )
            
            # Compile the login button click
            await compiler.compile_action(
                "Click on the 'Login' button",
                action_type="execute",
                params={"elements_conf": 0.3, "rows_conf": 0.4}
            )
            
            # Wait for the login page
            see_result = await sdk.see(
                description="The spotify login page with a username and password input field",
                wait=True,
                timeout=10.0,
                interval=2
            )
            
            # Compile the email entry step
            await compiler.compile_action(
                "Type 'peytoncas@gmail.com' into the email input field",
                action_type="execute",
                params={}
            )
            
            # Compile ESC key press
            await compiler.compile_action(
                "Press escape key",
                action_type="press_key",
                params={"key": "escape"}
            )
            """
            
            # Save the final task
            compiler.save_task_metadata()
            print(f"\n=== Compilation Complete ===")
            print(f"Task saved as: {compiler.task_id}")
            print(f"Total steps compiled: {len(compiler.steps)}")
            
        else:
            # Execute the previously compiled task
            print("\n=== Starting Execution Mode ===")
            await compiler.execute_compiled_task()
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 