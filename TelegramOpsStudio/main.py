import sys
from PySide6.QtWidgets import QApplication
from app.ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Telegram Ops Studio")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
