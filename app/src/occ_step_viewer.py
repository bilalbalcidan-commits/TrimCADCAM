import sys
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QFileDialog,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
    QToolBar,
)
from PySide6.QtGui import QAction

from OCC.Display.backend import load_backend
load_backend("pyside6")
from OCC.Display.qtDisplay import qtViewer3d

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopoDS import topods


def load_step(step_path: str):
    reader = STEPControl_Reader()
    status = reader.ReadFile(step_path)
    if status != IFSelect_RetDone:
        raise RuntimeError("STEP read failed")
    reader.TransferRoots()
    return reader.OneShape()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TrimCADCAM - STEP Viewer")
        self.resize(1600, 950)

        # ---- DATA ----
        self._current_shape = None
        self._edge_list = []             # stable IDs
        self._selection_mode = False
        self._selected_edge_ids = []
        self._polyline_counter = 0
        self._polylines = {}

        self._last_click_shift = False

        # ---- UI ----
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Model Tree")

        self.viewer = qtViewer3d(self)
        self.viewer.InitDriver()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.viewer)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        self.setCentralWidget(splitter)

        # Menu
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        open_action = QAction("Open STEP...", self)
        open_action.triggered.connect(self.open_step_dialog)
        file_menu.addAction(open_action)

        # Toolbar
        tb = QToolBar("Tools")
        self.addToolBar(tb)

        self.act_start_poly = QAction("Start Polyline Select", self)
        self.act_start_poly.setCheckable(True)
        self.act_start_poly.triggered.connect(self.toggle_polyline_mode)
        tb.addAction(self.act_start_poly)

        self.act_ok_poly = QAction("OK (Create Polyline)", self)
        self.act_ok_poly.triggered.connect(self.commit_polyline)
        tb.addAction(self.act_ok_poly)

        self.act_cancel_poly = QAction("Cancel Selection", self)
        self.act_cancel_poly.triggered.connect(self.cancel_polyline_selection)
        tb.addAction(self.act_cancel_poly)

        # Viewer defaults
        self.viewer._display.View_Iso()
        self.viewer._display.FitAll()

        # ✅ Event filter (kritik)
        self.viewer.installEventFilter(self)

        self.build_empty_tree()

    # ---------------- OCC helpers ----------------
    def _get_occ_view(self):
        disp = getattr(self.viewer, "_display", None)
        if disp is None:
            return None
        v = getattr(disp, "View", None)
        if v is not None:
            return v
        v = getattr(disp, "_view", None)
        if v is not None:
            return v
        return None

    def _get_ctx(self):
        disp = getattr(self.viewer, "_display", None)
        if disp is None:
            return None
        return getattr(disp, "Context", None)

    def _force_edge_selection_mode(self):
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
        try:
            d.EnableSelection()
        except Exception:
            pass

    # ✅ DPI + coordinate conversion
    def _qt_to_occ_xy(self, event) -> tuple[int, int] | None:
        """
        Qt mouse position -> OCC device-pixel coordinates
        - handles Windows scaling %100/%125/%150
        - handles Qt top-left -> OCC bottom-left (Y flip)
        """
        try:
            p = event.position().toPoint()  # logical coords
            lx, ly = int(p.x()), int(p.y())
        except Exception:
            p = event.pos()
            lx, ly = int(p.x()), int(p.y())

        # device pixel ratio
        dpr = 1.0
        try:
            dpr = float(self.viewer.devicePixelRatioF())
        except Exception:
            pass

        dx = int(lx * dpr)
        dy = int(ly * dpr)

        # Y flip
        h = int(self.viewer.height() * dpr)
        dy = h - dy

        return dx, dy

    # ---------------- EventFilter ----------------
    def eventFilter(self, obj, event):
        if obj is self.viewer:
            # ✅ MouseMove: highlight/picking’i biz düzeltelim
            if event.type() == QEvent.MouseMove:
                if self._selection_mode and self._current_shape is not None:
                    ctx = self._get_ctx()
                    view = self._get_occ_view()
                    if ctx is not None and view is not None:
                        xy = self._qt_to_occ_xy(event)
                        if xy is not None:
                            x, y = xy
                            try:
                                ctx.MoveTo(x, y, view, True)
                            except Exception:
                                pass

            # ✅ Click: Detected edge’i al
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                if self._selection_mode and self._current_shape is not None:
                    mods = QApplication.keyboardModifiers()
                    self._last_click_shift = bool(mods & Qt.ShiftModifier)
                    QTimer.singleShot(0, self._capture_detected_edge_after_click)

        return super().eventFilter(obj, event)

    def _capture_detected_edge_after_click(self):
        if not self._selection_mode:
            return
        if self._current_shape is None or not self._edge_list:
            return

        ctx = self._get_ctx()
        if ctx is None:
            return

        picked_edge = None
        try:
            if ctx.HasDetected():
                shp = ctx.DetectedShape()
                picked_edge = topods.Edge(shp)
        except Exception:
            picked_edge = None

        if picked_edge is None:
            return

        # Edge -> ID
        eid = None
        for i, e in enumerate(self._edge_list):
            if e.IsSame(picked_edge):
                eid = i
                break
        if eid is None:
            return

        # SHIFT remove / normal add
        if self._last_click_shift:
            if eid in self._selected_edge_ids:
                self._selected_edge_ids.remove(eid)
                self.statusBar().showMessage(f"Removed Edge_{eid:04d} (selected: {len(self._selected_edge_ids)})")
        else:
            if eid not in self._selected_edge_ids:
                self._selected_edge_ids.append(eid)
                self.statusBar().showMessage(f"Added Edge_{eid:04d} (selected: {len(self._selected_edge_ids)})")

    # ---------------- Tree ----------------
    def build_empty_tree(self):
        self.tree.clear()
        root = QTreeWidgetItem(self.tree, ["Model"])
        QTreeWidgetItem(root, ["Shapes"])
        QTreeWidgetItem(root, ["Polylines"])
        self.tree.expandAll()

    def set_tree_for_step(self, file_path: str, edge_count: int):
        self.tree.clear()
        root = QTreeWidgetItem(self.tree, ["Model"])

        shapes = QTreeWidgetItem(root, ["Shapes"])
        step_node = QTreeWidgetItem(shapes, [Path(file_path).name])
        step_node.setData(0, Qt.UserRole, "STEP_SHAPE")
        QTreeWidgetItem(step_node, [f"Edges: {edge_count}"])

        polylines = QTreeWidgetItem(root, ["Polylines"])
        polylines.setData(0, Qt.UserRole, "POLYLINES_ROOT")

        # existing polylines
        for name, edge_ids in self._polylines.items():
            pnode = QTreeWidgetItem(polylines, [name])
            pnode.setData(0, Qt.UserRole, ("POLYLINE", name))
            for eid in edge_ids:
                enode = QTreeWidgetItem(pnode, [f"Edge_{eid:04d}"])
                enode.setData(0, Qt.UserRole, ("EDGE_REF", eid))

        self.tree.expandAll()

    # ---------------- Edge index ----------------
    def rebuild_edge_index(self):
        self._edge_list = []
        if self._current_shape is None:
            return
        exp = TopExp_Explorer(self._current_shape, TopAbs_EDGE)
        while exp.More():
            e = topods.Edge(exp.Current())
            self._edge_list.append(e)
            exp.Next()

    # ---------------- Polyline mode ----------------
    def toggle_polyline_mode(self, checked: bool):
        self._selection_mode = bool(checked)

        if self._selection_mode:
            self._selected_edge_ids = []
            self._force_edge_selection_mode()
            self.statusBar().showMessage(
                "Polyline selection: Hover highlights edge; Click selects. SHIFT+Click removes. Then OK."
            )
        else:
            self.statusBar().showMessage("Selection mode off.")

    def cancel_polyline_selection(self):
        self._selected_edge_ids = []
        self.statusBar().showMessage("Polyline selection cleared.")

    def commit_polyline(self):
        if not self._selection_mode:
            QMessageBox.information(self, "Info", "Start Polyline Select mode first.")
            return
        if not self._selected_edge_ids:
            QMessageBox.information(self, "Info", "No edges selected.")
            return

        self._polyline_counter += 1
        name = f"Polyline_{self._polyline_counter:03d}"
        self._polylines[name] = list(self._selected_edge_ids)

        # Update tree
        root = self.tree.invisibleRootItem()
        model = root.child(0)

        polylines_root = None
        for i in range(model.childCount()):
            item = model.child(i)
            if item.text(0) == "Polylines":
                polylines_root = item
                break
        if polylines_root is None:
            polylines_root = QTreeWidgetItem(model, ["Polylines"])

        pnode = QTreeWidgetItem(polylines_root, [name])
        pnode.setData(0, Qt.UserRole, ("POLYLINE", name))
        for eid in self._selected_edge_ids:
            enode = QTreeWidgetItem(pnode, [f"Edge_{eid:04d}"])
            enode.setData(0, Qt.UserRole, ("EDGE_REF", eid))

        self.tree.expandAll()

        self._selected_edge_ids = []
        self.statusBar().showMessage(f"{name} created.")

    # ---------------- File open ----------------
    def open_step_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open STEP file",
            str(Path.cwd()),
            "STEP Files (*.stp *.step);;All Files (*.*)",
        )
        if not file_path:
            return

        try:
            shape = load_step(file_path)
            self._current_shape = shape

            self.rebuild_edge_index()
            edge_count = len(self._edge_list)

            self.viewer._display.EraseAll()
            self.viewer._display.DisplayShape(shape, update=True)
            self.viewer._display.FitAll()

            if self._selection_mode:
                self._force_edge_selection_mode()

            self.set_tree_for_step(file_path, edge_count)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open STEP:\n{e}")


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
