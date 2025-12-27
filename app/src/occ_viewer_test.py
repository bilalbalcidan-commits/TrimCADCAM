import sys
from PySide6.QtWidgets import QApplication, QMainWindow

from OCC.Display.backend import load_backend
# Önce backend'i seç
load_backend("pyside6")

# Sonra qtDisplay import et (sıra önemli)
from OCC.Display.qtDisplay import qtViewer3d


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TrimCADCAM - OCC Viewer Test")
        self.resize(1200, 800)

        self.viewer = qtViewer3d(self)
        self.setCentralWidget(self.viewer)

        self.viewer.InitDriver()
        self.viewer._display.View_Iso()
        self.viewer._display.FitAll()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
