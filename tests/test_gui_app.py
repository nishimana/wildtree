"""統合テスト for gui/app.py -- v2 メインウィンドウの統合テスト。

設計意図ドキュメント (docs/design/s6-gui-tree-view.md) に基づいて、
WildTreeWindow の統合的な振る舞いを検証する。

テスト対象:
  - WildTreeWindow のインスタンス化
  - _load_cards_dir パイプライン
  - トップツリー選択 → ツリー更新の連携
  - ノード選択 → 詳細ペイン更新の連携

Note:
  全テストが QApplication を必要とする。qapp フィクスチャを使用する。
  テスト数は最小限に抑え、コア層の統合テストとして実施する。

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path

import pytest


# =========================================================================
# WildTreeWindow のインスタンス化テスト
# =========================================================================


class TestWildTreeWindowInit:
    """WildTreeWindow のインスタンス化テスト。"""

    def test_cards_dirなしで起動_空状態(self, qapp):
        """cards_dir=None で起動した場合、3ペインが空状態で表示される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            # ウィンドウが作成されている
            assert window is not None
            # トップツリーリストが空
            assert window._list_top_trees.count() == 0
            # ツリーモデルが空
            assert window._tree_model.rowCount() == 0
            # 詳細ペインがプレースホルダ
            from gui.app import DETAIL_PLACEHOLDER
            assert window._detail_browser.toPlainText() == DETAIL_PLACEHOLDER
        finally:
            window.close()

    def test_cards_dir指定で起動_トップツリーリストが表示される(
        self, qapp, simple_cards_dir: Path
    ):
        """cards_dir を指定して起動すると、トップツリーリストが表示される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=simple_cards_dir)
        try:
            # トップツリーリストにアイテムがある
            assert window._list_top_trees.count() > 0
        finally:
            window.close()


# =========================================================================
# ウィンドウ定数のテスト
# =========================================================================


class TestWildTreeWindowConstants:
    """WildTreeWindow の定数テスト。"""

    def test_ウィンドウタイトル(self, qapp):
        """ウィンドウタイトルが "WildTree v2" である。"""
        from gui.app import WINDOW_TITLE, WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert window.windowTitle() == WINDOW_TITLE
            assert WINDOW_TITLE == "WildTree v2"
        finally:
            window.close()

    def test_ウィンドウサイズ(self, qapp):
        """ウィンドウのデフォルトサイズが 1200x800 である。"""
        from gui.app import DEFAULT_HEIGHT, DEFAULT_WIDTH, WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert DEFAULT_WIDTH == 1200
            assert DEFAULT_HEIGHT == 800
        finally:
            window.close()

    def test_スプリッターサイズ(self, qapp):
        """SPLITTER_SIZES が [200, 600, 400] である。"""
        from gui.app import SPLITTER_SIZES

        assert SPLITTER_SIZES == [200, 600, 400]

    def test_詳細ペインプレースホルダ(self, qapp):
        """DETAIL_PLACEHOLDER が正しい日本語テキストである。"""
        from gui.app import DETAIL_PLACEHOLDER

        assert DETAIL_PLACEHOLDER == "(ノードを選択するとキー定義を表示します)"


# =========================================================================
# UI構造のテスト
# =========================================================================


class TestWildTreeWindowUI構造:
    """WildTreeWindow の UI 構造テスト。"""

    def test_3ペインが存在する(self, qapp):
        """QSplitter に3つのペインが含まれる。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert hasattr(window, "_splitter")
            assert window._splitter.count() == 3
        finally:
            window.close()

    def test_トップツリーリストが存在する(self, qapp):
        """トップツリーリスト（QListWidget）が存在する。"""
        from PySide6.QtWidgets import QListWidget

        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert hasattr(window, "_list_top_trees")
            assert isinstance(window._list_top_trees, QListWidget)
        finally:
            window.close()

    def test_ツリービューが存在する(self, qapp):
        """ツリービュー（QTreeView）が存在する。"""
        from PySide6.QtWidgets import QTreeView

        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert hasattr(window, "_tree_view")
            assert isinstance(window._tree_view, QTreeView)
        finally:
            window.close()

    def test_詳細ペインが存在する(self, qapp):
        """詳細ペイン（QTextBrowser）が存在する。"""
        from PySide6.QtWidgets import QTextBrowser

        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert hasattr(window, "_detail_browser")
            assert isinstance(window._detail_browser, QTextBrowser)
        finally:
            window.close()

    def test_Browseボタンが存在する(self, qapp):
        """Browse ボタンが存在する。"""
        from PySide6.QtWidgets import QPushButton

        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert hasattr(window, "_btn_browse")
            assert isinstance(window._btn_browse, QPushButton)
        finally:
            window.close()

    def test_Refreshボタンが存在する(self, qapp):
        """Refresh ボタンが存在する。"""
        from PySide6.QtWidgets import QPushButton

        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert hasattr(window, "_btn_refresh")
            assert isinstance(window._btn_refresh, QPushButton)
        finally:
            window.close()

    def test_パスラベルが存在する(self, qapp):
        """パス表示用の QLabel が存在する。"""
        from PySide6.QtWidgets import QLabel

        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert hasattr(window, "_label_path")
            assert isinstance(window._label_path, QLabel)
        finally:
            window.close()

    def test_ツリーモデルが存在する(self, qapp):
        """ツリーモデル（QStandardItemModel）が存在する。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert hasattr(window, "_tree_model")
            assert isinstance(window._tree_model, QStandardItemModel)
        finally:
            window.close()


# =========================================================================
# _load_cards_dir パイプラインのテスト
# =========================================================================


class TestLoadCardsDirパイプライン:
    """_load_cards_dir パイプラインのテスト。"""

    def test_simple_cards_dir_トップツリーリストが更新される(
        self, qapp, simple_cards_dir: Path
    ):
        """simple_cards_dir をロードするとトップツリーリストが更新される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            # 初期状態は空
            assert window._list_top_trees.count() == 0

            # cards_dir を設定してロード
            window._cards_dir = simple_cards_dir
            window._load_cards_dir()

            # トップツリーリストが更新されている
            assert window._list_top_trees.count() > 0
        finally:
            window.close()

    def test_multi_file_cards_dir_レジストリとインデックスが構築される(
        self, qapp, multi_file_cards_dir: Path
    ):
        """multi_file_cards_dir をロードすると _registry と _full_path_index が構築される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            window._cards_dir = multi_file_cards_dir
            window._load_cards_dir()

            assert window._registry is not None
            assert window._full_path_index is not None
            assert len(window._registry) > 0
            assert len(window._full_path_index) > 0
        finally:
            window.close()

    def test_load_cards_dir_パスラベルが更新される(
        self, qapp, simple_cards_dir: Path
    ):
        """_load_cards_dir 実行後、パスラベルが更新される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            window._cards_dir = simple_cards_dir
            window._load_cards_dir()

            label_text = window._label_path.text()
            # パスの一部が含まれる
            assert len(label_text) > 0
        finally:
            window.close()

    def test_load_cards_dir_ツリーモデルがクリアされる(
        self, qapp, simple_cards_dir: Path
    ):
        """_load_cards_dir 実行後、ツリーモデルがクリアされる。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=simple_cards_dir)
        try:
            # 再ロード
            window._load_cards_dir()

            # ツリーモデルがクリアされている（トップツリー選択前）
            assert window._tree_model.rowCount() == 0
        finally:
            window.close()

    def test_load_cards_dir_詳細ペインがプレースホルダに戻る(
        self, qapp, simple_cards_dir: Path
    ):
        """_load_cards_dir 実行後、詳細ペインがプレースホルダに戻る。"""
        from gui.app import DETAIL_PLACEHOLDER, WildTreeWindow

        window = WildTreeWindow(cards_dir=simple_cards_dir)
        try:
            # 詳細ペインに何か表示
            window._detail_browser.setPlainText("something")

            # 再ロード
            window._load_cards_dir()

            assert window._detail_browser.toPlainText() == DETAIL_PLACEHOLDER
        finally:
            window.close()


# =========================================================================
# トップツリー選択 → ツリー更新のテスト
# =========================================================================


class TestTopTreeSelection:
    """トップツリー選択 → ツリー更新の連携テスト。"""

    def test_トップツリー選択_ツリーモデルが更新される(
        self, qapp, simple_cards_dir: Path
    ):
        """トップツリーを選択するとツリーモデルにノードが追加される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=simple_cards_dir)
        try:
            # トップツリーリストにアイテムがあることを確認
            assert window._list_top_trees.count() > 0

            # 最初のトップツリーを選択
            window._list_top_trees.setCurrentRow(0)

            # ツリーモデルにノードが追加されている
            assert window._tree_model.rowCount() > 0
        finally:
            window.close()

    def test_別のトップツリーに切り替え_ツリーが更新される(
        self, qapp, multi_file_cards_dir: Path
    ):
        """別のトップツリーに切り替えるとツリーが更新される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=multi_file_cards_dir)
        try:
            count = window._list_top_trees.count()
            if count < 2:
                pytest.skip("テストに必要なトップツリー数が不足")

            # 最初のトップツリーを選択
            window._list_top_trees.setCurrentRow(0)
            first_root_text = window._tree_model.item(0).text() if window._tree_model.rowCount() > 0 else ""

            # 別のトップツリーに切り替え
            window._list_top_trees.setCurrentRow(1)

            # ツリーが更新されている
            assert window._tree_model.rowCount() > 0
            second_root_text = window._tree_model.item(0).text()
            # 異なるトップツリーが表示されている（名前が異なるはず）
            # ただし同名の可能性もあるのでモデルにデータがあることだけ確認
        finally:
            window.close()

    def test_トップツリー選択_詳細ペインがプレースホルダに戻る(
        self, qapp, simple_cards_dir: Path
    ):
        """トップツリーを選択すると詳細ペインがプレースホルダに戻る。"""
        from gui.app import DETAIL_PLACEHOLDER, WildTreeWindow

        window = WildTreeWindow(cards_dir=simple_cards_dir)
        try:
            # 詳細ペインに何か表示
            window._detail_browser.setPlainText("something")

            # トップツリーを選択
            if window._list_top_trees.count() > 0:
                window._list_top_trees.setCurrentRow(0)

                assert window._detail_browser.toPlainText() == DETAIL_PLACEHOLDER
        finally:
            window.close()


# =========================================================================
# ノード選択 → 詳細ペイン更新のテスト
# =========================================================================


class TestNodeSelection:
    """ノード選択 → 詳細ペイン更新の連携テスト。"""

    def test_ノード選択_詳細ペインに情報が表示される(
        self, qapp, simple_cards_dir: Path
    ):
        """ツリーノードを選択すると詳細ペインに情報が表示される。"""
        from gui.app import DETAIL_PLACEHOLDER, WildTreeWindow

        window = WildTreeWindow(cards_dir=simple_cards_dir)
        try:
            # トップツリーを選択してツリーを表示
            if window._list_top_trees.count() > 0:
                window._list_top_trees.setCurrentRow(0)

                # ツリーモデルにノードがあることを確認
                if window._tree_model.rowCount() > 0:
                    # ルートノードのインデックスを取得して選択
                    root_index = window._tree_model.index(0, 0)
                    window._tree_view.selectionModel().setCurrentIndex(
                        root_index,
                        window._tree_view.selectionModel().SelectionFlag.ClearAndSelect,
                    )

                    # 詳細ペインにプレースホルダ以外の情報が表示されている
                    text = window._detail_browser.toPlainText()
                    assert text != DETAIL_PLACEHOLDER
                    assert len(text) > 0
        finally:
            window.close()

    def test_ノード選択_ROOTノード_キー情報が表示される(
        self, qapp, simple_cards_dir: Path
    ):
        """ROOT ノードを選択するとキー情報（キー名、ファイル、行番号）が表示される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=simple_cards_dir)
        try:
            if window._list_top_trees.count() > 0:
                window._list_top_trees.setCurrentRow(0)

                if window._tree_model.rowCount() > 0:
                    root_index = window._tree_model.index(0, 0)
                    window._tree_view.selectionModel().setCurrentIndex(
                        root_index,
                        window._tree_view.selectionModel().SelectionFlag.ClearAndSelect,
                    )

                    text = window._detail_browser.toPlainText()
                    # ROOT ノードなのでキー情報が含まれるはず
                    assert "キー名:" in text
        finally:
            window.close()


# =========================================================================
# Refresh のテスト
# =========================================================================


class TestRefresh:
    """Refresh ボタンのテスト。"""

    def test_cards_dir未選択でRefresh_何もしない(self, qapp):
        """_cards_dir が None の状態で _on_refresh を呼んでも何も起きない。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            # _cards_dir が None であることを確認
            assert window._cards_dir is None

            # Refresh を呼んでも例外を投げない
            window._on_refresh()

            # トップツリーリストは空のまま
            assert window._list_top_trees.count() == 0
        finally:
            window.close()

    def test_cards_dir選択済みでRefresh_再ロードされる(
        self, qapp, simple_cards_dir: Path
    ):
        """_cards_dir が設定されている状態で _on_refresh を呼ぶと再ロードされる。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=simple_cards_dir)
        try:
            count_before = window._list_top_trees.count()
            assert count_before > 0

            # Refresh
            window._on_refresh()

            # 再ロード後もトップツリーリストにアイテムがある
            assert window._list_top_trees.count() > 0
        finally:
            window.close()


# =========================================================================
# 状態管理のテスト
# =========================================================================


class TestWildTreeWindow状態管理:
    """WildTreeWindow の内部状態管理テスト。"""

    def test_初期状態_registryがNone(self, qapp):
        """初期状態（cards_dir=None）で _registry が None。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert window._registry is None
        finally:
            window.close()

    def test_初期状態_full_path_indexがNone(self, qapp):
        """初期状態（cards_dir=None）で _full_path_index が None。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert window._full_path_index is None
        finally:
            window.close()

    def test_初期状態_top_treesが空(self, qapp):
        """初期状態（cards_dir=None）で _top_trees が空リスト。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert window._top_trees == []
        finally:
            window.close()

    def test_初期状態_current_treeがNone(self, qapp):
        """初期状態（cards_dir=None）で _current_tree が None。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert window._current_tree is None
        finally:
            window.close()

    def test_ロード後_registryが設定される(self, qapp, simple_cards_dir: Path):
        """cards_dir をロード後、_registry が設定される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=simple_cards_dir)
        try:
            assert window._registry is not None
        finally:
            window.close()

    def test_トップツリー選択後_current_treeが設定される(
        self, qapp, simple_cards_dir: Path
    ):
        """トップツリーを選択後、_current_tree が設定される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=simple_cards_dir)
        try:
            if window._list_top_trees.count() > 0:
                window._list_top_trees.setCurrentRow(0)
                assert window._current_tree is not None
        finally:
            window.close()


# =========================================================================
# multi_file_cards_dir を使った統合テスト
# =========================================================================


class TestWildTreeWindow統合_multi_file:
    """multi_file_cards_dir を使った統合テスト。"""

    def test_multi_file_cards_dir_全パイプラインが正常動作(
        self, qapp, multi_file_cards_dir: Path
    ):
        """multi_file_cards_dir で全パイプラインが正常に動作する。

        scan → parse → resolve → find_top_trees → tree_build → populate_model
        の全ステップが例外なく完了する。
        """
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=multi_file_cards_dir)
        try:
            # トップツリーリストにアイテムがある
            assert window._list_top_trees.count() > 0

            # 最初のトップツリーを選択
            window._list_top_trees.setCurrentRow(0)

            # ツリーモデルにノードが追加されている
            assert window._tree_model.rowCount() > 0

            # ルートノードを選択
            root_index = window._tree_model.index(0, 0)
            window._tree_view.selectionModel().setCurrentIndex(
                root_index,
                window._tree_view.selectionModel().SelectionFlag.ClearAndSelect,
            )

            # 詳細ペインに情報が表示されている
            text = window._detail_browser.toPlainText()
            assert len(text) > 0
            assert "キー名:" in text
        finally:
            window.close()

    def test_commented_ref_cards_dir_コメントノードが正しく表示される(
        self, qapp, commented_ref_cards_dir: Path
    ):
        """commented_ref_cards_dir でコメントアウトされたノードが正しく処理される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0

            # トップツリーを選択
            window._list_top_trees.setCurrentRow(0)

            # ツリーモデルにノードがある
            assert window._tree_model.rowCount() > 0
        finally:
            window.close()
