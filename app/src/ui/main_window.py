from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow,
    QFileDialog,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
    QToolBar,
)

from OCC.Display.backend import load_backend

load_backend("pyside6")
from OCC.Display.qtDisplay import qtViewer3d

# ✅ AIS Trihedron (works in all pythonocc setups)
from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax2
from OCC.Core.Geom import Geom_Axis2Placement
from OCC.Core.AIS import AIS_Trihedron

from core.document import Document
from core.step_io import load_step, build_edge_index
from core.selection import EdgePicker

# FAZ 3 – geometry ordering
from geometry.edge_ordering import order_edges
from geometry.edge_endpoints import edge_endpoints


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TrimCADCAM")
        self.resize(1600, 950)

        # ---- Model (Document) ----
        self.doc = Document()

        # ---- UI: Tree + Viewer ----
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

        # ---- Menu ----
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open STEP...", self)
        open_action.triggered.connect(self.open_step_dialog)
        file_menu.addAction(open_action)

        # ---- Toolbar ----
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

        self.act_order_poly = QAction("Order Selected Polyline", self)
        self.act_order_poly.triggered.connect(self.on_order_selected_polyline)
        tb.addAction(self.act_order_poly)

        # ---- Selection State ----
        self._selected_edge_ids: list[int] = []
        self._polyline_mode = False

        # Edge picker
        self.picker = EdgePicker(self.viewer, self.doc.edges)

        # Viewer defaults
        self.viewer._display.View_Iso()
        self.viewer._display.FitAll()

        # -------------------------------------------------
        # Global Coordinate System (AIS_Trihedron)
        # - Works everywhere
        # - We keep it visible after STEP import (EraseAll)
        # - We auto-adjust size so it stays readable on zoom
        # -------------------------------------------------
        self._trihedron = self._create_trihedron()
        self._display_trihedron()

        # Zoom-friendly: keep trihedron readable (approx. zoom-independent feel)
        self._tri_update = QTimer(self)
        self._tri_update.setInterval(200)  # ms
        self._tri_update.timeout.connect(self._update_trihedron_size)
        self._tri_update.start()

        # Poll timer
        self._pick_poll = QTimer(self)
        self._pick_poll.setInterval(40)
        self._pick_poll.timeout.connect(self._consume_last_pick)

        self.build_tree()

    # ---------------- Trihedron helpers ----------------
    def _create_trihedron(self) -> AIS_Trihedron | None:
        try:
            ax2 = gp_Ax2(
                gp_Pnt(0.0, 0.0, 0.0),  # Origin
                gp_Dir(0.0, 0.0, 1.0),  # Z
                gp_Dir(1.0, 0.0, 0.0),  # X
            )
            geom_ax2 = Geom_Axis2Placement(ax2)
            tri = AIS_Trihedron(geom_ax2)
            tri.SetSize(80.0)  # baseline
            return tri
        except Exception as e:
            print("AIS_Trihedron create failed:", e)
            return None

    def _display_trihedron(self) -> None:
        """Display trihedron in context (safe to call multiple times)."""
        if self._trihedron is None:
            return
        try:
            ctx = self.viewer._display.Context
            ctx.Display(self._trihedron, False)
        except Exception as e:
            print("AIS_Trihedron display failed:", e)

    def _update_trihedron_size(self) -> None:
        """
        Keep trihedron readable while zooming.
        This is an approximation (screen-constant feel) that works without overlay APIs.
        """
        if self._trihedron is None:
            return
        try:
            view = self.viewer._display.View
            s = float(view.Scale())  # typically increases with zoom-in

            # Tune: bigger = more stable visual size.
            # Clamp to avoid extreme sizes.
            size = 80.0 / max(0.0001, s)
            size = max(30.0, min(140.0, size))

            self._trihedron.SetSize(size)

            # Optional: request redraw
            try:
                view.Redraw()
            except Exception:
                pass
        except Exception:
            # Keep silent; size update is best-effort
            pass

    # ---------------- Tree ----------------
    def build_tree(self) -> None:
        self.tree.clear()
        root = QTreeWidgetItem(self.tree, ["Model"])

        shapes = QTreeWidgetItem(root, ["Shapes"])
        polylines = QTreeWidgetItem(root, ["Polylines"])

        if self.doc.file_path:
            step_node = QTreeWidgetItem(shapes, [Path(self.doc.file_path).name])
            QTreeWidgetItem(step_node, [f"Edges: {len(self.doc.edges)}"])
        else:
            QTreeWidgetItem(shapes, ["(no model loaded)"])

        for name, edge_ids in self.doc.polylines.items():
            pnode = QTreeWidgetItem(polylines, [name])
            for eid in edge_ids:
                QTreeWidgetItem(pnode, [f"Edge_{eid:04d}"])

        self.tree.expandAll()

    # ---------------- STEP Open ----------------
    def open_step_dialog(self) -> None:
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
            edges = build_edge_index(shape)

            self.doc.set_model(file_path, shape, edges)
            self.picker.set_edges(self.doc.edges)

            # EraseAll clears displayed AIS objects (including trihedron)
            self.viewer._display.EraseAll()
            self.viewer._display.DisplayShape(shape, update=True)

            # ✅ Re-display trihedron after EraseAll
            self._display_trihedron()

            self.viewer._display.FitAll()

            if self._polyline_mode:
                self.picker.enable()

            self.build_tree()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open STEP:\n{e}")

    # ---------------- Polyline Mode ----------------
    def toggle_polyline_mode(self, checked: bool) -> None:
        self._polyline_mode = bool(checked)

        if self._polyline_mode:
            if not self.doc.shape or not self.doc.edges:
                QMessageBox.information(self, "Info", "Önce STEP aç.")
                self.act_start_poly.setChecked(False)
                self._polyline_mode = False
                return

            self._selected_edge_ids = []
            self.picker.enable()
            self._pick_poll.start()
            self.statusBar().showMessage(
                "Polyline mode ON: Edge'lere tıkla. SHIFT+Click = remove."
            )
        else:
            self._pick_poll.stop()
            self.picker.disable()
            self.statusBar().showMessage("Polyline mode OFF.")

    def _consume_last_pick(self) -> None:
        pr = getattr(self.picker, "last_pick", None)
        if pr is None:
            return

        edge_id = getattr(pr, "edge_id", None)
        if edge_id is None:
            return

        self.picker.last_pick = None

        if self.picker.last_shift:
            if edge_id in self._selected_edge_ids:
                self._selected_edge_ids.remove(edge_id)
        else:
            if edge_id not in self._selected_edge_ids:
                self._selected_edge_ids.append(edge_id)

    def cancel_polyline_selection(self) -> None:
        self._selected_edge_ids = []
        self.statusBar().showMessage("Selection cleared.")

    def commit_polyline(self) -> None:
        self._consume_last_pick()

        if not self._polyline_mode or not self._selected_edge_ids:
            return

        name = self.doc.add_polyline(self._selected_edge_ids)
        self._selected_edge_ids = []

        self.build_tree()
        self.statusBar().showMessage(f"{name} created.")

    # ---------------- Order Polyline ----------------
    def on_order_selected_polyline(self) -> None:
        item = self.tree.currentItem()
        if not item:
            return

        polyline_name = item.text(0)
        if polyline_name not in self.doc.polylines:
            return

        edge_ids = self.doc.polylines[polyline_name]

        def get_endpoints_by_id(eid: int):
            return edge_endpoints(self.doc.edges[eid])

        ordered = order_edges(edge_ids, get_endpoints=get_endpoints_by_id, tol_mm=0.05)
        self.doc.set_ordered_polyline(polyline_name, ordered)

        r = ordered.report
        msg = (
            f"{polyline_name}: edges={len(ordered.edge_ids)} "
            f"closed={r.is_closed} gaps={len(r.gaps)}"
        )
        print(msg)
        self.statusBar().showMessage(msg, 8000)
