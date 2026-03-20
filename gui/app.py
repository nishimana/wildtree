"""WildTree v2 メインウィンドウ — 3ペイン構成のツリービューア。

S6 — v2 GUI のメインウィンドウ。
S1-S5 のコア層を統合し、ワイルドカード YAML のツリーを表示する。

レイアウト:
  +-------------------------------------------------------------------+
  | WildTree v2                                                 [_][X] |
  +-------------------------------------------------------------------+
  | cards: [/path/to/cards]                      [Browse...] [Refresh] |
  +-------------------------------------------------------------------+
  | Top Trees    | Tree View               | Detail                    |
  | +---------+  | +--------------------+  | +----------------------+  |
  | | メイン    |  | | メイン              |  | | キー名: メイン       |  |
  | | メインNP  |  | | ├── デフォルト     |  | | ファイル: main.yaml  |  |
  | |          |  | | │   ├── シネマ...  |  | | 行番号: 1            |  |
  | |          |  | | └── シーンまとめ   |  | |   - __cards/xxx__    |  |
  | +---------+  | +--------------------+  | +----------------------+  |
  +-------------------------------------------------------------------+

ペイン構成:
  - 左ペイン: トップツリーリスト（QListWidget）
  - 中央ペイン: ツリービュー（QTreeView + QStandardItemModel）
  - 右ペイン: 詳細表示（QTextBrowser）

データフロー:
  1. cards_dir のロード:
     scan_yaml_files → build_registry → build_full_path_index
     → find_top_trees → トップツリーリスト更新
  2. トップツリー選択:
     build_tree → populate_model → ツリービュー更新
  3. ノード選択:
     TreeNode 取得 → format_node_detail → 詳細ペイン更新

読み取り専用。編集機能は S7, S8 で追加する。

Attributes:
    _cards_dir: 現在の cards ディレクトリパス。未選択の場合は None。
    _registry: パーサーが構築したキーレジストリ。未ロードの場合は None。
    _full_path_index: フルパスインデックス。未ロードの場合は None。
    _top_trees: トップツリー情報リスト。
    _current_tree: 現在表示中のツリーのルートノード。未選択の場合は None。
    _label_path: cards ディレクトリのパスを表示する QLabel。
    _btn_browse: ディレクトリ選択ダイアログを開く QPushButton。
    _btn_refresh: 再スキャンを実行する QPushButton。
    _list_top_trees: トップツリーリストの QListWidget。
    _tree_view: ツリー表示の QTreeView。
    _tree_model: ツリーデータの QStandardItemModel。
    _detail_browser: 詳細表示の QTextBrowser。
    _splitter: 3ペインを管理する QSplitter。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from core.models import FullPathIndex, KeyRegistry, TreeNode
from core.top_tree import TopTreeInfo

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

WINDOW_TITLE: str = "WildTree v2"
"""ウィンドウタイトル。"""

DEFAULT_WIDTH: int = 1200
"""ウィンドウのデフォルト幅（ピクセル）。

3ペイン構成に合わせて v1 の 1000px から拡大。
"""

DEFAULT_HEIGHT: int = 800
"""ウィンドウのデフォルト高さ（ピクセル）。"""

SPLITTER_SIZES: list[int] = [200, 600, 400]
"""3ペインの初期サイズ比（ピクセル）。

[トップツリーリスト, ツリービュー, 詳細ペイン]
"""

DETAIL_PLACEHOLDER: str = "(ノードを選択するとキー定義を表示します)"
"""詳細ペインの初期テキスト。ノード未選択時に表示する。"""

TOP_TREE_DATA_ROLE: int = Qt.ItemDataRole.UserRole
"""QListWidgetItem に TopTreeInfo を格納するためのカスタムデータロール。"""


# ---------------------------------------------------------------------------
# メインウィンドウ
# ---------------------------------------------------------------------------


class WildTreeWindow(QMainWindow):
    """WildTree v2 のメインウィンドウ。

    3ペイン構成でワイルドカード YAML のツリー構造を表示する。
    読み取り専用。

    初期化の流れ:
      1. _setup_ui(): UI ウィジェットの構築
      2. _connect_signals(): シグナルとスロットの接続
      3. cards_dir が指定されている場合、_load_cards_dir() を呼んでロード
    """

    def __init__(
        self,
        cards_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """ウィンドウを初期化する。

        Args:
            cards_dir: 初期 cards ディレクトリパス。
                None の場合、ユーザーが Browse ボタンで選択する。
            parent: 親ウィジェット（通常は None）。
        """
        super().__init__(parent)

        # 内部状態の初期化
        self._cards_dir: Path | None = cards_dir
        self._registry: KeyRegistry | None = None
        self._full_path_index: FullPathIndex | None = None
        self._top_trees: list[TopTreeInfo] = []
        self._current_tree: TreeNode | None = None

        # UI 構築
        self._setup_ui()

        # シグナル接続
        self._connect_signals()

        # cards_dir が指定されていればロード
        if self._cards_dir is not None:
            self._load_cards_dir()

    def _setup_ui(self) -> None:
        """UI ウィジェットを構築する。

        レイアウト階層:
          - 中央ウィジェット (QWidget)
            - メインレイアウト (QVBoxLayout)
              - 上段バー (QHBoxLayout)
                - "cards:" ラベル
                - _label_path: パス表示 QLabel
                - _btn_browse: Browse ボタン
                - _btn_refresh: Refresh ボタン
              - メインエリア (QSplitter, 水平)
                - _list_top_trees: トップツリーリスト (QListWidget)
                - _tree_view: ツリービュー (QTreeView)
                - _detail_browser: 詳細ペイン (QTextBrowser)

        ツリービュー:
          - ヘッダー非表示
          - _tree_model を setModel() で設定
          - 編集不可

        詳細ペイン:
          - 読み取り専用（QTextBrowser のデフォルト）
          - 初期テキスト: DETAIL_PLACEHOLDER
        """
        # ウィンドウの基本設定
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)

        # 中央ウィジェット
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # メインレイアウト（垂直）
        main_layout = QVBoxLayout(central_widget)

        # --- 上段バー ---
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("cards:"))

        self._label_path = QLabel("")
        top_bar.addWidget(self._label_path, 1)  # stretch=1 で伸縮

        self._btn_browse = QPushButton("Browse...")
        top_bar.addWidget(self._btn_browse)

        self._btn_refresh = QPushButton("Refresh")
        top_bar.addWidget(self._btn_refresh)

        main_layout.addLayout(top_bar)

        # --- メインエリア（3ペインの QSplitter） ---
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左ペイン: トップツリーリスト
        self._list_top_trees = QListWidget()
        self._splitter.addWidget(self._list_top_trees)

        # 中央ペイン: ツリービュー
        self._tree_view = QTreeView()
        self._tree_model = QStandardItemModel()
        self._tree_view.setModel(self._tree_model)
        self._tree_view.setHeaderHidden(True)
        self._tree_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self._splitter.addWidget(self._tree_view)

        # 右ペイン: 詳細ペイン
        self._detail_browser = QTextBrowser()
        self._detail_browser.setPlainText(DETAIL_PLACEHOLDER)
        self._splitter.addWidget(self._detail_browser)

        # スプリッターの初期サイズ比
        self._splitter.setSizes(SPLITTER_SIZES)

        main_layout.addWidget(self._splitter)

    def _connect_signals(self) -> None:
        """シグナルとスロットを接続する。

        接続:
          - _btn_browse.clicked → _on_browse
          - _btn_refresh.clicked → _on_refresh
          - _list_top_trees.currentItemChanged → _on_top_tree_selected
          - _tree_view.selectionModel().currentChanged → _on_tree_node_selected
        """
        self._btn_browse.clicked.connect(self._on_browse)
        self._btn_refresh.clicked.connect(self._on_refresh)
        self._list_top_trees.currentItemChanged.connect(self._on_top_tree_selected)
        self._tree_view.selectionModel().currentChanged.connect(
            self._on_tree_node_selected
        )

    def _on_browse(self) -> None:
        """Browse ボタンのクリックハンドラ。

        QFileDialog.getExistingDirectory() でディレクトリを選択し、
        選択された場合は _cards_dir を更新して _load_cards_dir() を呼ぶ。
        キャンセルされた場合は何もしない。
        """
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "cards ディレクトリを選択",
            str(self._cards_dir) if self._cards_dir else "",
        )
        if dir_path:
            self._cards_dir = Path(dir_path)
            self._load_cards_dir()

    def _on_refresh(self) -> None:
        """Refresh ボタンのクリックハンドラ。

        _cards_dir が設定されている場合のみ _load_cards_dir() を呼ぶ。
        未設定の場合は何もしない。
        """
        if self._cards_dir is not None:
            self._load_cards_dir()

    def _load_cards_dir(self) -> None:
        """cards ディレクトリのロードパイプラインを実行する。

        S1-S4 のパイプラインを順に実行し、トップツリーリストを更新する:
          1. scan_yaml_files(cards_dir) → yaml_files
          2. build_registry(yaml_files) → registry
          3. build_full_path_index(registry, cards_dir) → full_path_index
          4. find_top_trees(registry) → top_trees
          5. トップツリーリストを更新

        エラー時は QMessageBox.warning() で通知し、処理を中断する。

        更新する状態:
          - _label_path のテキスト
          - _registry
          - _full_path_index
          - _top_trees
          - _list_top_trees のアイテム
          - _tree_model をクリア
          - _detail_browser をプレースホルダに戻す
          - _current_tree を None にリセット
        """
        from core.parser import build_registry
        from core.resolver import build_full_path_index
        from core.scanner import scan_yaml_files
        from core.top_tree import find_top_trees

        if self._cards_dir is None:
            return

        # ディレクトリ存在チェック
        if not self._cards_dir.exists():
            QMessageBox.warning(self, "エラー", f"ディレクトリが見つかりません: {self._cards_dir}")
            return
        if not self._cards_dir.is_dir():
            QMessageBox.warning(self, "エラー", f"ディレクトリではありません: {self._cards_dir}")
            return

        try:
            # S1-S4 パイプラインを順に実行
            yaml_files = scan_yaml_files(self._cards_dir)
            self._registry = build_registry(yaml_files)
            self._full_path_index = build_full_path_index(
                self._registry, self._cards_dir
            )
            self._top_trees = find_top_trees(self._registry)

            # パイプライン成功後にパスラベルを更新
            self._label_path.setText(str(self._cards_dir))

            # UI 状態をリセット
            self._tree_model.clear()
            self._detail_browser.setPlainText(DETAIL_PLACEHOLDER)
            self._current_tree = None

            # トップツリーリストを更新
            self._list_top_trees.clear()
            for top in self._top_trees:
                item = QListWidgetItem(top.name)
                item.setData(TOP_TREE_DATA_ROLE, top)
                self._list_top_trees.addItem(item)

        except Exception as e:
            # エラーは QMessageBox で通知し、処理を中断
            QMessageBox.warning(
                self,
                "読み込みエラー",
                f"cards ディレクトリの読み込みに失敗しました:\n{e}",
            )

    def _on_top_tree_selected(self) -> None:
        """トップツリーリストの選択変更ハンドラ。

        選択された QListWidgetItem から TopTreeInfo を取得し、
        build_tree() でツリーを構築して tree_model に投入する。

        処理の流れ:
          1. 現在の選択アイテムから TopTreeInfo を取得
          2. build_tree(top.key_def, registry, full_path_index) でツリー構築
          3. populate_model(tree_node, _tree_model) でモデル更新
          4. ルートノードを展開
          5. _current_tree を更新
          6. _detail_browser をプレースホルダに戻す

        選択なし（currentItem が None）の場合は何もしない。
        _registry / _full_path_index が None の場合は何もしない。
        """
        from core.tree_builder import build_tree

        from gui.tree_model import populate_model

        # 選択なしの場合は何もしない
        current_item = self._list_top_trees.currentItem()
        if current_item is None:
            return

        # レジストリ / インデックスが未構築の場合は何もしない
        if self._registry is None or self._full_path_index is None:
            return

        # TopTreeInfo を取得
        top_info: TopTreeInfo = current_item.data(TOP_TREE_DATA_ROLE)
        if top_info is None:
            return

        # ツリーを構築
        tree_node = build_tree(
            top_info.key_def, self._registry, self._full_path_index
        )

        # モデルに投入
        populate_model(tree_node, self._tree_model)

        # ルートノードを展開
        root_index = self._tree_model.index(0, 0)
        self._tree_view.expand(root_index)

        # 状態を更新
        self._current_tree = tree_node

        # 詳細ペインをプレースホルダに戻す
        self._detail_browser.setPlainText(DETAIL_PLACEHOLDER)

    def _on_tree_node_selected(
        self,
        current: QModelIndex,
        previous: QModelIndex,
    ) -> None:
        """ツリーノードの選択変更ハンドラ。

        選択された QModelIndex から TreeNode を取得し、
        format_node_detail() で詳細テキストを生成して右ペインに表示する。

        処理の流れ:
          1. current.data(TREE_NODE_ROLE) で TreeNode を取得
          2. TreeNode が None の場合はプレースホルダを表示
          3. format_node_detail(node) でテキスト生成
          4. _detail_browser.setPlainText() で表示

        Args:
            current: 新しい選択のモデルインデックス。
            previous: 前の選択のモデルインデックス（未使用）。
        """
        from gui.detail_pane import format_node_detail
        from gui.tree_model import TREE_NODE_ROLE

        # current から TreeNode を取得
        node = current.data(TREE_NODE_ROLE)
        if node is None:
            # TreeNode が取得できない場合はプレースホルダを表示
            self._detail_browser.setPlainText(DETAIL_PLACEHOLDER)
            return

        # 詳細テキストを生成して表示
        detail_text = format_node_detail(node)
        self._detail_browser.setPlainText(detail_text)
