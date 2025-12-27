from __future__ import annotations

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopoDS import topods


def load_step(step_path: str):
    """
    STEP dosyasını okur ve tek bir TopoDS_Shape döner.
    """
    reader = STEPControl_Reader()
    status = reader.ReadFile(step_path)
    if status != IFSelect_RetDone:
        raise RuntimeError("STEP read failed")
    reader.TransferRoots()
    return reader.OneShape()


def build_edge_index(shape) -> list:
    """
    Shape içindeki tüm edge'leri sırayla gezip liste döndürür.
    Listedeki index => bizim stable edge ID'miz.
    """
    edges = []
    exp = TopExp_Explorer(shape, TopAbs_EDGE)
    while exp.More():
        edges.append(topods.Edge(exp.Current()))
        exp.Next()
    return edges
