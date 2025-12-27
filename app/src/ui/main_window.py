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

from core.document import Document
from core.step_io import load_step, build_edge_index
from core.selection import EdgePicker

# ✅ FAZ 3 – ADIM 4B: geometry ordering imports
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

        # -----------------------------
        # Global Coordinate System (Trihedron)
        # -----------------------------
        try:
            self.viewer._display.View_Trihedron(True)
        except Exception:
            pass

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

        # ---- Toolbar (Polyline Select) ----
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

        # ✅ FAZ 3 – ADIM 4B: Order Selected Polyline action
        self.act_order_poly = QAction("Order Selected Polyline", self)
        self.act_order_poly.triggered.connect(self.on_order_selected_polyline)
        tb.addAction(self.act_order_poly)

        # ---- Selection State ----
        self._selected_edge_ids: list[int] = []
        self._polyline_mode = False

        # Edge picker (mouse selection)
        self.picker = EdgePicker(self.viewer, self.doc.edges)

        # Viewer defaults
        self.viewer._display.View_Iso()
        self.viewer._display.FitAll()

        # Poll timer: picker.last_pick'i okuyup listeye alacağız
        self._pick_poll = QTimer(self)
        self._pick_poll.setInterval(40)  # ms
        self._pick_poll.timeout.connect(self._consume_last_pick)

        # Initial tree
        self.build_tree()

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

            # picker edge listesi güncelle
            self.picker.set_edges(self.doc.edges)

            self.viewer._display.EraseAll()
            self.viewer._display.DisplayShape(shape, update=True)
            self.viewer._display.FitAll()

            # seçim açıkken model değiştiyse mod devam edebilir
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
                "Polyline mode ON: Edge'lere tıkla. SHIFT+Click = remove. OK ile polyline oluştur."
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

        # consume once
        self.picker.last_pick = None

        if self.picker.last_shift:
            # SHIFT: remove
            if edge_id in self._selected_edge_ids:
                self._selected_edge_ids.remove(edge_id)
                self.statusBar().showMessage(
                    f"Removed Edge_{edge_id:04d} (selected: {len(self._selected_edge_ids)})"
                )
        else:
            # normal: add
            if edge_id not in self._selected_edge_ids:
                self._selected_edge_ids.append(edge_id)
                self.statusBar().showMessage(
                    f"Added Edge_{edge_id:04d} (selected: {len(self._selected_edge_ids)})"
                )

    def cancel_polyline_selection(self) -> None:
        self._selected_edge_ids = []
        self.statusBar().showMessage("Selection cleared.")

    def commit_polyline(self) -> None:
        # ✅ OK’e basıldıysa, son click daha list'e düşmemiş olabilir
        self._consume_last_pick()

        if not self._polyline_mode:
            QMessageBox.information(self, "Info", "Önce Start Polyline Select aç.")
            return
        if not self._selected_edge_ids:
            QMessageBox.information(self, "Info", "Seçili edge yok.")
            return

        name = self.doc.add_polyline(self._selected_edge_ids)
        self._selected_edge_ids = []

        self.build_tree()
        self.statusBar().showMessage(f"{name} created.")

    # ---------------- FAZ 3: Order Polyline ----------------
    def on_order_selected_polyline(self) -> None:
        """
        Orders the currently selected polyline from the tree and stores it in Document.
        Minimal UI plumbing: logs a short report to console and status bar.
        """
        # 1) Get selected polyline name from the tree
        item = self.tree.currentItem()
        if item is None:
            print("[OrderPolyline] Select a polyline node in the tree (e.g., Polyline_001).")
            return

        polyline_name = item.text(0)
        if polyline_name not in self.doc.polylines:
            print("[OrderPolyline] Select a polyline node in the tree (e.g., Polyline_001).")
            return

        edge_ids = self.doc.polylines.get(polyline_name, [])
        if not edge_ids:
            print(f"[OrderPolyline] Polyline '{polyline_name}' has no edges.")
            return

        # 2) Build endpoints callback: edge_id -> (P0, P1)
        def get_endpoints_by_id(eid: int):
            try:
                edge = self.doc.edges[eid]
            except Exception as ex:
                raise IndexError(f"Invalid edge id {eid}: {ex}") from ex
            return edge_endpoints(edge)

        # 3) Run ordering
        ordered = order_edges(edge_ids, get_endpoints=get_endpoints_by_id, tol_mm=0.05)

        # 4) Store result in Document
        self.doc.set_ordered_polyline(polyline_name, ordered)

        # 5) Minimal feedback
        r = ordered.report
        msg = (
            f"[OrderPolyline] {polyline_name}: "
            f"edges={len(ordered.edge_ids)} closed={r.is_closed} "
            f"gaps={len(r.gaps)} branch={r.branches_detected} disconnected={r.disconnected_islands}"
        )
        print(msg)
        self.statusBar().showMessage(msg, 8000)
