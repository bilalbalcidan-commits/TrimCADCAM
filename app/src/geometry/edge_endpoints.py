from __future__ import annotations

from typing import Tuple

from .polyline_types import Point3D

# OCC imports (pythonocc-core)
from OCC.Core.TopoDS import TopoDS_Edge
from OCC.Core.BRep import BRep_Tool
from OCC.Core.gp import gp_Pnt


def _pnt_to_tuple(p: gp_Pnt) -> Point3D:
    """Convert OCC gp_Pnt -> (x, y, z) tuple."""
    return (float(p.X()), float(p.Y()), float(p.Z()))


def edge_curve_params(edge: TopoDS_Edge):
    """
    Return (curve_handle, u0, u1) for the edge.
    curve_handle is a Geom_Curve handle (OCC).
    """
    curve_handle, u0, u1 = BRep_Tool.Curve(edge)
    if curve_handle is None:
        raise ValueError("BRep_Tool.Curve returned None. Edge may be degenerate or invalid.")
    return curve_handle, float(u0), float(u1)


def edge_endpoints(edge: TopoDS_Edge) -> Tuple[Point3D, Point3D]:
    """
    Get the two endpoint coordinates of a TopoDS_Edge as (P0, P1).
    NOTE:
      - This follows the underlying curve parameter range (u0 -> u1).
      - Polyline traversal direction (+1/-1) will be handled separately in ordering logic.
    """
    curve, u0, u1 = edge_curve_params(edge)
    p0 = curve.Value(u0)
    p1 = curve.Value(u1)
    return _pnt_to_tuple(p0), _pnt_to_tuple(p1)


def edge_point_at(edge: TopoDS_Edge, t: float) -> Point3D:
    """
    Point at normalized parameter t in [0, 1] along the edge curve range.
    """
    if t < 0.0 or t > 1.0:
        raise ValueError(f"t must be within [0, 1], got: {t}")
    curve, u0, u1 = edge_curve_params(edge)
    u = (1.0 - t) * u0 + t * u1
    p = curve.Value(u)
    return _pnt_to_tuple(p)


def edge_midpoint(edge: TopoDS_Edge) -> Point3D:
    """Convenience midpoint at t=0.5."""
    return edge_point_at(edge, 0.5)
