"""
Google AI Studio automation using the Argus SDK
"""

import asyncio
import os
import time
from coffeeblack import Argus

async def main():
    # Initialize the SDK with API key for authentication
    # You can provide your API key directly or through an environment variable
    api_key = os.environ.get("COFFEEBLACK_API_KEY")
    
    # Initialize SDK
    sdk = Argus(
        api_key=api_key,  # API key for authentication
        verbose=True,
        debug_enabled=True,
        elements_conf=0.2,
        rows_conf=0.4,
        model="ui-detect"  # Set the UI detection model to use
    )
    
    # Define the browser name
    browser_name = "Safari"  # Change to your preferred browser
    
    try:
        # Open and attach to the browser
        print("Opening browser and navigating to Google AI Studio...")
        await sdk.open_and_attach_to_app(browser_name, wait_time=2.0)

        # Navigate to Google AI Studio
        await sdk.execute_action("Use the keyboard command. Type 'https://aistudio.google.com/prompts/new_chat' into the url bar", elements_conf=0.2, rows_conf=0.2)
        await sdk.press_key("enter")

        # Wait for the page to load
        time.sleep(5)
        
        # Click on the Model dropdown
        print("Selecting Gemini 2.0 Flash Experimental model...")
        await sdk.execute_action("Click on the Model dropdown button")
        time.sleep(2)
        
        # Select the Gemini 2.0 Flash Experimental (Image Generation) option
        await sdk.execute_action("Click on the 'Gemini 2.0 Flash Experimental (Image Generation)' option")
        time.sleep(3)

        print("Entering prompt...")
        await sdk.execute_action("Click on the 'Type Something' label", elements_conf=0.2, rows_conf=0.2)
        time.sleep(1)

        async def type_text(sdk, text: str):
            for char in text:
                await sdk.press_key(char)
            
        await type_text(sdk, "Add a girlfriend next to him")
        time.sleep(1)

        # Click on the Add Attachment button in the chat box
        print("Uploading image...")
        await sdk.execute_action("Click on the Add Attachment at the bottom of the screen. Its a plus with a circle around it", elements_conf=0.3, rows_conf=0.5)
        time.sleep(2)
        
        # Click on Upload File
        await sdk.execute_action("Click on the Upload File button in the selector", elements_conf=0.2, rows_conf=0.2)
        time.sleep(2)
        
        # Click on the specific file
        await sdk.execute_action("Click on 'Single.png' text label" , elements_conf=0.2, rows_conf=0.8)
        time.sleep(1)
        
        # Click on Open Button
        await sdk.execute_action("Click on the Open button")
        time.sleep(3)

        await sdk.execute_action("Click on the Run button")
        time.sleep(3)
        
        
        # Wait for processing
        print("Processing request...")
        time.sleep(10)
        
        print("✅ Successfully completed Google AI Studio workflow")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 