"""Tests for W1: Node selection -> right pane key definition display.

Tests are organized by test target:
  1. _format_key_definition()  -- pure logic, no QApplication needed
  2. _on_tree_item_selected()  -- requires QApplication (qapp fixture)
  3. GUI integration tests     -- requires QApplication (qapp fixture)

Test naming convention: test_<subject>_<condition>_<expected_result>
Using Japanese names to reflect actual use cases.
"""

from __future__ import annotations

from pathlib import Path

from core.wildcard_parser import KeyDefinition, WildcardResolver


# =========================================================================
# 1. _format_key_definition() -- QApplication not required
# =========================================================================


class TestFormatKeyDefinition:
    """Tests for _format_key_definition(key_name, raw_values).

    This is a pure string formatting function. No QApplication needed.
    The expected format is:
        key_name:
          - value1
          - value2
    """

    @staticmethod
    def _call_format(key_name: str, raw_values: list[str]) -> str:
        """Call _format_key_definition via an instance.

        Since _format_key_definition is an instance method on MainWindow,
        we need to import the class. However, QApplication is NOT needed
        for this pure logic method -- we import only to access the method.
        We use __new__ to avoid __init__ which requires QApplication.
        """
        from gui.main_window import MainWindow

        # Create instance without calling __init__ to avoid QApplication
        # requirement. This works because _format_key_definition is a
        # pure function that does not access self.
        return MainWindow._format_key_definition(None, key_name, raw_values)

    # -- Normal cases --

    def test_フォーマット_複数値行_ヘッダと値行が正しく整形される(self):
        """Multiple values are formatted with header and prefixed lines."""
        result = self._call_format(
            "朝田詩乃体格",
            ["slender body", "__cards/SAO/options/エイジスライダー__"],
        )
        lines = result.splitlines()
        assert lines[0] == "朝田詩乃体格:"
        assert lines[1] == "  - slender body"
        assert lines[2] == "  - __cards/SAO/options/エイジスライダー__"

    def test_フォーマット_1行のみ_ヘッダと1値行(self):
        """A single value line produces header + one prefixed line."""
        result = self._call_format("greeting", ["hello world"])
        lines = result.splitlines()
        assert len(lines) == 2
        assert lines[0] == "greeting:"
        assert lines[1] == "  - hello world"

    def test_フォーマット_日本語キーと日本語値(self):
        """Japanese key names and values are correctly formatted."""
        result = self._call_format("シロコ体格", ["athletic body"])
        assert "シロコ体格:" in result
        assert "  - athletic body" in result

    # -- Edge cases --

    def test_フォーマット_空リスト_ヘッダ行のみ(self):
        """An empty raw_values list produces only the header line."""
        result = self._call_format("disabled_key", [])
        lines = result.splitlines()
        assert len(lines) == 1
        assert lines[0] == "disabled_key:"

    def test_フォーマット_空文字列のキー名(self):
        """Empty key name still produces a valid header line."""
        result = self._call_format("", ["value"])
        lines = result.splitlines()
        # Header should be ":" (empty key name + colon)
        assert lines[0] == ":"
        assert lines[1] == "  - value"

    def test_フォーマット_値行にコロンを含む(self):
        """Value lines containing colons are preserved as-is."""
        result = self._call_format(
            "prompt", ["masterpiece, best quality, 1girl: sitting"]
        )
        assert "  - masterpiece, best quality, 1girl: sitting" in result

    def test_フォーマット_値行に特殊文字を含む(self):
        """Value lines with special characters (braces, underscores) are preserved."""
        result = self._call_format(
            "scene", ["__{__season__}_{__character__}__"]
        )
        assert "  - __{__season__}_{__character__}__" in result

    def test_フォーマット_多数の値行(self):
        """A large number of value lines are all included."""
        values = [f"value_{i}" for i in range(50)]
        result = self._call_format("many_values", values)
        lines = result.splitlines()
        # 1 header + 50 value lines
        assert len(lines) == 51
        assert lines[0] == "many_values:"
        for i in range(50):
            assert lines[i + 1] == f"  - value_{i}"


# =========================================================================
# 2. _on_tree_item_selected() -- requires QApplication
# =========================================================================


class TestOnTreeItemSelected:
    """Tests for _on_tree_item_selected(current, previous).

    All tests require the qapp fixture for QApplication.
    """

    # -- Normal cases --

    def test_ノード選択_キー定義が右ペインに表示される(
        self, wildtree_main_window, simple_cards_dir: Path
    ):
        """Selecting a node displays the key definition in the right pane."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        window = wildtree_main_window

        # Set up resolver manually
        from core.wildcard_parser import (
            WildcardResolver,
            build_key_registry,
            scan_yaml_files,
        )

        yaml_files = scan_yaml_files(simple_cards_dir)
        registry = build_key_registry(yaml_files)
        window._resolver = WildcardResolver(registry, simple_cards_dir)

        # Create a QTreeWidgetItem with ref_name data
        item = QTreeWidgetItem(["greeting"])
        item.setData(0, Qt.ItemDataRole.UserRole, "greeting")

        # Call the handler
        window._on_tree_item_selected(item, None)

        # Verify the right pane shows the key definition
        text = window._text_detail.toPlainText()
        assert "greeting:" in text
        assert "  - hello" in text
        assert "  - __farewell__" in text

    def test_ノード選択_リーフノードのキー定義表示(
        self, wildtree_main_window, simple_cards_dir: Path
    ):
        """Selecting a leaf node (no references) shows its values."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        window = wildtree_main_window

        from core.wildcard_parser import (
            WildcardResolver,
            build_key_registry,
            scan_yaml_files,
        )

        yaml_files = scan_yaml_files(simple_cards_dir)
        registry = build_key_registry(yaml_files)
        window._resolver = WildcardResolver(registry, simple_cards_dir)

        item = QTreeWidgetItem(["farewell"])
        item.setData(0, Qt.ItemDataRole.UserRole, "farewell")

        window._on_tree_item_selected(item, None)

        text = window._text_detail.toPlainText()
        assert "farewell:" in text
        assert "  - goodbye" in text

    def test_ノード選択_日本語キーのキー定義表示(
        self, qapp, multi_file_cards_dir: Path
    ):
        """Selecting a Japanese-named node shows its definition."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=None)
        try:
            from core.wildcard_parser import (
                WildcardResolver,
                build_key_registry,
                scan_yaml_files,
            )

            yaml_files = scan_yaml_files(multi_file_cards_dir)
            registry = build_key_registry(yaml_files)
            window._resolver = WildcardResolver(registry, multi_file_cards_dir)

            item = QTreeWidgetItem(["朝田詩乃体格"])
            item.setData(0, Qt.ItemDataRole.UserRole, "朝田詩乃体格")

            window._on_tree_item_selected(item, None)

            text = window._text_detail.toPlainText()
            assert "朝田詩乃体格:" in text
            assert "  - slender body" in text
        finally:
            window.close()

    # -- Error cases --

    def test_ノード選択_currentがNone_プレースホルダ表示(
        self, wildtree_main_window
    ):
        """When current is None, the placeholder text is displayed."""
        window = wildtree_main_window

        # First set some non-placeholder text to verify it gets reset
        window._text_detail.setPlainText("something else")

        window._on_tree_item_selected(None, None)

        text = window._text_detail.toPlainText()
        assert text == window.DETAIL_PLACEHOLDER

    def test_ノード選択_refNameがNone_プレースホルダ表示(
        self, wildtree_main_window
    ):
        """When ref_name is None (setData not called), placeholder is shown."""
        from PySide6.QtWidgets import QTreeWidgetItem

        window = wildtree_main_window

        # Create item WITHOUT setting UserRole data -> data() returns None
        item = QTreeWidgetItem(["no_ref_name"])

        window._text_detail.setPlainText("something else")
        window._on_tree_item_selected(item, None)

        text = window._text_detail.toPlainText()
        assert text == window.DETAIL_PLACEHOLDER

    def test_ノード選択_resolveがNone_見つかりませんメッセージ(
        self, wildtree_main_window, simple_cards_dir: Path
    ):
        """When resolve() returns None, a 'not found' message is shown."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        window = wildtree_main_window

        from core.wildcard_parser import (
            WildcardResolver,
            build_key_registry,
            scan_yaml_files,
        )

        yaml_files = scan_yaml_files(simple_cards_dir)
        registry = build_key_registry(yaml_files)
        window._resolver = WildcardResolver(registry, simple_cards_dir)

        # Use a ref_name that does not exist in the registry
        item = QTreeWidgetItem(["non_existent_key"])
        item.setData(0, Qt.ItemDataRole.UserRole, "non_existent_key")

        window._on_tree_item_selected(item, None)

        text = window._text_detail.toPlainText()
        assert "(キー定義が見つかりません)" in text

    def test_ノード選択_resolverがNone_プレースホルダ表示(
        self, wildtree_main_window
    ):
        """When _resolver is None, the placeholder text is displayed."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        window = wildtree_main_window

        # Ensure resolver is None
        assert window._resolver is None

        item = QTreeWidgetItem(["some_key"])
        item.setData(0, Qt.ItemDataRole.UserRole, "some_key")

        window._text_detail.setPlainText("something else")
        window._on_tree_item_selected(item, None)

        text = window._text_detail.toPlainText()
        assert text == window.DETAIL_PLACEHOLDER

    # -- Edge cases --

    def test_ノード選択_循環参照ノード_キー定義を正常に表示(
        self, qapp, circular_ref_cards_dir: Path
    ):
        """Selecting a circular ref node shows the key definition normally.

        Circular reference nodes have is_circular=True but the key
        itself exists, so resolve() should return the KeyDefinition.
        """
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=None)
        try:
            from core.wildcard_parser import (
                WildcardResolver,
                build_key_registry,
                scan_yaml_files,
            )

            yaml_files = scan_yaml_files(circular_ref_cards_dir)
            registry = build_key_registry(yaml_files)
            window._resolver = WildcardResolver(registry, circular_ref_cards_dir)

            # Simulate selecting the circular ref node for "alpha"
            item = QTreeWidgetItem(["alpha (circular ref)"])
            item.setData(0, Qt.ItemDataRole.UserRole, "alpha")

            window._on_tree_item_selected(item, None)

            text = window._text_detail.toPlainText()
            # alpha's definition exists, so it should be displayed
            assert "alpha:" in text
            assert "  - __beta__" in text
        finally:
            window.close()

    def test_ノード選択_空文字列のrefName_プレースホルダではなく処理される(
        self, wildtree_main_window, simple_cards_dir: Path
    ):
        """Empty string ref_name is not treated as None.

        Design note: code should use ``if ref_name is not None``
        not ``if ref_name``, to handle empty string correctly.
        An empty-string ref_name will not match any key, so it
        should show the 'not found' message rather than placeholder.
        """
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        window = wildtree_main_window

        from core.wildcard_parser import (
            WildcardResolver,
            build_key_registry,
            scan_yaml_files,
        )

        yaml_files = scan_yaml_files(simple_cards_dir)
        registry = build_key_registry(yaml_files)
        window._resolver = WildcardResolver(registry, simple_cards_dir)

        item = QTreeWidgetItem(["empty_ref"])
        item.setData(0, Qt.ItemDataRole.UserRole, "")

        window._on_tree_item_selected(item, None)

        text = window._text_detail.toPlainText()
        # Empty string is a valid ref_name (not None), so it should attempt
        # resolution, which will fail -> "not found" message
        assert "(キー定義が見つかりません)" in text
        # Should NOT show placeholder
        assert text != window.DETAIL_PLACEHOLDER

    def test_ノード選択_raw_valuesが空_ヘッダのみ表示(
        self, wildtree_main_window, tmp_path: Path
    ):
        """When raw_values is empty, only the header line is displayed."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        window = wildtree_main_window

        # Create a resolver with a key that has empty raw_values
        kd = KeyDefinition(
            name="empty_key",
            file_path=tmp_path / "test.yaml",
            raw_values=[],
        )
        cards_dir = tmp_path / "cards"
        registry = {"empty_key": [kd]}
        window._resolver = WildcardResolver(registry, cards_dir)

        item = QTreeWidgetItem(["empty_key"])
        item.setData(0, Qt.ItemDataRole.UserRole, "empty_key")

        window._on_tree_item_selected(item, None)

        text = window._text_detail.toPlainText()
        lines = text.splitlines()
        assert lines[0] == "empty_key:"
        # Only header line, no value lines
        assert len(lines) == 1

    def test_ノード選択_previousは使用されない(
        self, wildtree_main_window, simple_cards_dir: Path
    ):
        """The 'previous' parameter is ignored -- behavior depends only on current."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        window = wildtree_main_window

        from core.wildcard_parser import (
            WildcardResolver,
            build_key_registry,
            scan_yaml_files,
        )

        yaml_files = scan_yaml_files(simple_cards_dir)
        registry = build_key_registry(yaml_files)
        window._resolver = WildcardResolver(registry, simple_cards_dir)

        current = QTreeWidgetItem(["greeting"])
        current.setData(0, Qt.ItemDataRole.UserRole, "greeting")

        previous = QTreeWidgetItem(["farewell"])
        previous.setData(0, Qt.ItemDataRole.UserRole, "farewell")

        # Call with a non-None previous -- should not affect the result
        window._on_tree_item_selected(current, previous)

        text = window._text_detail.toPlainText()
        # Should show greeting's definition, not farewell's
        assert "greeting:" in text


# =========================================================================
# 3. GUI integration tests -- requires QApplication
# =========================================================================


class TestDetailPaneGUIIntegration:
    """Integration tests for the detail pane GUI structure and wiring."""

    def test_QSplitterが存在し左右にウィジェットが配置されている(
        self, wildtree_main_window
    ):
        """QSplitter exists and contains tree (left) and text edit (right)."""
        from PySide6.QtWidgets import QSplitter

        window = wildtree_main_window

        # _splitter attribute should exist
        assert hasattr(window, "_splitter")
        assert isinstance(window._splitter, QSplitter)

        # Left widget is the tree, right widget is the text edit
        assert window._splitter.count() == 2
        assert window._splitter.widget(0) is window._tree_widget
        assert window._splitter.widget(1) is window._text_detail

    def test_QTextEditが読み取り専用である(self, wildtree_main_window):
        """The QTextEdit detail pane is read-only."""
        from PySide6.QtWidgets import QTextEdit

        window = wildtree_main_window

        assert hasattr(window, "_text_detail")
        assert isinstance(window._text_detail, QTextEdit)
        assert window._text_detail.isReadOnly() is True

    def test_初期状態でプレースホルダが表示されている(
        self, wildtree_main_window
    ):
        """The initial state shows the placeholder text in the detail pane."""
        window = wildtree_main_window

        text = window._text_detail.toPlainText()
        assert text == window.DETAIL_PLACEHOLDER

    def test_ツリー再構築で右ペインがクリアされる(
        self, wildtree_main_window_with_data
    ):
        """Rebuilding the tree resets the detail pane to placeholder.

        When _build_and_display_tree() is called, the right pane should
        be reset to DETAIL_PLACEHOLDER before displaying the new tree.
        """
        window = wildtree_main_window_with_data

        # First, simulate selecting a node to put non-placeholder text
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        item = QTreeWidgetItem(["greeting"])
        item.setData(0, Qt.ItemDataRole.UserRole, "greeting")
        window._on_tree_item_selected(item, None)

        # Verify something was displayed (not placeholder)
        text_before = window._text_detail.toPlainText()
        assert text_before != window.DETAIL_PLACEHOLDER

        # Now rebuild the tree
        window._build_and_display_tree("greeting")

        # The detail pane should be back to placeholder
        text_after = window._text_detail.toPlainText()
        assert text_after == window.DETAIL_PLACEHOLDER

    def test_currentItemChangedシグナルが接続されている(
        self, wildtree_main_window
    ):
        """The currentItemChanged signal is connected to the handler.

        Verify by checking that selecting a tree item triggers the handler.
        """
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        window = wildtree_main_window

        # Set up a resolver so the handler can do its work
        kd = KeyDefinition(
            name="test_key",
            file_path=Path("dummy.yaml"),
            raw_values=["test_value"],
        )
        registry = {"test_key": [kd]}
        window._resolver = WildcardResolver(registry, Path("."))

        # Add a tree item and set its data
        root_item = QTreeWidgetItem(["test_key"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, "test_key")
        window._tree_widget.addTopLevelItem(root_item)

        # Programmatically select the item -- this should trigger
        # currentItemChanged, which should call _on_tree_item_selected
        window._tree_widget.setCurrentItem(root_item)

        # If the signal is connected, the detail pane should now show
        # the key definition (not placeholder)
        text = window._text_detail.toPlainText()
        assert "test_key:" in text
        assert "  - test_value" in text

    def test_ウィンドウ幅がデフォルト1000px(self, wildtree_main_window):
        """The default window width is 1000px to accommodate the right pane."""
        window = wildtree_main_window
        assert window.width() == window.DEFAULT_WIDTH
        assert window.DEFAULT_WIDTH == 1000

    def test_QSplitterの初期比率(self, wildtree_main_window):
        """The QSplitter initial sizes ratio is approximately 400:600."""
        window = wildtree_main_window

        sizes = window._splitter.sizes()
        assert len(sizes) == 2
        # The actual sizes may differ from setSizes() due to Qt layout,
        # but the ratio should be approximately 2:3 (400:600)
        total = sum(sizes)
        if total > 0:
            left_ratio = sizes[0] / total
            # 400/1000 = 0.4, allow some tolerance
            assert 0.3 <= left_ratio <= 0.5

    def test_REF_NAME_ROLEがUserRole(self, wildtree_main_window):
        """REF_NAME_ROLE class constant is set to Qt.ItemDataRole.UserRole."""
        from PySide6.QtCore import Qt

        window = wildtree_main_window
        assert window.REF_NAME_ROLE == Qt.ItemDataRole.UserRole

    def test_DETAIL_PLACEHOLDERの値(self, wildtree_main_window):
        """DETAIL_PLACEHOLDER constant has the expected Japanese text."""
        window = wildtree_main_window
        assert window.DETAIL_PLACEHOLDER == "(ノードを選択するとキー定義を表示します)"

    def test_ツリーアイテムにrefNameが格納されている(
        self, wildtree_main_window_with_data
    ):
        """QTreeWidgetItems store ref_name in UserRole data.

        After tree construction, each item should have setData()
        with the ref_name from TreeNode.
        """
        from PySide6.QtCore import Qt

        window = wildtree_main_window_with_data

        # Get the root item
        root_item = window._tree_widget.topLevelItem(0)
        assert root_item is not None

        # The root item should have ref_name stored in UserRole
        ref_name = root_item.data(0, Qt.ItemDataRole.UserRole)
        assert ref_name is not None
        assert isinstance(ref_name, str)
        assert len(ref_name) > 0

    def test_ツリーアイテムの子ノードにもrefNameが格納されている(
        self, wildtree_main_window_with_data
    ):
        """Child QTreeWidgetItems also store ref_name in UserRole data."""
        from PySide6.QtCore import Qt

        window = wildtree_main_window_with_data

        root_item = window._tree_widget.topLevelItem(0)
        assert root_item is not None

        # Check child items (greeting -> farewell)
        if root_item.childCount() > 0:
            child_item = root_item.child(0)
            ref_name = child_item.data(0, Qt.ItemDataRole.UserRole)
            assert ref_name is not None
            assert isinstance(ref_name, str)
            assert len(ref_name) > 0

    def test_エントリポイント変更で右ペインがリセットされる(
        self, qapp, multi_file_cards_dir: Path
    ):
        """Changing the entry point resets the detail pane to placeholder."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=multi_file_cards_dir)
        try:
            # Select a node to set non-placeholder text
            item = QTreeWidgetItem(["メイン"])
            item.setData(0, Qt.ItemDataRole.UserRole, "メイン")
            window._on_tree_item_selected(item, None)

            text_before = window._text_detail.toPlainText()
            assert text_before != window.DETAIL_PLACEHOLDER

            # Change entry point
            all_keys = window._resolver.get_all_key_names()
            another_key = [k for k in all_keys if k != "メイン"][0]
            window._build_and_display_tree(another_key)

            # Detail pane should be back to placeholder
            text_after = window._text_detail.toPlainText()
            assert text_after == window.DETAIL_PLACEHOLDER
        finally:
            window.close()
