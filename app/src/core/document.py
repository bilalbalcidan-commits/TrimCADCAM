from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.src.geometry.polyline_types import OrderedPolyline


@dataclass
class Document:
    """
    CAD/CAM uygulamalarında tipik 'aktif doküman' modeli:
    - yüklü shape
    - edge index
    - oluşturulan polylineler
    - (FAZ 3) ordered polyline çıktıları
    """
    file_path: Optional[str] = None
    shape: object | None = None
    edges: List[object] = field(default_factory=list)  # TopoDS_Edge
    polylines: Dict[str, List[int]] = field(default_factory=dict)

    # (FAZ 3) Ordered polyline results keyed by polyline name (e.g., "Polyline_001")
    ordered_polylines: Dict[str, "OrderedPolyline"] = field(default_factory=dict)

    _polyline_counter: int = 0

    def reset(self) -> None:
        self.file_path = None
        self.shape = None
        self.edges = []
        self.polylines = {}
        self.ordered_polylines = {}
        self._polyline_counter = 0

    def set_model(self, file_path: str, shape: object, edges: List[object]) -> None:
        self.file_path = file_path
        self.shape = shape
        self.edges = edges

        # Model değişince polyline state'leri de tutarlı olsun (istersen kaldırabiliriz)
        self.polylines = {}
        self.ordered_polylines = {}
        self._polyline_counter = 0

    def new_polyline_name(self) -> str:
        self._polyline_counter += 1
        return f"Polyline_{self._polyline_counter:03d}"

    def add_polyline(self, edge_ids: List[int]) -> str:
        name = self.new_polyline_name()
        self.polylines[name] = list(edge_ids)

        # Aynı isimde daha önce ordered polyline varsa (olmaz ama garanti)
        self.ordered_polylines.pop(name, None)
        return name

    # -----------------------------
    # GEOMETRY STATE (FAZ 3)
    # -----------------------------
    def set_ordered_polyline(self, polyline_name: str, ordered: "OrderedPolyline") -> None:
        """
        Store ordered result for a given polyline name.
        polyline_name must exist in self.polylines.
        """
        if polyline_name not in self.polylines:
            raise KeyError(f"Polyline not found: {polyline_name}")
        self.ordered_polylines[polyline_name] = ordered

    def get_ordered_polyline(self, polyline_name: str) -> "OrderedPolyline | None":
        return self.ordered_polylines.get(polyline_name)

    def clear_ordered_polyline(self, polyline_name: str) -> None:
        self.ordered_polylines.pop(polyline_name, None)

    def clear_all_ordered_polylines(self) -> None:
        self.ordered_polylines.clear()
