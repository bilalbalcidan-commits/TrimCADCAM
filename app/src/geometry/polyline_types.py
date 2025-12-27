from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Simple, dependency-free 3D point representation (mm units assumed)
Point3D = Tuple[float, float, float]


@dataclass(frozen=True)
class GapInfo:
    """
    A connectivity gap detected between consecutive edges in an ordered polyline.
    index: connection index between edge[index] -> edge[index+1]
    distance_mm: gap distance in mm
    """
    index: int
    distance_mm: float


@dataclass
class PolylineReport:
    """
    Diagnostic report for edge ordering and connectivity checks.
    This is intentionally UI/CAM-agnostic and can be printed/logged anywhere.
    """
    tol_mm: float = 0.05

    is_closed: bool = False

    # Gaps between consecutive edges after ordering
    gaps: List[GapInfo] = field(default_factory=list)

    # Topology / validity flags
    branches_detected: bool = False          # node degree > 2 (T junction / branching)
    disconnected_islands: bool = False       # not all edges can be connected into one chain
    reused_edges: bool = False               # same edge used more than once

    # Optional extra diagnostics
    unused_edge_ids: List[int] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def ok(self) -> bool:
        """True if the ordering result looks valid for a single continuous polyline."""
        return (
            (not self.branches_detected)
            and (not self.disconnected_islands)
            and (not self.reused_edges)
            and (len(self.gaps) == 0)
        )


@dataclass
class OrderedPolyline:
    """
    Ordered polyline representation:
      - edge_ids: ordered edge indices (refer to Document edge index list)
      - directions: +1 or -1 per edge, representing traversal direction
    """
    edge_ids: List[int] = field(default_factory=list)
    directions: List[int] = field(default_factory=list)

    # Optional endpoints for open polylines (computed later by geometry layer)
    start_point: Optional[Point3D] = None
    end_point: Optional[Point3D] = None

    report: PolylineReport = field(default_factory=PolylineReport)

    def __post_init__(self) -> None:
        if len(self.edge_ids) != len(self.directions):
            raise ValueError(
                f"edge_ids and directions must have same length "
                f"({len(self.edge_ids)} != {len(self.directions)})"
            )

        for d in self.directions:
            if d not in (-1, 1):
                raise ValueError(
                    f"direction values must be +1 or -1, got: {d}"
                )

    def is_empty(self) -> bool:
        return len(self.edge_ids) == 0

    def is_closed(self) -> bool:
        return self.report.is_closed

    def ok(self) -> bool:
        return self.report.ok()
