from dataclasses import dataclass
from typing import Optional, List, Any, Dict, Union
import json
import csv
import io

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

class ExtractResponse:
    """
    Response object for HTML extraction that supports chaining format conversions.
    """
    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self._raw_response = data.get('response', {})
        self._format = data.get('format', 'json')
        self._query = data.get('query', '')
        self._processing_time = data.get('processing_time', 0)

    @property
    def data(self) -> Dict[str, Any]:
        """Get the raw data from the response"""
        return self._data

    def json(self) -> Dict[str, Any]:
        """Return the data as a JSON object"""
        if isinstance(self._data.get('data'), str):
            return json.loads(self._data['data'])
        return self._data.get('data', {})

    def csv(self, delimiter: str = ',') -> str:
        """
        Convert the data to CSV format.
        
        Args:
            delimiter: The delimiter to use for CSV formatting (default: ',')
            
        Returns:
            String containing the CSV data
        """
        data = self.json()
        if not isinstance(data, list):
            data = [data]
            
        if not data:
            return ""
            
        # Get all unique keys from all objects
        fieldnames = set()
        for item in data:
            if isinstance(item, dict):
                fieldnames.update(item.keys())
                
        fieldnames = sorted(list(fieldnames))
        
        # Write to CSV string
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(data)
        
        return output.getvalue()

    def __str__(self) -> str:
        """Return a string representation of the data"""
        return str(self._data)

    def __repr__(self) -> str:
        """Return a detailed string representation"""
        return f"ExtractResponse(format={self._format}, query='{self._query}', processing_time={self._processing_time}s)" 