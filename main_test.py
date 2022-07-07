from PyQt5.uic import loadUi
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QMainWindow
import sys
from graphwidget import GraphWidget
from tree_test import RegionTree
from polywidget import PolyWidget


UI_FILE = 'mainwindow_test.ui'


class MainWindow(QMainWindow):
    count = 0

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self._init_ui()

    def _init_ui(self):
        loadUi(UI_FILE, self)
        layout = QHBoxLayout()
        self.groupBox.setLayout(layout)
        # !!!
        customGraphWidget = PolyWidget(self)
        layout.addWidget(customGraphWidget)
        # my_widget = GraphWidget(self)
        # layout.addWidget(my_widget)
        # layout.addWidget(RegionTree(self))


def main():
    app = QApplication(sys.argv)
    ex = MainWindow()
    ex.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
