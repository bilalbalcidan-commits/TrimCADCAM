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
    QSplashScreen,
)
from PySide6.QtGui import QAction, QPixmap

from OCC.Display.backend import load_backend
load_backend("pyside6")
from OCC.Display.qtDisplay import qtViewer3d

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopoDS import topods

from OCC.Core.AIS import AIS_Shape
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB

from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopoDS import TopoDS_Compound

from OCC.Core.Aspect import Aspect_TOL_SOLID


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
        self._current_step_path: str | None = None

        self._edge_list = []
        self._selection_mode = False
        self._selected_edge_ids = []
        self._polyline_counter = 0
        self._polylines = {}

        self._last_click_shift = False

        # Selected edges overlay (persistent)
        self._selected_ais = {}
        self._selected_color = (0.0, 1.0, 0.0)

        # Displayed objects (hide/show)
        self._model_ais = None
        self._polyline_ais = {}  # name -> AIS_Shape

        # Tree highlight (temporary)
        self._tree_highlight_ais = None
        self._tree_highlight_kind = None

        # Active polyline picked from viewport
        self._active_polyline_name: str | None = None
        self._active_polyline_prev_style = {}

        # Polyline pick style (blue + thick)
        self._picked_poly_color = (0.2, 0.4, 1.0)
        self._picked_poly_width = 3.0

        # ---- UI ----
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Model Tree")
        self.tree.setSelectionMode(QTreeWidget.SingleSelection)
        self.tree.itemChanged.connect(self.on_tree_item_changed)
        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)

        self.viewer = qtViewer3d(self)
        self.viewer.InitDriver()
        self.viewer.setFocusPolicy(Qt.StrongFocus)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.viewer)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([280, 1120])
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

        self.viewer._display.View_Iso()
        self.viewer._display.FitAll()

        # ✅ DO NOT swallow clicks: let viewer update its detection/selection state
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
        return getattr(disp, "_view", None)

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

    def _qt_to_occ_xy(self, event) -> tuple[int, int] | None:
        try:
            p = event.position().toPoint()
            lx, ly = int(p.x()), int(p.y())
        except Exception:
            p = event.pos()
            lx, ly = int(p.x()), int(p.y())

        dpr = 1.0
        try:
            dpr = float(self.viewer.devicePixelRatioF())
        except Exception:
            pass

        dx = int(lx * dpr)
        dy = int(ly * dpr)

        h = int(self.viewer.height() * dpr)
        dy = h - dy
        return dx, dy

    # ---------------- ESC: clear all selections ----------------
    def clear_all_selections(self):
        self._selected_edge_ids = []
        self._clear_selected_overlay()

        self._polyline_clear_picked_style()

        self._tree_unhighlight()
        try:
            self.tree.clearSelection()
        except Exception:
            pass

        ctx = self._get_ctx()
        if ctx is not None:
            try:
                ctx.ClearSelected(True)
            except Exception:
                try:
                    ctx.ClearSelected()
                except Exception:
                    pass
            try:
                ctx.RemoveAllSelected(True)
            except Exception:
                pass
            try:
                ctx.UpdateCurrentViewer()
            except Exception:
                pass

        self.statusBar().showMessage("ESC: all selections cleared.")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clear_all_selections()
            event.accept()
            return
        super().keyPressEvent(event)

    # ---------------- Selected edge overlay ----------------
    def _clear_selected_overlay(self):
        ctx = self._get_ctx()
        if ctx is None:
            self._selected_ais.clear()
            return
        for _, ais in list(self._selected_ais.items()):
            try:
                ctx.Remove(ais, True)
            except Exception:
                try:
                    ctx.Remove(ais, False)
                except Exception:
                    pass
        self._selected_ais.clear()
        try:
            ctx.UpdateCurrentViewer()
        except Exception:
            pass

    def _display_selected_edge_overlay(self, eid: int):
        if eid in self._selected_ais:
            return
        if self._current_shape is None or not self._edge_list:
            return
        if not (0 <= eid < len(self._edge_list)):
            return

        ctx = self._get_ctx()
        if ctx is None:
            return

        ais = AIS_Shape(self._edge_list[eid])
        try:
            r, g, b = self._selected_color
            ais.SetColor(Quantity_Color(float(r), float(g), float(b), Quantity_TOC_RGB))
        except Exception:
            pass

        ctx.Display(ais, False)
        self._selected_ais[eid] = ais
        try:
            ctx.UpdateCurrentViewer()
        except Exception:
            pass

    def _remove_selected_edge_overlay(self, eid: int):
        ctx = self._get_ctx()
        if ctx is None:
            self._selected_ais.pop(eid, None)
            return
        ais = self._selected_ais.pop(eid, None)
        if ais is None:
            return
        try:
            ctx.Remove(ais, True)
        except Exception:
            try:
                ctx.Remove(ais, False)
            except Exception:
                pass
        try:
            ctx.UpdateCurrentViewer()
        except Exception:
            pass

    # ---------------- Hide/Show helpers ----------------
    def _set_ais_visible(self, ais_obj, visible: bool):
        ctx = self._get_ctx()
        if ctx is None or ais_obj is None:
            return
        try:
            if visible:
                ctx.Display(ais_obj, False)
            else:
                ctx.Erase(ais_obj, False)
            ctx.UpdateCurrentViewer()
        except Exception:
            try:
                if visible:
                    ctx.Display(ais_obj, True)
                else:
                    ctx.Erase(ais_obj, True)
            except Exception:
                pass

    def _display_model(self, shape):
        ctx = self._get_ctx()
        if ctx is None:
            return
        if self._model_ais is not None:
            try:
                ctx.Remove(self._model_ais, True)
            except Exception:
                try:
                    ctx.Remove(self._model_ais, False)
                except Exception:
                    pass
            self._model_ais = None

        ais = AIS_Shape(shape)
        ctx.Display(ais, True)
        self._model_ais = ais

    def _clear_all_polylines_display(self):
        ctx = self._get_ctx()
        if ctx is None:
            self._polyline_ais.clear()
            return
        for _, ais in list(self._polyline_ais.items()):
            try:
                ctx.Remove(ais, True)
            except Exception:
                try:
                    ctx.Remove(ais, False)
                except Exception:
                    pass
        self._polyline_ais.clear()
        try:
            ctx.UpdateCurrentViewer()
        except Exception:
            pass

    # ---------------- Tree highlight helpers ----------------
    def _tree_unhighlight(self):
        ctx = self._get_ctx()
        if ctx is None:
            self._tree_highlight_ais = None
            self._tree_highlight_kind = None
            return
        if self._tree_highlight_ais is None:
            return
        try:
            ctx.Unhilight(self._tree_highlight_ais, True)
        except Exception:
            try:
                ctx.Unhilight(self._tree_highlight_ais)
            except Exception:
                pass
        self._tree_highlight_ais = None
        self._tree_highlight_kind = None
        try:
            ctx.UpdateCurrentViewer()
        except Exception:
            pass

    def _tree_highlight(self, ais_obj, kind: str):
        ctx = self._get_ctx()
        if ctx is None or ais_obj is None:
            return

        self._tree_unhighlight()

        col = Quantity_Color(1.0, 1.0, 0.0, Quantity_TOC_RGB) if kind == "MODEL" \
            else Quantity_Color(0.2, 0.4, 1.0, Quantity_TOC_RGB)

        try:
            ctx.HilightWithColor(ais_obj, col, True)
        except Exception:
            try:
                ctx.HilightWithColor(ais_obj, col)
            except Exception:
                try:
                    ctx.Hilight(ais_obj, True)
                except Exception:
                    pass

        self._tree_highlight_ais = ais_obj
        self._tree_highlight_kind = kind
        try:
            ctx.UpdateCurrentViewer()
        except Exception:
            pass

    # ---------------- Polyline picked style helpers ----------------
    def _polyline_set_picked_style(self, name: str):
        if name not in self._polyline_ais:
            return
        self._polyline_clear_picked_style()

        ctx = self._get_ctx()
        if ctx is None:
            return

        ais = self._polyline_ais[name]

        old = {"has_color": False, "color": None}
        try:
            col = ais.Color()
            old["has_color"] = True
            old["color"] = col
        except Exception:
            pass
        self._active_polyline_prev_style[name] = old

        try:
            r, g, b = self._picked_poly_color
            ais.SetColor(Quantity_Color(float(r), float(g), float(b), Quantity_TOC_RGB))
        except Exception:
            pass

        try:
            ais.SetWidth(float(self._picked_poly_width))
        except Exception:
            try:
                drw = ais.Attributes()
                if drw is not None:
                    drw.SetLineWidth(float(self._picked_poly_width))
                    drw.SetLineType(Aspect_TOL_SOLID)
            except Exception:
                pass

        self._active_polyline_name = name
        try:
            ctx.Redisplay(ais, True)
        except Exception:
            try:
                ctx.UpdateCurrentViewer()
            except Exception:
                pass

    def _polyline_clear_picked_style(self):
        if not self._active_polyline_name:
            return
        name = self._active_polyline_name
        self._active_polyline_name = None

        if name not in self._polyline_ais:
            return

        ctx = self._get_ctx()
        if ctx is None:
            return

        ais = self._polyline_ais[name]
        old = self._active_polyline_prev_style.pop(name, None)

        if old:
            try:
                if old.get("has_color") and old.get("color") is not None:
                    ais.SetColor(old["color"])
            except Exception:
                pass

        try:
            ais.SetWidth(1.0)
        except Exception:
            try:
                drw = ais.Attributes()
                if drw is not None:
                    drw.SetLineWidth(1.0)
            except Exception:
                pass

        try:
            ctx.Redisplay(ais, True)
        except Exception:
            try:
                ctx.UpdateCurrentViewer()
            except Exception:
                pass

    # ---------------- EventFilter ----------------
    def eventFilter(self, obj, event):
        if obj is self.viewer:
            # Hover: keep detection updated (this is what your working code did)
            if event.type() == QEvent.MouseMove:
                if self._selection_mode and self._current_shape is not None:
                    self._hover_move_to_debounced(event, 120)

            # Click release: defer capture by 0ms so OCC finishes its internal update
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                QTimer.singleShot(0, self._capture_detected_object_after_click)

                if self._selection_mode and self._current_shape is not None:
                    mods = QApplication.keyboardModifiers()
                    self._last_click_shift = bool(mods & Qt.ShiftModifier)
                    QTimer.singleShot(0, self._capture_detected_edge_after_click)

        # ✅ DO NOT swallow event
        return super().eventFilter(obj, event)

    def _hover_move_to_debounced(self, event, debounce_ms: int = 30):
        self._pending_move_event = event
        if not hasattr(self, "_hover_timer") or self._hover_timer is None:
            self._hover_timer = QTimer(self)
            self._hover_timer.setSingleShot(True)
            self._hover_timer.timeout.connect(self._process_hover_move)
        self._hover_timer.stop()
        self._hover_timer.start(debounce_ms)

    def _process_hover_move(self):
        if not self._selection_mode or self._current_shape is None:
            return
        ctx = self._get_ctx()
        view = self._get_occ_view()
        if ctx is None or view is None:
            return
        event = getattr(self, "_pending_move_event", None)
        if event is None:
            return
        xy = self._qt_to_occ_xy(event)
        if xy is None:
            return
        x, y = xy
        try:
            ctx.MoveTo(x, y, view, True)
        except Exception:
            pass


    def _capture_detected_object_after_click(self):
        ctx = self._get_ctx()
        if ctx is None:
            return
        try:
            if not ctx.HasDetected():
                self._polyline_clear_picked_style()
                return
        except Exception:
            return

        detected_ais = None
        try:
            detected_ais = ctx.DetectedInteractive()
        except Exception:
            detected_ais = None

        if detected_ais is None:
            return

        for name, ais in self._polyline_ais.items():
            if ais == detected_ais:
                self._polyline_set_picked_style(name)
                self.statusBar().showMessage(f"Picked {name} (blue + thick)")
                return

        self._polyline_clear_picked_style()

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
                # Only accept EDGE; otherwise ignore
                try:
                    if shp.ShapeType() != TopAbs_EDGE:
                        return
                except Exception:
                    pass
                picked_edge = topods.Edge(shp)
        except Exception:
            picked_edge = None

        if picked_edge is None:
            return

        eid = None
        for i, e in enumerate(self._edge_list):
            if e.IsSame(picked_edge):
                eid = i
                break
        if eid is None:
            return

        if self._last_click_shift:
            if eid in self._selected_edge_ids:
                self._selected_edge_ids.remove(eid)
                self._remove_selected_edge_overlay(eid)
                self.statusBar().showMessage(f"Removed Edge_{eid:04d} (selected: {len(self._selected_edge_ids)})")
        else:
            if eid not in self._selected_edge_ids:
                self._selected_edge_ids.append(eid)
                self._display_selected_edge_overlay(eid)
                self.statusBar().showMessage(f"Added Edge_{eid:04d} (selected: {len(self._selected_edge_ids)})")

    # ---------------- Tree ----------------
    def build_empty_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()

        root = QTreeWidgetItem(self.tree, ["Model"])
        root.setFlags(root.flags() | Qt.ItemIsUserCheckable)
        root.setCheckState(0, Qt.Checked)
        root.setData(0, Qt.UserRole, ("ROOT", None))

        shapes = QTreeWidgetItem(root, ["Shapes"])
        shapes.setFlags(shapes.flags() | Qt.ItemIsUserCheckable)
        shapes.setCheckState(0, Qt.Checked)
        shapes.setData(0, Qt.UserRole, ("GROUP_SHAPES", None))

        polylines = QTreeWidgetItem(root, ["Polylines"])
        polylines.setFlags(polylines.flags() | Qt.ItemIsUserCheckable)
        polylines.setCheckState(0, Qt.Checked)
        polylines.setData(0, Qt.UserRole, ("GROUP_POLYLINES", None))

        self.tree.expandAll()
        self.tree.blockSignals(False)

    def set_tree_for_step(self, file_path: str, edge_count: int):
        self.tree.blockSignals(True)
        self.tree.clear()

        root = QTreeWidgetItem(self.tree, ["Model"])
        root.setFlags(root.flags() | Qt.ItemIsUserCheckable)
        root.setCheckState(0, Qt.Checked)
        root.setData(0, Qt.UserRole, ("ROOT", None))

        shapes = QTreeWidgetItem(root, ["Shapes"])
        shapes.setFlags(shapes.flags() | Qt.ItemIsUserCheckable)
        shapes.setCheckState(0, Qt.Checked)
        shapes.setData(0, Qt.UserRole, ("GROUP_SHAPES", None))

        step_node = QTreeWidgetItem(shapes, [Path(file_path).name])
        step_node.setData(0, Qt.UserRole, ("STEP_MODEL", "MODEL"))
        step_node.setFlags(step_node.flags() | Qt.ItemIsUserCheckable)
        step_node.setCheckState(0, Qt.Checked)

        edges_info = QTreeWidgetItem(step_node, [f"Edges: {edge_count}"])
        edges_info.setData(0, Qt.UserRole, ("INFO", None))
        edges_info.setFlags(edges_info.flags() & ~Qt.ItemIsUserCheckable)

        polylines = QTreeWidgetItem(root, ["Polylines"])
        polylines.setData(0, Qt.UserRole, ("GROUP_POLYLINES", None))
        polylines.setFlags(polylines.flags() | Qt.ItemIsUserCheckable)
        polylines.setCheckState(0, Qt.Checked)

        for name, edge_ids in self._polylines.items():
            pnode = QTreeWidgetItem(polylines, [name])
            pnode.setData(0, Qt.UserRole, ("POLYLINE", name))
            pnode.setFlags(pnode.flags() | Qt.ItemIsUserCheckable)
            pnode.setCheckState(0, Qt.Checked)

            for eid in edge_ids:
                enode = QTreeWidgetItem(pnode, [f"Edge_{eid:04d}"])
                enode.setData(0, Qt.UserRole, ("EDGE_REF", eid))
                enode.setFlags(enode.flags() & ~Qt.ItemIsUserCheckable)

        self.tree.expandAll()
        self.tree.blockSignals(False)

    def on_tree_item_changed(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        kind, key = data
        visible = (item.checkState(0) == Qt.Checked)

        if kind == "STEP_MODEL" and key == "MODEL":
            self._set_ais_visible(self._model_ais, visible)
            return

        if kind == "POLYLINE" and isinstance(key, str):
            ais = self._polyline_ais.get(key)
            self._set_ais_visible(ais, visible)
            return

        if kind == "GROUP_SHAPES":
            self._set_ais_visible(self._model_ais, visible)
            return

        if kind == "GROUP_POLYLINES":
            for _, ais in self._polyline_ais.items():
                self._set_ais_visible(ais, visible)
            return

    def on_tree_selection_changed(self):
        selected_items = self.tree.selectedItems()
        if not selected_items:
            self._tree_unhighlight()
            return

        item = selected_items[0]
        data = item.data(0, Qt.UserRole)
        if not data:
            self._tree_unhighlight()
            return

        kind, key = data

        if kind == "STEP_MODEL" and key == "MODEL":
            self._tree_highlight(self._model_ais, "MODEL")
            return

        if kind == "POLYLINE" and isinstance(key, str):
            self._tree_highlight(self._polyline_ais.get(key), "POLYLINE")
            return

        self._tree_unhighlight()

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
            self._clear_selected_overlay()
            self._force_edge_selection_mode()
            self.statusBar().showMessage(
                "Polyline selection: Hover highlights edge; Click selects (deferred). SHIFT+Click removes. Then OK."
            )
        else:
            if hasattr(self, "_hover_timer") and self._hover_timer is not None:
                self._hover_timer.stop()
            self._pending_move_event = None
            self._selected_edge_ids = []
            self._clear_selected_overlay()
            self.statusBar().showMessage("Selection mode off.")

    def cancel_polyline_selection(self):
        self._selected_edge_ids = []
        self._clear_selected_overlay()
        self.statusBar().showMessage("Polyline selection cleared.")

    def _build_compound_from_edge_ids(self, edge_ids):
        comp = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(comp)
        for eid in edge_ids:
            if 0 <= eid < len(self._edge_list):
                builder.Add(comp, self._edge_list[eid])
        return comp

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

        ctx = self._get_ctx()
        if ctx is not None:
            comp = self._build_compound_from_edge_ids(self._selected_edge_ids)
            ais = AIS_Shape(comp)
            ctx.Display(ais, False)
            self._polyline_ais[name] = ais
            try:
                ctx.UpdateCurrentViewer()
            except Exception:
                pass

        if self._current_step_path:
            self.set_tree_for_step(self._current_step_path, len(self._edge_list))

        self._selected_edge_ids = []
        self._clear_selected_overlay()
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
            self._current_step_path = file_path

            self.clear_all_selections()

            self._polylines.clear()
            self._polyline_counter = 0
            self._clear_all_polylines_display()

            self.rebuild_edge_index()
            edge_count = len(self._edge_list)

            self.viewer._display.EraseAll()
            self._display_model(shape)
            self.viewer._display.FitAll()

            if self._selection_mode:
                self._force_edge_selection_mode()

            self.set_tree_for_step(file_path, edge_count)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open STEP:\n{e}")


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    splash = None
    splash_path = Path(__file__).resolve().parents[2] / "assets" / "splash.png"
    if splash_path.is_file():
        pixmap = QPixmap(str(splash_path))
        if not pixmap.isNull():
            splash = QSplashScreen(pixmap)
            splash.show()
            app.processEvents()
    if splash is None:
        w.showMaximized()
    else:
        def _show_main():
            splash.finish(w)
            w.showMaximized()
        QTimer.singleShot(5000, _show_main)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
