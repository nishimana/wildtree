"""WildTree main window: QTreeWidget-based wildcard dependency viewer.

Displays the dependency tree of Dynamic Prompts wildcard YAML files.
The GUI depends on core.wildcard_parser for all parsing logic.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.wildcard_parser import (
    TreeNode,
    WildcardResolver,
    build_key_registry,
    build_tree,
    scan_yaml_files,
)


class MainWindow(QMainWindow):
    """Main application window for WildTree.

    Layout:
        +---------------------------------------------------+
        | WildTree                                     [_][X]|
        +---------------------------------------------------+
        | cards: [path display] [Browse...]                  |
        | [entry point selector] v  [Refresh]                |
        +---------------------------------------------------+
        | QTreeWidget      |  QTextEdit (read-only)         |
        | (dependency tree) |  (key definition values)       |
        |                  |                                 |
        +---------------------------------------------------+

    The main area is a QSplitter with left (tree) and right
    (key definition) panes. Selecting a node in the tree
    displays the corresponding key's value lines in the right pane.

    Attributes:
        _cards_dir: Current cards directory path, or None if not set.
        _resolver: Current WildcardResolver instance, or None if
            not yet loaded.
        _combo_entry: QComboBox for selecting the entry point key.
        _tree_widget: QTreeWidget displaying the dependency tree.
        _text_detail: QTextEdit (read-only) showing the selected
            key's definition (raw value lines from YAML).
        _splitter: QSplitter dividing tree and detail panes.
        _label_path: QLabel showing the current cards directory path.
        _btn_browse: QPushButton to open folder selection dialog.
        _btn_refresh: QPushButton to re-scan YAML files and rebuild tree.
    """

    WINDOW_TITLE: str = "WildTree"
    DEFAULT_WIDTH: int = 1000
    DEFAULT_HEIGHT: int = 800
    CIRCULAR_REF_LABEL: str = "(circular ref)"
    SPLITTER_LEFT_RATIO: int = 400
    SPLITTER_RIGHT_RATIO: int = 600
    DETAIL_PLACEHOLDER: str = "(ノードを選択するとキー定義を表示します)"

    # QTreeWidgetItem.setData() で TreeNode.ref_name を格納するロール
    REF_NAME_ROLE: int = Qt.ItemDataRole.UserRole

    def __init__(
        self,
        cards_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the main window.

        Args:
            cards_dir: Initial cards directory path. If None, the user
                must select a directory via the Browse button before
                the tree can be displayed.
            parent: Parent widget (typically None for top-level window).
        """
        super().__init__(parent)
        self._cards_dir: Path | None = cards_dir
        self._resolver: WildcardResolver | None = None

        self._setup_ui()
        self._connect_signals()

        # 初期ディレクトリが指定されている場合は読み込む
        if self._cards_dir is not None:
            self._load_cards_dir()

    def _setup_ui(self) -> None:
        """Create and arrange all UI widgets.

        Called once during __init__. Creates the layout hierarchy:
        - Top bar: cards path label + Browse button
        - Middle bar: entry point combo + Refresh button
        - Main area: QSplitter with QTreeWidget (left) and QTextEdit (right)
        """
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

        # 中央ウィジェットとメインレイアウト
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # --- 上段: cards パス表示 + Browse ボタン ---
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("cards:"))
        self._label_path = QLabel("(未選択)")
        self._label_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        top_bar.addWidget(self._label_path, stretch=1)
        self._btn_browse = QPushButton("Browse...")
        top_bar.addWidget(self._btn_browse)
        main_layout.addLayout(top_bar)

        # --- 中段: エントリポイント選択 + Refresh ボタン ---
        mid_bar = QHBoxLayout()
        self._combo_entry = QComboBox()
        self._combo_entry.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        mid_bar.addWidget(self._combo_entry, stretch=1)
        self._btn_refresh = QPushButton("Refresh")
        mid_bar.addWidget(self._btn_refresh)
        main_layout.addLayout(mid_bar)

        # --- メインエリア: QSplitter (左: ツリー, 右: キー定義) ---
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        self._tree_widget = QTreeWidget()
        self._tree_widget.setHeaderHidden(True)
        self._tree_widget.setColumnCount(1)
        self._splitter.addWidget(self._tree_widget)

        self._text_detail = QTextEdit()
        self._text_detail.setReadOnly(True)
        self._text_detail.setPlainText(self.DETAIL_PLACEHOLDER)
        self._splitter.addWidget(self._text_detail)

        self._splitter.setSizes([self.SPLITTER_LEFT_RATIO, self.SPLITTER_RIGHT_RATIO])
        main_layout.addWidget(self._splitter)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots.

        Connections:
        - _btn_browse.clicked -> _on_browse
        - _btn_refresh.clicked -> _on_refresh
        - _combo_entry.currentTextChanged -> _on_entry_changed
        - _tree_widget.currentItemChanged -> _on_tree_item_selected
        """
        self._btn_browse.clicked.connect(self._on_browse)
        self._btn_refresh.clicked.connect(self._on_refresh)
        self._combo_entry.currentTextChanged.connect(self._on_entry_changed)
        self._tree_widget.currentItemChanged.connect(self._on_tree_item_selected)

    def _on_browse(self) -> None:
        """Handle Browse button click.

        Opens a QFileDialog.getExistingDirectory dialog. If the user
        selects a directory, updates _cards_dir and triggers a full
        reload (scan + tree rebuild).
        """
        directory = QFileDialog.getExistingDirectory(
            self,
            "cards ディレクトリを選択",
            str(self._cards_dir) if self._cards_dir is not None else "",
        )
        if not directory:
            return
        self._cards_dir = Path(directory)
        self._load_cards_dir()

    def _on_refresh(self) -> None:
        """Handle Refresh button click.

        Re-scans the YAML files in _cards_dir and rebuilds the tree
        for the currently selected entry point.
        Does nothing if _cards_dir is None.
        """
        if self._cards_dir is None:
            return
        self._load_cards_dir()

    def _on_entry_changed(self, entry_key: str) -> None:
        """Handle entry point selection change.

        Rebuilds the tree for the newly selected entry key.
        Does nothing if entry_key is empty or _resolver is None.

        Args:
            entry_key: The newly selected key name from the combo box.
        """
        if not entry_key or self._resolver is None:
            return
        self._build_and_display_tree(entry_key)

    def _on_tree_item_selected(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        """Handle tree node selection change.

        Retrieves the ref_name stored in the selected QTreeWidgetItem's
        UserRole data, resolves it to a KeyDefinition via the resolver,
        and displays the key's raw_values in _text_detail.

        If the selected node cannot be resolved (e.g., circular ref marker
        or no resolver), displays an appropriate message or clears the pane.

        The display format is one value per line, preserving the original
        order from the YAML file. The key name is shown as a header.

        Args:
            current: The newly selected QTreeWidgetItem, or None if
                selection was cleared.
            previous: The previously selected QTreeWidgetItem (unused).
        """
        # current が None の場合はプレースホルダに戻す
        if current is None:
            self._text_detail.setPlainText(self.DETAIL_PLACEHOLDER)
            return

        # ref_name を取得（setData 未設定の場合は None）
        ref_name = current.data(0, self.REF_NAME_ROLE)
        if ref_name is None:
            self._text_detail.setPlainText(self.DETAIL_PLACEHOLDER)
            return

        # resolver が未設定の場合はプレースホルダに戻す
        if self._resolver is None:
            self._text_detail.setPlainText(self.DETAIL_PLACEHOLDER)
            return

        # 名前解決してキー定義を取得
        key_def = self._resolver.resolve(ref_name)
        if key_def is None:
            self._text_detail.setPlainText("(キー定義が見つかりません)")
            return

        # キー定義を整形して右ペインに表示
        formatted = self._format_key_definition(key_def.name, key_def.raw_values)
        self._text_detail.setPlainText(formatted)

    def _format_key_definition(self, key_name: str, raw_values: list[str]) -> str:
        """Format a key definition for display in the detail pane.

        Produces a text block with the key name as header followed by
        its value lines, each prefixed with "  - " for readability.

        Args:
            key_name: The key name to display as header.
            raw_values: The list of value lines from KeyDefinition.raw_values.

        Returns:
            Formatted multi-line string for display in QTextEdit.
        """
        # ヘッダ行: キー名 + コロン
        lines = [f"{key_name}:"]
        # 値行: "  - " プレフィックス付きで1行ずつ追加
        for value in raw_values:
            lines.append(f"  - {value}")
        return "\n".join(lines)

    def _load_cards_dir(self) -> None:
        """Scan YAML files and build the resolver.

        Called when _cards_dir changes (via Browse or initial argument).
        Updates:
        1. _label_path text
        2. _resolver (new WildcardResolver from scanned files)
        3. _combo_entry items (all key names from resolver)
        4. Selects default entry point if available

        Does nothing if _cards_dir is None.
        """
        if self._cards_dir is None:
            return

        self._label_path.setText(str(self._cards_dir))

        try:
            yaml_files = scan_yaml_files(self._cards_dir)
        except (FileNotFoundError, NotADirectoryError) as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "エラー", str(e))
            return

        registry = build_key_registry(yaml_files)
        self._resolver = WildcardResolver(registry, self._cards_dir)

        # コンボボックスを更新（シグナル発火を一時的にブロック）
        current_text = self._combo_entry.currentText()
        self._combo_entry.blockSignals(True)
        self._combo_entry.clear()

        all_keys = self._resolver.get_all_key_names()
        self._combo_entry.addItems(all_keys)

        # 以前の選択を維持、なければデフォルト "メイン" を選択
        if current_text and current_text in all_keys:
            self._combo_entry.setCurrentText(current_text)
        elif "メイン" in all_keys:
            self._combo_entry.setCurrentText("メイン")

        self._combo_entry.blockSignals(False)

        # ツリーを構築・表示
        selected = self._combo_entry.currentText()
        if selected:
            self._build_and_display_tree(selected)

    def _build_and_display_tree(self, entry_key: str) -> None:
        """Build tree from entry key and display in QTreeWidget.

        Clears the existing tree widget, calls build_tree() from
        the core module, and populates the QTreeWidget.

        Args:
            entry_key: The key name to use as tree root.
        """
        if self._resolver is None:
            return

        self._tree_widget.clear()
        self._text_detail.setPlainText(self.DETAIL_PLACEHOLDER)

        tree = build_tree(entry_key, self._resolver)

        # ルートアイテムを作成
        display_text = tree.name
        if tree.is_circular:
            display_text = f"{tree.name} {self.CIRCULAR_REF_LABEL}"

        root_item = QTreeWidgetItem([display_text])
        root_item.setData(0, self.REF_NAME_ROLE, tree.ref_name)
        self._tree_widget.addTopLevelItem(root_item)

        # 子ノードを再帰的に追加
        self._populate_tree_item(root_item, tree)

        # ルートを展開
        root_item.setExpanded(True)

    def _populate_tree_item(
        self,
        parent: QTreeWidgetItem,
        node: TreeNode,
    ) -> None:
        """Recursively add TreeNode children to a QTreeWidgetItem.

        For each child node:
        - Creates a QTreeWidgetItem with the node's display name
        - If is_circular, appends CIRCULAR_REF_LABEL to the text
        - Recursively adds grandchildren

        Args:
            parent: The parent QTreeWidgetItem to add children to.
            node: The TreeNode whose children to render.
        """
        for child in node.children:
            display_text = child.name
            if child.is_circular:
                display_text = f"{child.name} {self.CIRCULAR_REF_LABEL}"

            child_item = QTreeWidgetItem(parent, [display_text])
            child_item.setData(0, self.REF_NAME_ROLE, child.ref_name)
            # 子ノードを再帰的に追加
            self._populate_tree_item(child_item, child)
