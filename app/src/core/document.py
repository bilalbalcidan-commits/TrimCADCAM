from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Document:
    """
    CAD/CAM uygulamalarında tipik 'aktif doküman' modeli:
    - yüklü shape
    - edge index
    - oluşturulan polylineler
    """
    file_path: Optional[str] = None
    shape: object | None = None
    edges: List[object] = field(default_factory=list)  # TopoDS_Edge
    polylines: Dict[str, List[int]] = field(default_factory=dict)

    _polyline_counter: int = 0

    def reset(self) -> None:
        self.file_path = None
        self.shape = None
        self.edges = []
        self.polylines = {}
        self._polyline_counter = 0

    def set_model(self, file_path: str, shape: object, edges: List[object]) -> None:
        self.file_path = file_path
        self.shape = shape
        self.edges = edges

    def new_polyline_name(self) -> str:
        self._polyline_counter += 1
        return f"Polyline_{self._polyline_counter:03d}"

    def add_polyline(self, edge_ids: List[int]) -> str:
        name = self.new_polyline_name()
        self.polylines[name] = list(edge_ids)
        return name
