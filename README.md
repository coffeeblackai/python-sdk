# CoffeeBlack SDK

Python client for interacting with the CoffeeBlack visual reasoning API.

## Installation

You can install the package using pip:

```bash
# Install from PyPI
pip install coffeeblack

# Install from local directory
pip install -e .

# Or install from GitHub
pip install git+https://github.com/coffeeblack/sdk.git
```

## Features

- Find and interact with windows on your system
- Take screenshots and send them to the CoffeeBlack API
- Execute actions based on natural language queries
- Reason about UI elements without executing actions
- Find and launch applications with semantic search

## Quick Start

```python
import asyncio
import os
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
        # Open and attach to the browser
        await sdk.open_and_attach_to_app(browser_name, wait_time=2.0)

        # Execute an action based on a natural language query
        await sdk.execute_action("Type https://www.google.com into the url bar")
        
        # Press enter key
        await sdk.press_key("enter")
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

## License

MIT

## Documentation

For more detailed documentation, please visit [https://docs.coffeeblack.ai](https://docs.coffeeblack.ai) 