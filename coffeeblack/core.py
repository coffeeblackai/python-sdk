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
import base64
from typing import List, Dict, Optional, Any, Tuple, Callable, TypeVar, Union

from .types import WindowInfo, Action, CoffeeBlackResponse, ExtractResponse
from .utils import debug, window, screenshot
from .utils.app_manager import AppManager
from .tasks import TaskManager
from .extract import HTMLExtractor

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
    - Manage and process tasks through the CoffeeBlack API
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
                 container_conf: float = 0.3,
                 model: str = "ui-tars",
                 max_tokens: int = 1024,
                 max_retries: int = 2,
                 retry_backoff: float = 0.5):
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
            container_conf: Confidence threshold for UI container detection (0.0-1.0)
            model: UI detection model to use ("cua", "ui-detect", or "ui-tars")
            max_tokens: Maximum number of tokens for model generation (UI-TARS only)
            max_retries: Maximum number of retries for transient errors
            retry_backoff: Backoff time between retries in seconds
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
        if not 0.0 <= container_conf <= 1.0:
            raise ValueError("container_conf must be between 0.0 and 1.0")
            
        # Validate model selection
        valid_models = ["cua", "ui-detect", "ui-tars"]
        if model not in valid_models:
            raise ValueError(f"Model must be one of: {', '.join(valid_models)}")
            
        self.elements_conf = elements_conf
        self.rows_conf = rows_conf
        self.container_conf = container_conf
        self.model = model
        self.max_tokens = max_tokens
        
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
        
        # Initialize task manager for task management
        self.tasks = TaskManager(self)
        
        # Retry settings
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        
        # Initialize HTML extractor
        self.html_extractor = HTMLExtractor(
            base_url=base_url,
            api_key=api_key,
            debug_enabled=debug_enabled,
            debug_dir=debug_dir
        )
    
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
        
    async def open_app(self, query: str, path: str = None) -> Tuple[bool, str]:
        """
        Find and open an application using natural language query.
        
        Args:
            query: Natural language query like "open Safari" or "launch web browser"
            
        Returns:
            Tuple of (success, message)
        """
        success, message = self.app_manager.open_app(query, path=path)
        return success, message
    
    async def open_and_attach_to_app(self, app_name: str, path: str = None, wait_time: float = 2.0) -> None:
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
        success, message = await self.open_app(app_name, path=path)
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
                           rows_conf: Optional[float] = None,
                           model: Optional[str] = "ui-detect",
                           max_tokens: Optional[int] = None,
                           reference_element: Optional[Union[str, bytes]] = None,
                           container_conf: Optional[float] = None,
                           iou_threshold: Optional[float] = None,
                           detection_sensitivity: Optional[float] = None,
                           elements: Optional[str] = None,
                           skip_image_for_static: Optional[bool] = None,
                           temperature: Optional[float] = None,
                           device_type: Optional[str] = None,
                           execute: bool = True) -> CoffeeBlackResponse:
        """
        Execute a natural language query on the API and optionally execute the chosen action.
        
        Args:
            query: Natural language query
            elements_conf: Optional override for element detection confidence (0.0-1.0)
            rows_conf: Optional override for row detection confidence (0.0-1.0)
            model: Optional override for UI detection model ("cua", "ui-detect", "ui-tars", "oai-cua", "bytedance-research/UI-TARS-7B-DPO")
            max_tokens: Optional maximum number of tokens for model generation (UI-TARS only)
            reference_element: Optional image data (bytes) or file path (str) of a reference UI element to help with detection
            container_conf: Optional override for container detection confidence (0.0-1.0)
            iou_threshold: Optional Intersection over Union threshold (0.0-1.0)
            detection_sensitivity: Optional single value to adjust all confidence parameters
            elements: Optional JSON string containing element information
            skip_image_for_static: Optional boolean to skip image processing for static commands
            temperature: Optional temperature parameter for UI-TARS/CUA models (0.0-1.0)
            device_type: Optional device type ("desktop" or "mobile")
            execute: If True (default), execute the chosen action (click, type, etc.). If False, return the analysis without executing the action.
            
        Returns:
            CoffeeBlackResponse with the API response
            
        Raises:
            ValueError: If no active window is attached
            ValueError: If invalid model is specified
            ValueError: If invalid confidence thresholds are provided
            RuntimeError: If the API request fails
        """
        # Check if we have an active window
        if not self.active_window:
            raise ValueError("No active window attached. Call attach_to_window() first.")
        
        # Use default confidence values if not provided
        elements_conf = elements_conf if elements_conf is not None else self.elements_conf
        rows_conf = rows_conf if rows_conf is not None else self.rows_conf
        
        # Use default model if not provided
        selected_model = model if model is not None else self.model
        
        # Validate model selection if provided
        valid_models = ["cua", "ui-detect", "ui-tars", "oai-cua", "bytedance-research/UI-TARS-7B-DPO"]
        if selected_model not in valid_models:
            raise ValueError(f"Model must be one of: {', '.join(valid_models)}")
        
        # Validate confidence thresholds
        if not 0.0 <= elements_conf <= 1.0:
            raise ValueError("elements_conf must be between 0.0 and 1.0")
        if not 0.0 <= rows_conf <= 1.0:
            raise ValueError("rows_conf must be between 0.0 and 1.0")
        if container_conf is not None and not 0.0 <= container_conf <= 1.0:
            raise ValueError("container_conf must be between 0.0 and 1.0")
        if iou_threshold is not None and not 0.0 <= iou_threshold <= 1.0:
            raise ValueError("iou_threshold must be between 0.0 and 1.0")
        if detection_sensitivity is not None and not 0.0 <= detection_sensitivity <= 1.0:
            raise ValueError("detection_sensitivity must be between 0.0 and 1.0")
        if temperature is not None and not 0.0 <= temperature <= 1.0:
            raise ValueError("temperature must be between 0.0 and 1.0")
            
        # Validate device type if provided
        if device_type is not None and device_type not in ["desktop", "mobile"]:
            raise ValueError("device_type must be either 'desktop' or 'mobile'")

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
        
        # Prepare reference element if provided
        reference_element_data = None
        using_reference_element = False
        
        if reference_element is not None:
            # Check if reference_element is a file path (str) or image data (bytes)
            if isinstance(reference_element, str):
                # It's a file path, read the file
                with open(reference_element, 'rb') as f:
                    reference_element_data = f.read()
            else:
                # It's already image data (bytes), use it directly
                reference_element_data = reference_element
            
            using_reference_element = True
        
        # API URL for the reason endpoint
        url = f"{self.base_url}/api/reason"
        
        try:
            # Log request details
            if self.debug_enabled:
                request_debug = {
                    'url': url,
                    'query': query,
                    'screenshot': os.path.basename(screenshot_path),
                    'elements_conf': elements_conf,
                    'rows_conf': rows_conf,
                    'model': selected_model,
                    'reference_element': 'reference_element.png' if using_reference_element else None,
                    'container_conf': container_conf,
                    'iou_threshold': iou_threshold,
                    'detection_sensitivity': detection_sensitivity,
                    'elements': elements,
                    'skip_image_for_static': skip_image_for_static,
                    'temperature': temperature,
                    'device_type': device_type,
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
                    
                    # Add container confidence if provided
                    if container_conf is not None:
                        data.add_field('container_conf', str(container_conf))
                    
                    # Add IOU threshold if provided
                    if iou_threshold is not None:
                        data.add_field('iou_threshold', str(iou_threshold))
                    
                    # Add detection sensitivity if provided
                    if detection_sensitivity is not None:
                        data.add_field('detection_sensitivity', str(detection_sensitivity))
                    
                    # Add elements JSON if provided
                    if elements is not None:
                        data.add_field('elements', elements)
                    
                    # Add skip_image_for_static if provided
                    if skip_image_for_static is not None:
                        data.add_field('skip_image_for_static', str(skip_image_for_static).lower())
                    
                    # Add reference element if provided
                    if using_reference_element:
                        data.add_field('reference_element', 
                                     reference_element_data,
                                     filename='reference_element.png',
                                     content_type='image/png')
                    
                    # Add logging to show what's being sent to API
                    if self.verbose:
                        print("\n=== API Request Parameters ===")
                        print(f"Query: {query}")
                        print(f"Screenshot: {os.path.basename(screenshot_path)}")
                        print(f"element_conf: {elements_conf}")
                        print(f"row_conf: {rows_conf}")
                        if container_conf is not None:
                            print(f"container_conf: {container_conf}")
                        if iou_threshold is not None:
                            print(f"iou_threshold: {iou_threshold}")
                        if detection_sensitivity is not None:
                            print(f"detection_sensitivity: {detection_sensitivity}")
                        if elements is not None:
                            print(f"elements: {elements}")
                        if skip_image_for_static is not None:
                            print(f"skip_image_for_static: {skip_image_for_static}")
                        print(f"model: {selected_model}")
                        if temperature is not None:
                            print(f"temperature: {temperature}")
                        if device_type is not None:
                            print(f"device_type: {device_type}")
                        if using_reference_element:
                            print(f"reference_element: reference_element.png")
                        print("=============================\n")
                    
                    # Add the model parameter
                    data.add_field('model', selected_model)
                    
                    # Add max_tokens parameter if provided (UI-TARS only)
                    if selected_model in ["ui-tars", "bytedance-research/UI-TARS-7B-DPO"]:
                        tokens = max_tokens if max_tokens is not None else self.max_tokens
                        data.add_field('max_tokens', str(tokens))
                    
                    # Add temperature if provided (UI-TARS/CUA only)
                    if temperature is not None and selected_model in ["ui-tars", "bytedance-research/UI-TARS-7B-DPO", "cua", "oai-cua"]:
                        data.add_field('temperature', str(temperature))
                    
                    # Add device_type if provided
                    if device_type is not None:
                        data.add_field('device_type', device_type)
                    
                    # Add additional options if using experimental features
                    if self.use_hierarchical_indexing:
                        data.add_field('use_hierarchical_indexing', 'true')
                    if self.use_query_rewriting:
                        data.add_field('use_query_rewriting', 'true')
                    
                    # Create headers with Authorization if API key is provided
                    headers = {}
                    if self.api_key:
                        headers['Authorization'] = f'Bearer {self.api_key}'
                    
                    # Use the retry utility method
                    success, response_text, error_message = await self._make_api_request_with_retry(
                        session=session,
                        url=url,
                        data=data,
                        headers=headers,
                        debug_prefix="execute",
                        timestamp=timestamp
                    )
                    
                    if not success:
                        raise RuntimeError(f"Failed to execute action: {error_message}")
                    
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
                    
                    # Handle different API response formats (ui-tars vs ui-detect)
                    chosen_action = None
                    if 'chosen_action' in result:
                        # Standard format
                        chosen_action = Action(**result.get("chosen_action", {})) if result.get("chosen_action") else None
                    elif 'action' in result:
                        # UI-TARS format - convert to our Action format
                        action_data = result.get('action', {})
                        if action_data:
                            # Map 'type' to 'action' for UI-TARS responses
                            chosen_action = Action(
                                action=action_data.get('type'),  # Map 'type' to 'action'
                                key_command=action_data.get('key_command'),
                                input_text=action_data.get('input_text'),
                                scroll_direction=action_data.get('scroll_direction'),
                                confidence=1.0  # Default confidence if not provided
                            )
                    
                    # Process results and find best element
                    response = CoffeeBlackResponse(
                        response=response_text,
                        boxes=result.get("boxes", []),
                        raw_detections=result.get("raw_detections", {}),
                        hierarchy=result.get("hierarchy", {}),
                        num_boxes=len(result.get("boxes", [])),
                        chosen_action=chosen_action,
                        chosen_element_index=result.get("chosen_element_index"),
                        explanation=result.get("explanation", ""),
                        timings=result.get("timings")
                    )
                    
                    # Execute the action only if execute=True
                    if execute and response.chosen_action and response.chosen_element_index is not None and response.chosen_element_index >= 0:
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
                            
                            # Check if we have pre-calculated absolute coordinates from the API
                            if "absolute_coordinates" in chosen_box:
                                print(f"Using pre-calculated absolute coordinates: {chosen_box['absolute_coordinates']}")
                                abs_x = chosen_box["absolute_coordinates"][0]
                                abs_y = chosen_box["absolute_coordinates"][1]
                                
                                # Still need to apply window offset
                                element_x = int(window_x + abs_x)
                                element_y = int(window_y + abs_y)
                                print(f"After window offset: ({element_x}, {element_y})")
                                
                                # Set these for debug logging below
                                element_width = int(bbox['x2'] - bbox['x1'])
                                element_height = int(bbox['y2'] - bbox['y1'])
                            
                            # Check if we have normalized coordinates from UI-TARS
                            elif "normalized_coordinates" in chosen_box:
                                print(f"Using normalized coordinates: {chosen_box['normalized_coordinates']}")
                                norm_x = chosen_box["normalized_coordinates"][0]
                                norm_y = chosen_box["normalized_coordinates"][1]
                                
                                # UI-TARS uses a 0-1000 scale, so we need to convert to pixels
                                # based on the screenshot/window dimensions
                                abs_x = int(norm_x * bounds['width'] / 1000)
                                abs_y = int(norm_y * bounds['height'] / 1000)
                                
                                # Apply window offset
                                element_x = int(window_x + abs_x)
                                element_y = int(window_y + abs_y)
                                print(f"Calculated from normalized (0-1000): ({element_x}, {element_y})")
                                
                                # Set these for debug logging below
                                element_width = int(bbox['x2'] - bbox['x1'])
                                element_height = int(bbox['y2'] - bbox['y1'])
                            
                            else:
                                # Original bbox-based calculation
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
                            # Log the error but don't necessarily raise it if we only failed execution
                            # The reasoning part might still be valuable
                            error_message = f"Failed to execute action: {e}"
                            logger.error(error_message)
                            # Optionally, add the execution error to the response object
                            if not hasattr(response, 'execution_error'):
                                response.execution_error = error_message
                            # Depending on desired behavior, you might re-raise or just return the response
                            # Re-raising for now to keep original behavior on execution failure
                            raise RuntimeError(error_message)
                    
                    return response
                    
        except Exception as e:
            raise RuntimeError(f"Failed to execute action: {e}")
        finally:
            # Clean up temporary reference element file if we created one
            if using_reference_element and reference_element_data:
                # No need to clean up since we're using the data directly
                pass

    async def reason(self, 
                   query: str, 
                   screenshot_data: Optional[bytes] = None,
                   elements_conf: Optional[float] = None, 
                   rows_conf: Optional[float] = None,
                   model: Optional[str] = None,
                   max_tokens: Optional[int] = None,
                   reference_element: Optional[bytes] = None,
                   container_conf: Optional[float] = None) -> CoffeeBlackResponse:
        """
        Send a reasoning query to the API without executing any actions.
        Useful for analysis, planning, or information gathering.
        
        Args:
            query: Natural language query
            screenshot_data: Optional raw screenshot bytes (if None, uses the active window)
            elements_conf: Optional override for element detection confidence (0.0-1.0)
            rows_conf: Optional override for row detection confidence (0.0-1.0)
            model: Optional override for UI detection model ("cua", "ui-detect", or "ui-tars")
            max_tokens: Optional maximum number of tokens for model generation (UI-TARS only)
            reference_element: Optional image data (bytes) of a reference UI element to help with detection
            container_conf: Optional override for container detection confidence (0.0-1.0)
            
        Returns:
            CoffeeBlackResponse with the API response
            
        Raises:
            ValueError: If no active window is attached and no screenshot is provided
            ValueError: If invalid model is specified
            RuntimeError: If the API request fails
        """
        # Use default confidence values if not provided
        elements_conf = elements_conf if elements_conf is not None else self.elements_conf
        rows_conf = rows_conf if rows_conf is not None else self.rows_conf
        
        # Use default model if not provided
        selected_model = model if model is not None else self.model
        
        # Validate model selection if provided
        valid_models = ["cua", "ui-detect", "ui-tars"]
        if selected_model not in valid_models:
            raise ValueError(f"Model must be one of: {', '.join(valid_models)}")
        
        # Validate confidence thresholds
        if not 0.0 <= elements_conf <= 1.0:
            raise ValueError("elements_conf must be between 0.0 and 1.0")
        if not 0.0 <= rows_conf <= 1.0:
            raise ValueError("rows_conf must be between 0.0 and 1.0")
        if container_conf is not None and not 0.0 <= container_conf <= 1.0:
            raise ValueError("container_conf must be between 0.0 and 1.0")
            
        # API URL for the reason endpoint
        url = f"{self.base_url}/api/reason"
        
        # Either use provided screenshot or take one of the active window
        screenshot_path = None
        using_temp_file = False
        
        # Prepare reference element if provided
        reference_element_path = None
        using_reference_element = False
        
        if reference_element is not None:
            # Save the reference element to a temporary file
            timestamp_ref = int(time.time())
            reference_element_path = f"{self.debug_dir}/reason_reference_element_{timestamp_ref}.png"
            with open(reference_element_path, 'wb') as f:
                f.write(reference_element)
            using_reference_element = True
        
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
                request_debug = {
                    'url': url,
                    'query': query,
                    'screenshot': os.path.basename(screenshot_path),
                    'elements_conf': elements_conf,
                    'rows_conf': rows_conf,
                    'model': selected_model,
                    'reference_element': os.path.basename(reference_element_path) if using_reference_element else None,
                    'container_conf': container_conf,
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
                    
                    # Add container confidence if provided
                    if container_conf is not None:
                        data.add_field('container_conf', str(container_conf))
                    
                    # Add reference element if provided
                    if using_reference_element:
                        with open(reference_element_path, 'rb') as ref_f:
                            data.add_field('reference_element', 
                                           ref_f, 
                                           filename=os.path.basename(reference_element_path),
                                           content_type='image/png')
                    
                    # Disable action execution
                    data.add_field('execute_action', 'false')
                    
                    # Add the model parameter
                    data.add_field('model', selected_model)
                    
                    # Add max_tokens parameter if provided (UI-TARS only)
                    if selected_model == "ui-tars":
                        tokens = max_tokens if max_tokens is not None else self.max_tokens
                        data.add_field('max_tokens', str(tokens))
                    
                    # Add additional options if using experimental features
                    if self.use_hierarchical_indexing:
                        data.add_field('use_hierarchical_indexing', 'true')
                    if self.use_query_rewriting:
                        data.add_field('use_query_rewriting', 'true')
                    
                    # Create headers with Authorization if API key is provided
                    headers = {}
                    if self.api_key:
                        headers['Authorization'] = f'Bearer {self.api_key}'
                    
                    # Use the retry utility method
                    success, response_text, error_message = await self._make_api_request_with_retry(
                        session=session,
                        url=url,
                        data=data,
                        headers=headers,
                        debug_prefix="reason",
                        timestamp=timestamp
                    )
                    
                    if not success:
                        if self.verbose:
                            print(f"Warning: {error_message}")
                        
                        # Return a default error response instead of raising an exception
                        return CoffeeBlackResponse(
                            response=error_message,
                            boxes=[],
                            raw_detections={},
                            hierarchy={},
                            num_boxes=0,
                            chosen_action=None,
                            chosen_element_index=None,
                            explanation="API request failed",
                            timings=None
                        )
                    
                    # Parse response
                    try:
                        result = json.loads(response_text)
                    except json.JSONDecodeError:
                        if self.verbose:
                            print(f"Warning: Failed to parse response as JSON. Response saved to {self.debug_dir}/reason_response_raw_{timestamp}.txt")
                        # Instead of crashing, return a default error response
                        return CoffeeBlackResponse(
                            response=f"Failed to parse response as JSON. Response saved to {self.debug_dir}/reason_response_raw_{timestamp}.txt",
                            boxes=[],
                            raw_detections={},
                            hierarchy={},
                            num_boxes=0,
                            chosen_action=None,
                            chosen_element_index=None,
                            explanation="Failed to parse response",
                            timings=None
                        )
                    
                    # Remove fields not in our CoffeeBlackResponse type
                    if 'annotated_screenshot' in result:
                        del result['annotated_screenshot']
                    if 'query' in result:
                        del result['query']
                    
                    # Log parsed response
                    if self.debug_enabled:
                        with open(f'{self.debug_dir}/reason_response_{timestamp}.json', 'w') as f:
                            json.dump(result, f, indent=2)
                    
                    # Handle different API response formats (ui-tars vs ui-detect)
                    chosen_action = None
                    if 'chosen_action' in result:
                        # Standard format
                        chosen_action = Action(**result.get("chosen_action", {})) if result.get("chosen_action") else None
                    elif 'action' in result:
                        # UI-TARS format - convert to our Action format
                        action_data = result.get('action', {})
                        if action_data:
                            # Map 'type' to 'action' for UI-TARS responses
                            chosen_action = Action(
                                action=action_data.get('type'),  # Map 'type' to 'action'
                                key_command=action_data.get('key_command'),
                                input_text=action_data.get('input_text'),
                                scroll_direction=action_data.get('scroll_direction'),
                                confidence=1.0  # Default confidence if not provided
                            )
                    
                    # Process results
                    response = CoffeeBlackResponse(
                        response=response_text,
                        boxes=result.get("boxes", []),
                        raw_detections=result.get("raw_detections", {}),
                        hierarchy=result.get("hierarchy", {}),
                        num_boxes=len(result.get("boxes", [])),
                        chosen_action=chosen_action,
                        chosen_element_index=result.get("chosen_element_index"),
                        explanation=result.get("explanation", ""),
                        timings=result.get("timings")
                    )
                    
                    return response
                    
        except Exception as e:
            raise RuntimeError(f"Failed to execute reasoning query: {e}")
        finally:
            # Clean up temporary files
            if using_temp_file and screenshot_path and os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                except Exception as e:
                    if self.verbose:
                        print(f"Warning: Failed to remove temporary screenshot file {screenshot_path}: {e}")
            
            # Clean up temporary reference element file if we created one
            if using_reference_element and reference_element_path and os.path.exists(reference_element_path):
                # Only remove if it's a temporary file (contains a timestamp in the path)
                if str(timestamp_ref) in reference_element_path:
                    try:
                        os.remove(reference_element_path)
                    except Exception as e:
                        if self.verbose:
                            print(f"Warning: Failed to remove temporary reference element file {reference_element_path}: {e}")

    async def see(self,
                description: str,
                screenshot_data: Optional[bytes] = None,
                reference_images: Optional[List[bytes]] = None,
                wait: bool = False,
                timeout: float = 10.0,
                interval: float = 0.5) -> Dict[str, Any]:
        """
        Call the 'see' API to compare a screenshot with a description and optional reference images.
        
        Args:
            description: Text description of what to look for in the screenshot
            screenshot_data: Optional raw screenshot bytes (if None, automatically captures a screenshot)
            reference_images: Optional list of reference image bytes to compare against
            wait: Whether to wait for the element to appear
            timeout: Maximum time to wait in seconds (only used if wait=True)
            interval: Time between checks in seconds (only used if wait=True)
            
        Returns:
            Dictionary with the API response, containing at minimum:
            - matches (bool): Whether the screenshot matches the description/reference images
            - confidence (str): Confidence level of the match (high, medium, low)
            - reasoning (str): Explanation of the match decision
            
        Raises:
            ValueError: If no active window is attached and no screenshot can be captured
            RuntimeError: If the API request fails
            TimeoutError: If wait=True and the element doesn't appear within the timeout period
        """
        # If wait is True, try repeatedly until timeout
        if wait:
            start_time = time.time()
            last_result = None
            
            while time.time() - start_time < timeout:
                # Call see API with the current screenshot
                result = await self._see_implementation(
                    description=description,
                    screenshot_data=screenshot_data,
                    reference_images=reference_images
                )
                
                # Store the last result for returning in case of timeout
                last_result = result
                
                # If we found a match, return immediately
                if result.get('matches', False):
                    if self.verbose:
                        print(f"Element found after waiting {time.time() - start_time:.2f} seconds")
                    return result
                
                # Wait before trying again
                await asyncio.sleep(interval)
                
                # Get a fresh screenshot for the next attempt (only if no screenshot_data was provided)
                if screenshot_data is None:
                    try:
                        screenshot_data = await self.get_screenshot()
                    except Exception as e:
                        if self.verbose:
                            print(f"Warning: Failed to capture screenshot during wait: {e}")
                        # Continue with the previous screenshot data rather than failing completely
                        # This allows the operation to potentially succeed on a retry with the previous image
            
            # If we reach here, we timed out
            if self.verbose:
                print(f"Timed out after {timeout} seconds waiting for element to appear")
            
            # Return the last result we got
            return last_result
        
        # If wait is False, just do a single check
        return await self._see_implementation(
            description=description,
            screenshot_data=screenshot_data,
            reference_images=reference_images
        )
    
    async def _see_implementation(self,
                description: str,
                screenshot_data: Optional[bytes] = None,
                reference_images: Optional[List[bytes]] = None) -> Dict[str, Any]:
        """
        Internal implementation of the see API call.
        
        This contains the actual implementation details that were previously in the see method.
        
        Args:
            description: Text description of what to look for in the screenshot
            screenshot_data: Optional raw screenshot bytes (if None, automatically captures a screenshot)
            reference_images: Optional list of reference image bytes to compare against
            
        Returns:
            Dictionary with the API response
            
        Raises:
            ValueError: If no active window is attached and no screenshot can be captured
            RuntimeError: If the API request fails
        """
        # API URL for the see endpoint
        url = f"{self.base_url}/api/see"
        
        # Either use provided screenshot or take one of the active window
        screenshot_path = None
        using_temp_file = False
        reference_paths = []
        
        try:
            # If no screenshot data is provided, automatically capture one
            if screenshot_data is None:
                try:
                    if self.verbose:
                        print("No screenshot provided, automatically capturing one...")
                    screenshot_data = await self.get_screenshot()
                except Exception as e:
                    if self.verbose:
                        print(f"Warning: Failed to automatically capture screenshot: {e}")
                    # Return a helpful error response instead of crashing
                    return {
                        "matches": False,
                        "confidence": "unknown",
                        "reasoning": f"Failed to automatically capture screenshot: {e}"
                    }
            
            # Save the screenshot data to a temporary file
            timestamp = int(time.time())
            screenshot_path = f"{self.debug_dir}/see_screenshot_{timestamp}.png"
            with open(screenshot_path, 'wb') as f:
                f.write(screenshot_data)
            using_temp_file = True
            
            # Get the screenshot filename for the form data
            screenshot_filename = os.path.basename(screenshot_path)
            
            # Prepare reference image paths if provided
            reference_paths = []
            reference_contents = []
            reference_filenames = []
            
            if reference_images:
                for i, ref_img in enumerate(reference_images):
                    timestamp = int(time.time())
                    ref_path = f"{self.debug_dir}/see_reference_{i}_{timestamp}.png"
                    with open(ref_path, 'wb') as f:
                        f.write(ref_img)
                    reference_paths.append(ref_path)
                    reference_contents.append(ref_img)  # Store the binary content
                    reference_filenames.append(os.path.basename(ref_path))
            
            # Log request details
            if self.debug_enabled:
                request_debug = {
                    'url': url,
                    'description': description,
                    'screenshot': screenshot_filename,
                    'reference_images': reference_filenames,
                    'timestamp': timestamp
                }
                debug.log_debug(self.debug_dir, "0", request_debug, "see_request")
            
            # Send request to API
            async with aiohttp.ClientSession() as session:
                # Create form data
                data = aiohttp.FormData()
                data.add_field('description', description)
                
                # Read screenshot into memory before adding to form data
                with open(screenshot_path, 'rb') as f:
                    screenshot_content = f.read()
                
                # Add screenshot using the binary content
                data.add_field('screenshot', 
                              screenshot_content, 
                              filename=screenshot_filename,
                              content_type='image/png')
                
                # Add reference images if available
                for i, ref_path in enumerate(reference_paths):
                    with open(ref_path, 'rb') as f:
                        ref_content = f.read()
                    data.add_field(f'reference{i+1}', 
                                  ref_content, 
                                  filename=reference_filenames[i],
                                  content_type='image/png')
                
                # Create headers with Authorization using API key
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                # Use the retry utility method
                success, response_text, error_message = await self._make_api_request_with_retry(
                    session=session,
                    url=url,
                    data=data,
                    headers=headers,
                    debug_prefix="see",
                    timestamp=timestamp
                )
                
                if not success:
                    if self.verbose:
                        print(f"Warning: {error_message}")
                    
                    # Return a default error response instead of raising an exception
                    return {
                        "matches": False,
                        "confidence": "unknown",
                        "reasoning": error_message
                    }
                
                # Parse response
                try:
                    result = json.loads(response_text)
                except json.JSONDecodeError:
                    if self.verbose:
                        print(f"Warning: Failed to parse response as JSON. Response saved to {self.debug_dir}/see_response_raw_{timestamp}.txt")
                    # Instead of crashing, return a default error response
                    return {
                        "matches": False,
                        "confidence": "unknown",
                        "reasoning": f"Failed to parse response as JSON. Response saved to {self.debug_dir}/see_response_raw_{timestamp}.txt"
                    }
                
                # Log parsed response
                if self.debug_enabled:
                    with open(f'{self.debug_dir}/see_response_{timestamp}.json', 'w') as f:
                        json.dump(result, f, indent=2)
                
                if self.verbose:
                    # Print key information
                    print(f"See API Result: Matches={result.get('matches', False)}, " +
                          f"Confidence={result.get('confidence', 'unknown')}")
                    if 'reasoning' in result:
                        print(f"Reasoning: {result['reasoning']}")
                
                return result
        
        except Exception as e:
            timestamp = int(time.time())
            error_message = f"Unexpected error in see implementation: {str(e)}"
            
            if self.verbose:
                print(f"Warning: {error_message}")
                
            # Log the error
            if self.debug_enabled:
                with open(f'{self.debug_dir}/see_error_{timestamp}.txt', 'w') as f:
                    f.write(error_message)
                    
            # Return a default error response
            return {
                "matches": False,
                "confidence": "unknown",
                "reasoning": error_message
            }
        finally:
            # Clean up temporary files
            if using_temp_file and screenshot_path and os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                except Exception as e:
                    # Just log the error but don't propagate it
                    if self.verbose:
                        print(f"Warning: Failed to remove temporary file {screenshot_path}: {e}")
            
            for path in reference_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as e:
                        # Just log the error but don't propagate it
                        if self.verbose:
                            print(f"Warning: Failed to remove temporary file {path}: {e}")

    async def scroll_down(self, scroll_percentage: float = 0.5) -> None:
        """
        Scroll down by a specified percentage of the window height.
        
        This is a simplified version of the more general scroll method that:
        1. Always scrolls downward
        2. Always moves the cursor to the center first
        3. Takes a simple percentage parameter
        
        Args:
            scroll_percentage: Percentage of window height to scroll (0.0-1.0), default 0.5 (50%)
        """
        if not 0.0 <= scroll_percentage <= 1.0:
            raise ValueError(f"scroll_percentage must be between 0.0 and 1.0, got {scroll_percentage}")
            
        # Scale down the scroll percentage since the full height may be too large
        adjusted_percentage = scroll_percentage * 0.5
            
        await self.scroll(
            scroll_direction="down",
            scroll_amount=adjusted_percentage,
            click_for_focus=True
        )
        
    async def scroll_up(self, scroll_percentage: float = 0.5) -> None:
        """
        Scroll up by a specified percentage of the window height.
        
        This is a simplified version of the more general scroll method that:
        1. Always scrolls upward
        2. Always moves the cursor to the center first
        3. Takes a simple percentage parameter
        
        Args:
            scroll_percentage: Percentage of window height to scroll (0.0-1.0), default 0.5 (50%)
        """
        if not 0.0 <= scroll_percentage <= 1.0:
            raise ValueError(f"scroll_percentage must be between 0.0 and 1.0, got {scroll_percentage}")
            
        await self.scroll(
            scroll_direction="up",
            scroll_amount=scroll_percentage,
            click_for_focus=True
        ) 
        
    async def solve_captcha(self, 
                           screenshot_data: Optional[bytes] = None,
                           max_attempts: int = 15,
                           click_checkbox_first: bool = True,
                           checkbox_wait_time: float = 3.0,
                           apply_solution: bool = True,
                           click_delay: float = 0.5,
                           detection_sensitivity: float = 0.5) -> Dict[str, Any]:
        """
        Detect and solve a CAPTCHA challenge automatically.
        
        This method handles the entire CAPTCHA solving process:
        1. Detects if a CAPTCHA challenge is present on the screen
        2. Clicks the "I'm not a robot" checkbox if needed
        3. Detects if a visual challenge appears after clicking the checkbox
        4. Solves the visual challenge if needed
        5. Automatically clicks on the solution coordinates if apply_solution=True
        6. Clicks the verify/submit button after selecting tiles
        
        Args:
            screenshot_data: Optional raw screenshot bytes (if None, automatically captures a screenshot)
            max_attempts: Maximum number of attempts to solve the CAPTCHA (default: 15)
            click_checkbox_first: Whether to click the "I'm not a robot" checkbox first (default: True)
            checkbox_wait_time: Time to wait after clicking the checkbox for animations (default: 3.0)
            apply_solution: Whether to automatically click on the solution coordinates (default: True)
            click_delay: Delay in seconds between clicks when multiple coordinates are returned (default: 0.5)
            detection_sensitivity: Sensitivity for element detection (0.0-1.0, default: 0.5)
                
        Returns:
            Dictionary containing the CAPTCHA solving results with fields:
            - status: 'success', 'no_captcha_detected', or error status
            - solution: Coordinates for clicking and visualized image (if visual challenge solved)
            - captchaAnalysis: Information about the CAPTCHA type and requirements (if visual challenge solved)
            - timing: Performance metrics for the solution process
            - click_status: Status of coordinate clicking if apply_solution=True
            - verify_button_clicked: Whether the verify button was successfully clicked
            - error: Error message if something went wrong
                
        Raises:
            ValueError: If no active window is attached and no screenshot can be captured
        """
        try:
            if self.verbose:
                print("Starting CAPTCHA detection and solving process...")
            
            if screenshot_data is None:
                screenshot_data = await self.get_screenshot()
            
            # Modified query to detect both checkbox and visual challenges
            visual_captcha_query = "Is this a CAPTCHA challenge? This could be either a checkbox that needs to be clicked OR a visual challenge with images to select from."
            see_response = await self.see(visual_captcha_query, screenshot_data=screenshot_data)
            
            if not see_response.get("matches", False):
                if self.verbose:
                    print("No CAPTCHA challenge detected.")
                return {
                    "status": "no_captcha_detected",
                    "message": "No CAPTCHA challenge detected on the screen."
                }
            
            if self.verbose:
                print("CAPTCHA challenge detected!")
            
            # If click_checkbox_first is True, try to find and click the checkbox first
            if click_checkbox_first:
                if self.verbose:
                    print("Attempting to find and click the CAPTCHA checkbox...")
                
                # Use execute_action to find and click the checkbox
                checkbox_result = await self.execute_action(
                    "Click the 'I am not a robot' checkbox or reCAPTCHA checkbox",
                    elements_conf=0.3,  # Lower confidence threshold for checkbox detection
                    detection_sensitivity=detection_sensitivity
                )
                
                if checkbox_result.chosen_action and checkbox_result.chosen_element_index is not None:
                    if self.verbose:
                        print("Successfully clicked the checkbox")
                    
                    # Wait for animations to complete
                    if self.verbose:
                        print(f"Waiting {checkbox_wait_time} seconds for animations to complete...")
                    await asyncio.sleep(checkbox_wait_time)
                    
                    # Take a new screenshot after clicking the checkbox
                    screenshot_data = await self.get_screenshot()
                else:
                    if self.verbose:
                        print("Could not find the checkbox, continuing with visual challenge detection")
            
            # Call the API to solve the visual challenge
            url = f"{self.base_url}/api/captcha"
            timestamp = int(time.time())
            
            # Send request to API
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('max_attempts', str(max_attempts))
                data.add_field('file', screenshot_data, filename='captcha.png', content_type='image/png')
                
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                success, response_text, error_message = await self._make_api_request_with_retry(
                    session=session,
                    url=url,
                    data=data,
                    headers=headers,
                    debug_prefix="captcha",
                    timestamp=timestamp
                )
                
                if not success:
                    return {
                        "status": "error",
                        "error": error_message
                    }
                
                try:
                    result = json.loads(response_text)
                    result["captchaDetectionMethod"] = "automatic"
                    
                    # If we got coordinates and apply_solution is True, we need to click them
                    if apply_solution and result.get("status") == "success":
                        solution_data = result.get("solution", {})
                        coordinates = solution_data.get("coordinates", [])
                        
                        if coordinates:
                            if self.verbose:
                                print(f"Found {len(coordinates)} coordinates to click")
                                print("Starting coordinate processing...")
                            
                            try:
                                # Get window bounds and DPI scaling for coordinate translation
                                window_bounds = None
                                dpi_scaling = 1.0
                                if self.active_window:
                                    if self.verbose:
                                        print("Getting window bounds and DPI scaling...")
                                    window_bounds = self.active_window.bounds
                                    # Get DPI scaling for the window's display
                                    dpi_scaling = screenshot.detect_retina_dpi(target_bounds=window_bounds)
                                    if self.verbose:
                                        print(f"Window DPI scaling: {dpi_scaling}")
                                else:
                                    if self.verbose:
                                        print("Warning: No active window found")
                                
                                # Validate and process coordinates
                                processed_coordinates = []
                                if self.verbose:
                                    print("Starting coordinate validation and processing...")
                                
                                for i, coord in enumerate(coordinates):
                                    if self.verbose:
                                        print(f"Processing coordinate {i+1}: {coord}")
                                    
                                    try:
                                        # Validate coordinate format
                                        if not isinstance(coord, dict) or 'x' not in coord or 'y' not in coord:
                                            print(f"Warning: Invalid coordinate format at index {i}: {coord}")
                                            continue
                                        
                                        x, y = coord.get("x"), coord.get("y")
                                        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                                            print(f"Warning: Invalid coordinate values at index {i}: x={x}, y={y}")
                                            continue
                                        
                                        # Apply DPI scaling
                                        x = int(x * dpi_scaling)
                                        y = int(y * dpi_scaling)
                                        
                                        # Apply window offset if needed
                                        if window_bounds:
                                            x += window_bounds["x"]
                                            y += window_bounds["y"]
                                        
                                        processed_coordinates.append({"x": x, "y": y})
                                        
                                        if self.verbose:
                                            print(f"Successfully processed coordinate {i+1}: original=({coord['x']}, {coord['y']}), scaled=({x}, {y})")
                                            
                                    except Exception as coord_error:
                                        print(f"Error processing coordinate {i+1}: {str(coord_error)}")
                                        if self.verbose:
                                            import traceback
                                            print(f"Coordinate processing error traceback: {traceback.format_exc()}")
                                        continue
                                
                                if not processed_coordinates:
                                    if self.verbose:
                                        print("No valid coordinates found after processing")
                                    return {
                                        "status": "error",
                                        "error": "No valid coordinates found in the solution"
                                    }
                                
                                if self.verbose:
                                    print(f"Successfully processed {len(processed_coordinates)} coordinates")
                                
                                # Click each coordinate
                                if self.verbose:
                                    print(f"Starting to click {len(processed_coordinates)} coordinates")
                                
                                for i, coord in enumerate(processed_coordinates):
                                    if self.verbose:
                                        print(f"Clicking coordinate {i+1}: ({coord['x']}, {coord['y']})")
                                    
                                    # Click the coordinate
                                    pyautogui.moveTo(coord['x'], coord['y'], duration=0.3)
                                    pyautogui.click()
                                    
                                    # Wait between clicks
                                    if i < len(processed_coordinates) - 1:
                                        if self.verbose:
                                            print(f"Waiting {click_delay} seconds before next click")
                                        await asyncio.sleep(click_delay)
                                
                                # Short wait after clicking all coordinates
                                if self.verbose:
                                    print("Waiting 1 second after clicking all coordinates")
                                await asyncio.sleep(1.0)
                                
                                # Now click the verify/submit button
                                if self.verbose:
                                    print("Attempting to click verify/submit button")
                                verify_result = await self.execute_action(
                                    "Click the 'Verify' or 'Submit' button to complete the CAPTCHA",
                                    detection_sensitivity=detection_sensitivity
                                )
                                
                                # Add verify button click status and coordinate details to result
                                result["verify_button_clicked"] = verify_result.get("success", False)
                                result["click_details"] = {
                                    "coordinates_clicked": len(processed_coordinates),
                                    "dpi_scaling_applied": dpi_scaling,
                                    "window_offset_applied": bool(window_bounds),
                                    "processed_coordinates": processed_coordinates
                                }
                                
                                if self.verbose:
                                    if result["verify_button_clicked"]:
                                        print("Successfully clicked verify button")
                                    else:
                                        print("Failed to click verify button")
                                
                            except Exception as e:
                                print(f"Error during coordinate processing: {str(e)}")
                                if self.verbose:
                                    import traceback
                                    print(f"Coordinate processing error traceback: {traceback.format_exc()}")
                                return {
                                    "status": "error",
                                    "error": f"Failed to process coordinates: {str(e)}"
                                }
                    
                    return result
                    
                except json.JSONDecodeError:
                    return {
                        "status": "error",
                        "error": "Failed to parse API response as JSON"
                    }
        
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def load_reference_element(self, file_path: str) -> bytes:
        """
        Load a reference element image from a file path.
        
        Args:
            file_path: Path to the reference element image file
            
        Returns:
            Bytes of the reference element image
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            IOError: If there's an error reading the file
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Reference element file not found: {file_path}")
            
        try:
            with open(file_path, 'rb') as f:
                return f.read()
        except Exception as e:
            raise IOError(f"Error reading reference element file: {e}")
            
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

    # Add a new utility method for making API requests with retry
    async def _make_api_request_with_retry(self, 
                                           session: aiohttp.ClientSession,
                                           url: str, 
                                           data: aiohttp.FormData, 
                                           headers: Dict[str, str],
                                           debug_prefix: str = "",
                                           timestamp: int = None):
        """
        Make an API request with retry and exponential backoff for transient errors.
        
        Args:
            session: The aiohttp ClientSession to use
            url: The API endpoint URL
            data: The FormData to send in the request
            headers: Headers to include in the request
            debug_prefix: Prefix for debug logs
            timestamp: Timestamp for debug logs
            
        Returns:
            Tuple of (success, response_data, error_message)
        """
        if timestamp is None:
            timestamp = int(time.time())
            
        retries = 0
        last_exception = None
        
        while retries <= self.max_retries:
            try:
                # If this is a retry, wait with exponential backoff
                if retries > 0:
                    backoff_time = self.retry_backoff * (2 ** (retries - 1))
                    if self.verbose:
                        print(f"Retrying API request (attempt {retries}/{self.max_retries}) after {backoff_time}s backoff")
                    await asyncio.sleep(backoff_time)
                
                async with session.post(url, data=data, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        
                        # Log the error response
                        if self.debug_enabled:
                            with open(f'{self.debug_dir}/{debug_prefix}_error_response_{timestamp}.txt', 'w') as f:
                                f.write(error_text)
                                
                        error_message = f"API request failed with status {response.status}: {error_text}"
                        
                        # Only retry on connection errors or 5xx (server) errors, not on client errors (4xx)
                        if response.status < 500 and response.status != 429:  # Don't retry on client errors except rate limits
                            return False, None, error_message
                            
                        last_exception = RuntimeError(error_message)
                        retries += 1
                        continue
                    
                    # Get the raw response text
                    response_text = await response.text()
                    
                    # Log raw response
                    if self.debug_enabled:
                        with open(f'{self.debug_dir}/{debug_prefix}_response_raw_{timestamp}.txt', 'w') as f:
                            f.write(response_text)
                    
                    return True, response_text, None
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                # These are possibly transient errors, so we'll retry
                if self.debug_enabled:
                    with open(f'{self.debug_dir}/{debug_prefix}_error_{timestamp}_{retries}.txt', 'w') as f:
                        f.write(f"Error during API request (attempt {retries+1}): {str(e)}\n")
                        f.write(traceback.format_exc())
                
                last_exception = e
                retries += 1
                
            except Exception as e:
                # Other exceptions we won't retry
                error_message = f"Unexpected error during API request: {str(e)}"
                if self.debug_enabled:
                    with open(f'{self.debug_dir}/{debug_prefix}_error_{timestamp}.txt', 'w') as f:
                        f.write(error_message + "\n")
                        f.write(traceback.format_exc())
                return False, None, error_message
        
        # If we've exhausted retries, return failure
        error_message = f"API request failed after {self.max_retries} retries. Last error: {str(last_exception)}"
        if self.verbose:
            print(f"Warning: {error_message}")
            
        return False, None, error_message 

    async def embed(self, 
                   images: List[Union[str, bytes]], 
                   normalize: bool = False) -> Dict[str, Any]:
        """
        Generate embeddings for the provided images using the CoffeeBlack embeddings API.
        
        Args:
            images: List of images as file paths (str) or raw image data (bytes)
            normalize: Whether to normalize the embeddings (default: False)
            
        Returns:
            Dictionary containing the embeddings and processing time:
            {
                "embeddings": List of embedding vectors,
                "processing_time": Time taken to generate embeddings in seconds
            }
            
        Raises:
            ValueError: If no images are provided
            RuntimeError: If the API request fails
        """
        if not images:
            raise ValueError("No images provided for embedding")
            
        # API URL for the embeddings endpoint
        url = f"{self.base_url}/api/embeddings"
        
        # Track temporary files to clean up later
        temp_files = []
        timestamp = int(time.time())
        
        try:
            # Log request details
            if self.debug_enabled:
                request_debug = {
                    'url': url,
                    'normalize': normalize,
                    'num_images': len(images),
                    'timestamp': timestamp
                }
                debug.log_debug(self.debug_dir, "0", request_debug, "embed_request")
            
            # Send request to API
            async with aiohttp.ClientSession() as session:
                # Create form data
                data = aiohttp.FormData()
                data.add_field('normalize', str(normalize).lower())
                
                # Process each image and add to form data
                for i, image in enumerate(images):
                    if isinstance(image, str):
                        # It's a file path
                        if not os.path.exists(image):
                            raise ValueError(f"Image file not found: {image}")
                            
                        with open(image, 'rb') as f:
                            image_data = f.read()
                            filename = os.path.basename(image)
                    else:
                        # It's raw image data
                        image_data = image
                        filename = f"image_{i}.png"  # Default filename
                    
                    # Add to form data
                    data.add_field('files', 
                                  image_data, 
                                  filename=filename,
                                  content_type='image/png')
                
                # Create headers with Authorization if API key is provided
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                # Use the retry utility method
                success, response_text, error_message = await self._make_api_request_with_retry(
                    session=session,
                    url=url,
                    data=data,
                    headers=headers,
                    debug_prefix="embed",
                    timestamp=timestamp
                )
                
                if not success:
                    raise RuntimeError(f"Failed to generate embeddings: {error_message}")
                
                # Parse response
                try:
                    result = json.loads(response_text)
                except json.JSONDecodeError:
                    raise RuntimeError(f"Failed to parse response as JSON. Response saved to {self.debug_dir}/embed_response_raw_{timestamp}.txt")
                
                # Log parsed response
                if self.debug_enabled:
                    with open(f'{self.debug_dir}/embed_response_{timestamp}.json', 'w') as f:
                        json.dump(result, f, indent=2)
                
                # Return the embeddings result
                return {
                    "embeddings": result.get("embeddings", []),
                    "processing_time": result.get("processing_time", 0)
                }
                
        except Exception as e:
            error_msg = f"Error generating embeddings: {str(e)}"
            if self.verbose:
                print(f"Warning: {error_msg}")
                
            # Log the error
            if self.debug_enabled:
                with open(f'{self.debug_dir}/embed_error_{timestamp}.txt', 'w') as f:
                    f.write(error_msg)
                    f.write("\n\n")
                    f.write(traceback.format_exc())
            
            raise RuntimeError(error_msg) from e
            
        finally:
            # Clean up any temporary files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception as e:
                        if self.verbose:
                            print(f"Warning: Failed to remove temporary file {temp_file}: {e}")

    async def compare(self, 
                     image1: Union[str, bytes],
                     image2: Union[str, bytes],
                     normalize: bool = True) -> Dict[str, Any]:
        """
        Compare two images by calculating the cosine distance between their embeddings.
        
        Args:
            image1: First image as file path (str) or raw image data (bytes)
            image2: Second image as file path (str) or raw image data (bytes)
            normalize: Whether to normalize the embeddings (default: True)
            
        Returns:
            Dictionary containing the comparison results:
            {
                "cosine_distance": Cosine distance between embeddings (0-2, where 0 means identical),
                "cosine_similarity": Cosine similarity between embeddings (1 to -1, where 1 means identical),
                "embeddings": List of embeddings for each image,
                "processing_time": Total time taken for embedding and comparison
            }
            
        Raises:
            ValueError: If images couldn't be processed
            RuntimeError: If the API request fails
        """
        import numpy as np
        start_time = time.time()
        
        try:
            # Get embeddings for both images
            if self.verbose:
                print("Getting embeddings for both images...")
                
            embed_result = await self.embed([image1, image2], normalize=normalize)
            embeddings = embed_result.get("embeddings", [])
            
            if len(embeddings) != 2:
                raise ValueError(f"Expected 2 embeddings, but got {len(embeddings)}")
            
            # Convert to numpy arrays for vector operations
            embedding1 = np.array(embeddings[0])
            embedding2 = np.array(embeddings[1])
            
            # Calculate cosine similarity
            # Formula: cos_sim = dot(v1, v2) / (norm(v1) * norm(v2))
            dot_product = np.dot(embedding1, embedding2)
            norm1 = np.linalg.norm(embedding1)
            norm2 = np.linalg.norm(embedding2)
            
            # Avoid division by zero
            if norm1 == 0 or norm2 == 0:
                cosine_similarity = 0
            else:
                cosine_similarity = dot_product / (norm1 * norm2)
                
            # Calculate cosine distance (1 - similarity)
            # Range: 0 (identical) to 2 (completely opposite)
            cosine_distance = 1 - cosine_similarity
            
            processing_time = time.time() - start_time
            
            if self.verbose:
                print(f"Comparison complete: distance={cosine_distance:.4f}, similarity={cosine_similarity:.4f}")
                
            return {
                "cosine_distance": float(cosine_distance),
                "cosine_similarity": float(cosine_similarity),
                "embeddings": embeddings,
                "processing_time": processing_time
            }
            
        except Exception as e:
            error_msg = f"Error comparing images: {str(e)}"
            if self.verbose:
                print(f"Warning: {error_msg}")
            raise RuntimeError(error_msg) from e
            
    async def compare_screenshots(self, 
                                delay: float = 2.0,
                                normalize: bool = True) -> Dict[str, Any]:
        """
        Take two screenshots with a specified delay between them and compare 
        the visual difference by calculating the cosine distance between their embeddings.
        
        This is useful for detecting if a UI has changed after an action.
        
        Args:
            delay: Time in seconds to wait between screenshots (default: 2.0)
            normalize: Whether to normalize the embeddings (default: True)
            
        Returns:
            Dictionary containing the comparison results:
            {
                "cosine_distance": Cosine distance between embeddings,
                "cosine_similarity": Cosine similarity between embeddings,
                "first_screenshot": Path to the first screenshot if debug is enabled,
                "second_screenshot": Path to the second screenshot if debug is enabled,
                "processing_time": Total time taken for the operation
            }
            
        Raises:
            ValueError: If no active window is attached
            RuntimeError: If image comparison fails
        """
        start_time = time.time()
        first_screenshot_path = None
        second_screenshot_path = None
        
        try:
            if not self.active_window:
                raise ValueError("No active window to capture. Call attach_to_window first.")
                
            if self.verbose:
                print(f"Taking first screenshot...")
                
            # Take first screenshot
            screenshot1 = await self.get_screenshot()
            
            # Save debug copy if debug is enabled
            if self.debug_enabled:
                timestamp = int(time.time())
                first_screenshot_path = f"{self.debug_dir}/compare_first_{timestamp}.png"
                with open(first_screenshot_path, 'wb') as f:
                    f.write(screenshot1)
                    
            # Wait for specified delay
            if self.verbose:
                print(f"Waiting {delay} seconds before taking second screenshot...")
            await asyncio.sleep(delay)
            
            # Take second screenshot
            if self.verbose:
                print(f"Taking second screenshot...")
            screenshot2 = await self.get_screenshot()
            
            # Save debug copy if debug is enabled
            if self.debug_enabled:
                timestamp = int(time.time())
                second_screenshot_path = f"{self.debug_dir}/compare_second_{timestamp}.png"
                with open(second_screenshot_path, 'wb') as f:
                    f.write(screenshot2)
                    
            # Compare the screenshots
            if self.verbose:
                print(f"Comparing screenshots...")
            compare_result = await self.compare(screenshot1, screenshot2, normalize=normalize)
            
            # Add screenshot paths to result if in debug mode
            if self.debug_enabled:
                compare_result["first_screenshot"] = first_screenshot_path
                compare_result["second_screenshot"] = second_screenshot_path
                
            # Calculate total processing time
            compare_result["total_processing_time"] = time.time() - start_time
            
            return compare_result
            
        except Exception as e:
            error_msg = f"Error in compare_screenshots: {str(e)}"
            if self.verbose:
                print(f"Warning: {error_msg}")
            raise RuntimeError(error_msg) from e
            
    async def extract_html(self,
                          html: str,
                          query: str,
                          output_format: str = "json",
                          schema: Optional[Dict[str, Any]] = None) -> ExtractResponse:
        """
        Extract structured data from HTML based on a natural language query.
        The HTML content will be automatically base64 encoded before sending to the API.
        
        Args:
            html: The raw HTML content to extract data from
            query: Natural language query describing what data to extract
            output_format: Format for the output data ("json" or "csv")
            schema: Optional schema defining the expected structure of the output data
        
        Returns:
            ExtractResponse object that supports chaining format conversions
        
        Raises:
            ValueError: If output_format is invalid
            RuntimeError: If the API request fails
        """
        return await self.html_extractor.extract(html, query, output_format, schema)
