# CoffeeBlack SDK

Python client for interacting with the CoffeeBlack visual reasoning API.

## Installation

You can install the package locally using pip:

```bash
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
from coffeeblack import CoffeeBlackSDK

async def main():
    # Initialize the SDK
    sdk = CoffeeBlackSDK()
    
    # Get all open windows
    windows = await sdk.get_open_windows()
    
    # Attach to a window by name
    await sdk.attach_to_window_by_name("Chrome")
    
    # Execute an action based on natural language
    response = await sdk.execute_action("Click on the search bar")
    
    # Type some text
    await sdk.press_key("Hello, world!")
    
    # Take a screenshot
    screenshot = await sdk.get_screenshot()

if __name__ == "__main__":
    asyncio.run(main())
```

## License

MIT

## Documentation

For more detailed documentation, please visit [https://docs.coffeeblack.ai](https://docs.coffeeblack.ai) 