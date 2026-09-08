#!/usr/bin/env python3
"""
GOD SWARM COMMAND CENTER — V2
Autonomous Tool-Using Recursive Swarm

Run:
    pip install -r requirements.txt
    python app.py

See README.md for model placement, the tool-registry sandbox, and
what changed from V1.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication

from config import MODEL_DIR, WORKSPACE_DIR
from ui.main_window import MainWindow


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
