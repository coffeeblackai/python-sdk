"""
Screenshot utilities for the CoffeeBlack SDK
"""

import os
import platform
import pyautogui
from typing import Dict, Optional, List, Tuple
import subprocess
import tempfile
import ctypes


def detect_retina_dpi(target_bounds: Optional[Dict[str, float]] = None) -> float:
    """
    Detect Retina DPI scaling on macOS, with enhanced multi-monitor support.
    
    Args:
        target_bounds: Optional bounds of the target window to determine which display it's on
        
    Returns:
        DPI scaling factor (1.0 for non-Retina displays)
    """
    try:
        system = platform.system()
        if system == 'Darwin':  # macOS
            import Quartz
            import ctypes
            from AppKit import NSScreen
            
            # First try using NSScreen, which is more reliable for modern macOS
            try:
                screens = NSScreen.screens()
                if not screens:
                    print("No screens found via NSScreen")
                    return 2.0  # Default for Retina MacBooks
                    
                # If no target bounds provided, just use the main screen
                if not target_bounds:
                    main_screen = NSScreen.mainScreen()
                    scale_factor = main_screen.backingScaleFactor()
                    print(f"Using main screen scale factor: {scale_factor}")
                    return float(scale_factor)
                
                # Find screen that contains the window
                window_center_x = target_bounds['x'] + target_bounds['width'] / 2
                window_center_y = target_bounds['y'] + target_bounds['height'] / 2
                
                for screen in screens:
                    frame = screen.frame()
                    if (frame.origin.x <= window_center_x <= frame.origin.x + frame.size.width and
                        frame.origin.y <= window_center_y <= frame.origin.y + frame.size.height):
                        scale_factor = screen.backingScaleFactor()
                        
                        # Check for standard external monitor resolutions
                        if (frame.size.width in [1920, 2560, 3840] and 
                            frame.size.height in [1080, 1440, 2160]):
                            print(f"Detected standard external monitor {frame.size.width}x{frame.size.height}, using scale factor 1.0")
                            return 1.0
                            
                        print(f"Window on screen with scale factor: {scale_factor}")
                        return float(scale_factor)
                
                # If we didn't find a matching screen, use main screen
                main_screen = NSScreen.mainScreen()
                scale_factor = main_screen.backingScaleFactor()
                print(f"Using main screen scale factor (no match): {scale_factor}")
                return float(scale_factor)
                
            except Exception as e:
                print(f"Error detecting DPI via NSScreen: {e}")
                # Continue to Quartz methods
            
            # If target bounds provided, determine which display it's primarily on
            target_display_id = Quartz.CGMainDisplayID()  # Default to main display
            
            if target_bounds:
                try:
                    # Get all displays properly
                    MAX_DISPLAYS = 32
                    display_array = (ctypes.c_uint32 * MAX_DISPLAYS)()
                    count_ptr = ctypes.c_uint32()
                    err = Quartz.CGGetActiveDisplayList(MAX_DISPLAYS, display_array, ctypes.byref(count_ptr))
                    if err == 0 and count_ptr.value > 0:
                        count = count_ptr.value
                        # Calculate window center
                        window_center_x = target_bounds['x'] + target_bounds['width'] / 2
                        window_center_y = target_bounds['y'] + target_bounds['height'] / 2
                        
                        # Check each display
                        for i in range(count):
                            display_id = display_array[i]
                            bounds = Quartz.CGDisplayBounds(display_id)
                            if (bounds.origin.x <= window_center_x <= bounds.origin.x + bounds.size.width and
                                bounds.origin.y <= window_center_y <= bounds.origin.y + bounds.size.height):
                                # Window is primarily on this display
                                target_display_id = display_id
                                print(f"Window is on display {i+1} with ID {display_id}")
                                break
                except Exception as e:
                    print(f"Error finding display for window: {e}")
            
            # Get display scaling factor for the target display
            try:
                # Ask macOS directly for the backing scale factor (most reliable)
                scale_factor = Quartz.CGDisplayScaleFactor(target_display_id)
                if scale_factor > 1.0:
                    print(f"Using macOS reported scale factor: {scale_factor}")
                    return scale_factor
            except Exception as e:
                print(f"Error getting display scale factor: {e}")
            
            # Try the pixel-based approach as fallback
            try:
                main_display = Quartz.CGDisplayCreateImage(target_display_id)
                if main_display:
                    width = Quartz.CGImageGetWidth(main_display)
                    height = Quartz.CGImageGetHeight(main_display)
                    
                    # Get the logical screen size for this display
                    display_bounds = Quartz.CGDisplayBounds(target_display_id)
                    logical_width = display_bounds.size.width
                    logical_height = display_bounds.size.height
                    
                    # Calculate the scaling factor
                    scale_x = width / logical_width
                    scale_y = height / logical_height
                    
                    # Use the average of x and y scaling factors
                    dpi = (scale_x + scale_y) / 2
                    
                    # Round to nearest .25 to avoid minor variations
                    dpi = round(dpi * 4) / 4
                    
                    print(f"Detected DPI using pixel ratio: {dpi}")
                    return dpi
            except Exception as e:
                print(f"Error calculating DPI from pixels: {e}")
    
    except Exception as e:
        print(f"Error detecting Retina DPI: {e}")
    
    # If we get here, we couldn't detect Retina DPI or we're not on macOS
    # Default to 2.0 for MacBooks with Retina Display when we can't detect properly
    if platform.system() == 'Darwin':
        # Check for standard external monitor resolutions using system_profiler
        try:
            import subprocess
            result = subprocess.run(['system_profiler', 'SPDisplaysDataType'], capture_output=True, text=True)
            output = result.stdout
            
            # Check for common standard resolutions
            standard_resolutions = ['1920 x 1080', '2560 x 1440', '3840 x 2160']
            for resolution in standard_resolutions:
                if resolution in output:
                    print(f"Detected standard external monitor resolution: {resolution}")
                    print("Using scale factor 1.0 for standard external monitor")
                    return 1.0
            
            # Only use Retina scaling if we detect a Retina display and didn't find standard monitors
            if 'Retina' in output:
                print("MacBook with Retina display detected, using default scale factor of 2.0")
                return 2.0
        except Exception as e:
            print(f"Error checking display resolution: {e}")
    
    return 1.0


def get_display_info_macos() -> List[Dict]:
    """
    Get information about all displays on macOS.
    
    Returns:
        List of dictionaries with display information
    """
    try:
        import Quartz
        import ctypes
        from AppKit import NSScreen
        
        # Use NSScreen as a more reliable way to get display info
        displays = []
        
        # First try using NSScreen which is more reliable
        try:
            screens = NSScreen.screens()
            main_screen = NSScreen.mainScreen()
            
            for i, screen in enumerate(screens):
                # Get frame and visibleFrame in points
                frame = screen.frame()
                screen_dict = {
                    'id': i,  # NSScreen doesn't provide direct display ID
                    'bounds': {
                        'x': frame.origin.x,
                        'y': frame.origin.y,
                        'width': frame.size.width,
                        'height': frame.size.height
                    },
                    'resolution': {
                        'width': frame.size.width,
                        'height': frame.size.height
                    },
                    'scale_factor': screen.backingScaleFactor(),
                    'is_main': screen == main_screen
                }
                
                # Override scale factor for standard monitor resolutions
                if (frame.size.width in [1920, 2560, 3840] and 
                    frame.size.height in [1080, 1440, 2160]):
                    print(f"Detected standard monitor {frame.size.width}x{frame.size.height}, forcing scale_factor to 1.0")
                    screen_dict['scale_factor'] = 1.0
                
                displays.append(screen_dict)
            
            if displays:
                print(f"Found {len(displays)} displays using NSScreen")
                return displays
        except Exception as e:
            print(f"Error getting display info via NSScreen: {e}")
        
        # Fall back to CGDisplay methods if NSScreen fails
        try:
            # Get active displays properly
            MAX_DISPLAYS = 32
            display_array = (ctypes.c_uint32 * MAX_DISPLAYS)()
            count_ptr = ctypes.c_uint32()
            err = Quartz.CGGetActiveDisplayList(MAX_DISPLAYS, display_array, ctypes.byref(count_ptr))
            
            if err != 0:
                print(f"Error getting display list: {err}")
                return []
            
            for i in range(count_ptr.value):
                display_id = display_array[i]
                try:
                    # Get display bounds
                    bounds = Quartz.CGDisplayBounds(display_id)
                    
                    # Get display mode
                    mode = Quartz.CGDisplayCopyDisplayMode(display_id)
                    
                    # Get scaling factor
                    scale_factor = Quartz.CGDisplayScaleFactor(display_id)
                    
                    # Get resolution
                    width = Quartz.CGDisplayModeGetWidth(mode)
                    height = Quartz.CGDisplayModeGetHeight(mode)
                    
                    displays.append({
                        'id': display_id,
                        'bounds': {
                            'x': bounds.origin.x,
                            'y': bounds.origin.y,
                            'width': bounds.size.width,
                            'height': bounds.size.height
                        },
                        'resolution': {
                            'width': width,
                            'height': height
                        },
                        'scale_factor': scale_factor,
                        'is_main': display_id == Quartz.CGMainDisplayID()
                    })
                except Exception as e:
                    print(f"Error getting info for display {display_id}: {e}")
            
            print(f"Found {len(displays)} displays using CGDisplay methods")
            return displays
        except Exception as e:
            print(f"Error getting display info via CGDisplay: {e}")
            return []
                    
    except Exception as e:
        print(f"Error getting display info: {e}")
        return []


def take_window_screenshot(screenshot_path: str, window_bounds: Dict[str, float]) -> bool:
    """
    Take a screenshot of a window.
    
    Args:
        screenshot_path: Path to save the screenshot
        window_bounds: Window bounds (x, y, width, height)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract window bounds
        x = int(window_bounds['x'])
        y = int(window_bounds['y'])
        width = int(window_bounds['width'])
        height = int(window_bounds['height'])
        
        # Take the screenshot of the specified region
        screenshot = pyautogui.screenshot(region=(x, y, width, height))
        screenshot.save(screenshot_path)
        
        return True
    
    except Exception as e:
        print(f"Error taking window screenshot: {e}")
        return False


def take_window_screenshot_macos(
    screenshot_path: str, 
    window_id: str, 
    window_bounds: Dict[str, float]
) -> bool:
    """
    Take a screenshot of a window on macOS.
    
    This method uses the more reliable pyautogui approach rather than the Quartz
    method which can sometimes produce corrupted images.
    
    Args:
        screenshot_path: Path to save the screenshot
        window_id: ID of the window to capture
        window_bounds: Window bounds (x, y, width, height)
        
    Returns:
        True if successful, False otherwise
    """
    # We'll use pyautogui approach which is more reliable for this case
    return take_window_screenshot(screenshot_path, window_bounds)


def take_window_screenshot_macos_screencapture(
    screenshot_path: str, 
    window_id: str
) -> bool:
    """
    Alternative method to take a screenshot of a window on macOS using screencapture command.
    
    This is a backup method that uses the system's built-in screencapture command
    which can be more reliable for capturing specific windows by their ID.
    
    Args:
        screenshot_path: Path to save the screenshot
        window_id: ID of the window to capture
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Use macOS screencapture command which is more reliable for window captures
        subprocess.run([
            "screencapture", 
            "-l", window_id,  # Capture window with specific ID
            "-o",             # Don't include window shadow
            "-x",             # Don't play sound
            screenshot_path
        ], check=True)
        
        return os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0
    except Exception as e:
        print(f"Error using screencapture: {e}")
        return False 