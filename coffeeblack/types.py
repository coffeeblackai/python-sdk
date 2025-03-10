from dataclasses import dataclass
from typing import Optional, List, Any, Dict

@dataclass
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    height: float

@dataclass
class Mesh:
    x: float
    y: float
    width: float
    height: float

@dataclass
class Box:
    _uniqueid: str
    mesh: Mesh
    metadata: dict
    bbox: dict  # Changed from BoundingBox to dict to match API response
    class_id: int
    class_name: str
    confidence: float
    is_chosen: bool

@dataclass
class Action:
    action: Optional[str]  # 'click' or 'type' or None
    key_command: Optional[str]
    input_text: Optional[str]
    scroll_direction: Optional[str]
    confidence: float

@dataclass
class CoffeeBlackResponse:
    response: str
    boxes: List[Dict[str, Any]]  # Hierarchical structure of UI elements
    raw_detections: Optional[Dict[str, List[Dict[str, Any]]]] = None
    hierarchy: Optional[List[Dict[str, Any]]] = None  # Full hierarchical tree
    num_boxes: Optional[int] = None
    chosen_action: Optional[Action] = None
    chosen_element_index: Optional[int] = None
    explanation: Optional[str] = None
    timings: Optional[Dict[str, Any]] = None

@dataclass
class WindowInfo:
    id: str
    title: str
    bounds: Dict[str, float]
    is_active: bool
    app_name: str = ""  # Application name that owns this window
    bundle_id: str = ""  # Bundle ID on macOS (e.g. com.apple.Safari)
    metadata: Dict[str, Any] = None  # Additional platform-specific metadata
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def __str__(self) -> str:
        if self.app_name:
            return f"{self.title} ({self.app_name})"
        return self.title

@dataclass
class UIElement:
    box_id: str
    bbox: BoundingBox
    class_name: str
    confidence: float
    type: str
    children: Optional[List['UIElement']] = None 