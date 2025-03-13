"""
Core implementation of the CoffeeBlack SDK
"""

import os
import time
import json
import platform
import pyautogui
import asyncio
import aiohttp
import traceback
from typing import List, Dict, Optional, Any, Tuple

from .types import WindowInfo, Action, CoffeeBlackResponse
from .utils import debug, window, screenshot
from .utils.app_manager import AppManager

# Configure logging
import logging
logger = logging.getLogger(__name__)


class CoffeeBlackSDK:
    """
    CoffeeBlack SDK - Python client for interacting with the CoffeeBlack visual reasoning API.
    
    This SDK allows you to:
    - Find and interact with windows on your system
    - Take screenshots and send them to the CoffeeBlack API
    - Execute actions based on natural language queries
    - Reason about UI elements without executing actions
    - Find and launch applications with semantic search
    """
    
    def __init__(self, 
                 api_key: str = None,
                 base_url: str = 'https://app.coffeeblack.ai',
                 use_hierarchical_indexing: bool = False,
                 use_query_rewriting: bool = False,
                 debug_enabled: bool = True,
                 debug_dir: str = 'debug',
                 use_embeddings: bool = True,
                 verbose: bool = False,
                 elements_conf: float = 0.4,
                 rows_conf: float = 0.3,
                 model: str = "ui-tars"):
        """
        Initialize the CoffeeBlack SDK.
        
        Args:
            api_key: API key for authentication with the CoffeeBlack API
            base_url: API base URL for CoffeeBlack service
            use_hierarchical_indexing: Whether to use hierarchical indexing for element selection
            use_query_rewriting: Whether to use query rewriting to enhance natural language understanding
            debug_enabled: Whether to enable debug logging and visualization
            debug_dir: Directory to store debug information
            use_embeddings: Whether to use sentence embeddings for semantic app search
            verbose: Whether to show verbose output during operations
            elements_conf: Confidence threshold for UI element detection (0.0-1.0)
            rows_conf: Confidence threshold for UI row detection (0.0-1.0)
            model: UI detection model to use ("cua", "ui-detect", or "ui-tars")
        """
        self.api_key = api_key
        self.base_url = base_url
        self.use_hierarchical_indexing = use_hierarchical_indexing
        self.use_query_rewriting = use_query_rewriting
        self.debug_enabled = debug_enabled
        self.debug_dir = debug_dir
        self.verbose = verbose
        
        # Validate confidence thresholds
        if not 0.0 <= elements_conf <= 1.0:
            raise ValueError("elements_conf must be between 0.0 and 1.0")
        if not 0.0 <= rows_conf <= 1.0:
            raise ValueError("rows_conf must be between 0.0 and 1.0")
            
        # Validate model selection
        valid_models = ["cua", "ui-detect", "ui-tars"]
        if model not in valid_models:
            raise ValueError(f"Model must be one of: {', '.join(valid_models)}")
            
        self.elements_conf = elements_conf
        self.rows_conf = rows_conf
        self.model = model
        
        # Suppress verbose output if not explicitly enabled
        if not verbose:
            for logger_name in ['sentence_transformers', 'transformers', 'huggingface']:
                logging.getLogger(logger_name).setLevel(logging.ERROR)
        
        # Initialize state
        self.active_window = None
        self.last_screenshot_path = None
        
        # Initialize with default DPI value - will be updated per-window
        self.retina_dpi = 1.0
        
        # Print display information if verbose
        if verbose and platform.system() == 'Darwin':
            try:
                displays = screenshot.get_display_info_macos()
                print("Available displays:")
                for i, display in enumerate(displays):
                    print(f"  Display {i+1}: {display['bounds']['width']}x{display['bounds']['height']} " +
                          f"at ({display['bounds']['x']}, {display['bounds']['y']}) " +
                          f"scale: {display['scale_factor']}" +
                          f"{' (main)' if display['is_main'] else ''}")
            except Exception as e:
                if verbose:
                    print(f"Error getting display info: {e}")
        
        # Create debug directory if needed
        if self.debug_enabled:
            os.makedirs(self.debug_dir, exist_ok=True)
            
        # Initialize app manager for app discovery and launching
        self.app_manager = AppManager(use_embeddings=use_embeddings, verbose=verbose)
    
    async def get_open_windows(self) -> List[WindowInfo]:
        """
        Get a list of all open windows on the system.
        
        Returns:
            List of WindowInfo objects, each representing an open window
        """
        return window.get_open_windows()
    
    async def attach_to_window(self, window_id: str) -> None:
        """
        Attach to a specific window, focus it, and capture a screenshot.
        
        Args:
            window_id: The ID of the window to attach to
            
        Raises:
            ValueError: If the window is not found
        """
        # Find the window in our list of windows
        windows = await self.get_open_windows()
        target_window = next((w for w in windows if w.id == window_id), None)
        
        if not target_window:
            raise ValueError(f"Window with ID {window_id} not found")
            
        self.active_window = target_window
        
        # Create debug directory if it doesn't exist
        if self.debug_enabled:
            os.makedirs(self.debug_dir, exist_ok=True)
        
        # Take a screenshot of the window
        timestamp = int(time.time())
        screenshot_path = f"{self.debug_dir}/screenshot_{timestamp}.png"
        
        # Use the reliable pyautogui screenshot method for all platforms
        success = screenshot.take_window_screenshot(screenshot_path, self.active_window.bounds)
            
        if success:
            self.last_screenshot_path = screenshot_path
            if self.verbose:
                print(f"Attached to window: {target_window.title} (ID: {window_id})")
                print(f"Screenshot saved to: {screenshot_path}")
        else:
            raise RuntimeError(f"Failed to take screenshot of window: {target_window.title}")
    
    async def attach_to_window_by_name(self, query: str) -> None:
        """
        Find and attach to a window based on a partial name match.
        
        Args:
            query: Part of the window title to search for
            
        Raises:
            ValueError: If no matching window is found
        """
        target_window = window.find_window_by_name(query)
        await self.attach_to_window(target_window.id)
        
    async def open_app(self, query: str) -> Tuple[bool, str]:
        """
        Find and open an application using natural language query.
        
        Args:
            query: Natural language query like "open Safari" or "launch web browser"
            
        Returns:
            Tuple of (success, message)
        """
        success, message = self.app_manager.open_app(query)
        return success, message
    
    async def open_and_attach_to_app(self, app_name: str, wait_time: float = 2.0) -> None:
        """
        Open an app with the specified name, wait for it to launch, and then attach to it.
        
        Args:
            app_name: Name of the application to open
            wait_time: Time to wait in seconds for the app to launch before attaching
            
        Raises:
            ValueError: If the app couldn't be found or opened
            ValueError: If no window matching the app name could be found after waiting
        """
        logger.info(f"Opening and attaching to {app_name}...")
        
        # Open the app
        success, message = await self.open_app(app_name)
        if not success:
            raise ValueError(f"Failed to open {app_name}: {message}")
        
        # Wait for the specified time to allow the app to launch
        logger.info(f"Waiting {wait_time} seconds for {app_name} to launch...")
        await asyncio.sleep(wait_time)
        
        # Try to attach to the window
        try:
            # Format the window name as "window_name - app_name"
            # First try with exact app name
            window_query = f"{app_name}"
            await self.attach_to_window_by_name(window_query)
            logger.info(f"Successfully attached to {window_query}")
        except ValueError:
            # If that fails, try with just the app name (more permissive)
            try:
                await self.attach_to_window_by_name(app_name)
                logger.info(f"Successfully attached to {app_name}")
            except ValueError:
                # If that also fails, get all open windows and try to find a match
                open_windows = await self.get_open_windows()
                logger.info(f"Available windows: {[w.title for w in open_windows]}")
                raise ValueError(f"Could not find a window matching '{app_name}' after waiting {wait_time} seconds")
    
    def is_app_installed(self, app_name: str) -> bool:
        """
        Check if an application is installed.
        
        Args:
            app_name: Name of the application
            
        Returns:
            True if installed, False otherwise
        """
        return self.app_manager.is_app_installed(app_name)
    
    def get_installed_apps(self) -> List[Any]:
        """
        Get a list of all installed applications.
        
        Returns:
            List of AppInfo objects containing details about installed apps
        """
        return self.app_manager.get_all_apps()
    
    def find_apps(self, query: str) -> List[Tuple[Any, float]]:
        """
        Find applications matching a query.
        
        Args:
            query: Natural language query (e.g., "browser", "text editor")
            
        Returns:
            List of tuples (AppInfo, score) sorted by relevance
        """
        return self.app_manager.find_app(query)
    
    async def execute_action(self, 
                           query: str, 
                           elements_conf: Optional[float] = None, 
                           rows_conf: Optional[float] = None) -> CoffeeBlackResponse:
        """
        Execute a natural language query on the API and optionally execute the chosen action.
        
        Args:
            query: Natural language query
            elements_conf: Optional override for element detection confidence (0.0-1.0)
            rows_conf: Optional override for row detection confidence (0.0-1.0)
            
        Returns:
            CoffeeBlackResponse with the API response
            
        Raises:
            ValueError: If no active window is attached
            RuntimeError: If the API request fails
        """
        # Check if we have an active window
        if not self.active_window:
            raise ValueError("No active window attached. Call attach_to_window() first.")
        
        # Use default confidence values if not provided
        elements_conf = elements_conf if elements_conf is not None else self.elements_conf
        rows_conf = rows_conf if rows_conf is not None else self.rows_conf
        
        # Validate confidence thresholds
        if not 0.0 <= elements_conf <= 1.0:
            raise ValueError("elements_conf must be between 0.0 and 1.0")
        if not 0.0 <= rows_conf <= 1.0:
            raise ValueError("rows_conf must be between 0.0 and 1.0")

        # Always take a fresh screenshot - this is essential for accurate coordinates
        # especially after scrolling operations
        timestamp = int(time.time())
        screenshot_path = f"{self.debug_dir}/action_screenshot_{timestamp}.png"
        
        # Use reliable screenshot method
        success = screenshot.take_window_screenshot(screenshot_path, self.active_window.bounds)
            
        if success:
            self.last_screenshot_path = screenshot_path
        else:
            raise RuntimeError("Failed to take screenshot of active window")
        
        # API URL for the reason endpoint
        url = f"{self.base_url}/api/reason"
        
        try:
            # Log request details
            if self.debug_enabled:
                timestamp = int(time.time())
                request_debug = {
                    'url': url,
                    'query': query,
                    'screenshot': os.path.basename(screenshot_path),
                    'elements_conf': elements_conf,
                    'rows_conf': rows_conf,
                    'timestamp': timestamp
                }
                debug.log_debug(self.debug_dir, "0", request_debug, "request")
            
            # Send request to API
            async with aiohttp.ClientSession() as session:
                with open(screenshot_path, 'rb') as f:
                    # Create form data
                    data = aiohttp.FormData()
                    data.add_field('query', query)
                    data.add_field('file', f, filename=os.path.basename(screenshot_path))
                    
                    # Add confidence parameters
                    data.add_field('element_conf', str(elements_conf))
                    data.add_field('row_conf', str(rows_conf))
                    
                    # Add the model parameter
                    data.add_field('model', self.model)
                    
                    # Add additional options if using experimental features
                    if self.use_hierarchical_indexing:
                        data.add_field('use_hierarchical_indexing', 'true')
                    if self.use_query_rewriting:
                        data.add_field('use_query_rewriting', 'true')
                    
                    # Create headers with Authorization if API key is provided
                    headers = {}
                    if self.api_key:
                        headers['Authorization'] = f'Bearer {self.api_key}'
                    
                    # Send request
                    async with session.post(url, data=data, headers=headers) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise RuntimeError(f"API request failed with status {response.status}: {error_text}")
                        
                        # Get the raw response text
                        response_text = await response.text()
                        
                        # Log raw response
                        if self.debug_enabled:
                            with open(f'{self.debug_dir}/response_raw_{timestamp}.txt', 'w') as f:
                                f.write(response_text)
                        
                        # Parse response
                        try:
                            result = json.loads(response_text)
                        except json.JSONDecodeError:
                            raise RuntimeError(f"Failed to parse response as JSON. Response saved to {self.debug_dir}/response_raw_{timestamp}.txt")
                        
                        # Remove fields not in our CoffeeBlackResponse type
                        if 'annotated_screenshot' in result:
                            del result['annotated_screenshot']
                        if 'query' in result:
                            del result['query']
                        
                        # Log parsed response
                        if self.debug_enabled:
                            with open(f'{self.debug_dir}/response_{timestamp}.json', 'w') as f:
                                json.dump(result, f, indent=2)
                        
                        # Create debug visualization
                        debug_viz_path = ""
                        if self.debug_enabled and 'boxes' in result and screenshot_path:
                            debug_viz_path = debug.create_debug_visualization(
                                self.debug_dir,
                                screenshot_path,
                                result['boxes'],
                                result.get('chosen_element_index', -1),
                                timestamp
                            )
                            if debug_viz_path:
                                print(f"Debug visualization saved to: {debug_viz_path}")
                        
                        # Process results and find best element
                        response = CoffeeBlackResponse(
                            response=response_text,
                            boxes=result.get("boxes", []),
                            raw_detections=result.get("raw_detections", {}),
                            hierarchy=result.get("hierarchy", {}),
                            num_boxes=len(result.get("boxes", [])),
                            chosen_action=Action(**result.get("chosen_action", {})) if result.get("chosen_action") else None,
                            chosen_element_index=result.get("chosen_element_index"),
                            explanation=result.get("explanation", ""),
                            timings=result.get("timings")
                        )
                        
                        # Execute the action
                        if response.chosen_action and response.chosen_element_index is not None and response.chosen_element_index >= 0:
                            try:
                                chosen_box = response.boxes[response.chosen_element_index]
                                action = response.chosen_action
                                
                                # Calculate absolute coordinates based on window position
                                bounds = self.active_window.bounds
                                window_x = bounds['x']
                                window_y = bounds['y']
                                
                                # Get center of the element using bbox
                                bbox = chosen_box["bbox"]
                                
                                # Log basic debug info before calculations
                                print(f"\nDebug coordinate calculation:")
                                print(f"Window position: ({window_x}, {window_y})")
                                print(f"Window dimensions: {bounds['width']}x{bounds['height']}")
                                print(f"Original bbox: x1={bbox['x1']}, y1={bbox['y1']}, x2={bbox['x2']}, y2={bbox['y2']}")
                                
                                # Detect the DPI scaling for the specific monitor this window is on
                                display_dpi = screenshot.detect_retina_dpi(target_bounds=bounds)
                                print(f"Detected DPI for window's display: {display_dpi}")
                                
                                # Update the stored retina_dpi value
                                if abs(self.retina_dpi - display_dpi) > 0.1:
                                    print(f"Updating DPI from {self.retina_dpi} to {display_dpi}")
                                    self.retina_dpi = display_dpi
                                
                                # Get information about displays if we're on macOS
                                system = platform.system()
                                displays = []
                                if system == 'Darwin':
                                    try:
                                        displays = screenshot.get_display_info_macos()
                                        print(f"Found {len(displays)} displays:")
                                        for i, display in enumerate(displays):
                                            print(f"  Display {i+1}: {display['bounds']['width']}x{display['bounds']['height']} " +
                                                f"at ({display['bounds']['x']}, {display['bounds']['y']}) " +
                                                f"scale: {display['scale_factor']}" +
                                                f"{' (main)' if display['is_main'] else ''}")
                                    except Exception as e:
                                        print(f"Error getting display info: {e}")
                                        displays = []
                                
                                # Calculate element dimensions and center point with improved multi-monitor awareness
                                if system == 'Darwin':  # Always use scaling logic on macOS
                                    try:
                                        # Determine scaling factor to use
                                        scaling_factor = self.retina_dpi
                                        primary_display = None
                                        
                                        # Identify primary display for the window
                                        if len(displays) > 0:
                                            # Check if window bounds overlap with any display
                                            window_rect = {
                                                'left': bounds['x'],
                                                'top': bounds['y'],
                                                'right': bounds['x'] + bounds['width'],
                                                'bottom': bounds['y'] + bounds['height']
                                            }
                                            
                                            max_overlap_area = 0
                                            for display in displays:
                                                display_rect = {
                                                    'left': display['bounds']['x'],
                                                    'top': display['bounds']['y'],
                                                    'right': display['bounds']['x'] + display['bounds']['width'],
                                                    'bottom': display['bounds']['y'] + display['bounds']['height']
                                                }
                                                
                                                # Calculate overlap
                                                overlap_left = max(window_rect['left'], display_rect['left'])
                                                overlap_top = max(window_rect['top'], display_rect['top'])
                                                overlap_right = min(window_rect['right'], display_rect['right'])
                                                overlap_bottom = min(window_rect['bottom'], display_rect['bottom'])
                                                
                                                if overlap_left < overlap_right and overlap_top < overlap_bottom:
                                                    overlap_area = (overlap_right - overlap_left) * (overlap_bottom - overlap_top)
                                                    if overlap_area > max_overlap_area:
                                                        max_overlap_area = overlap_area
                                                        primary_display = display
                                                        
                                            if primary_display:
                                                print(f"Window primarily on display at ({primary_display['bounds']['x']}, {primary_display['bounds']['y']})")
                                                print(f"Display scale factor: {primary_display['scale_factor']}")
                                                # Use the display's scaling factor
                                                scaling_factor = primary_display['scale_factor']
                                            else:
                                                print("Couldn't match window to a specific display, using default scaling")
                                        
                                        # For standalone MacBook Retina displays, we need different logic
                                        is_standalone_macbook = (len(displays) == 1 and 
                                                                displays[0]['scale_factor'] > 1.0 and
                                                                displays[0]['is_main'])
                                        
                                        # External monitor detection - check for common non-Retina resolutions
                                        is_standard_monitor = False
                                        for display in displays:
                                            # Check for common monitor resolutions (1080p, 1440p, etc)
                                            if (display['bounds']['width'] in [1920, 2560, 3840] and
                                                display['bounds']['height'] in [1080, 1440, 2160]):
                                                print(f"Detected standard external monitor: {display['bounds']['width']}x{display['bounds']['height']}")
                                                is_standard_monitor = True
                                                # Override the scaling factor for standard monitors
                                                scaling_factor = 1.0
                                                break
                                        
                                        if is_standard_monitor:
                                            print("Using standard monitor scaling (1.0)")
                                            element_width = int(bbox['x2'] - bbox['x1'])
                                            element_height = int(bbox['y2'] - bbox['y1'])
                                            element_x = int(window_x + bbox['x1'] + (element_width / 2))
                                            element_y = int(window_y + bbox['y1'] + (element_height / 2))
                                        elif is_standalone_macbook:
                                            print("Detected standalone MacBook with Retina display")
                                            
                                            # For standalone MacBook, we need to handle UI coordinates differently
                                            # First check if this window might be a system-level UI element
                                            is_system_ui = (bounds['width'] < 100 and bounds['height'] < 100) or bounds['y'] < 50
                                            
                                            # System UI elements like menu bar don't need scaling adjustment
                                            if is_system_ui:
                                                print("Detected system UI element, using direct coordinates")
                                                element_width = int(bbox['x2'] - bbox['x1'])
                                                element_height = int(bbox['y2'] - bbox['y1'])
                                                element_x = int(window_x + bbox['x1'] + (element_width / 2))
                                                element_y = int(window_y + bbox['y1'] + (element_height / 2))
                                            else:
                                                # Regular app window on Retina display
                                                element_width = int((bbox['x2'] - bbox['x1']) / scaling_factor)
                                                element_height = int((bbox['y2'] - bbox['y1']) / scaling_factor)
                                                element_x = int(window_x + (bbox['x1'] / scaling_factor) + (element_width / 2))
                                                element_y = int(window_y + (bbox['y1'] / scaling_factor) + (element_height / 2))
                                        else:
                                            # Multi-monitor or non-Retina setup
                                            element_width = int((bbox['x2'] - bbox['x1']) / scaling_factor)
                                            element_height = int((bbox['y2'] - bbox['y1']) / scaling_factor)
                                            element_x = int(window_x + (bbox['x1'] / scaling_factor) + (element_width / 2))
                                            element_y = int(window_y + (bbox['y1'] / scaling_factor) + (element_height / 2))
                                        
                                        print(f"Adjusted for display scaling: width={element_width}, height={element_height}")
                                        print(f"Scaling factor used: {scaling_factor}")
                                    except Exception as e:
                                        print(f"Error calculating coordinates with multi-monitor awareness: {e}")
                                        # Fall back to basic calculation
                                        element_width = int(bbox['x2'] - bbox['x1'])
                                        element_height = int(bbox['y2'] - bbox['y1'])
                                        element_x = int(window_x + bbox['x1'] + (element_width / 2))
                                        element_y = int(window_y + bbox['y1'] + (element_height / 2))
                                else:
                                    # Non-macOS - basic calculation
                                    element_width = int(bbox['x2'] - bbox['x1'])
                                    element_height = int(bbox['y2'] - bbox['y1'])
                                    element_x = int(window_x + bbox['x1'] + (element_width / 2))
                                    element_y = int(window_y + bbox['y1'] + (element_height / 2))
                                
                                # Log calculated coordinates
                                print(f"Calculated target: ({element_x}, {element_y})")
                                print(f"PyAutoGUI screen size: {pyautogui.size()}")
                                
                                # Round final coordinates to integers
                                element_x = int(element_x)
                                element_y = int(element_y)
                                
                                # Log action details
                                if self.debug_enabled:
                                    action_debug = {
                                        'action_type': action.action,
                                        'coordinates': {
                                            'window_x': window_x,
                                            'window_y': window_y,
                                            'element_x': element_x,
                                            'element_y': element_y,
                                            'element_width': element_width,
                                            'element_height': element_height,
                                            'bbox': {
                                                'x1': bbox['x1'],
                                                'y1': bbox['y1'],
                                                'x2': bbox['x2'],
                                                'y2': bbox['y2']
                                            }
                                        },
                                        'retina_dpi': self.retina_dpi,
                                        'timestamp': timestamp
                                    }
                                    with open(f'{self.debug_dir}/action_{timestamp}.json', 'w') as f:
                                        json.dump(action_debug, f, indent=2)
                                
                                # Execute the appropriate action
                                if action.action == "click":
                                    # Move to position and click
                                    print(f"Executing click at ({element_x}, {element_y})")
                                    pyautogui.moveTo(element_x, element_y, duration=0.2)
                                    pyautogui.click()
                                    
                                elif action.action == "type" and action.input_text:
                                    # Move to position, click to focus, and type
                                    print(f"Clicking at ({element_x}, {element_y}) and typing: {action.input_text}")
                                    pyautogui.moveTo(element_x, element_y, duration=0.2)
                                    pyautogui.click()
                                    time.sleep(1.0)  # Wait for focus
                                    pyautogui.write(action.input_text)
                                    
                                elif action.action == "scroll" and action.scroll_direction:
                                    # Move to position and scroll
                                    print(f"Scrolling {action.scroll_direction} at ({element_x}, {element_y})")
                                    pyautogui.moveTo(element_x, element_y, duration=0.2)
                                    scroll_amount = 100 if action.scroll_direction == "down" else -100
                                    pyautogui.scroll(scroll_amount)
                                
                                elif action.action == "key" and action.key_command:
                                    # Execute a keyboard command
                                    print(f"Pressing key: {action.key_command}")
                                    pyautogui.press(action.key_command)
                                
                                elif action.action == "no_action":
                                    # No action required
                                    print("No action required")
                                
                                else:
                                    print(f"Unsupported action: {action.action}")
                                    
                            except Exception as e:
                                raise RuntimeError(f"Failed to execute action: {e}")
                        
                        return response
                        
        except Exception as e:
            raise RuntimeError(f"Failed to execute action: {e}")

    async def reason(self, 
                   query: str, 
                   screenshot_data: Optional[bytes] = None,
                   elements_conf: Optional[float] = None, 
                   rows_conf: Optional[float] = None) -> CoffeeBlackResponse:
        """
        Send a reasoning query to the API without executing any actions.
        Useful for analysis, planning, or information gathering.
        
        Args:
            query: Natural language query
            screenshot_data: Optional raw screenshot bytes (if None, uses the active window)
            elements_conf: Optional override for element detection confidence (0.0-1.0)
            rows_conf: Optional override for row detection confidence (0.0-1.0)
            
        Returns:
            CoffeeBlackResponse with the API response
            
        Raises:
            ValueError: If no active window is attached and no screenshot is provided
            RuntimeError: If the API request fails
        """
        # Use default confidence values if not provided
        elements_conf = elements_conf if elements_conf is not None else self.elements_conf
        rows_conf = rows_conf if rows_conf is not None else self.rows_conf
        
        # Validate confidence thresholds
        if not 0.0 <= elements_conf <= 1.0:
            raise ValueError("elements_conf must be between 0.0 and 1.0")
        if not 0.0 <= rows_conf <= 1.0:
            raise ValueError("rows_conf must be between 0.0 and 1.0")
            
        # API URL for the reason endpoint
        url = f"{self.base_url}/api/reason"
        
        # Either use provided screenshot or take one of the active window
        screenshot_path = None
        using_temp_file = False
        
        try:
            if screenshot_data is not None:
                # Save the provided screenshot to a temporary file
                timestamp = int(time.time())
                screenshot_path = f"{self.debug_dir}/reason_screenshot_{timestamp}.png"
                with open(screenshot_path, 'wb') as f:
                    f.write(screenshot_data)
                using_temp_file = True
            elif self.active_window and self.last_screenshot_path and os.path.exists(self.last_screenshot_path):
                # Use existing screenshot
                screenshot_path = self.last_screenshot_path
            elif self.active_window:
                # Take a fresh screenshot
                timestamp = int(time.time())
                screenshot_path = f"{self.debug_dir}/reason_screenshot_{timestamp}.png"
                
                # Use reliable screenshot method
                success = screenshot.take_window_screenshot(screenshot_path, self.active_window.bounds)
                    
                if not success:
                    raise RuntimeError("Failed to take screenshot of active window")
            else:
                raise ValueError("No active window and no screenshot provided")
            
            # Log request details
            if self.debug_enabled:
                timestamp = int(time.time())
                request_debug = {
                    'url': url,
                    'query': query,
                    'screenshot': os.path.basename(screenshot_path),
                    'elements_conf': elements_conf,
                    'rows_conf': rows_conf,
                    'timestamp': timestamp
                }
                debug.log_debug(self.debug_dir, "0", request_debug, "reason_request")
            
            # Send request to API
            async with aiohttp.ClientSession() as session:
                with open(screenshot_path, 'rb') as f:
                    # Create form data
                    data = aiohttp.FormData()
                    data.add_field('query', query)
                    data.add_field('file', f, filename=os.path.basename(screenshot_path))
                    
                    # Add confidence parameters
                    data.add_field('element_conf', str(elements_conf))
                    data.add_field('row_conf', str(rows_conf))
                    
                    # Disable action execution
                    data.add_field('execute_action', 'false')
                    
                    # Add the model parameter
                    data.add_field('model', self.model)
                    
                    # Add additional options if using experimental features
                    if self.use_hierarchical_indexing:
                        data.add_field('use_hierarchical_indexing', 'true')
                    if self.use_query_rewriting:
                        data.add_field('use_query_rewriting', 'true')
                    
                    # Create headers with Authorization if API key is provided
                    headers = {}
                    if self.api_key:
                        headers['Authorization'] = f'Bearer {self.api_key}'
                    
                    # Send request
                    async with session.post(url, data=data, headers=headers) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise RuntimeError(f"API request failed with status {response.status}: {error_text}")
                        
                        # Get the raw response text
                        response_text = await response.text()
                        
                        # Log raw response
                        if self.debug_enabled:
                            with open(f'{self.debug_dir}/reason_response_raw_{timestamp}.txt', 'w') as f:
                                f.write(response_text)
                        
                        # Parse response
                        try:
                            result = json.loads(response_text)
                        except json.JSONDecodeError:
                            raise RuntimeError(f"Failed to parse response as JSON. Response saved to {self.debug_dir}/reason_response_raw_{timestamp}.txt")
                        
                        # Remove fields not in our CoffeeBlackResponse type
                        if 'annotated_screenshot' in result:
                            del result['annotated_screenshot']
                        if 'query' in result:
                            del result['query']
                        
                        # Log parsed response
                        if self.debug_enabled:
                            with open(f'{self.debug_dir}/reason_response_{timestamp}.json', 'w') as f:
                                json.dump(result, f, indent=2)
                        
                        # Process results
                        response = CoffeeBlackResponse(
                            response=response_text,
                            boxes=result.get("boxes", []),
                            raw_detections=result.get("raw_detections", {}),
                            hierarchy=result.get("hierarchy", {}),
                            num_boxes=len(result.get("boxes", [])),
                            chosen_action=Action(**result.get("chosen_action", {})) if result.get("chosen_action") else None,
                            chosen_element_index=result.get("chosen_element_index"),
                            explanation=result.get("explanation", ""),
                            timings=result.get("timings")
                        )
                        
                        return response
                        
        except Exception as e:
            raise RuntimeError(f"Failed to execute reasoning query: {e}")
        finally:
            # Clean up temporary file if we created one
            if using_temp_file and screenshot_path and os.path.exists(screenshot_path):
                os.remove(screenshot_path)

    async def press_enter(self) -> None:
        """
        Press the Enter key.
        
        This method provides a simple way to press the Enter key, which is a common
        operation after entering text into a field.
        
        Uses the more generic press_key method.
        """
        await self.press_key('enter')
        
    async def press_key(self, key: str, modifiers: List[str] = None) -> None:
        """
        Press a specified key on the keyboard.
        
        This method provides a flexible way to press any key available in pyautogui.
        Common keys include 'enter', 'tab', 'space', 'backspace', 'esc', 'up', 'down', etc.
        
        Args:
            key (str): The key to press. Must be a valid key name recognized by pyautogui.
                       See pyautogui documentation for available key names.
            modifiers (List[str], optional): List of modifier keys to hold while pressing the main key.
                                             Examples: ['ctrl'], ['command'], ['shift', 'alt'], etc.
        """
        # Convert modifiers if provided
        mod_keys = []
        if modifiers:
            for mod in modifiers:
                mod = mod.lower()
                if mod in ['command', 'cmd']:
                    mod_keys.append('command')
                elif mod in ['control', 'ctrl']:
                    mod_keys.append('ctrl')
                elif mod in ['option', 'alt']:
                    mod_keys.append('alt')
                elif mod in ['shift']:
                    mod_keys.append('shift')
        
        # Press modifiers, then key, then release all
        try:
            with pyautogui.hold(mod_keys):
                pyautogui.press(key)
            logger.info(f"Pressed key: {key}" + (f" with modifiers: {mod_keys}" if mod_keys else ""))
        except Exception as e:
            logger.error(f"Error pressing key {key}: {str(e)}")
    
    async def scroll(self, 
                    scroll_direction: str = "down",
                    scroll_amount: float = 0.5,  # Percentage (0.0-1.0) of window height
                    click_for_focus: bool = True) -> None:
        """
        Scroll the active window in the specified direction by the specified amount
        
        Args:
            scroll_direction: Direction to scroll ('up', 'down', 'left', 'right')
            scroll_amount: Percentage of window height/width to scroll (0.0-1.0)
            click_for_focus: Whether to click in the center of the window first for focus
        """
        if not self.active_window:
            raise ValueError("No active window to scroll. Please attach to a window first.")
            
        try:
            # Validate scroll amount as percentage
            if not 0.0 <= scroll_amount <= 1.0:
                raise ValueError(f"scroll_amount must be between 0.0 and 1.0, got {scroll_amount}")
                
            # Map scroll direction to signs (will be multiplied by calculated scroll amount later)
            direction_signs = {
                "down": -1,  # Negative for down
                "up": 1,     # Positive for up
                "left": 0,   # Not directly supported
                "right": 0   # Not directly supported
            }
            
            # Ensure valid scroll direction
            if scroll_direction.lower() not in direction_signs:
                raise ValueError(f"Invalid scroll_direction: {scroll_direction}. "
                               f"Must be one of: {', '.join(direction_signs.keys())}")
                               
            direction_sign = direction_signs[scroll_direction.lower()]
            
            # Get window bounds
            bounds = self.active_window.bounds
            window_width = bounds['width']
            window_height = bounds['height']
            
            # Calculate window center points
            window_center_x = bounds['x'] + window_width / 2
            window_center_y = bounds['y'] + window_height / 2
            
            # For vertical scrolling (up/down)
            if scroll_direction.lower() in ["up", "down"]:
                # Position cursor in the middle of the window for more reliable scrolling
                if click_for_focus:
                    # Move mouse to center of window
                    logger.info(f"Moving cursor to window center ({window_center_x}, {window_center_y}) before scrolling")
                    pyautogui.moveTo(window_center_x, window_center_y)
                    
                    # Click to ensure the window has focus
                    logger.info("Clicking to ensure window has focus before scrolling")
                    pyautogui.click(window_center_x, window_center_y)
                    await asyncio.sleep(0.2)  # Short pause after click
                
                # Calculate scroll amount in pixels based on window height percentage
                # pyautogui.scroll accepts "clicks" where each click is ~10-20 pixels depending on OS
                # We'll use 15 as a reasonable approximation
                pixels_to_scroll = int(window_height * scroll_amount)
                clicks_to_scroll = pixels_to_scroll // 15  # Approximate conversion to clicks
                
                # Ensure at least 1 click if scroll_amount > 0
                if clicks_to_scroll == 0 and scroll_amount > 0:
                    clicks_to_scroll = 1
                
                # Apply direction sign to get final scroll value
                scroll_value = direction_sign * clicks_to_scroll
                
                # Now scroll from this position
                logger.info(f"Scrolling {scroll_direction} by {abs(scroll_value)} clicks ({pixels_to_scroll} pixels, {scroll_amount:.1%} of window height)")
                pyautogui.scroll(scroll_value)
            else:
                # For left/right scrolling - not directly supported by pyautogui.scroll
                logger.warning(f"Scrolling {scroll_direction} is not directly supported")
                
        except Exception as e:
            logger.error(f"Error scrolling: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def get_screenshot(self) -> bytes:
        """
        Capture a screenshot of the current application window
        
        Returns:
            Screenshot as bytes that can be saved or passed to Gemini
        """
        if not self.active_window:
            raise ValueError("No active window to capture. Call attach_to_window first.")
            
        try:
            # Get the window bounds
            bounds = self.active_window.bounds
            
            # Create a temporary file for the screenshot
            timestamp = int(time.time())
            screenshot_path = f"{self.debug_dir}/screenshot_{timestamp}.png"
            os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
            
            # Use the reliable screenshot method
            success = screenshot.take_window_screenshot(screenshot_path, self.active_window.bounds)
            
            if not success:
                raise RuntimeError("Failed to take screenshot of active window")
            
            # Read the screenshot file into bytes
            with open(screenshot_path, 'rb') as f:
                screenshot_data = f.read()
            
            # Log the capture
            if self.debug_enabled:
                debug_dir = os.path.join(self.debug_dir, 'screenshots')
                os.makedirs(debug_dir, exist_ok=True)
                debug_path = os.path.join(debug_dir, f"screenshot_{timestamp}.png")
                with open(debug_path, 'wb') as f:
                    f.write(screenshot_data)
                print(f"Screenshot saved to {debug_path}")
            
            return screenshot_data
        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            # Return a basic placeholder image in case of error
            from PIL import Image
            import io
            img = Image.new('RGB', (800, 600), color=(73, 109, 137))
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()
    
    async def scroll_until_found(self, 
                                target_description: str, 
                                reference_image: str = None,
                                scroll_direction: str = "down",
                                max_scrolls: int = 10,
                                scroll_amount: float = 0.2,  # Now a percentage (0.0-1.0) of window height
                                scroll_pause: float = 1.0,
                                confidence_threshold: float = 0.7,
                                click_for_focus: bool = True) -> Tuple[bool, Optional[Dict]]:
        """
        Scroll until a specific visual element is found using Gemini Vision model.
        
        This method uses Google's Vertex AI Gemini Vision model to analyze screenshots
        and determine if the target element is visible. If not, it scrolls and checks again.
        
        Args:
            target_description (str): Detailed description of what to look for.
            reference_image (str, optional): Path to a reference image that will be included
                                            in the Gemini prompt to help identify the element.
            scroll_direction (str): Direction to scroll ('up', 'down', 'left', 'right').
            max_scrolls (int): Maximum number of scrolls to attempt.
            scroll_amount (float): Percentage (0.0-1.0) of window height to scroll each time.
                                   For example, 0.5 means scroll half a window height.
            scroll_pause (float): Seconds to pause after each scroll.
            confidence_threshold (float): Minimum confidence score (0-1) to consider the element found.
            click_for_focus (bool): Whether to click in the center of the window before scrolling
                                   to ensure the window has focus for scroll events.
            
        Returns:
            Tuple[bool, Optional[Dict]]: (success, details)
                - success: True if element was found, False otherwise
                - details: Information from Gemini about the found element, or None if not found
        """
        try:
            # Import Vertex AI libraries
            from google.cloud import aiplatform
            from vertexai.preview.generative_models import GenerativeModel, Part
            
            # Initialize Vertex AI
            logger.info(f"Initializing Vertex AI to find: {target_description}")
            aiplatform.init(project=os.getenv('GOOGLE_CLOUD_PROJECT'))
            
            # Load the Gemini model - using the newer and more efficient model
            model = GenerativeModel(
                model_name="gemini-1.5-pro",
                generation_config={
                    "temperature": 0.5,
                    "top_p": 0.8,
                    "max_output_tokens": 2048
                }
            )
            
            # Validate scroll amount as percentage
            if not 0.0 <= scroll_amount <= 1.0:
                raise ValueError(f"scroll_amount must be between 0.0 and 1.0, got {scroll_amount}")
            
            # Map scroll direction to signs (will be multiplied by calculated scroll amount later)
            direction_signs = {
                "down": -1,  # Negative for down
                "up": 1,     # Positive for up
                "left": 0,   # Not directly supported, would need custom impl
                "right": 0   # Not directly supported, would need custom impl
            }
            
            # Ensure valid scroll direction
            if scroll_direction.lower() not in direction_signs:
                raise ValueError(f"Invalid scroll_direction: {scroll_direction}. "
                                f"Must be one of: {', '.join(direction_signs.keys())}")
            
            direction_sign = direction_signs[scroll_direction.lower()]
            scroll_count = 0
            
            # Create reference image part if provided
            reference_image_part = None
            if reference_image and os.path.exists(reference_image):
                logger.info(f"Using reference image to help identify element: {reference_image}")
                with open(reference_image, "rb") as f:
                    reference_bytes = f.read()
                reference_image_part = Part.from_data(mime_type="image/png", data=reference_bytes)
            
            # Create the prompt for Gemini
            prompt_text = f"""## Visual Element Detection Task

**Target Description:** {target_description}

{"I've also attached a reference image of what I'm looking for." if reference_image_part else ""}

Analyze the screenshot and determine if the described element is visible.

If the element IS VISIBLE:
1. Respond with status "FOUND"
2. Describe where it appears on screen (top/middle/bottom, left/right)
3. Provide a confidence score between 0-1 of how certain you are

If the element IS NOT VISIBLE:
1. Respond with status "NOT_FOUND"
2. Briefly explain why you believe it's not visible

## Response Format (JSON)
{{
  "status": "FOUND" or "NOT_FOUND",
  "confidence": <float between 0-1>,
  "description": "<brief description>",
  "location": "<position on screen>",
  "explanation": "<explanation>"
}}
"""
            
            while scroll_count < max_scrolls:
                # Take a screenshot of the current window
                logger.info(f"Taking screenshot (attempt {scroll_count + 1}/{max_scrolls})")
                
                # Check if a window is active
                if not self.active_window:
                    logger.error("No active window to screenshot. Please attach to a window first.")
                    return False, None
                
                # Take the screenshot
                screenshot_path = None
                try:
                    timestamp = int(time.time())
                    screenshot_path = os.path.join(self.debug_dir, f"scroll_search_{timestamp}.png")
                    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                    
                    # Take screenshot using the SDK functionality
                    success = screenshot.take_window_screenshot(screenshot_path, self.active_window.bounds)
                    if not success:
                        logger.error(f"Failed to take screenshot of window: {self.active_window.title}")
                        return False, None
                    
                    # Build multimodal content for Gemini
                    content_parts = []
                    
                    # Add the prompt text first
                    content_parts.append(prompt_text)
                    
                    # Read and add the screenshot
                    with open(screenshot_path, "rb") as f:
                        screenshot_bytes = f.read()
                    content_parts.append(Part.from_data(mime_type="image/png", data=screenshot_bytes))
                    
                    # Add reference image if provided
                    if reference_image_part:
                        content_parts.append(reference_image_part)
                    
                    # Query Gemini
                    logger.info(f"Querying Gemini Vision model")
                    response = model.generate_content(
                        content_parts,
                        stream=False,
                        generation_config={
                            "response_mime_type": "application/json"
                        }
                    )
                    
                    # Parse the response
                    try:
                        # Extract JSON from the response
                        response_text = response.text
                        logger.debug(f"Raw Gemini response: {response_text}")
                        
                        # Handle different response formats
                        import json
                        result = json.loads(response_text)
                        
                        # Handle case where Gemini returns a list
                        if isinstance(result, list):
                            result = result[0] if result else {}
                        
                        # Save debug info if debug is enabled
                        if self.debug_enabled:
                            debug_path = os.path.join(self.debug_dir, f"gemini_response_{timestamp}.json")
                            with open(debug_path, "w") as f:
                                json.dump(result, f, indent=2)
                            logger.info(f"Saved Gemini response to {debug_path}")
                        
                        # Check if found with sufficient confidence
                        if (result.get("status") == "FOUND" and 
                            float(result.get("confidence", 0)) >= confidence_threshold):
                            logger.info(f"Target found: {result.get('description')}")
                            
                            # Save detection image if debug is enabled
                            if self.debug_enabled:
                                # Make a copy of the screenshot in the debug dir
                                import shutil
                                found_image_path = os.path.join(self.debug_dir, f"element_found_{timestamp}.png")
                                shutil.copy(screenshot_path, found_image_path)
                                result["debug_image"] = found_image_path
                            
                            return True, result
                        
                        # Not found or low confidence, continue scrolling
                        logger.info(f"Target not found in current view (confidence: {result.get('confidence', 0)}), scrolling {scroll_direction}")
                        
                    except Exception as e:
                        logger.error(f"Error parsing Gemini response: {str(e)}")
                        import traceback
                        logger.debug(traceback.format_exc())
                        logger.debug(f"Raw response: {response.text}")
                    
                    # Scroll and continue
                    if scroll_direction.lower() in ["up", "down"]:
                        # Position cursor in the middle of the window for more reliable scrolling
                        window_bounds = self.active_window.bounds
                        window_center_x = window_bounds['x'] + window_bounds['width'] // 2
                        window_center_y = window_bounds['y'] + window_bounds['height'] // 2
                        window_height = window_bounds['height']
                        
                        # Calculate scroll amount in pixels based on window height percentage
                        # pyautogui.scroll accepts "clicks" where each click is ~10-20 pixels depending on OS
                        # Converting from percentage to pixels to clicks
                        pixels_to_scroll = int(window_height * scroll_amount)
                        clicks_to_scroll = pixels_to_scroll // 15  # Approximate conversion to clicks (varies by system)
                        
                        # Ensure at least 1 click even for small percentages
                        if clicks_to_scroll == 0 and scroll_amount > 0:
                            clicks_to_scroll = 1
                        
                        # Apply direction sign to get final scroll value
                        scroll_value = direction_sign * clicks_to_scroll
                        
                        # Move cursor to center of window
                        logger.info(f"Moving cursor to window center ({window_center_x}, {window_center_y}) before scrolling")
                        pyautogui.moveTo(window_center_x, window_center_y, duration=0.1)
                        
                        # Click to ensure window has focus if requested
                        if click_for_focus:
                            logger.info("Clicking to ensure window has focus before scrolling")
                            pyautogui.click()
                            await asyncio.sleep(0.1)  # Brief pause after click
                        
                        # Now scroll from this position
                        logger.info(f"Scrolling {scroll_direction} by {abs(scroll_value)} clicks ({pixels_to_scroll} pixels, {scroll_amount:.1%} of window height)")
                        pyautogui.scroll(scroll_value)
                    else:
                        # For left/right, would need custom horizontal scroll implementation
                        logger.warning(f"Scrolling {scroll_direction} is not directly supported")
                    
                    # Increment counter and pause
                    scroll_count += 1
                    await asyncio.sleep(scroll_pause)
                    
                finally:
                    # Clean up temporary file if not in debug mode
                    if screenshot_path and os.path.exists(screenshot_path) and not self.debug_enabled:
                        try:
                            os.remove(screenshot_path)
                        except:
                            pass
            
            # If we get here, we've hit max_scrolls without finding the element
            logger.info(f"Target not found after {max_scrolls} scroll attempts")
            return False, None
            
        except ImportError:
            logger.error("Google Cloud Vertex AI libraries not installed. Please install with: "
                        "pip install google-cloud-aiplatform vertexai")
            return False, None
        except Exception as e:
            logger.error(f"Error in scroll_until_found: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return False, None 