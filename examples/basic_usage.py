"""
Basic usage example for the Argus SDK
"""

import asyncio
import os
import sys
import os.path
import time
from coffeeblack import Argus

async def main():
    # Initialize the SDK with API key for authentication
    # You can provide your API key directly or through an environment variable
    api_key = os.environ.get("COFFEEBLACK_API_KEY")
    sdk = Argus(
        api_key=api_key,  # API key for authentication
        verbose=True,
        debug_enabled=True,
        elements_conf=0.2,
        rows_conf=0.4,
        model="ui-detect"  # Set the UI detection model to use (cua, ui-detect, or ui-tars)
    )
    
    # Define the browser name
    browser_name = "Safari" 
    
    try:
        # Open and attach to the browser, waiting 2 seconds by default
        # You can adjust the wait time as needed - longer for slower apps, shorter for faster ones
        await sdk.open_and_attach_to_app(browser_name, wait_time=2.0)

        # Execute an action based on a natural language query
        print("\nExecuting action based on natural language query...")
        await sdk.execute_action("Type https://www.google.com into the url bar")
        
        await sdk.press_key("enter")
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 