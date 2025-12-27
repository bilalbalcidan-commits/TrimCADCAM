from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .polyline_types import GapInfo, OrderedPolyline, Point3D, PolylineReport

# A function that returns endpoints of an edge by id:
#   get_endpoints(edge_id) -> (P0, P1)
GetEndpointsFn = Callable[[int], Tuple[Point3D, Point3D]]


def _dist(a: Point3D, b: Point3D) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return (dx * dx + dy * dy + dz * dz) ** 0.5


@dataclass(frozen=True)
class _EndpointRef:
    edge_id: int
    end: int  # 0 for P0, 1 for P1


class _NodeIndex:
    """
    Groups endpoints into nodes using distance tolerance.
    Simple O(N*M) clustering (good enough for typical trim polylines).
    """

    def __init__(self, tol_mm: float) -> None:
        self.tol_mm = tol_mm
        self._reps: List[Point3D] = []              # representative point per node
        self._members: List[List[_EndpointRef]] = []  # endpoint refs per node

    def add_endpoint(self, p: Point3D, ref: _EndpointRef) -> int:
        for i, rep in enumerate(self._reps):
            if _dist(p, rep) <= self.tol_mm:
                self._members[i].append(ref)
                return i
        # new node
        self._reps.append(p)
        self._members.append([ref])
        return len(self._reps) - 1

    def rep_point(self, node_id: int) -> Point3D:
        return self._reps[node_id]

    def members(self, node_id: int) -> List[_EndpointRef]:
        return self._members[node_id]

    def node_count(self) -> int:
        return len(self._reps)


def order_edges(
    edge_ids: List[int],
    get_endpoints: GetEndpointsFn,
    tol_mm: float = 0.05,
) -> OrderedPolyline:
    """
    Order an unordered set of edges (by ids) into a single continuous polyline.

    Kernel/UI agnostic:
      - input is edge_ids + a callback to retrieve endpoints
      - output is OrderedPolyline(edge_ids, directions, report)

    directions:
      +1 means traverse edge P0->P1
      -1 means traverse edge P1->P0
    """
    report = PolylineReport(tol_mm=tol_mm)

    if not edge_ids:
        return OrderedPolyline(edge_ids=[], directions=[], report=report)

    # 1) Build node clusters for all endpoints
    nodes = _NodeIndex(tol_mm=tol_mm)

    # edge_id -> (node_of_P0, node_of_P1)
    edge_nodes: Dict[int, Tuple[int, int]] = {}

    # degree count per node (how many edge-ends attach to it /2 notion handled later)
    degree: Dict[int, int] = {}

    for eid in edge_ids:
        p0, p1 = get_endpoints(eid)
        n0 = nodes.add_endpoint(p0, _EndpointRef(edge_id=eid, end=0))
        n1 = nodes.add_endpoint(p1, _EndpointRef(edge_id=eid, end=1))
        edge_nodes[eid] = (n0, n1)

    # compute node degrees (edge incidence count)
    for eid, (n0, n1) in edge_nodes.items():
        degree[n0] = degree.get(n0, 0) + 1
        degree[n1] = degree.get(n1, 0) + 1

    # Branch detection: any node with degree > 2 means branching / T junction
    if any(d > 2 for d in degree.values()):
        report.branches_detected = True
        report.notes.append("Branching detected (node degree > 2). Ordering expects a single chain.")

    # 2) Choose start node
    end_nodes = [nid for nid, d in degree.items() if d == 1]

    is_closed_topology = (len(end_nodes) == 0)
    report.is_closed = is_closed_topology

    if not is_closed_topology and len(end_nodes) != 2:
        # disconnected / malformed chain (e.g., multiple islands)
        report.disconnected_islands = True
        report.notes.append(
            f"Expected exactly 2 end nodes for open polyline, got {len(end_nodes)}."
        )

    start_node = end_nodes[0] if end_nodes else edge_nodes[edge_ids[0]][0]

    # 3) Walk to build ordered edge sequence
    used = set()
    ordered_ids: List[int] = []
    directions: List[int] = []

    current_node = start_node

    # adjacency: node -> incident edge_ids
    adjacency: Dict[int, List[int]] = {}
    for eid, (n0, n1) in edge_nodes.items():
        adjacency.setdefault(n0, []).append(eid)
        adjacency.setdefault(n1, []).append(eid)

    # Helper: pick next unused incident edge
    def pick_next_edge(node_id: int) -> Optional[int]:
        for eid in adjacency.get(node_id, []):
            if eid not in used:
                return eid
        return None

    # Safety: prevent infinite loops
    max_steps = len(edge_ids) + 5

    steps = 0
    while steps < max_steps:
        steps += 1
        next_eid = pick_next_edge(current_node)
        if next_eid is None:
            break

        n0, n1 = edge_nodes[next_eid]

        # Determine traversal direction based on which endpoint matches current_node
        if current_node == n0:
            dir_val = +1
            next_node = n1
        elif current_node == n1:
            dir_val = -1
            next_node = n0
        else:
            # Shouldn't happen if adjacency built correctly
            report.notes.append(f"Adjacency inconsistency at node {current_node} for edge {next_eid}.")
            report.disconnected_islands = True
            break

        ordered_ids.append(next_eid)
        directions.append(dir_val)
        used.add(next_eid)
        current_node = next_node

        # Closed loop termination: if closed and we returned to start and used all edges
        if report.is_closed and (current_node == start_node) and (len(used) == len(edge_ids)):
            break

    # 4) Post checks
    if len(used) != len(edge_ids):
        report.disconnected_islands = True
        report.unused_edge_ids = [eid for eid in edge_ids if eid not in used]
        report.notes.append(
            f"Not all edges were used in a single walk (used {len(used)}/{len(edge_ids)})."
        )

    # reused_edges can happen only if algorithm is wrong; still keep a guard
    if len(set(ordered_ids)) != len(ordered_ids):
        report.reused_edges = True
        report.notes.append("An edge was used more than once (unexpected).")

    # 5) Compute gaps between consecutive edges in ordered result
    # Determine start/end points of each edge based on direction, then compare.
    def edge_start_end(eid: int, dir_val: int) -> Tuple[Point3D, Point3D]:
        p0, p1 = get_endpoints(eid)
        return (p0, p1) if dir_val == +1 else (p1, p0)

    for i in range(len(ordered_ids) - 1):
        a_id, a_dir = ordered_ids[i], directions[i]
        b_id, b_dir = ordered_ids[i + 1], directions[i + 1]
        _, a_end = edge_start_end(a_id, a_dir)
        b_start, _ = edge_start_end(b_id, b_dir)
        gap = _dist(a_end, b_start)
        if gap > tol_mm:
            report.gaps.append(GapInfo(index=i, distance_mm=gap))

    # 6) Construct result
    result = OrderedPolyline(
        edge_ids=ordered_ids,
        directions=directions,
        report=report,
    )

    # Optionally set endpoints for open polylines if we successfully produced something
    if result.edge_ids:
        s0, _ = edge_start_end(result.edge_ids[0], result.directions[0])
        _, e1 = edge_start_end(result.edge_ids[-1], result.directions[-1])
        result.start_point = s0
        result.end_point = e1

    return result


# -------------------------
# Minimal self-test (no OCC)
# -------------------------
def _selftest() -> None:
    # Create a simple open chain: 1--2--3 using three edges
    # Edge ids: 10, 11, 12
    A = (0.0, 0.0, 0.0)
    B = (10.0, 0.0, 0.0)
    C = (20.0, 0.0, 0.0)
    D = (30.0, 0.0, 0.0)

    endpoints = {
        10: (B, A),  # reversed on purpose
        11: (B, C),
        12: (D, C),  # reversed on purpose
    }

    def get_ep(eid: int) -> Tuple[Point3D, Point3D]:
        return endpoints[eid]

    op = order_edges([10, 11, 12], get_ep, tol_mm=0.001)
    assert op.ok(), f"Expected ok, got report: {op.report}"
    assert op.edge_ids == [10, 11, 12], f"Unexpected order: {op.edge_ids}"
    assert op.directions == [-1, +1, -1], f"Unexpected dirs: {op.directions}"
    assert op.start_point == A and op.end_point == D, f"Unexpected endpoints: {op.start_point} -> {op.end_point}"


if __name__ == "__main__":
    _selftest()
    print("SELFTEST_OK")
