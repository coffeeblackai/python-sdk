"""
Basic usage example for the CoffeeBlack SDK
"""

import asyncio
from coffeeblack import CoffeeBlackSDK

async def main():
    # Initialize the SDK
    sdk = CoffeeBlackSDK()
    
    # Get all open windows
    windows = await sdk.get_open_windows()
    print(f"Found {len(windows)} open windows:")
    for window in windows:
        print(f"- {window.title} ({window.app_name})")
    
    # Attach to a window by name (e.g., Chrome, Safari, etc.)
    browser_name = "Chrome"  # Change this to match your browser
    print(f"\nAttempting to attach to {browser_name}...")
    try:
        await sdk.attach_to_window_by_name(browser_name)
        print(f"Successfully attached to {browser_name}")
        
        # Take a screenshot
        print("Taking a screenshot...")
        screenshot = await sdk.get_screenshot()
        print(f"Screenshot taken, size: {len(screenshot)} bytes")
        
        # Reason about the UI
        print("\nReasoning about the UI...")
        response = await sdk.reason("What elements are visible on the page?")
        print(f"Response: {response.response}")
        print(f"Number of elements detected: {response.num_boxes}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 