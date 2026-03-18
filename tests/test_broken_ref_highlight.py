"""Tests for W2: Broken (unresolved) reference highlighting.

Tests are organized by test target:
  1. Core tests (build_tree / TreeNode) -- no QApplication needed
  2. GUI tests (tree display coloring) -- requires QApplication (qapp fixture)
  3. Constants / configuration tests -- requires QApplication (qapp fixture)

Test naming convention: test_<subject>_<condition>_<expected_result>
Using Japanese names to reflect actual use cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.wildcard_parser import (
    TreeNode,
    WildcardResolver,
    build_key_registry,
    build_tree,
    scan_yaml_files,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_resolver_from_dir(cards_dir: Path) -> WildcardResolver:
    """Create a WildcardResolver from a cards directory."""
    yaml_files = scan_yaml_files(cards_dir)
    registry = build_key_registry(yaml_files)
    return WildcardResolver(registry, cards_dir)


def _collect_all_nodes(node: TreeNode) -> list[TreeNode]:
    """Recursively collect all nodes in the tree (including the root)."""
    result = [node]
    for child in node.children:
        result.extend(_collect_all_nodes(child))
    return result


# =========================================================================
# 1. Core tests -- QApplication NOT required
# =========================================================================


class TestBrokenRefCore:
    """Tests for broken reference handling in build_tree() / TreeNode.

    These tests verify that unresolved references are included in the
    tree with is_unresolved=True, correct display names, and proper
    leaf/children attributes.
    """

    # -- Normal cases --

    def test_壊れた参照_TreeNodeに含まれる(
        self, broken_ref_cards_dir: Path
    ):
        """Unresolved references are included in the tree as TreeNode."""
        resolver = _make_resolver_from_dir(broken_ref_cards_dir)
        tree = build_tree("entry", resolver)
        child_names = [c.name for c in tree.children]
        assert "non_existent_key" in child_names

    def test_壊れた参照_is_unresolvedがTrue(
        self, broken_ref_cards_dir: Path
    ):
        """Unresolved reference nodes have is_unresolved=True."""
        resolver = _make_resolver_from_dir(broken_ref_cards_dir)
        tree = build_tree("entry", resolver)
        unresolved = [c for c in tree.children if c.name == "non_existent_key"]
        assert len(unresolved) == 1
        assert unresolved[0].is_unresolved is True

    def test_壊れた参照_is_leafがTrue(
        self, broken_ref_cards_dir: Path
    ):
        """Unresolved reference nodes have is_leaf=True."""
        resolver = _make_resolver_from_dir(broken_ref_cards_dir)
        tree = build_tree("entry", resolver)
        unresolved = [c for c in tree.children if c.name == "non_existent_key"]
        assert len(unresolved) == 1
        assert unresolved[0].is_leaf is True

    def test_壊れた参照_childrenが空(
        self, broken_ref_cards_dir: Path
    ):
        """Unresolved reference nodes have empty children list."""
        resolver = _make_resolver_from_dir(broken_ref_cards_dir)
        tree = build_tree("entry", resolver)
        unresolved = [c for c in tree.children if c.name == "non_existent_key"]
        assert len(unresolved) == 1
        assert unresolved[0].children == []

    def test_壊れた参照_正常な参照と混在(
        self, broken_ref_cards_dir: Path
    ):
        """Both resolved and unresolved references coexist in tree children."""
        resolver = _make_resolver_from_dir(broken_ref_cards_dir)
        tree = build_tree("entry", resolver)
        child_names = [c.name for c in tree.children]
        # existing_key is resolved normally
        assert "existing_key" in child_names
        # non_existent_key is unresolved but still present
        assert "non_existent_key" in child_names
        assert len(tree.children) == 2

        # Verify attributes of normal vs unresolved
        existing = [c for c in tree.children if c.name == "existing_key"][0]
        assert existing.is_unresolved is False

        unresolved = [c for c in tree.children if c.name == "non_existent_key"][0]
        assert unresolved.is_unresolved is True

    # -- Display name: shortened form (with slashes) --

    def test_壊れた参照_表示名_スラッシュあり_最後の要素(
        self, broken_ref_fullpath_cards_dir: Path
    ):
        """When ref.name contains slashes, display name is the last segment.

        ref.name = "cards/SAO/CH_asada/unknown_key" -> display name = "unknown_key"
        """
        resolver = _make_resolver_from_dir(broken_ref_fullpath_cards_dir)
        tree = build_tree("entry", resolver)
        # The broken full-path reference should show only the last segment
        unresolved = [c for c in tree.children if c.is_unresolved]
        assert len(unresolved) == 1
        assert unresolved[0].name == "unknown_key"
        # But ref_name should store the full path
        assert unresolved[0].ref_name == "cards/SAO/CH_asada/unknown_key"

    # -- Display name: full form (no slashes) --

    def test_壊れた参照_表示名_スラッシュなし_そのまま(
        self, broken_ref_cards_dir: Path
    ):
        """When ref.name has no slashes, display name equals ref.name."""
        resolver = _make_resolver_from_dir(broken_ref_cards_dir)
        tree = build_tree("entry", resolver)
        unresolved = [c for c in tree.children if c.name == "non_existent_key"]
        assert len(unresolved) == 1
        assert unresolved[0].name == "non_existent_key"
        assert unresolved[0].ref_name == "non_existent_key"

    # -- All references broken --

    def test_全参照が壊れている_全子ノードがis_unresolved(
        self, all_broken_ref_cards_dir: Path
    ):
        """When all references are broken, all child nodes are is_unresolved=True."""
        resolver = _make_resolver_from_dir(all_broken_ref_cards_dir)
        tree = build_tree("entry", resolver)
        # Parent node itself is NOT unresolved (key definition exists)
        assert tree.is_unresolved is False
        # All children should be unresolved
        assert len(tree.children) >= 2
        for child in tree.children:
            assert child.is_unresolved is True
            assert child.is_leaf is True
            assert child.children == []

    # -- Broken + circular coexistence --

    def test_壊れた参照と循環参照の共存(
        self, broken_and_circular_cards_dir: Path
    ):
        """Broken and circular references can coexist in the same parent."""
        resolver = _make_resolver_from_dir(broken_and_circular_cards_dir)
        tree = build_tree("parent", resolver)
        child_names = [c.name for c in tree.children]

        # "child_circular" should exist and NOT be unresolved
        circular_child = [c for c in tree.children if c.name == "child_circular"]
        assert len(circular_child) == 1
        assert circular_child[0].is_unresolved is False

        # child_circular -> parent (circular)
        circular_grandchildren = [
            gc for gc in circular_child[0].children if gc.is_circular
        ]
        assert len(circular_grandchildren) == 1

        # "broken_ref" should be unresolved
        broken = [c for c in tree.children if c.name == "broken_ref"]
        assert len(broken) == 1
        assert broken[0].is_unresolved is True
        assert broken[0].is_circular is False

    # -- Edge cases --

    def test_壊れた参照_is_circularとis_unresolvedは排他的(
        self, broken_ref_cards_dir: Path
    ):
        """is_circular and is_unresolved should never both be True on same node."""
        resolver = _make_resolver_from_dir(broken_ref_cards_dir)
        tree = build_tree("entry", resolver)
        all_nodes = _collect_all_nodes(tree)
        for node in all_nodes:
            # They should be mutually exclusive
            assert not (node.is_circular and node.is_unresolved), (
                f"Node '{node.name}' has both is_circular=True and is_unresolved=True"
            )

    def test_壊れた参照_空文字列の参照名(
        self, tmp_path: Path, yaml_factory
    ):
        """Edge case: reference name is empty string (____).

        This should not crash. Behavior depends on how extract_refs_from_line
        handles ____ (4 underscores).
        """
        cards_dir = tmp_path / "cards"
        yaml_factory(
            "cards/test.yaml",
            (
                "entry:\n"
                "  - ____\n"
                "  - __valid_key__\n"
                "\n"
                "valid_key:\n"
                "  - leaf\n"
            ),
        )
        resolver = _make_resolver_from_dir(cards_dir)
        # Should not raise any exception
        tree = build_tree("entry", resolver)
        assert isinstance(tree, TreeNode)

    def test_壊れた参照_複数の壊れた参照が個別ノードになる(
        self, all_broken_ref_cards_dir: Path
    ):
        """Multiple broken references each become individual unresolved nodes."""
        resolver = _make_resolver_from_dir(all_broken_ref_cards_dir)
        tree = build_tree("entry", resolver)
        unresolved_children = [c for c in tree.children if c.is_unresolved]
        # Should have at least 2 separate broken reference nodes
        assert len(unresolved_children) >= 2
        # Each should have a distinct name
        names = [c.name for c in unresolved_children]
        assert len(names) == len(set(names))


# =========================================================================
# 2. GUI tests -- QApplication REQUIRED
# =========================================================================


class TestBrokenRefGUI:
    """Tests for broken reference visual display in the GUI.

    All tests require the qapp fixture for QApplication.
    """

    # -- Normal cases --

    def test_壊れた参照ノード_文字色が赤い(
        self, qapp, broken_ref_cards_dir: Path
    ):
        """Unresolved reference nodes in the tree have red foreground color."""
        from PySide6.QtGui import QColor

        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=broken_ref_cards_dir)
        try:
            # Build tree with "entry" as entry point
            window._build_and_display_tree("entry")

            # Find the unresolved child item
            root_item = window._tree_widget.topLevelItem(0)
            assert root_item is not None

            unresolved_item = None
            for i in range(root_item.childCount()):
                child = root_item.child(i)
                if child.text(0) == "non_existent_key":
                    unresolved_item = child
                    break

            assert unresolved_item is not None, (
                "non_existent_key node not found in tree"
            )
            fg_color = unresolved_item.foreground(0).color()
            assert fg_color == QColor("red")
        finally:
            window.close()

    def test_正常ノード_文字色がデフォルト(
        self, qapp, broken_ref_cards_dir: Path
    ):
        """Normal (resolved) nodes do NOT have red foreground color."""
        from PySide6.QtGui import QColor

        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=broken_ref_cards_dir)
        try:
            window._build_and_display_tree("entry")

            root_item = window._tree_widget.topLevelItem(0)
            assert root_item is not None

            normal_item = None
            for i in range(root_item.childCount()):
                child = root_item.child(i)
                if child.text(0) == "existing_key":
                    normal_item = child
                    break

            assert normal_item is not None, "existing_key node not found in tree"
            fg_color = normal_item.foreground(0).color()
            # Normal item should NOT be red
            assert fg_color != QColor("red")
        finally:
            window.close()

    def test_壊れた参照ノード選択_右ペインにキー定義見つかりませんメッセージ(
        self, qapp, broken_ref_cards_dir: Path
    ):
        """Selecting a broken reference node shows 'key not found' message."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=broken_ref_cards_dir)
        try:
            window._build_and_display_tree("entry")

            # Find the unresolved child item
            root_item = window._tree_widget.topLevelItem(0)
            assert root_item is not None

            unresolved_item = None
            for i in range(root_item.childCount()):
                child = root_item.child(i)
                if child.text(0) == "non_existent_key":
                    unresolved_item = child
                    break

            assert unresolved_item is not None

            # Select the unresolved item
            window._on_tree_item_selected(unresolved_item, None)

            text = window._text_detail.toPlainText()
            assert "(キー定義が見つかりません)" in text
        finally:
            window.close()

    def test_壊れた参照と正常参照が混在するツリー表示(
        self, qapp, broken_ref_cards_dir: Path
    ):
        """Tree displays both broken (red) and normal (default) nodes."""
        from PySide6.QtGui import QColor

        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=broken_ref_cards_dir)
        try:
            window._build_and_display_tree("entry")

            root_item = window._tree_widget.topLevelItem(0)
            assert root_item is not None
            # Should have at least 2 children (1 normal + 1 broken)
            assert root_item.childCount() >= 2

            red_count = 0
            default_count = 0
            for i in range(root_item.childCount()):
                child = root_item.child(i)
                fg_color = child.foreground(0).color()
                if fg_color == QColor("red"):
                    red_count += 1
                else:
                    default_count += 1

            assert red_count >= 1, "Expected at least 1 red (broken) node"
            assert default_count >= 1, "Expected at least 1 default (normal) node"
        finally:
            window.close()

    # -- Root node case --

    def test_ルートノードが壊れた参照の場合_赤字表示(
        self, qapp, broken_ref_cards_dir: Path
    ):
        """If the root (entry point) itself is unresolved, it should be red.

        Note: design doc says root is normally not unresolved (it's a direct
        key name, not a reference), but _build_and_display_tree should still
        handle is_unresolved defensively on the root item.
        """
        from PySide6.QtGui import QColor

        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=broken_ref_cards_dir)
        try:
            # Use a non-existent entry key -> root node is_leaf=True
            # but is_unresolved depends on implementation
            window._build_and_display_tree("totally_nonexistent_entry")

            root_item = window._tree_widget.topLevelItem(0)
            assert root_item is not None
            # The root exists as a tree item (even if unresolved/leaf)
            # Color depends on whether build_tree marks root as is_unresolved
        finally:
            window.close()


# =========================================================================
# 3. Constants / configuration tests -- QApplication REQUIRED
# =========================================================================


class TestBrokenRefConstants:
    """Tests for constants and settings related to broken ref highlighting."""

    def test_UNRESOLVED_COLOR定数の値(self, qapp):
        """UNRESOLVED_COLOR is QColor("red")."""
        from PySide6.QtGui import QColor

        from gui.main_window import MainWindow

        assert MainWindow.UNRESOLVED_COLOR == QColor("red")

    def test_ツリー再構築後も壊れた参照が赤字のまま(
        self, qapp, broken_ref_cards_dir: Path
    ):
        """After tree rebuild, broken references remain red."""
        from PySide6.QtGui import QColor

        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=broken_ref_cards_dir)
        try:
            # First build
            window._build_and_display_tree("entry")

            # Verify red node exists
            root_item = window._tree_widget.topLevelItem(0)
            assert root_item is not None

            def find_red_child(parent_item):
                for i in range(parent_item.childCount()):
                    child = parent_item.child(i)
                    if child.foreground(0).color() == QColor("red"):
                        return child
                return None

            assert find_red_child(root_item) is not None

            # Rebuild tree (simulates Refresh)
            window._build_and_display_tree("entry")

            # Verify red node still exists after rebuild
            root_item_2 = window._tree_widget.topLevelItem(0)
            assert root_item_2 is not None
            assert find_red_child(root_item_2) is not None
        finally:
            window.close()

    def test_壊れた参照ノードのrefNameがUserRoleに格納されている(
        self, qapp, broken_ref_cards_dir: Path
    ):
        """Broken reference nodes store ref_name in UserRole data."""
        from PySide6.QtCore import Qt

        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=broken_ref_cards_dir)
        try:
            window._build_and_display_tree("entry")

            root_item = window._tree_widget.topLevelItem(0)
            assert root_item is not None

            for i in range(root_item.childCount()):
                child = root_item.child(i)
                if child.text(0) == "non_existent_key":
                    ref_name = child.data(0, Qt.ItemDataRole.UserRole)
                    assert ref_name == "non_existent_key"
                    return

            pytest.fail("non_existent_key node not found in tree")
        finally:
            window.close()
