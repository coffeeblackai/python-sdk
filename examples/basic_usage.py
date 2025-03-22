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
        model="ui-tars"  # Set the UI detection model to use (cua, ui-detect, or ui-tars)
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
        
        # Wait for page to load using the new wait parameter in see()
        # This will automatically retry until the page loads or the timeout is reached
        print("\nWaiting for Google search page to appear...")
        see_result = await sdk.see(
            description="A Google search page with a search box and the Google logo",
            wait=True,      # Enable waiting for the element to appear
            timeout=10.0,   # Wait up to 10 seconds (default)
            interval=0.5    # Check every 0.5 seconds (default)
        )
        
        # Extract the key information from the response
        matches = see_result.get('matches', False)
        confidence = see_result.get('confidence', 'unknown')
        reasoning = see_result.get('reasoning', 'No reasoning provided')
        
        # Display the results
        print(f"Result: {'✅ Match' if matches else '❌ No match'}")
        print(f"Confidence: {confidence}")
        print(f"Reasoning: {reasoning}")
        
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 