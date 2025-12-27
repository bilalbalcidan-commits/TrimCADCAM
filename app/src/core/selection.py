from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

from PySide6.QtCore import QObject, QEvent, Qt, QTimer
from PySide6.QtWidgets import QApplication

from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopoDS import topods


@dataclass
class PickResult:
    edge_id: Optional[int] = None


class EdgePicker(QObject):
    """
    İlk sürüm picking:
    - Click sonrası OCC context seçimi bazen event sonunda güncellenir.
    - Bu yüzden QTimer.singleShot(0, ...) ile bir event-loop turu sonra okuruz.
    """

    def __init__(self, viewer, edges: List[object]):
        super().__init__(viewer)
        self.viewer = viewer
        self.edges = edges
        self.enabled = False

        self.last_shift = False
        self.last_pick: Optional[PickResult] = None

        # internal
        self._pending_read = False

    def set_edges(self, edges: List[object]) -> None:
        self.edges = edges

    def enable(self) -> None:
        if self.enabled:
            return
        self.enabled = True
        self.viewer.installEventFilter(self)
        self._force_edge_selection_mode()

    def disable(self) -> None:
        if not self.enabled:
            return
        self.enabled = False
        self.viewer.removeEventFilter(self)

    def _force_edge_selection_mode(self) -> None:
        d = getattr(self.viewer, "_display", None)
        if d is None:
            return
        try:
            d.SetSelectionModeEdge()
            return
        except Exception:
            pass
        try:
            d.SetSelectionMode(TopAbs_EDGE)
            return
        except Exception:
            pass

    def _get_ctx(self):
        disp = getattr(self.viewer, "_display", None)
        if disp is None:
            return None
        return getattr(disp, "Context", None)

    def _read_pick_from_context(self) -> None:
        """Event-loop bir tur döndükten sonra güvenli okuma."""
        self._pending_read = False

        ctx = self._get_ctx()
        if ctx is None or not self.edges:
            return

        picked_edge = None
        try:
            ctx.InitSelected()
            while ctx.MoreSelected():
                shp = ctx.SelectedShape()
                try:
                    picked_edge = topods.Edge(shp)
                except Exception:
                    picked_edge = None
                ctx.NextSelected()
        except Exception:
            picked_edge = None

        if picked_edge is None:
            return

        eid = None
        for i, e in enumerate(self.edges):
            try:
                if e.IsSame(picked_edge):
                    eid = i
                    break
            except Exception:
                continue

        if eid is None:
            return

        self.last_pick = PickResult(edge_id=eid)

    def eventFilter(self, obj, event):
        if not self.enabled:
            return False

        if obj is self.viewer and event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            mods = QApplication.keyboardModifiers()
            self.last_shift = bool(mods & Qt.ShiftModifier)

            # Seçim hemen oluşmayabilir -> event loop turu sonrası oku
            if not self._pending_read:
                self._pending_read = True
                QTimer.singleShot(0, self._read_pick_from_context)

            return False

        return False
