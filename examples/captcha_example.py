#!/usr/bin/env python3
"""
CoffeeBlack SDK - CAPTCHA Solving Example

This example demonstrates how to use the CoffeeBlack SDK to:
1. Navigate to a website with a CAPTCHA
2. Fill in form fields
3. Automatically detect, solve, and click on CAPTCHA challenges
4. Submit the form

This example uses the Nursys.com nurse license verification form which contains a CAPTCHA.
"""

import os
import sys
import asyncio
import pyautogui
from typing import Dict, Any, Optional
import time

# Import the CoffeeBlack SDK
from coffeeblack import Argus

async def automate_captcha_form(api_key: Optional[str] = None) -> None:
    """
    Automate filling out a form with a CAPTCHA challenge.
    
    Args:
        api_key: Your CoffeeBlack API key (or None to use environment variable)
    """
    print("\n=== CoffeeBlack CAPTCHA Demo ===\n")
    
    # Get API key from environment if not provided
    if not api_key:
        api_key = os.environ.get('COFFEEBLACK_API_KEY')
        if not api_key:
            print("Error: No API key provided. Please set COFFEEBLACK_API_KEY environment variable or pass as parameter.")
            return
    
    # Ensure the API key is properly formatted (no extra whitespace)
    api_key = api_key.strip()
    print(f"Using API key: {api_key[:5]}...{api_key[-5:] if len(api_key) > 10 else ''}")
    
    # Initialize the SDK
    print("Initializing CoffeeBlack SDK...")
    try:
        sdk = Argus(
            api_key=api_key,
            debug_enabled=True,
            verbose=True,
            model="ui-detect"
        )
    except Exception as e:
        print(f"Error initializing SDK: {e}")
        return
    
    try:
        # Step 1: Open the browser and navigate to the demo page
        print("\nStep 1: Opening browser and navigating to reCAPTCHA demo page...")
        await sdk.open_and_attach_to_app("Safari")
        
        # Wait for Safari to fully load
        await asyncio.sleep(3)
        
        # Type the URL and press Enter
        try:
            await sdk.execute_action("Type 'https://www.nursys.com/LQC/LQCSearch.aspx' into the address bar", elements_conf=0.2)
            await asyncio.sleep(1)  # Short pause between actions
            await sdk.press_key("enter")
            # Wait for page to load
            print("Waiting for page to load...")
            await asyncio.sleep(5)  # Increased wait time
        except Exception as e:
            print(f"Error navigating to URL: {e}")
            return
        
        # Step 2: Handle any initial CAPTCHA and agree button
        try:
            # Use the enhanced solve_captcha method to automatically detect and solve CAPTCHA
            # The method will:
            # 1. Check if a CAPTCHA is present
            # 2. Click the "I'm not a robot" checkbox if needed
            # 3. If a visual challenge appears, solve it and click on the solution coordinates
            print("\nStep 2: Checking for initial CAPTCHA...")
            captcha_result = await sdk.solve_captcha(
                click_checkbox_first=True,  # Automatically click checkbox if found
                checkbox_wait_time=3.0,     # Wait 3 seconds after clicking checkbox
                apply_solution=True         # Automatically click on solution coordinates
            )
            
            if captcha_result.get("status") == "success":
                # Check if clicks were applied
                if captcha_result.get("click_status") == "success":
                    print("CAPTCHA solved and solution applied successfully!")
                    print(f"Clicked on {captcha_result.get('click_details', {}).get('coordinates_clicked', 0)} coordinates")
                else:
                    print("CAPTCHA solved successfully, but no clicks were needed.")
            elif captcha_result.get("status") == "no_captcha_detected":
                print("No CAPTCHA detected on initial page.")
            else:
                print(f"Note: CAPTCHA handling: {captcha_result.get('message', captcha_result.get('error', 'Unknown status'))}")
            
            # Look for and click the agree button if present
            await sdk.scroll_down(1)
            await asyncio.sleep(2)  
            await sdk.execute_action("Click on the Agree button")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"Error interacting with initial page: {e}")
            # Continue despite errors

        # Step 3: Fill out the form fields
        try:
            print("\nStep 3: Filling out form fields...")
            response = await sdk.execute_action("Type 'Doe' into the Last Name field", elements_conf=0.2)
            await asyncio.sleep(2)
            
            response = await sdk.execute_action("Type 'John' into the First Name button", elements_conf=0.2, rows_conf=0.2)
            await asyncio.sleep(2)
            
            response = await sdk.execute_action("Click on the License Type selector", elements_conf=0.2)
            await asyncio.sleep(2)
            
            response = await sdk.execute_action("Select RN from the License Type selector", elements_conf=0.2)
            await asyncio.sleep(2)
            
            response = await sdk.execute_action("Click on the State selector", elements_conf=0.2)
            await asyncio.sleep(2)
            
            response = await sdk.execute_action("Select CALIFORNIA-RN from the State selector", elements_conf=0.2)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"Error filling form fields: {e}")
            # Continue despite errors

        # Step 4: Solve the CAPTCHA before submitting the form
        try:
            print("\nStep 4: Checking for CAPTCHA before form submission...")
            captcha_result = await sdk.solve_captcha(
                click_checkbox_first=True,  # Automatically click checkbox if found
                apply_solution=True,        # Automatically click on solution coordinates
                click_delay=0.5             # Wait 0.5 seconds between clicks if multiple
            )
            
            if captcha_result.get("status") == "success":
                # Check if solution required clicking
                if captcha_result.get("click_status") == "success":
                    print("CAPTCHA solved and solution coordinates clicked automatically!")
                    click_details = captcha_result.get("click_details", {})
                    print(f"Clicked on {click_details.get('coordinates_clicked', 0)} coordinates")
                    if click_details.get('window_offset_applied'):
                        print("Window offset was applied to coordinates")
                elif captcha_result.get("click_status") == "no_coordinates":
                    print("CAPTCHA solved but no clicks were needed")
                else:
                    print("CAPTCHA solved successfully!")
            elif captcha_result.get("status") == "no_captcha_detected":
                print("No CAPTCHA detected before submission.")
            else:
                print(f"Warning: CAPTCHA handling issue: {captcha_result.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"Error handling CAPTCHA: {e}")
            # Continue despite errors

        # Step 5: Submit the form and check results
        try:
            print("\nStep 5: Submitting form...")
            response = await sdk.execute_action("Click on the Search button", elements_conf=0.2)
            await asyncio.sleep(3)
            
            # Wait to see the result
            print("\nWaiting to see the result...")
            await asyncio.sleep(5)
            
            # Take a final screenshot to see the result
            print("\nTaking a final screenshot to verify result...")
            await sdk.get_screenshot()
            
            print("\nCAPTCHA automation demo completed!")
        except Exception as e:
            print(f"Error in final steps: {e}")
            
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        # Optionally close the browser here if needed
        # await sdk.execute_action("Close the browser")
        print("\nDemo finished.")

if __name__ == "__main__":
    # Get API key from command line if provided
    api_key = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Run the example
    asyncio.run(automate_captcha_form(api_key)) 