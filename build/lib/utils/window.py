"""
Window management utilities for the CoffeeBlack SDK
"""

import platform
import subprocess
import json
from typing import List, Dict, Optional

from ..types import WindowInfo


def get_open_windows_windows() -> List[WindowInfo]:
    """
    Get a list of all open windows on Windows.
    
    Returns:
        List of WindowInfo objects, each representing an open window
    """
    try:
        import win32gui
        import win32process
        
        windows = []
        
        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    rect = win32gui.GetWindowRect(hwnd)
                    
                    # Get process info
                    try:
                        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                        process_info = {"process_id": process_id}
                    except:
                        process_info = {}
                    
                    windows.append(WindowInfo(
                        id=str(hwnd),
                        title=title,
                        bounds={
                            'x': rect[0],
                            'y': rect[1],
                            'width': rect[2] - rect[0],
                            'height': rect[3] - rect[1]
                        },
                        is_active=hwnd == win32gui.GetForegroundWindow(),
                        app_name="",  # Not easily available on Windows
                        bundle_id="",  # Not applicable on Windows
                        metadata=process_info
                    ))
        
        win32gui.EnumWindows(callback, windows)
        return windows
        
    except ImportError:
        print("Please install pywin32: pip install pywin32")
        return []


def get_open_windows_macos() -> List[WindowInfo]:
    """
    Get a list of all open windows on macOS with enhanced metadata.
    
    Returns:
        List of WindowInfo objects, each representing an open window
    """
    try:
        import Quartz
        windows = []
        
        # Get window list with detailed info
        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID
        )
        
        # Get active app process ID
        active_app_pid = None
        front_app = Quartz.NSWorkspace.sharedWorkspace().frontmostApplication()
        if front_app:
            active_app_pid = front_app.processIdentifier()
        
        for window in window_list:
            name = window.get(Quartz.kCGWindowName, "")
            owner = window.get(Quartz.kCGWindowOwnerName, "")
            
            # Skip windows without a title, unless they have an owner name
            if not name and not owner:
                continue
                
            bounds = window.get(Quartz.kCGWindowBounds)
            window_id = window.get(Quartz.kCGWindowNumber, 0)
            process_id = window.get(Quartz.kCGWindowOwnerPID, 0)
            
            # Determine if this window is from the active application
            is_active = False
            if active_app_pid and process_id == active_app_pid:
                is_active = True
            
            # Enhanced metadata
            app_name = owner
            bundle_id = ""
            
            # Try to get bundle ID for the app
            try:
                # Use the 'lsappinfo' command to get more information about the app
                result = subprocess.run(
                    ["lsappinfo", "info", "-only", "bundleid", str(process_id)],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    # Extract the bundle ID from the output
                    output = result.stdout.strip()
                    if "bundleid=" in output:
                        bundle_id = output.split("bundleid=")[1].strip('"')
            except Exception:
                pass
            
            # Additional metadata
            metadata = {
                "process_id": process_id,
                "owner": owner,
                "layer": window.get(Quartz.kCGWindowLayer, 0),
                "alpha": window.get(Quartz.kCGWindowAlpha, 1.0),
                "memory_usage": window.get(Quartz.kCGWindowMemoryUsage, 0)
            }
            
            # Create window info with enhanced metadata
            window_info = WindowInfo(
                id=str(window_id),
                title=name or f"{owner} Window",  # Use owner name if window has no title
                bounds={
                    'x': bounds.get('X', 0),
                    'y': bounds.get('Y', 0),
                    'width': bounds.get('Width', 0),
                    'height': bounds.get('Height', 0)
                },
                is_active=is_active,
                app_name=app_name,
                bundle_id=bundle_id,
                metadata=metadata
            )
            
            windows.append(window_info)
                
        return windows
        
    except ImportError:
        print("Please install pyobjc-framework-Quartz: pip install pyobjc-framework-Quartz")
        return []


def get_open_windows_linux() -> List[WindowInfo]:
    """
    Get a list of all open windows on Linux with enhanced metadata.
    
    Returns:
        List of WindowInfo objects, each representing an open window
    """
    try:
        import Xlib.display
        display = Xlib.display.Display()
        root = display.screen().root
        
        # Get the active window
        active_window_id = None
        try:
            active_window_prop = root.get_full_property(
                display.intern_atom('_NET_ACTIVE_WINDOW'),
                Xlib.X.AnyPropertyType
            )
            if active_window_prop:
                active_window_id = active_window_prop.value[0]
        except Exception:
            pass
        
        windows = []
        window_ids = root.get_full_property(
            display.intern_atom('_NET_CLIENT_LIST'),
            Xlib.X.AnyPropertyType
        ).value
        
        for window_id in window_ids:
            window = display.create_resource_object('window', window_id)
            try:
                geometry = window.get_geometry()
                name = window.get_wm_name()
                pid = None
                app_name = ""
                
                # Try to get the process ID
                try:
                    pid_property = window.get_full_property(
                        display.intern_atom('_NET_WM_PID'),
                        Xlib.X.AnyPropertyType
                    )
                    if pid_property:
                        pid = pid_property.value[0]
                        
                        # Try to get the command name from /proc/{pid}/cmdline
                        try:
                            with open(f"/proc/{pid}/cmdline", "r") as f:
                                cmdline = f.read().split('\0')[0]
                                app_name = cmdline.split('/')[-1]
                        except Exception:
                            pass
                except Exception:
                    pass
                
                # Get the class hint if possible
                class_hint = None
                try:
                    class_hint = window.get_wm_class()
                except Exception:
                    pass
                
                if name:
                    metadata = {
                        "process_id": pid,
                        "wm_class": class_hint
                    }
                    
                    windows.append(WindowInfo(
                        id=str(window_id),
                        title=name,
                        bounds={
                            'x': geometry.x,
                            'y': geometry.y,
                            'width': geometry.width,
                            'height': geometry.height
                        },
                        is_active=window_id == active_window_id,
                        app_name=app_name,
                        bundle_id="",  # Not applicable on Linux
                        metadata=metadata
                    ))
            except Exception:
                continue
                
        return windows
        
    except ImportError:
        print("Please install python-xlib: pip install python-xlib")
        return []


def get_open_windows() -> List[WindowInfo]:
    """
    Get a list of all open windows on the current platform.
    
    Returns:
        List of WindowInfo objects, each representing an open window
    """
    system = platform.system()
    
    if system == 'Windows':
        return get_open_windows_windows()
    elif system == 'Darwin':  # macOS
        return get_open_windows_macos()
    elif system == 'Linux':
        return get_open_windows_linux()
        
    return []  # Fallback for unsupported platforms


def find_window_by_name(query: str) -> WindowInfo:
    """
    Find a window by name (partial match).
    
    Args:
        query: Partial window title to search for
        
    Returns:
        WindowInfo object for the matching window
        
    Raises:
        ValueError: If no matching window is found
    """
    windows = get_open_windows()
    
    # First, try to match by exact window title
    exact_matches = [w for w in windows if w.title.lower() == query.lower()]
    if exact_matches:
        return exact_matches[0]
    
    # Then try partial match in window title
    matching_windows = [w for w in windows if query.lower() in w.title.lower()]
    if matching_windows:
        # Sort by exact match first, then by title length (prefer shorter titles)
        matching_windows.sort(key=lambda w: (w.title.lower() != query.lower(), len(w.title)))
        return matching_windows[0]
        
    # If no matches by title, try matching by app name
    app_matches = [w for w in windows if w.app_name and query.lower() in w.app_name.lower()]
    if app_matches:
        return app_matches[0]
    
    # If still no matches, try bundle ID (macOS)
    bundle_matches = [w for w in windows if w.bundle_id and query.lower() in w.bundle_id.lower()]
    if bundle_matches:
        return bundle_matches[0]
    
    raise ValueError(f"No windows matching '{query}' found")


def get_windows_by_app_name(app_name: str) -> List[WindowInfo]:
    """
    Get all windows belonging to a specific application.
    
    Args:
        app_name: Name of the application to search for
        
    Returns:
        List of WindowInfo objects for the matching application
    """
    windows = get_open_windows()
    
    # Match by app name
    app_matches = [w for w in windows if w.app_name and app_name.lower() in w.app_name.lower()]
    
    # If no matches by app name, try bundle ID (macOS)
    if not app_matches:
        app_matches = [w for w in windows if w.bundle_id and app_name.lower() in w.bundle_id.lower()]
    
    # If still no matches, try window title as last resort
    if not app_matches:
        app_matches = [w for w in windows if app_name.lower() in w.title.lower()]
    
    return app_matches 