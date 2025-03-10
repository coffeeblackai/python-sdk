"""
CoffeeBlack SDK - Python client for interacting with the CoffeeBlack visual reasoning API
"""

from .core import CoffeeBlackSDK
from .types import WindowInfo, Action, CoffeeBlackResponse
from .utils.app_manager import AppInfo, AppManager

__all__ = [
    'CoffeeBlackSDK', 
    'WindowInfo', 
    'Action', 
    'CoffeeBlackResponse',
    'AppInfo',
    'AppManager'
] 