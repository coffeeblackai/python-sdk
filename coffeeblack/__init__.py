"""
CoffeeBlack SDK - Python client for interacting with the CoffeeBlack visual reasoning API
"""

from .core import CoffeeBlackSDK
from .types import WindowInfo, Action, CoffeeBlackResponse
from .utils.app_manager import AppInfo, AppManager

# Define Argus as a proper class instead of just an alias to ensure all methods are correctly exposed
class Argus(CoffeeBlackSDK):
    """
    Argus is the public-facing interface to the CoffeeBlack SDK.
    It inherits all functionality from CoffeeBlackSDK.
    """
    pass

# Make sure all the necessary methods are properly exposed
# The get_screenshot method should be available through the Argus class
# since Argus is just an alias for CoffeeBlackSDK

__all__ = [
    'Argus', 
    'WindowInfo', 
    'Action', 
    'CoffeeBlackResponse',
    'AppInfo',
    'AppManager'
] 