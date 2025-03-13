"""
Shopify login automation using the Argus SDK
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
    
    # Shopify login credentials
    shopify_email="peyton@coffeeblack.ai"
    shopify_password="2iQZtYRzccA7vPj"
    # shopify_email = os.environ.get("SHOPIFY_EMAIL")  # Set this environment variable or replace with your email
    # shopify_password = os.environ.get("SHOPIFY_PASSWORD")  # Set this environment variable or replace with your password
    
    # Initialize SDK
    sdk = Argus(
        api_key=api_key,  # API key for authentication
        verbose=True,
        debug_enabled=True,
        elements_conf=0.2,
        rows_conf=0.2,
        model="ui-detect"  # Set the UI detection model to use (cua, ui-detect, or ui-tars)
    )
    
    # Define the browser name (You can change this to your preferred browser)
    browser_name = "Safari"  # Change to Safari, Firefox, etc. based on your preference
    
    try:
        # Open and attach to the browser
        print("Opening browser and navigating to Shopify login page...")
        await sdk.open_and_attach_to_app(browser_name, wait_time=2.0)

        # Navigate to Shopify login page
        await sdk.execute_action("Type 'https://www.shopify.com/' into the url bar")
        await sdk.press_key("enter")

        # Wait for the login page to load
        time.sleep(3)
        
        # Verify we're on the login page
        # see_result = await sdk.see(
        #     description="Shopify login page",
        #     wait=True,
        #     timeout=10.0,
        #     interval=0.5
        # )

        await sdk.execute_action("Click on the 'Log in' button")

        
        # if not see_result.get('matches', False):
        #     print("Failed to find Shopify login page. Please check if the URL is correct.")
        #     return
        time.sleep(3)

        # Enter email
        print("Entering email...")
        await sdk.execute_action(f"Type {shopify_email} into the email field")
        
        # Click Next or Continue button to proceed to password
        await sdk.execute_action("Click on the 'Continue with email' button")
        
        time.sleep(2)
        
        # Enter password
        print("Entering password...")
        await sdk.execute_action(f"Type {shopify_password} into the password field")
        time.sleep(2)

        # Click Login button
        await sdk.execute_action("Click on the 'Log in' button")
        
        time.sleep(5)
        await sdk.execute_action("Click on the 'Settings' button")
        time.sleep(2)

        # Verify successful login by checking for dashboard elements
        see_result = await sdk.see(
            description="Shopify dashboard or admin page",
            wait=True,
            timeout=15.0,
            interval=0.5
        )
        
        # Extract the key information from the response
        matches = see_result.get('matches', False)
        confidence = see_result.get('confidence', 'unknown')
        reasoning = see_result.get('reasoning', 'No reasoning provided')
        
        # Display the results
        print(f"Login Result: {'✅ Successfully logged in' if matches else '❌ Login failed'}")
        print(f"Confidence: {confidence}")
        print(f"Reasoning: {reasoning}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
