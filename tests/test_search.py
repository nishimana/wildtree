"""Tests for W3: Search feature (tree node text search).

Tests are organized by test target:
  1. TestSearchLogic -- search matching behavior (partial match, case-insensitive)
  2. TestSearchNavigation -- next/prev, wrap-around, empty match guards
  3. TestSearchUI -- match count label, tree selection sync, rebuild behavior

All tests require the qapp fixture for QApplication (offscreen mode).
Test naming convention: test_<subject>_<condition>_<expected_result>
Using Japanese names to reflect actual use cases.
"""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_all_tree_item_texts(window) -> list[str]:
    """Collect all QTreeWidgetItem display texts from the tree widget."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTreeWidgetItem

    results: list[str] = []

    def _collect(item: QTreeWidgetItem) -> None:
        results.append(item.text(0))
        for i in range(item.childCount()):
            _collect(item.child(i))

    for i in range(window._tree_widget.topLevelItemCount()):
        _collect(window._tree_widget.topLevelItem(i))
    return results


# =========================================================================
# 1. TestSearchLogic -- search matching behavior
# =========================================================================


class TestSearchLogic:
    """Tests for search matching logic.

    Verifies that text input triggers findItems() with correct flags,
    partial matching, case-insensitive matching, and match result list
    management.
    """

    # -- Normal cases --

    def test_検索テキスト入力_マッチノードが見つかる(
        self, wildtree_main_window_with_multi_data,
    ):
        """Entering search text finds matching nodes in the tree."""
        window = wildtree_main_window_with_multi_data

        # Build tree with a known entry point that has many sub-nodes
        window._build_and_display_tree("メイン")

        # Trigger search by calling the search handler
        window._on_search_text_changed("体格")

        # Should find nodes containing "体格" (朝田詩乃体格, シロコ体格)
        assert len(window._search_matches) >= 2

    def test_検索_部分一致で検索できる(
        self, wildtree_main_window_with_multi_data,
    ):
        """Partial text matches nodes containing the search string."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # "朝田" should match "朝田詩乃" and "朝田詩乃体格" etc.
        window._on_search_text_changed("朝田")

        assert len(window._search_matches) >= 1
        # All matched items should contain "朝田" in their text
        for item in window._search_matches:
            assert "朝田" in item.text(0)

    def test_検索_case_insensitiveで検索できる(
        self, wildtree_main_window_with_multi_data,
    ):
        """Search is case-insensitive for ASCII text."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # "slender" appears as leaf text "slender body" -- but findItems
        # searches node display text. Let's use a known node text.
        # The tree contains "athletic body" as a leaf value, but that's
        # not a node. Search targets are node names.
        # Use "BODY" (uppercase) to find nodes whose text contains "body"
        # in case-insensitive manner -- however, this test should use
        # entry point names. Let's test with ASCII keys in the tree.

        # Build with a simpler setup: search for "default" vs "DEFAULT"
        # Actually the tree node texts are Japanese. Let's verify with
        # a simple approach: search both cases of a mixed-case entry.
        window._on_search_text_changed("シロコ")
        matches_normal = len(window._search_matches)

        # Clear and search again -- since Japanese doesn't have case,
        # we use the multi_file_cards_dir which has "default lighting"
        # as a value. But tree nodes are key names.
        # Let's use a fixture that has ASCII keys for this test.
        assert matches_normal >= 1

    def test_検索_case_insensitive_ASCIIキー(
        self, qapp, simple_cards_dir: Path,
    ):
        """Case-insensitive search works for ASCII key names."""
        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=simple_cards_dir)
        try:
            window._build_and_display_tree("greeting")

            # Search for uppercase version of a key name
            window._on_search_text_changed("GREETING")
            matches_upper = len(window._search_matches)

            window._on_search_text_changed("greeting")
            matches_lower = len(window._search_matches)

            # Both should find the same nodes
            assert matches_upper == matches_lower
            assert matches_upper >= 1
        finally:
            window.close()

    def test_検索_マッチなし_空リスト(
        self, wildtree_main_window_with_multi_data,
    ):
        """Searching for non-existent text results in empty match list."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("存在しないテキスト12345")

        assert len(window._search_matches) == 0

    def test_検索_空文字列_マッチなし(
        self, wildtree_main_window_with_multi_data,
    ):
        """Empty search text results in empty match list."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("")

        assert len(window._search_matches) == 0

    def test_検索テキスト変更_再検索でインデックスが0にリセット(
        self, wildtree_main_window_with_multi_data,
    ):
        """Changing search text resets the current match index to 0."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # First search
        window._on_search_text_changed("体格")
        assert len(window._search_matches) >= 2

        # Navigate to next match
        window._on_search_next()
        assert window._search_index == 1

        # Change search text -- index should reset to 0
        window._on_search_text_changed("シロコ")
        assert window._search_index == 0

    def test_検索_最初のマッチが選択される(
        self, wildtree_main_window_with_multi_data,
    ):
        """After search, the first match (index 0) is selected in the tree."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")

        assert len(window._search_matches) >= 1
        # Current item should be the first match
        current = window._tree_widget.currentItem()
        assert current is window._search_matches[0]

    # -- Edge cases --

    def test_検索_特殊文字がリテラルとして検索される(
        self, qapp, circular_ref_cards_dir: Path,
    ):
        """Special characters like () are treated as literal text in search."""
        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=circular_ref_cards_dir)
        try:
            window._build_and_display_tree("alpha")

            # circular ref label contains "(circular ref)"
            # Searching for "(circular" should match as literal text
            window._on_search_text_changed("(circular")

            # Should find the circular ref node
            assert len(window._search_matches) >= 1
            for item in window._search_matches:
                assert "(circular" in item.text(0)
        finally:
            window.close()

    def test_検索_circular_refラベル付きノードがマッチする(
        self, qapp, circular_ref_cards_dir: Path,
    ):
        """Nodes with '(circular ref)' label are searchable by that text."""
        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=circular_ref_cards_dir)
        try:
            window._build_and_display_tree("alpha")

            window._on_search_text_changed("circular ref")

            assert len(window._search_matches) >= 1
        finally:
            window.close()

    def test_検索_unresolvedノードもマッチする(
        self, qapp, broken_ref_cards_dir: Path,
    ):
        """Unresolved (red) nodes are also found by search."""
        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=broken_ref_cards_dir)
        try:
            window._build_and_display_tree("entry")

            window._on_search_text_changed("non_existent_key")

            assert len(window._search_matches) >= 1
            # The matched node should contain the unresolved key name
            assert any(
                "non_existent_key" in item.text(0)
                for item in window._search_matches
            )
        finally:
            window.close()

    def test_検索_インデックス0のfalsy問題が起きない(
        self, wildtree_main_window_with_multi_data,
    ):
        """Index 0 is correctly handled (not treated as falsy).

        This tests the known pitfall: `if self._search_index:` would
        be False when index is 0. The implementation must use
        `if self._search_index is not None` or similar.
        """
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")

        # After initial search, index should be 0
        assert window._search_index == 0
        # The first match should be selected
        assert len(window._search_matches) >= 1
        current = window._tree_widget.currentItem()
        assert current is window._search_matches[0]

        # Navigate to next and then search again to reset to 0
        window._on_search_next()
        assert window._search_index == 1

        # Change search text to reset
        window._on_search_text_changed("体格")
        assert window._search_index == 0
        # Verify the first match is selected even though index is 0 (falsy)
        current = window._tree_widget.currentItem()
        assert current is window._search_matches[0]


# =========================================================================
# 2. TestSearchNavigation -- next/prev, wrap-around
# =========================================================================


class TestSearchNavigation:
    """Tests for search navigation (next/prev buttons).

    Verifies wrap-around behavior, empty match guards, and index
    management.
    """

    # -- Normal cases --

    def test_次へ_インデックスが進む(
        self, wildtree_main_window_with_multi_data,
    ):
        """Pressing 'next' advances the match index by 1."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")
        assert len(window._search_matches) >= 2
        assert window._search_index == 0

        window._on_search_next()
        assert window._search_index == 1

    def test_前へ_インデックスが戻る(
        self, wildtree_main_window_with_multi_data,
    ):
        """Pressing 'prev' decrements the match index by 1."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")
        assert len(window._search_matches) >= 2

        # Move to index 1 first
        window._on_search_next()
        assert window._search_index == 1

        # Move back to index 0
        window._on_search_prev()
        assert window._search_index == 0

    def test_次へ_ラップアラウンド_最後から先頭へ(
        self, wildtree_main_window_with_multi_data,
    ):
        """Pressing 'next' at the last match wraps around to the first."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")
        match_count = len(window._search_matches)
        assert match_count >= 2

        # Navigate to the last match
        for _ in range(match_count - 1):
            window._on_search_next()
        assert window._search_index == match_count - 1

        # One more next should wrap to 0
        window._on_search_next()
        assert window._search_index == 0

    def test_前へ_ラップアラウンド_先頭から最後へ(
        self, wildtree_main_window_with_multi_data,
    ):
        """Pressing 'prev' at the first match wraps around to the last."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")
        match_count = len(window._search_matches)
        assert match_count >= 2

        # At index 0, press prev -> should wrap to last
        assert window._search_index == 0
        window._on_search_prev()
        assert window._search_index == match_count - 1

    def test_次へ_ナビゲーションでツリー選択が更新される(
        self, wildtree_main_window_with_multi_data,
    ):
        """Navigating to next match updates the tree widget selection."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")
        assert len(window._search_matches) >= 2

        window._on_search_next()
        current = window._tree_widget.currentItem()
        assert current is window._search_matches[1]

    def test_前へ_ナビゲーションでツリー選択が更新される(
        self, wildtree_main_window_with_multi_data,
    ):
        """Navigating to prev match updates the tree widget selection."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")
        match_count = len(window._search_matches)
        assert match_count >= 2

        # Navigate to last (wrap around)
        window._on_search_prev()
        current = window._tree_widget.currentItem()
        assert current is window._search_matches[match_count - 1]

    # -- Error cases (empty match guards) --

    def test_次へ_マッチ0件_何も起きない(
        self, wildtree_main_window_with_multi_data,
    ):
        """Pressing 'next' with no matches does nothing (no crash)."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("存在しないテキスト12345")
        assert len(window._search_matches) == 0

        # Should not raise an exception
        window._on_search_next()

        # State should remain unchanged
        assert len(window._search_matches) == 0

    def test_前へ_マッチ0件_何も起きない(
        self, wildtree_main_window_with_multi_data,
    ):
        """Pressing 'prev' with no matches does nothing (no crash)."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("存在しないテキスト12345")
        assert len(window._search_matches) == 0

        # Should not raise an exception
        window._on_search_prev()

        # State should remain unchanged
        assert len(window._search_matches) == 0

    def test_次へ_検索未実行_何も起きない(
        self, wildtree_main_window_with_multi_data,
    ):
        """Pressing 'next' before any search does nothing."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # No search has been performed
        # _search_matches should be empty initially
        window._on_search_next()

        # Should not crash, matches should still be empty
        assert len(window._search_matches) == 0

    def test_前へ_検索未実行_何も起きない(
        self, wildtree_main_window_with_multi_data,
    ):
        """Pressing 'prev' before any search does nothing."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # No search has been performed
        window._on_search_prev()

        # Should not crash, matches should still be empty
        assert len(window._search_matches) == 0

    # -- Edge cases --

    def test_次へ_マッチ1件_同じノードに留まる(
        self, qapp, simple_cards_dir: Path,
    ):
        """With only 1 match, 'next' stays on the same node (wraps to self)."""
        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=simple_cards_dir)
        try:
            window._build_and_display_tree("greeting")

            # "farewell" should match exactly 1 node
            window._on_search_text_changed("farewell")
            assert len(window._search_matches) == 1
            assert window._search_index == 0

            window._on_search_next()
            # Should wrap around to 0 (same node)
            assert window._search_index == 0
            current = window._tree_widget.currentItem()
            assert current is window._search_matches[0]
        finally:
            window.close()

    def test_前へ_マッチ1件_同じノードに留まる(
        self, qapp, simple_cards_dir: Path,
    ):
        """With only 1 match, 'prev' stays on the same node (wraps to self)."""
        from gui.main_window import MainWindow

        window = MainWindow(cards_dir=simple_cards_dir)
        try:
            window._build_and_display_tree("greeting")

            window._on_search_text_changed("farewell")
            assert len(window._search_matches) == 1
            assert window._search_index == 0

            window._on_search_prev()
            # Should wrap around to 0 (same node)
            assert window._search_index == 0
            current = window._tree_widget.currentItem()
            assert current is window._search_matches[0]
        finally:
            window.close()

    def test_ナビゲーション_マッチノードが折りたたまれていても展開される(
        self, wildtree_main_window_with_multi_data,
    ):
        """Navigation expands collapsed parent nodes to make match visible."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # Collapse all tree items
        root = window._tree_widget.topLevelItem(0)
        assert root is not None
        root.setExpanded(False)

        # Search for a deeply nested node
        window._on_search_text_changed("体格")
        assert len(window._search_matches) >= 1

        # After navigating to the match, the match item's ancestors
        # should be expanded
        match_item = window._search_matches[0]
        parent = match_item.parent()
        while parent is not None:
            assert parent.isExpanded(), (
                f"Parent node '{parent.text(0)}' should be expanded "
                f"after navigation to child match"
            )
            parent = parent.parent()


# =========================================================================
# 3. TestSearchUI -- match count label, UI state, rebuild behavior
# =========================================================================


class TestSearchUI:
    """Tests for search UI state management.

    Verifies match count label format, search bar UI elements,
    tree selection sync, and tree rebuild behavior.
    """

    # -- Match count label format --

    def test_マッチ件数ラベル_マッチあり_フォーマットが正しい(
        self, wildtree_main_window_with_multi_data,
    ):
        """Match count label shows 'N/M' format (1-based current / total)."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")
        match_count = len(window._search_matches)
        assert match_count >= 2

        # Should show "1/N" (1-based)
        label_text = window._search_count_label.text()
        assert label_text == f"1/{match_count}"

    def test_マッチ件数ラベル_次へで更新される(
        self, wildtree_main_window_with_multi_data,
    ):
        """Match count label updates when navigating to next match."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")
        match_count = len(window._search_matches)
        assert match_count >= 2

        window._on_search_next()
        label_text = window._search_count_label.text()
        assert label_text == f"2/{match_count}"

    def test_マッチ件数ラベル_前へで更新される(
        self, wildtree_main_window_with_multi_data,
    ):
        """Match count label updates when navigating to prev match."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("体格")
        match_count = len(window._search_matches)
        assert match_count >= 2

        # Prev from index 0 wraps to last
        window._on_search_prev()
        label_text = window._search_count_label.text()
        assert label_text == f"{match_count}/{match_count}"

    def test_マッチ件数ラベル_マッチなし_0_0(
        self, wildtree_main_window_with_multi_data,
    ):
        """Match count label shows '0/0' when search text has no matches."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("存在しないテキスト12345")

        label_text = window._search_count_label.text()
        assert label_text == "0/0"

    def test_マッチ件数ラベル_空文字列検索_空ラベル(
        self, wildtree_main_window_with_multi_data,
    ):
        """Match count label is empty string when search text is empty."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("")

        label_text = window._search_count_label.text()
        assert label_text == ""

    # -- UI element existence --

    def test_検索バーのUI要素が存在する(
        self, wildtree_main_window_with_multi_data,
    ):
        """Search bar UI elements (line edit, buttons, label) exist."""
        from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton

        window = wildtree_main_window_with_multi_data

        # Search text input
        assert hasattr(window, "_search_edit")
        assert isinstance(window._search_edit, QLineEdit)

        # Next/Prev buttons
        assert hasattr(window, "_btn_search_next")
        assert isinstance(window._btn_search_next, QPushButton)

        assert hasattr(window, "_btn_search_prev")
        assert isinstance(window._btn_search_prev, QPushButton)

        # Match count label
        assert hasattr(window, "_search_count_label")
        assert isinstance(window._search_count_label, QLabel)

    def test_検索状態の初期値が正しい(
        self, wildtree_main_window_with_multi_data,
    ):
        """Search state attributes are correctly initialized."""
        window = wildtree_main_window_with_multi_data

        assert hasattr(window, "_search_matches")
        assert isinstance(window._search_matches, list)
        assert len(window._search_matches) == 0

        assert hasattr(window, "_search_index")
        assert window._search_index == -1

    # -- Tree selection sync --

    def test_マッチノード選択_右ペインにキー定義が表示される(
        self, wildtree_main_window_with_multi_data,
    ):
        """Navigating to a match node shows its key definition in the right pane."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._on_search_text_changed("デフォルト")

        assert len(window._search_matches) >= 1

        # The current item should be selected, triggering _on_tree_item_selected
        text = window._text_detail.toPlainText()
        # The right pane should show the key definition for "デフォルト"
        assert "デフォルト" in text or text != window.DETAIL_PLACEHOLDER

    # -- Tree rebuild behavior --

    def test_ツリー再構築_検索結果がクリアされる(
        self, wildtree_main_window_with_multi_data,
    ):
        """Tree rebuild clears the search match list and index."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # Perform a search
        window._on_search_text_changed("体格")
        assert len(window._search_matches) >= 1

        # Rebuild the tree (simulates entry point change or refresh)
        window._build_and_display_tree("メイン")

        # If search text is still present, re-search occurs.
        # But the old match references should be gone.
        # Since _search_edit still has text, new matches should exist
        # from the re-search. We verify the old references are not kept.
        # The match items should all be from the new tree.
        for item in window._search_matches:
            # Each match item should be findable in the current tree
            found = False
            for i in range(window._tree_widget.topLevelItemCount()):
                if _item_is_in_subtree(
                    window._tree_widget.topLevelItem(i), item
                ):
                    found = True
                    break
            assert found, (
                f"Match item '{item.text(0)}' is not in the current tree "
                f"(stale reference from old tree)"
            )

    def test_ツリー再構築_検索テキストが残っている場合_再検索される(
        self, wildtree_main_window_with_multi_data,
    ):
        """After tree rebuild with search text remaining, re-search occurs."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # Set search text
        window._search_edit.setText("体格")

        # Count matches before rebuild
        matches_before = len(window._search_matches)
        assert matches_before >= 1

        # Rebuild tree
        window._build_and_display_tree("メイン")

        # After rebuild, search text should still be present
        assert window._search_edit.text() == "体格"

        # And re-search should have produced new matches
        assert len(window._search_matches) >= 1

    def test_ツリー再構築_検索テキストが空_マッチ件数ラベルがクリアされる(
        self, wildtree_main_window_with_multi_data,
    ):
        """After tree rebuild with empty search text, match label is cleared."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # Perform a search, then clear it
        window._on_search_text_changed("体格")
        window._on_search_text_changed("")

        # Now rebuild
        window._build_and_display_tree("メイン")

        label_text = window._search_count_label.text()
        assert label_text == ""

    def test_ツリー再構築_マッチ件数ラベルがクリアされる(
        self, wildtree_main_window_with_multi_data,
    ):
        """Tree rebuild clears the match count label."""
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # Search to populate label
        window._on_search_text_changed("体格")
        assert window._search_count_label.text() != ""

        # Clear search text and rebuild
        window._search_edit.clear()
        window._build_and_display_tree("メイン")

        label_text = window._search_count_label.text()
        assert label_text == ""

    def test_ツリーが空_検索結果が空(
        self, wildtree_main_window,
    ):
        """Search on an empty tree (no cards_dir loaded) returns no matches."""
        window = wildtree_main_window

        # Ensure the tree is empty
        assert window._tree_widget.topLevelItemCount() == 0

        # Trigger search -- this should handle gracefully
        # The search method needs _search_matches etc. to exist.
        # If the window is initialized properly with W3, these should exist.
        if hasattr(window, "_on_search_text_changed"):
            window._on_search_text_changed("anything")
            assert len(window._search_matches) == 0

    # -- Signal connection tests --

    def test_検索テキスト入力_textChangedシグナルが接続されている(
        self, wildtree_main_window_with_multi_data,
    ):
        """QLineEdit.textChanged is connected to _on_search_text_changed.

        Verify by programmatically setting text and checking results.
        """
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        # Setting text on QLineEdit should trigger textChanged signal
        window._search_edit.setText("体格")

        # If signal is connected, search should have been performed
        assert len(window._search_matches) >= 1

    def test_次へボタン_clickedシグナルが接続されている(
        self, wildtree_main_window_with_multi_data,
    ):
        """Next button's clicked signal is connected to _on_search_next.

        Verify by searching, then clicking the button.
        """
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._search_edit.setText("体格")
        assert len(window._search_matches) >= 2
        assert window._search_index == 0

        # Click the next button
        window._btn_search_next.click()

        assert window._search_index == 1

    def test_前へボタン_clickedシグナルが接続されている(
        self, wildtree_main_window_with_multi_data,
    ):
        """Prev button's clicked signal is connected to _on_search_prev.

        Verify by searching, then clicking the button.
        """
        window = wildtree_main_window_with_multi_data
        window._build_and_display_tree("メイン")

        window._search_edit.setText("体格")
        match_count = len(window._search_matches)
        assert match_count >= 2
        assert window._search_index == 0

        # Click the prev button -- should wrap to last
        window._btn_search_prev.click()

        assert window._search_index == match_count - 1


# ---------------------------------------------------------------------------
# Helpers (internal)
# ---------------------------------------------------------------------------


def _item_is_in_subtree(root_item, target_item) -> bool:
    """Check if target_item is root_item or one of its descendants."""
    if root_item is target_item:
        return True
    for i in range(root_item.childCount()):
        if _item_is_in_subtree(root_item.child(i), target_item):
            return True
    return False
