"""
Multi-browser window manager example for the Argus SDK

This example demonstrates how to manage multiple browser instances simultaneously,
queueing vision requests and actions between different windows.
"""

import asyncio
import os
import sys
import time
import random
from typing import List, Dict, Any, Optional, Tuple
from collections import deque

from coffeeblack import Argus
from coffeeblack.types import WindowInfo, CoffeeBlackResponse


class BrowserInstance:
    """Represents a single browser instance that can be managed"""
    
    def __init__(self, 
                 name: str, 
                 sdk: Argus, 
                 window_info: Optional[WindowInfo] = None):
        self.name = name
        self.sdk = sdk
        self.window_info = window_info
        self.is_busy = False
        self.last_active = 0
        self.task_queue = deque()
        self.results = []
    
    def __str__(self):
        window_title = self.window_info.title if self.window_info else "Not attached"
        status = "Busy" if self.is_busy else "Idle"
        return f"Browser '{self.name}' - {window_title} - {status}"


class MultiBoxManager:
    """
    A manager for multiple browser instances that can queue and execute
    tasks across different windows efficiently.
    """
    
    def __init__(self, api_key: str, debug_enabled: bool = True):
        self.api_key = api_key
        self.debug_enabled = debug_enabled
        self.browsers: Dict[str, BrowserInstance] = {}
        self.running = False
    
    async def create_browser(self, name: str, wait_time: float = 2.0) -> BrowserInstance:
        """
        Create a new browser instance with the given name
        
        Args:
            name: A unique identifier for this browser instance
            wait_time: Time to wait for the browser to launch
            
        Returns:
            BrowserInstance: The created browser instance
        """
        # Create a new SDK instance for this browser
        sdk = Argus(
            api_key=self.api_key,
            verbose=True,
            debug_enabled=self.debug_enabled,
            elements_conf=0.2,
            rows_conf=0.4,
            model="ui-detect"
        )
        
        browser = BrowserInstance(name=name, sdk=sdk)
        self.browsers[name] = browser
        
        try:
            # For the first browser, open Safari normally
            if len(self.browsers) == 1:  # This is the first browser (since we already added it to self.browsers)
                print(f"Opening first Safari instance for {name}...")
                await sdk.open_and_attach_to_app("Safari", wait_time=wait_time)
            else:
                # For subsequent browsers, attach to the existing Safari and create a new window
                print(f"Creating new Safari window for {name}...")
                
                # Find an existing Safari window
                windows = await sdk.get_open_windows()
                safari_windows = [w for w in windows if w.app_name == "Safari" or "Safari" in w.title]
                
                if not safari_windows:
                    # If no Safari windows found, open Safari first
                    await sdk.open_and_attach_to_app("Safari", wait_time=wait_time)
                else:
                    # Attach to an existing Safari window
                    await sdk.attach_to_window(safari_windows[0].id)
                
                # Create a new window using Command+N
                print("Creating new window with Command+N...")
                await sdk.press_key("n", ["command"])
                
                # Wait for the new window to open and become active
                await asyncio.sleep(1.5)
            
            # Get the updated window info after creating the new window
            # This should now be the most recently created and active Safari window
            windows = await sdk.get_open_windows()
            safari_windows = [w for w in windows if (w.app_name == "Safari" or "Safari" in w.title) and w.is_active]
            
            # If no active Safari window found, try any Safari window
            if not safari_windows:
                safari_windows = [w for w in windows if w.app_name == "Safari" or "Safari" in w.title]
            
            if safari_windows:
                target_window = safari_windows[0]
                
                # Make sure we're attached to this window
                await sdk.attach_to_window(target_window.id)
                
                # Store the window info
                browser.window_info = target_window
                browser.last_active = time.time()
                print(f"Created browser instance: {browser}")
            else:
                raise ValueError("No Safari windows found after attempting to create one")
            
        except Exception as e:
            print(f"Error creating browser instance '{name}': {e}")
            import traceback
            traceback.print_exc()
        
        return browser
    
    async def queue_task(self, 
                        browser_name: str, 
                        task_type: str, 
                        task_args: Dict[str, Any]) -> None:
        """
        Queue a task for execution on a specific browser
        
        Args:
            browser_name: Name of the browser to queue the task for
            task_type: Type of task ('execute_action', 'see', etc.)
            task_args: Arguments for the task
        """
        if browser_name not in self.browsers:
            raise ValueError(f"Browser '{browser_name}' not found")
        
        browser = self.browsers[browser_name]
        browser.task_queue.append((task_type, task_args))
        print(f"Queued {task_type} for browser '{browser_name}', queue size: {len(browser.task_queue)}")
    
    async def process_queues(self):
        """Process all task queues for all browsers concurrently"""
        self.running = True
        
        while self.running:
            # Find the next browser with tasks that isn't busy
            next_browser = None
            for browser in self.browsers.values():
                if not browser.is_busy and browser.task_queue:
                    next_browser = browser
                    break
            
            if next_browser:
                # Mark browser as busy
                next_browser.is_busy = True
                
                # Get the next task
                task_type, task_args = next_browser.task_queue.popleft()
                
                try:
                    # Focus this browser window
                    await self._focus_browser(next_browser)
                    
                    # Execute the task
                    result = await self._execute_task(next_browser, task_type, task_args)
                    
                    # Store the result
                    next_browser.results.append({
                        "task_type": task_type,
                        "task_args": task_args,
                        "result": result,
                        "timestamp": time.time()
                    })
                    
                    # Update last active time
                    next_browser.last_active = time.time()
                    
                except Exception as e:
                    print(f"Error executing task on browser '{next_browser.name}': {e}")
                    
                finally:
                    # Mark browser as idle
                    next_browser.is_busy = False
            
            # If no tasks to process, wait a bit
            await asyncio.sleep(0.1)
    
    async def _focus_browser(self, browser: BrowserInstance) -> None:
        """
        Focus a specific browser window
        
        Args:
            browser: The browser instance to focus
        """
        if not browser.window_info:
            raise ValueError(f"Browser '{browser.name}' is not attached to a window")
        
        # Attach to the window to bring it into focus
        await browser.sdk.attach_to_window(browser.window_info.id)
        print(f"Focused browser '{browser.name}'")
    
    async def _execute_task(self, 
                           browser: BrowserInstance, 
                           task_type: str, 
                           task_args: Dict[str, Any]) -> Any:
        """
        Execute a specific task on a browser
        
        Args:
            browser: The browser instance to execute the task on
            task_type: Type of task to execute
            task_args: Arguments for the task
            
        Returns:
            The result of the task execution
        """
        print(f"Executing {task_type} on browser '{browser.name}'")
        
        if task_type == "execute_action":
            return await browser.sdk.execute_action(**task_args)
        elif task_type == "see":
            return await browser.sdk.see(**task_args)
        elif task_type == "press_key":
            return await browser.sdk.press_key(**task_args)
        elif task_type == "scroll":
            return await browser.sdk.scroll(**task_args)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def stop(self):
        """Stop processing queues"""
        self.running = False
    
    async def get_results(self, browser_name: str) -> List[Dict[str, Any]]:
        """
        Get all results for a specific browser
        
        Args:
            browser_name: Name of the browser to get results for
            
        Returns:
            List of task results
        """
        if browser_name not in self.browsers:
            raise ValueError(f"Browser '{browser_name}' not found")
        
        return self.browsers[browser_name].results


async def main():
    """
    Main entry point for the multi-browser window manager example
    """
    # Initialize with API key
    api_key = os.environ.get("COFFEEBLACK_API_KEY")
    if not api_key:
        print("Please set the COFFEEBLACK_API_KEY environment variable")
        sys.exit(1)
    
    # Create the multi-box manager
    manager = MultiBoxManager(api_key=api_key, debug_enabled=True)
    
    try:
        # Create multiple browser instances
        browsers = []
        browser_count = 4  # We want to manage 4 Safari instances
        
        print(f"Creating {browser_count} browser instances...")
        for i in range(browser_count):
            browser = await manager.create_browser(f"safari_{i}", wait_time=2.0)
            browsers.append(browser)
            # Add a small delay between launching browsers to avoid conflicts
            await asyncio.sleep(1.5)
        
        # Queue tasks for each browser (example: navigate to different websites)
        websites = [
            "https://www.google.com",
            "https://www.github.com",
            "https://www.wikipedia.org",
            "https://www.reddit.com"
        ]
        
        for i, browser_name in enumerate(manager.browsers.keys()):
            # Queue an action to navigate to a website
            await manager.queue_task(
                browser_name=browser_name,
                task_type="execute_action",
                task_args={"query": f"Type {websites[i]} into the url bar"}
            )
            
            # Queue a key press to submit the URL
            await manager.queue_task(
                browser_name=browser_name,
                task_type="press_key",
                task_args={"key": "enter"}
            )
            
            # Queue a vision check to verify the page loaded
            await manager.queue_task(
                browser_name=browser_name,
                task_type="see",
                task_args={
                    "description": f"A webpage from {websites[i].split('//')[1]}",
                    "wait": True,
                    "timeout": 10.0
                }
            )
        
        # Start processing queues in the background
        queue_processor = asyncio.create_task(manager.process_queues())
        
        # Wait for all tasks to complete (5 minute timeout)
        print("Processing tasks across all browsers...")
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *[asyncio.create_task(_wait_for_empty_queue(manager, name)) 
                      for name in manager.browsers.keys()]
                ),
                timeout=300  # 5 minute timeout
            )
            print("All tasks completed successfully!")
        except asyncio.TimeoutError:
            print("Timeout waiting for tasks to complete")
        
        # Stop the queue processor
        manager.stop()
        await queue_processor
        
        # Print results
        for browser_name, browser in manager.browsers.items():
            results = await manager.get_results(browser_name)
            print(f"\nResults for {browser_name}:")
            for i, result in enumerate(results):
                print(f"  Task {i+1}: {result['task_type']}")
                
                # For 'see' tasks, show if the page was detected
                if result['task_type'] == 'see' and 'result' in result:
                    see_result = result['result']
                    if isinstance(see_result, dict):
                        matches = see_result.get('matches', False)
                        confidence = see_result.get('confidence', 'unknown')
                        print(f"    {'✅ Match' if matches else '❌ No match'} (confidence: {confidence})")
        
    except Exception as e:
        print(f"Error in main: {e}")
        import traceback
        traceback.print_exc()


async def _wait_for_empty_queue(manager: MultiBoxManager, browser_name: str) -> None:
    """
    Wait until a browser's task queue is empty
    
    Args:
        manager: The MultiBoxManager instance
        browser_name: Name of the browser to wait for
    """
    browser = manager.browsers[browser_name]
    while len(browser.task_queue) > 0 or browser.is_busy:
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main()) 