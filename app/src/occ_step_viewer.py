import sys
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QFileDialog,
    QMessageBox,
    QMenu,
    QInputDialog,
    QColorDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
    QToolBar,
    QSplashScreen,
)
from PySide6.QtGui import QAction, QPixmap, QColor, QShortcut, QKeySequence

from OCC.Display.backend import load_backend
load_backend("pyside6")
from OCC.Display.qtDisplay import qtViewer3d

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_SOLID
from OCC.Core.TopoDS import topods

from OCC.Core.AIS import AIS_Shape
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCC.Core.Prs3d import Prs3d_Drawer

from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopoDS import TopoDS_Compound

from OCC.Core.Aspect import Aspect_TOL_SOLID, Aspect_TOTP_LEFT_LOWER
from OCC.Core.V3d import V3d_ZBUFFER

# ============================================================
# VIEW TOOLBAR (Icon'lu) – R0-working uyumlu
# ============================================================

from PySide6.QtCore import Qt, QSize, QByteArray, QObject, QEvent, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QGraphicsDropShadowEffect
from PySide6.QtSvg import QSvgRenderer

from OCC.Core.gp import gp_Dir


def _svg_icon(svg: str, size: int = 20) -> QIcon:
    # Force a stable stroke color (no currentColor / palette effects)
    stable_svg = svg.replace('stroke="currentColor"', 'stroke="#E6E6E6"')

    data = QByteArray(stable_svg.encode("utf-8"))
    renderer = QSvgRenderer(data)

    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)

    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()

    icon = QIcon()
    # Use the SAME pixmap for different states to avoid hover/active tinting
    icon.addPixmap(pix, QIcon.Normal, QIcon.Off)
    icon.addPixmap(pix, QIcon.Active, QIcon.Off)
    icon.addPixmap(pix, QIcon.Selected, QIcon.Off)
    icon.addPixmap(pix, QIcon.Normal, QIcon.On)
    icon.addPixmap(pix, QIcon.Active, QIcon.On)
    icon.addPixmap(pix, QIcon.Selected, QIcon.On)
    return icon


# ---------- SVG ICONS ----------
_ICON_CUBE_TOP = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">
  <path d="M12 2l9 5-9 5-9-5 9-5z"/>
  <path d="M3 7v10l9 5 9-5V7"/>
  <path d="M12 12v10"/>
  <path d="M3 7l9 5 9-5"/>
  <polygon points="12,2 21,7 12,12 3,7" fill="#1fb6c9" stroke="none" opacity="0.85"/>
</svg>"""

_ICON_CUBE_BOTTOM = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">
  <path d="M12 2l9 5-9 5-9-5 9-5z"/>
  <path d="M3 7v10l9 5 9-5V7"/>
  <path d="M12 12v10"/>
  <path d="M3 7l9 5 9-5"/>
  <polygon points="3,17 12,22 21,17 12,12" fill="#1fb6c9" stroke="none" opacity="0.85"/>
</svg>"""

_ICON_CUBE_LEFT = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">
  <path d="M12 2l9 5-9 5-9-5 9-5z"/>
  <path d="M3 7v10l9 5 9-5V7"/>
  <path d="M12 12v10"/>
  <path d="M3 7l9 5 9-5"/>
  <polygon points="3,7 12,12 12,22 3,17" fill="#1fb6c9" stroke="none" opacity="0.85"/>
</svg>"""

_ICON_CUBE_RIGHT = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">
  <path d="M12 2l9 5-9 5-9-5 9-5z"/>
  <path d="M3 7v10l9 5 9-5V7"/>
  <path d="M12 12v10"/>
  <path d="M3 7l9 5 9-5"/>
  <polygon points="21,7 12,12 12,22 21,17" fill="#1fb6c9" stroke="none" opacity="0.85"/>
</svg>"""

_ICON_CUBE_FRONT = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">
  <path d="M12 2l9 5-9 5-9-5 9-5z"/>
  <path d="M3 7v10l9 5 9-5V7"/>
  <path d="M12 12v10"/>
  <path d="M3 7l9 5 9-5"/>
  <!-- near/front face (choose left face as the prominent face) -->
  <polygon points="3,7 12,12 12,22 3,17" fill="#1fb6c9" stroke="none" opacity="0.85"/>
</svg>"""

_ICON_CUBE_BACK = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">
  <path d="M12 2l9 5-9 5-9-5 9-5z"/>
  <path d="M3 7v10l9 5 9-5V7"/>
  <path d="M12 12v10"/>
  <path d="M3 7l9 5 9-5"/>
  <!-- far/back face (use right face but more subtle) -->
  <polygon points="21,7 12,12 12,22 21,17" fill="#1fb6c9" stroke="none" opacity="0.40"/>
</svg>"""

_ICON_CUBE_ISO = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">
  <path d="M12 2l9 5-9 5-9-5 9-5z"/>
  <path d="M3 7v10l9 5 9-5V7"/>
  <path d="M12 12v10"/>
  <path d="M3 7l9 5 9-5"/>
  <polygon points="12,2 21,7 12,12 3,7" fill="#1fb6c9" stroke="none" opacity="0.35"/>
  <polygon points="3,7 12,12 12,22 3,17" fill="#1fb6c9" stroke="none" opacity="0.60"/>
  <polygon points="21,7 12,12 12,22 21,17" fill="#1fb6c9" stroke="none" opacity="0.85"/>
</svg>"""


class _ViewToolbar(QWidget):
    def __init__(self, parent, set_view_cb):
        super().__init__(parent)
        self._set_view = set_view_cb

        self.setObjectName("viewToolbar")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        items = [
            ("Top",    _ICON_CUBE_TOP,    (0,  0, -1)),  # face normal (0,0,+1) -> view -Z
            ("Bottom", _ICON_CUBE_BOTTOM, (0,  0,  1)),  # face normal (0,0,-1) -> view +Z
            ("Right",  _ICON_CUBE_RIGHT,  (-1, 0,  0)),  # face normal (+1,0,0) -> view -X
            ("Left",   _ICON_CUBE_LEFT,   (1,  0,  0)),  # face normal (-1,0,0) -> view +X
            ("Front",  _ICON_CUBE_FRONT,  (0, -1,  0)),  # face normal (0,+1,0) -> view -Y
            ("Back",   _ICON_CUBE_BACK,   (0,  1,  0)),  # face normal (0,-1,0) -> view +Y
            ("Iso",    _ICON_CUBE_ISO,    (-1, -1, -1)), # recommended CAD-like iso (top/front/right)
        ]

        for tip, svg, direction in items:
            btn = QToolButton(self)
            btn.setToolTip(tip)
            btn.setIcon(_svg_icon(svg))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(40, 40)
            btn.setAutoRaise(True)
            btn.clicked.connect(lambda _, d=direction: self._set_view(d))
            layout.addWidget(btn)

        layout.addStretch()

        self.setStyleSheet("""
        QWidget#viewToolbar {
            background: rgba(20, 20, 20, 170);
            border: 1px solid rgba(255,255,255,50);
            border-radius: 12px;
        }
        QToolButton {
            border-radius: 10px;
            padding: 2px;
        }
        QToolButton:hover {
            background: rgba(255,255,255,30);
        }
        QToolButton:pressed {
            background: rgba(255,255,255,45);
        }
        """)

        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(18)
        effect.setOffset(0, 3)
        effect.setColor(Qt.black)
        self.setGraphicsEffect(effect)


class ViewToolbarController(QObject):
    def __init__(self, viewer_widget, get_view):
        super().__init__(viewer_widget)
        self.viewer_widget = viewer_widget
        self.get_view = get_view

        self.toolbar = _ViewToolbar(viewer_widget, self._set_view)
        self.toolbar.show()
        QTimer.singleShot(0, self._post_show_fix)

        viewer_widget.installEventFilter(self)
        self._place()

    def eventFilter(self, obj, event):
        if obj is self.viewer_widget and event.type() in (QEvent.Resize, QEvent.Show):
            self._place()
        return False

    def _place(self):
        m = 12
        w, h = self.viewer_widget.width(), self.viewer_widget.height()
        tw, th = self.toolbar.sizeHint().width(), self.toolbar.sizeHint().height()
        self.toolbar.move(w - tw - m, h - th - m)

    def _post_show_fix(self):
        try:
            self._place()
            self.toolbar.raise_()
            self.toolbar.updateGeometry()
            self.toolbar.repaint()
            # repaint the parent too (helps on OpenGL widgets)
            self.viewer_widget.repaint()
        except Exception:
            pass

    def _set_view(self, direction):
        view = self.get_view()
        if not view:
            return

        x, y, z = direction

        # 1) Set projection (view direction)
        view.SetProj(float(x), float(y), float(z))

        # 2) Set a canonical UP vector to remove roll/twist relative to world axes
        #    Convention:
        #    - For Top/Bottom views: screen up should be +Y (forward)
        #    - For Front/Back/Left/Right: screen up should be +Z (up)
        if abs(z) > 0.5:
            up = (0.0, 1.0, 0.0)   # Top/Bottom
        else:
            up = (0.0, 0.0, 1.0)   # Side views

        # Some pythonOCC versions accept gp_Dir, some accept floats.
        # Try gp_Dir first, fallback to floats.
        try:
            view.SetUp(gp_Dir(*up))
        except Exception:
            view.SetUp(float(up[0]), float(up[1]), float(up[2]))

        # 3) If Twist is available, reset it to zero (strongest roll reset)
        try:
            view.SetTwist(0.0)
        except Exception:
            pass

        # 4) Fit + redraw
        view.FitAll()
        view.Redraw()

# ======================= END =======================


def load_step(step_path: str):
    reader = STEPControl_Reader()
    status = reader.ReadFile(step_path)
    if status != IFSelect_RetDone:
        raise RuntimeError("STEP read failed")
    reader.TransferRoots()
    return reader.OneShape()

def load_step_assembly(step_path: str):
    reader = STEPControl_Reader()
    status = reader.ReadFile(step_path)
    if status != IFSelect_RetDone:
        raise RuntimeError("STEP read failed")

    parts = []
    comp = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(comp)

    root_count = 0
    try:
        root_count = int(reader.NbRootsForTransfer())
    except Exception:
        root_count = 0

    for i in range(1, root_count + 1):
        try:
            reader.TransferRoot(i)
        except Exception:
            continue
        shp = None
        try:
            shp = reader.Shape(i)
        except Exception:
            shp = None
        if shp is None:
            continue
        try:
            if shp.IsNull():
                continue
        except Exception:
            pass
        name = f"Part_{i:03d}"
        parts.append({"name": name, "shape": shp})
        try:
            builder.Add(comp, shp)
        except Exception:
            pass

    if len(parts) <= 1:
        return None, []

    return comp, parts

def _extract_solids(shape):
    solids = []
    try:
        exp = TopExp_Explorer(shape, TopAbs_SOLID)
    except Exception:
        return solids
    while exp.More():
        s = exp.Current()
        try:
            if s is None or s.IsNull():
                exp.Next()
                continue
        except Exception:
            pass
        solids.append(s)
        exp.Next()
    return solids


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
        self._assembly_parts = []

        self._last_click_shift = False

        # Selected edges overlay (persistent)
        self._selected_ais = {}
        self._selected_color = (0.0, 1.0, 0.0)

        # View mode: 0=SHADED_CLEAN, 1=WIREFRAME
        self._view_mode = 0
        self._view_shortcut = QShortcut(QKeySequence("H"), self)
        self._view_shortcut.setAutoRepeat(False)
        self._view_shortcut.activated.connect(self._toggle_view_mode)

        # HLR debounce timer
        self._hlr_timer = QTimer(self)
        self._hlr_timer.setSingleShot(True)
        self._hlr_timer.setInterval(120)
        self._hlr_timer.timeout.connect(self._rebuild_hlr_overlay)

        # Displayed objects (hide/show)
        self._model_ais = None
        self._polyline_ais = {}  # name -> AIS_Shape
        self._assembly_ais = {}  # part name -> AIS_Shape
        self._assembly_edges_ais = {}  # part name -> AIS_Shape (wireframe overlay)

        # Tree highlight (temporary)
        self._tree_highlight_ais = None
        self._tree_highlight_kind = None
        self._tree_updating_checks = False

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
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)

        self.viewer = qtViewer3d(self)
        self.viewer.InitDriver()
        self.viewer.setFocusPolicy(Qt.StrongFocus)

        try:
            from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB

            ctx = self.viewer._display.Context
            drawer = ctx.DefaultDrawer()

            # Enable shaded with edges globally
            drawer.SetFaceBoundaryDraw(True)

            # Edge color (soft dark gray)
            edge_col = Quantity_Color(0.1, 0.1, 0.1, Quantity_TOC_RGB)

            drawer.SetFaceBoundaryAspect(
                edge_col,
                1.0,   # thin line
                True
            )

        except Exception:
            pass

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

        # --- View toolbar (bottom-right overlay) ---
        try:
            # Use the actual OCC canvas widget as parent (most reliable)
            parent_widget = getattr(self, "viewer", None)
            if parent_widget is None:
                parent_widget = self  # fallback

            # Create controller
            self._view_toolbar_ctrl = ViewToolbarController(
                parent_widget,
                lambda: self.viewer._display.View,
                self._schedule_hlr_rebuild,
            )

            # Force visibility and top stacking
            self._view_toolbar_ctrl.toolbar.setVisible(True)
            self._view_toolbar_ctrl.toolbar.raise_()
            self._view_toolbar_ctrl.toolbar.repaint()
            self._view_toolbar_ctrl._place()

            print("[ViewToolbar] created. parent =", type(parent_widget), "size =", parent_widget.size())

        except Exception as e:
            self._view_toolbar_ctrl = None
            print("[ViewToolbar] FAILED:", repr(e))

        # Corner XYZ trihedron (view decoration)
        try:
            self.viewer._display.View.TriedronDisplay(
                Aspect_TOTP_LEFT_LOWER, Quantity_Color(), 0.08, V3d_ZBUFFER
            )
        except Exception:
            pass

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

    def _apply_catia_shaded_style(self, ais_obj):
        if ais_obj is None:
            return

        try:
            if hasattr(ais_obj, "HasOwnAttributes"):
                if not ais_obj.HasOwnAttributes():
                    try:
                        ais_obj.SetAttributes(Prs3d_Drawer())
                    except Exception:
                        try:
                            ais_obj.SetOwnDrawer(Prs3d_Drawer())
                        except Exception:
                            pass
            elif hasattr(ais_obj, "HasOwnDrawer"):
                if not ais_obj.HasOwnDrawer():
                    try:
                        ais_obj.SetOwnDrawer(Prs3d_Drawer())
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            drawer = ais_obj.Attributes()
        except Exception:
            drawer = None

        if drawer is None:
            return

        try:
            drawer.SetFaceBoundaryDraw(True)
        except Exception:
            pass

        try:
            edge_col = Quantity_Color(0.15, 0.15, 0.15, Quantity_TOC_RGB)
            try:
                drawer.SetFaceBoundaryAspect(edge_col, 1.0, True)
            except Exception:
                try:
                    from OCC.Core.Prs3d import Prs3d_LineAspect
                    line_aspect = Prs3d_LineAspect(edge_col, Aspect_TOL_SOLID, 1.0)
                    drawer.SetFaceBoundaryAspect(line_aspect)
                except Exception:
                    pass
        except Exception:
            pass

        if int(getattr(self, "_view_mode", 0)) == 0:
            ctx = self._get_ctx()
            if ctx is not None:
                try:
                    ctx.SetDisplayMode(ais_obj, 1, False)
                except Exception:
                    pass

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
        self._clear_assembly_display()
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
        self._apply_catia_shaded_style(ais)
        self._model_ais = ais

    def _clear_assembly_display(self):
        ctx = self._get_ctx()
        if ctx is None:
            self._assembly_ais.clear()
            self._assembly_edges_ais.clear()
            return
        for _, ais in list(self._assembly_ais.items()):
            try:
                ctx.Remove(ais, True)
            except Exception:
                try:
                    ctx.Remove(ais, False)
                except Exception:
                    pass
        for _, ais in list(self._assembly_edges_ais.items()):
            try:
                ctx.Remove(ais, True)
            except Exception:
                try:
                    ctx.Remove(ais, False)
                except Exception:
                    pass
        self._assembly_ais.clear()
        self._assembly_edges_ais.clear()
        try:
            ctx.UpdateCurrentViewer()
        except Exception:
            pass
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
                self._schedule_hlr_rebuild()

            if event.type() == QEvent.MouseButtonRelease and event.button() != Qt.LeftButton:
                self._schedule_hlr_rebuild()

            if event.type() == QEvent.Wheel:
                self._schedule_hlr_rebuild()

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

    def set_tree_for_assembly(self, file_path: str, parts):
        self.tree.blockSignals(True)
        self.tree.clear()

        root = QTreeWidgetItem(self.tree, ["Assembly"])
        root.setFlags(root.flags() | Qt.ItemIsUserCheckable)
        root.setCheckState(0, Qt.Checked)
        root.setData(0, Qt.UserRole, ("ROOT", None))

        shapes = QTreeWidgetItem(root, [Path(file_path).name])
        shapes.setFlags(shapes.flags() | Qt.ItemIsUserCheckable)
        shapes.setCheckState(0, Qt.Checked)
        shapes.setData(0, Qt.UserRole, ("GROUP_SHAPES", None))

        file_name_norm = Path(file_path).name.strip().casefold()
        for idx, part in enumerate(parts):
            # Defensive: part may be a tuple like (key, dict)
            if isinstance(part, tuple):
                if len(part) >= 2 and isinstance(part[1], dict):
                    part = part[1]
                elif len(part) >= 1 and isinstance(part[0], dict):
                    part = part[0]
            name = part.get("name") or f"Part_{idx + 1:03d}"
            name_norm = str(name).strip().casefold()
            if name_norm == file_name_norm:
                continue
            pnode = QTreeWidgetItem(shapes, [name])
            shape = part.get("shape")
            ais = self._assembly_ais.get(name)
            ais_edges = self._assembly_edges_ais.get(name)
            pnode.setData(
                0,
                Qt.UserRole,
                {
                    "kind": "STEP_PART",
                    "key": name,
                    "id": idx,
                    "shape": shape,
                    "ais": ais,
                    "ais_edges": ais_edges,
                    "ais_hlr": None,
                },
            )
            pnode.setFlags(pnode.flags() | Qt.ItemIsUserCheckable)
            pnode.setCheckState(0, Qt.Checked)

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
        if self._tree_updating_checks:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        if isinstance(data, dict):
            kind = data.get("kind")
            key = data.get("key")
        else:
            kind, key = data
        visible = (item.checkState(0) == Qt.Checked)

        if kind in ("ROOT", "GROUP_SHAPES"):
            self._tree_updating_checks = True
            try:
                for i in range(item.childCount()):
                    child = item.child(i)
                    child.setCheckState(0, Qt.Checked if visible else Qt.Unchecked)
            finally:
                self._tree_updating_checks = False
            try:
                ctx = self._get_ctx()
                if ctx is not None:
                    for _, ais in self._assembly_ais.items():
                        if visible:
                            ctx.Display(ais, False)
                        else:
                            ctx.Remove(ais, False)
                    for _, ais in self._assembly_edges_ais.items():
                        if visible:
                            ctx.Display(ais, False)
                        else:
                            ctx.Remove(ais, False)
                    for it in self._iter_tree_items(item):
                        payload = None
                        try:
                            payload = it.data(0, Qt.UserRole)
                        except Exception:
                            payload = None
                        if isinstance(payload, dict):
                            ais_hlr = payload.get("ais_hlr")
                            if ais_hlr is not None:
                                if visible and int(getattr(self, "_view_mode", 0)) == 0:
                                    ctx.Display(ais_hlr, False)
                                else:
                                    ctx.Remove(ais_hlr, False)
                    ctx.UpdateCurrentViewer()
            except Exception:
                pass
            return

        if kind == "STEP_MODEL" and key == "MODEL":
            self._set_ais_visible(self._model_ais, visible)
            return

        if kind == "POLYLINE" and isinstance(key, str):
            ais = self._polyline_ais.get(key)
            self._set_ais_visible(ais, visible)
            return
        if kind == "STEP_PART" and isinstance(key, str):
            ais = self._assembly_ais.get(key)
            ais_edges = self._assembly_edges_ais.get(key)
            ais_hlr = None
            try:
                payload = item.data(0, Qt.UserRole)
                if isinstance(payload, dict):
                    ais_hlr = payload.get("ais_hlr")
            except Exception:
                pass
            try:
                ctx = self._get_ctx()
                if ctx is not None:
                    if ais is not None:
                        if visible:
                            ctx.Display(ais, False)
                        else:
                            ctx.Remove(ais, False)
                    if ais_edges is not None:
                        if visible:
                            ctx.Display(ais_edges, False)
                        else:
                            ctx.Remove(ais_edges, False)
                    if ais_hlr is not None:
                        if visible and int(getattr(self, "_view_mode", 0)) == 0:
                            ctx.Display(ais_hlr, False)
                        else:
                            ctx.Remove(ais_hlr, False)
                    ctx.UpdateCurrentViewer()
            except Exception:
                pass
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

        if isinstance(data, dict):
            kind = data.get("kind")
            key = data.get("key")
        else:
            kind, key = data

        if kind == "STEP_MODEL" and key == "MODEL":
            self._tree_highlight(self._model_ais, "MODEL")
            return

        if kind == "POLYLINE" and isinstance(key, str):
            self._tree_highlight(self._polyline_ais.get(key), "POLYLINE")
            return

        self._tree_unhighlight()

    def _on_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return

        locked = {"Assembly", "Polylines"}
        if item.text(0) in locked:
            return

        menu = QMenu(self.tree)
        act_rename = menu.addAction("Rename")
        act_delete = menu.addAction("Delete")
        act_duplicate = menu.addAction("Duplicate")
        act_color = menu.addAction("Color")
        act_props = menu.addAction("Properties")

        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if action == act_rename:
            self._rename_tree_item(item)
        elif action == act_delete:
            self._delete_tree_item(item)
        elif action == act_duplicate:
            self._duplicate_tree_item(item)
        elif action == act_color:
            self._color_tree_item(item)
        elif action == act_props:
            self._show_tree_item_properties(item)

    def _rename_tree_item(self, item):
        old = item.text(0)
        new, ok = QInputDialog.getText(self, "Rename", "New name:", text=old)
        if not ok:
            return

        new = (new or "").strip()
        if not new or new == old:
            return

        unique_new = self._make_unique_sibling_name(item, new)
        if unique_new != new:
            try:
                self.statusBar().showMessage(f"Name already used, renamed to: {unique_new}", 5000)
            except Exception:
                pass
        new = unique_new

        # Change only the visible label; do NOT alter any stable IDs stored in UserRole
        self.tree.blockSignals(True)
        try:
            item.setText(0, new)
        finally:
            self.tree.blockSignals(False)

    def _make_unique_sibling_name(self, item, base_name: str) -> str:
        parent = item.parent()
        if parent is None:
            siblings = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        else:
            siblings = [parent.child(i) for i in range(parent.childCount())]

        existing = {s.text(0) for s in siblings if s is not item}

        if base_name not in existing:
            return base_name

        import re
        m = re.match(r"^(.*)_(\d{3})$", base_name)
        stem = m.group(1) if m else base_name

        for n in range(1, 1000):
            candidate = f"{stem}_{n:03d}"
            if candidate not in existing:
                return candidate

        return f"{stem}_{1000:03d}"

    def _delete_tree_item(self, item):
        try:
            payload = item.data(0, Qt.UserRole)
        except Exception:
            payload = None
        if isinstance(payload, dict):
            ais = payload.get("ais")
            ais_edges = payload.get("ais_edges")
            ais_hlr = payload.get("ais_hlr")
            try:
                ctx = self._get_ctx()
                if ctx is not None:
                    if ais is not None:
                        try:
                            ctx.Remove(ais, False)
                        except Exception:
                            pass
                    if ais_edges is not None:
                        try:
                            ctx.Remove(ais_edges, False)
                        except Exception:
                            pass
                    if ais_hlr is not None:
                        try:
                            ctx.Remove(ais_hlr, False)
                        except Exception:
                            pass
                    try:
                        ctx.UpdateCurrentViewer()
                    except Exception:
                        pass
            except Exception:
                pass
        parent = item.parent()
        self.tree.blockSignals(True)
        try:
            if parent is None:
                idx = self.tree.indexOfTopLevelItem(item)
                if idx >= 0:
                    self.tree.takeTopLevelItem(idx)
            else:
                parent.removeChild(item)
        finally:
            self.tree.blockSignals(False)

    def _clone_subtree(self, src_item):
        clone = QTreeWidgetItem()
        clone.setText(0, src_item.text(0))
        for role in (Qt.UserRole,):
            try:
                clone.setData(0, role, src_item.data(0, role))
            except Exception:
                pass
        for i in range(src_item.childCount()):
            clone.addChild(self._clone_subtree(src_item.child(i)))
        return clone

    def _duplicate_tree_item(self, item):
        parent = item.parent()
        clone = self._clone_subtree(item)

        base = item.text(0)
        clone.setText(0, self._make_unique_sibling_name(item, base))

        self.tree.blockSignals(True)
        try:
            if parent is None:
                self.tree.addTopLevelItem(clone)
            else:
                parent.addChild(clone)
            clone.setExpanded(item.isExpanded())
        finally:
            self.tree.blockSignals(False)

    def _color_tree_item(self, item):
        c = QColorDialog.getColor(parent=self, title="Choose color")
        if not c.isValid():
            return

        self.tree.blockSignals(True)
        try:
            item.setData(0, Qt.UserRole + 1, (c.red(), c.green(), c.blue()))
        finally:
            self.tree.blockSignals(False)

        ais = self._resolve_ais_from_tree_item(item)
        if ais is None:
            try:
                self.statusBar().showMessage("No AIS object linked to this tree item (color stored only).", 5000)
            except Exception:
                pass
            return

        from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
        qcol = Quantity_Color(c.redF(), c.greenF(), c.blueF(), Quantity_TOC_RGB)

        try:
            ctx = self.viewer._display.Context
            try:
                ctx.SetColor(ais, qcol, True)
            except Exception:
                ctx.SetColor(ais, qcol, False)
            self._apply_catia_shaded_style(ais)
            try:
                ctx.Redisplay(ais, True)
            except Exception:
                pass
            try:
                ctx.UpdateCurrentViewer()
            except Exception:
                pass

            try:
                # Ensure shaded display mode
                ctx.SetDisplayMode(ais, 1, False)  # 1 = AIS_Shaded

                ctx.Redisplay(ais, True)
                ctx.UpdateCurrentViewer()
            except Exception:
                pass
            return
        except Exception:
            pass

        try:
            ais.SetColor(qcol)
            self._apply_catia_shaded_style(ais)
            try:
                self.viewer._display.Context.UpdateCurrentViewer()
            except Exception:
                pass
        except Exception:
            pass

    def _show_tree_item_properties(self, item):
        name = item.text(0)
        child_count = item.childCount()
        parent_name = item.parent().text(0) if item.parent() else "(top-level)"
        payload = None
        try:
            payload = item.data(0, Qt.UserRole)
        except Exception:
            payload = None

        msg = f"Name: {name}\nParent: {parent_name}\nChildren: {child_count}\nUserRole: {payload!r}"
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Properties", msg)
        except Exception:
            pass

    def _resolve_ais_from_tree_item(self, item):
        try:
            payload = item.data(0, Qt.UserRole)
        except Exception:
            payload = None

        if isinstance(payload, dict):
            for k in ("ais", "ais_handle", "ais_shape", "ais_obj"):
                if k in payload and payload[k] is not None:
                    return payload[k]
            for k in ("id", "shape_id", "ais_id"):
                if k in payload:
                    candidate = payload[k]
                    for attr in ("_ais_by_id", "_ais_map", "_shape_ais_map", "_ais_shapes"):
                        m = getattr(self, attr, None)
                        if isinstance(m, dict) and candidate in m:
                            return m[candidate]

        if payload is not None:
            if hasattr(payload, "SetColor"):
                return payload

        for attr in ("shape_to_ais", "_shape_to_ais", "_ais_map", "_shape_ais_map", "_ais_shapes"):
            m = getattr(self, attr, None)
            if isinstance(m, dict):
                key = item.text(0)
                if key in m:
                    return m[key]

        return None

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
            if len(self._assembly_parts) > 1:
                self.set_tree_for_assembly(self._current_step_path, self._assembly_parts)
            else:
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
            shape = None
            parts = []
            try:
                shape, parts = load_step_assembly(file_path)
            except Exception:
                shape = None
                parts = []
            if shape is None:
                shape = load_step(file_path)
            self._current_shape = shape
            self._current_step_path = file_path
            self._assembly_parts = parts

            self.clear_all_selections()

            self._polylines.clear()
            self._polyline_counter = 0
            self._clear_all_polylines_display()

            self.rebuild_edge_index()
            edge_count = len(self._edge_list)

            self.viewer._display.EraseAll()
            display_shape = shape
            solids_parts = []
            if len(self._assembly_parts) <= 1 and shape is not None:
                solids = _extract_solids(shape)
                if len(solids) > 1:
                    solids_parts = [
                        {"name": f"Part_{i + 1:03d}", "shape": s}
                        for i, s in enumerate(solids)
                    ]
                    self._assembly_parts = solids_parts

            if len(self._assembly_parts) > 1:
                ctx = self._get_ctx()
                if ctx is not None:
                    self._clear_assembly_display()
                    if self._model_ais is not None:
                        try:
                            ctx.Remove(self._model_ais, True)
                        except Exception:
                            try:
                                ctx.Remove(self._model_ais, False)
                            except Exception:
                                pass
                        self._model_ais = None
                    for part in self._assembly_parts:
                        ais_shaded = AIS_Shape(part["shape"])
                        ais_edges = AIS_Shape(part["shape"])
                        ctx.SetDisplayMode(ais_edges, 0, False)  # 0 = Wireframe
                        from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
                        edge_col = Quantity_Color(0.15, 0.15, 0.15, Quantity_TOC_RGB)
                        ctx.SetColor(ais_edges, edge_col, False)
                        ais_edges.SetTransparency(1.0)
                        ctx.Display(ais_shaded, False)
                        ctx.Display(ais_edges, False)
                        self._apply_catia_shaded_style(ais_shaded)
                        self._assembly_ais[part["name"]] = ais_shaded
                        self._assembly_edges_ais[part["name"]] = ais_edges
                    try:
                        ctx.UpdateCurrentViewer()
                    except Exception:
                        pass
            else:
                self._clear_assembly_display()
                self._display_model(display_shape)
            self.viewer._display.FitAll()

            if self._selection_mode:
                self._force_edge_selection_mode()

            if len(self._assembly_parts) > 1:
                self.set_tree_for_assembly(file_path, self._assembly_parts)
            else:
                self._assembly_parts = []
                self.set_tree_for_step(file_path, edge_count)
            self._apply_view_mode()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open STEP:\n{e}")


    def _iter_tree_items(self, root):
        for i in range(root.childCount()):
            ch = root.child(i)
            yield ch
            yield from self._iter_tree_items(ch)

    def _build_hlr_edges_for_shape(self, shape, view):
        from OCC.Core.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
        from OCC.Core.HLRAlgo import HLRAlgo_Projector
        from OCC.Core.gp import gp_Ax2, gp_Pnt, gp_Dir
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeCompound

        cam = None
        try:
            cam = view.Camera()
        except Exception:
            cam = None

        try:
            d = cam.Direction() if cam is not None else gp_Dir(0, 0, -1)
        except Exception:
            d = gp_Dir(0, 0, -1)
        try:
            xdir = cam.XDirection() if cam is not None else gp_Dir(1, 0, 0)
        except Exception:
            xdir = gp_Dir(1, 0, 0)

        ax2 = gp_Ax2(gp_Pnt(0, 0, 0), d, xdir)
        proj = HLRAlgo_Projector(ax2)

        algo = HLRBRep_Algo()
        algo.Add(shape)
        algo.Projector(proj)
        algo.Update()
        algo.Hide()

        hlr = HLRBRep_HLRToShape(algo)
        comp_mk = BRepBuilderAPI_MakeCompound()

        try:
            ve = hlr.VCompound()
            if not ve.IsNull():
                comp_mk.Add(ve)
        except Exception:
            pass

        try:
            outl = hlr.OutLineVCompound()
            if not outl.IsNull():
                comp_mk.Add(outl)
        except Exception:
            pass

        return comp_mk.Compound()

    def _ensure_part_hlr_overlay(self, item):
        payload = item.data(0, Qt.UserRole)
        if not isinstance(payload, dict):
            return
        shape = payload.get("shape")
        if shape is None:
            return

        ctx = self._get_ctx()
        view = self._get_occ_view()
        if ctx is None or view is None:
            return

        edge_shape = self._build_hlr_edges_for_shape(shape, view)
        if edge_shape is None:
            return

        ais_hlr = payload.get("ais_hlr")
        if ais_hlr is not None:
            try:
                ctx.Remove(ais_hlr, False)
            except Exception:
                pass

        ais_hlr = AIS_Shape(edge_shape)
        payload["ais_hlr"] = ais_hlr
        item.setData(0, Qt.UserRole, payload)

        try:
            ctx.SetDisplayMode(ais_hlr, 0, False)
        except Exception:
            pass

        edge_col = Quantity_Color(0.30, 0.30, 0.30, Quantity_TOC_RGB)
        try:
            ctx.SetColor(ais_hlr, edge_col, False)
        except Exception:
            try:
                ais_hlr.SetColor(edge_col)
            except Exception:
                pass

        try:
            ais_hlr.SetWidth(1.0)
        except Exception:
            pass

        if int(getattr(self, "_view_mode", 0)) == 0:
            try:
                ctx.Display(ais_hlr, False)
            except Exception:
                pass

    def _toggle_view_mode(self):
        self._view_mode = 1 - int(getattr(self, "_view_mode", 0))
        try:
            msg = "View mode : shaded" if self._view_mode == 0 else "View mode : wireframe"
            self.statusBar().showMessage(msg, 3000)
        except Exception:
            pass
        self._apply_view_mode()

    def _apply_view_mode(self):
        ctx = self._get_ctx()
        if ctx is None:
            return

        if self._model_ais is not None:
            try:
                ctx.Display(self._model_ais, False)
                ctx.SetDisplayMode(self._model_ais, 1 if self._view_mode == 0 else 0, False)
            except Exception:
                pass

        top = self.tree.invisibleRootItem()
        for it in self._iter_tree_items(top):
            payload = it.data(0, Qt.UserRole)
            if not isinstance(payload, dict):
                continue
            if "ais" not in payload:
                continue

            ais = payload.get("ais")
            ais_edges = payload.get("ais_edges")
            ais_hlr = payload.get("ais_hlr")

            if self._view_mode == 0:
                if ais is not None:
                    try:
                        ctx.Display(ais, False)
                        ctx.SetDisplayMode(ais, 1, False)
                    except Exception:
                        pass
                if ais_edges is not None:
                    try:
                        ctx.Erase(ais_edges, False)
                    except Exception:
                        pass
                if ais_hlr is not None:
                    try:
                        ctx.Display(ais_hlr, False)
                    except Exception:
                        pass
                else:
                    self._schedule_hlr_rebuild()
            else:
                if ais_hlr is not None:
                    try:
                        ctx.Erase(ais_hlr, False)
                    except Exception:
                        pass
                if ais_edges is not None:
                    try:
                        ctx.Display(ais_edges, False)
                    except Exception:
                        pass
                    if ais is not None:
                        try:
                            ctx.Erase(ais, False)
                        except Exception:
                            pass
                elif ais is not None:
                    try:
                        ctx.Display(ais, False)
                        ctx.SetDisplayMode(ais, 0, False)
                    except Exception:
                        pass

        try:
            ctx.UpdateCurrentViewer()
        except Exception:
            pass

    def _schedule_hlr_rebuild(self):
        if int(getattr(self, "_view_mode", 0)) != 0:
            return
        try:
            self._hlr_timer.start()
        except Exception:
            pass

    def _rebuild_hlr_overlay(self):
        if int(getattr(self, "_view_mode", 0)) != 0:
            return

        ctx = self._get_ctx()
        view = self._get_occ_view()
        if ctx is None or view is None:
            return

        top = self.tree.invisibleRootItem()
        for it in self._iter_tree_items(top):
            payload = it.data(0, Qt.UserRole)
            if not isinstance(payload, dict):
                continue
            if not payload.get("shape") or not payload.get("ais"):
                continue

            ais = payload.get("ais")
            ais_hlr = payload.get("ais_hlr")

            try:
                is_disp = ctx.IsDisplayed(ais)
            except Exception:
                is_disp = True

            if not is_disp:
                if ais_hlr is not None:
                    try:
                        ctx.Erase(ais_hlr, False)
                    except Exception:
                        pass
                continue

            self._ensure_part_hlr_overlay(it)

        try:
            ctx.UpdateCurrentViewer()
        except Exception:
            pass

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
