"""WildTree entry point.

Usage:
    python main.py [cards_dir]

If cards_dir is provided, the viewer opens with that directory pre-loaded.
If omitted, the user can select a directory via the Browse button.

Example:
    python main.py "C:/path/to/sd-dynamic-prompts/wildcards/cards"
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from gui.app import WildTreeWindow


def main() -> None:
    """Application entry point.

    Parses the optional cards_dir argument from sys.argv,
    creates QApplication and WildTreeWindow, and starts the event loop.
    """
    # オプションの cards_dir 引数を解析
    cards_dir: Path | None = None
    if len(sys.argv) > 1:
        cards_dir = Path(sys.argv[1])

    app = QApplication([sys.argv[0]])
    window = WildTreeWindow(cards_dir=cards_dir)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
