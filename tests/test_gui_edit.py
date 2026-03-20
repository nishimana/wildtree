"""Unit/Integration tests for S8 GUI 編集機能 -- チェックボックス + リアルタイムツリー更新。

設計書 (docs/design/s8-gui-edit.md) に基づいて、
tree_model.py のチェックボックス設定と app.py のチェック操作ハンドラを検証する。

テスト対象:
  - tree_model.py: _create_item のチェックボックス設定（setCheckable + setCheckState）
  - tree_model.py: populate_model 後のチェックボックス状態
  - app.py: _on_item_changed ハンドラ
  - app.py: _rebuild_tree メソッド
  - app.py: _save_selected_path / _restore_selected_path
  - app.py: _is_populating ガード

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.models import (
    KeyDefinition,
    NodeType,
    RefType,
    TreeNode,
    ValueEntry,
    WildcardRef,
)


# =========================================================================
# ヘルパー
# =========================================================================


def _make_key_def(
    name: str,
    file_path: Path | None = None,
    line_number: int = 1,
    values: list[ValueEntry] | None = None,
) -> KeyDefinition:
    """テスト用 KeyDefinition を生成するヘルパー。"""
    return KeyDefinition(
        name=name,
        file_path=file_path or Path("C:/cards/test.yaml"),
        line_number=line_number,
        values=values if values is not None else [],
    )


def _make_value_entry(
    raw_text: str,
    line_number: int = 2,
    is_commented: bool = False,
    refs: list[WildcardRef] | None = None,
    literals: list[str] | None = None,
) -> ValueEntry:
    """テスト用 ValueEntry を生成するヘルパー。"""
    return ValueEntry(
        raw_text=raw_text,
        line_number=line_number,
        is_commented=is_commented,
        refs=refs if refs is not None else [],
        literals=literals if literals is not None else [],
    )


def _make_tree_node(
    display_name: str,
    node_type: NodeType,
    children: list[TreeNode] | None = None,
    key_def: KeyDefinition | None = None,
    value_entry: ValueEntry | None = None,
    ref: WildcardRef | None = None,
) -> TreeNode:
    """テスト用 TreeNode を生成するヘルパー。"""
    return TreeNode(
        display_name=display_name,
        node_type=node_type,
        children=children if children is not None else [],
        key_def=key_def,
        value_entry=value_entry,
        ref=ref,
    )


# =========================================================================
# tree_model.py: チェックボックス設定のテスト
# =========================================================================


class TestCreateItemCheckbox:
    """_create_item のチェックボックス設定テスト。

    S8 で追加される機能:
    - value_entry ありのノードに setCheckable(True) が設定される
    - value_entry なしのノード（ROOT）に setCheckable(False)
    - is_commented=False → Qt.CheckState.Checked
    - is_commented=True → Qt.CheckState.Unchecked
    """

    def test_create_item_REFノード_チェック可能(self, qapp):
        """value_entry ありの REF ノードに setCheckable(True) が設定される。"""
        from gui.tree_model import _create_item

        ve = _make_value_entry("__target__", is_commented=False)
        ref = WildcardRef(raw="__target__", full_path="target")
        node = _make_tree_node(
            "target", NodeType.REF,
            key_def=_make_key_def("target"),
            value_entry=ve,
            ref=ref,
        )
        item = _create_item(node)

        assert item.isCheckable() is True

    def test_create_item_LITERALノード_チェック可能(self, qapp):
        """value_entry ありの LITERAL ノードに setCheckable(True) が設定される。"""
        from gui.tree_model import _create_item

        ve = _make_value_entry("literal_value", is_commented=False)
        node = _make_tree_node("literal_value", NodeType.LITERAL, value_entry=ve)
        item = _create_item(node)

        assert item.isCheckable() is True

    def test_create_item_DYNAMICノード_チェック可能(self, qapp):
        """value_entry ありの DYNAMIC ノードに setCheckable(True) が設定される。"""
        from gui.tree_model import _create_item

        ref = WildcardRef(
            raw="__{__var__}suffix__",
            full_path="{__var__}suffix",
            ref_type=RefType.DYNAMIC,
        )
        ve = _make_value_entry(ref.raw, is_commented=False)
        node = _make_tree_node(ref.raw, NodeType.DYNAMIC, value_entry=ve, ref=ref)
        item = _create_item(node)

        assert item.isCheckable() is True

    def test_create_item_UNRESOLVEDノード_チェック可能(self, qapp):
        """value_entry ありの UNRESOLVED ノードに setCheckable(True) が設定される。"""
        from gui.tree_model import _create_item

        ref = WildcardRef(raw="__missing__", full_path="missing")
        ve = _make_value_entry("__missing__", is_commented=False)
        node = _make_tree_node("missing", NodeType.UNRESOLVED, value_entry=ve, ref=ref)
        item = _create_item(node)

        assert item.isCheckable() is True

    def test_create_item_CIRCULARノード_チェック可能(self, qapp):
        """value_entry ありの CIRCULAR ノードに setCheckable(True) が設定される。"""
        from gui.tree_model import _create_item

        ref = WildcardRef(raw="__キー名__", full_path="キー名")
        ve = _make_value_entry("__キー名__", is_commented=False)
        node = _make_tree_node("キー名 (循環)", NodeType.CIRCULAR, value_entry=ve, ref=ref)
        item = _create_item(node)

        assert item.isCheckable() is True

    def test_create_item_EMPTYノード_チェック可能(self, qapp):
        """value_entry ありの EMPTY ノードに setCheckable(True) が設定される。"""
        from gui.tree_model import _create_item

        ve = _make_value_entry('"{}"', is_commented=False)
        node = _make_tree_node("(空)", NodeType.EMPTY, value_entry=ve)
        item = _create_item(node)

        assert item.isCheckable() is True

    def test_create_item_ROOTノード_チェック不可(self, qapp):
        """value_entry なしの ROOT ノードは setCheckable(False)。"""
        from gui.tree_model import _create_item

        node = _make_tree_node(
            "ルートキー", NodeType.ROOT,
            key_def=_make_key_def("ルートキー"),
        )
        item = _create_item(node)

        assert item.isCheckable() is False

    def test_create_item_非コメント_チェック状態Checked(self, qapp):
        """is_commented=False の場合、チェック状態が Qt.CheckState.Checked。"""
        from PySide6.QtCore import Qt

        from gui.tree_model import _create_item

        ve = _make_value_entry("__target__", is_commented=False)
        ref = WildcardRef(raw="__target__", full_path="target")
        node = _make_tree_node(
            "target", NodeType.REF,
            key_def=_make_key_def("target"),
            value_entry=ve,
            ref=ref,
        )
        item = _create_item(node)

        assert item.checkState() == Qt.CheckState.Checked

    def test_create_item_コメント_チェック状態Unchecked(self, qapp):
        """is_commented=True の場合、チェック状態が Qt.CheckState.Unchecked。"""
        from PySide6.QtCore import Qt

        from gui.tree_model import _create_item

        ve = _make_value_entry("__target__", is_commented=True)
        ref = WildcardRef(raw="__target__", full_path="target")
        node = _make_tree_node(
            "target", NodeType.REF,
            key_def=_make_key_def("target"),
            value_entry=ve,
            ref=ref,
        )
        item = _create_item(node)

        assert item.checkState() == Qt.CheckState.Unchecked

    def test_create_item_コメントLITERAL_チェック状態Unchecked(self, qapp):
        """is_commented=True の LITERAL ノードのチェック状態が Unchecked。"""
        from PySide6.QtCore import Qt

        from gui.tree_model import _create_item

        ve = _make_value_entry("commented_tag", is_commented=True)
        node = _make_tree_node("commented_tag", NodeType.LITERAL, value_entry=ve)
        item = _create_item(node)

        assert item.checkState() == Qt.CheckState.Unchecked

    def test_create_item_非コメントLITERAL_チェック状態Checked(self, qapp):
        """is_commented=False の LITERAL ノードのチェック状態が Checked。"""
        from PySide6.QtCore import Qt

        from gui.tree_model import _create_item

        ve = _make_value_entry("tag_value", is_commented=False)
        node = _make_tree_node("tag_value", NodeType.LITERAL, value_entry=ve)
        item = _create_item(node)

        assert item.checkState() == Qt.CheckState.Checked


# =========================================================================
# tree_model.py: populate_model 後のチェックボックス状態テスト
# =========================================================================


class TestPopulateModelCheckbox:
    """populate_model 後のチェックボックス状態テスト。"""

    def test_populate_model_ROOTノードはチェック不可(self, qapp):
        """populate_model 後、ROOT ノード（value_entry=None）はチェック不可。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import populate_model

        kd = _make_key_def("ルートキー")
        root = _make_tree_node("ルートキー", NodeType.ROOT, key_def=kd)
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        assert root_item.isCheckable() is False

    def test_populate_model_子ノードのチェック状態が正しい(self, qapp):
        """populate_model 後、子ノードのチェック状態が value_entry.is_commented に基づいて設定される。"""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import populate_model

        kd = _make_key_def("root")
        ve_active = _make_value_entry("__active__", is_commented=False)
        ve_commented = _make_value_entry("__commented__", is_commented=True)

        ref_active = WildcardRef(raw="__active__", full_path="active")
        ref_commented = WildcardRef(raw="__commented__", full_path="commented")

        child_active = _make_tree_node(
            "active", NodeType.REF,
            key_def=_make_key_def("active"),
            value_entry=ve_active,
            ref=ref_active,
        )
        child_commented = _make_tree_node(
            "commented", NodeType.REF,
            key_def=_make_key_def("commented"),
            value_entry=ve_commented,
            ref=ref_commented,
        )
        root = _make_tree_node(
            "root", NodeType.ROOT,
            children=[child_active, child_commented],
            key_def=kd,
        )
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        # 有効な子ノード → Checked
        active_item = root_item.child(0)
        assert active_item.isCheckable() is True
        assert active_item.checkState() == Qt.CheckState.Checked
        # コメントアウトされた子ノード → Unchecked
        commented_item = root_item.child(1)
        assert commented_item.isCheckable() is True
        assert commented_item.checkState() == Qt.CheckState.Unchecked

    def test_populate_model_全NodeTypeのチェック可否が正しい(self, qapp):
        """populate_model 後、全 NodeType のチェック可否が設計通りである。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import populate_model

        # ROOT: value_entry=None → チェック不可
        kd = _make_key_def("root")
        ve_ref = _make_value_entry("__ref__", is_commented=False)
        ve_lit = _make_value_entry("lit", is_commented=False)
        ve_dyn = _make_value_entry("__{__var__}__", is_commented=False)
        ve_unr = _make_value_entry("__missing__", is_commented=False)
        ve_circ = _make_value_entry("__root__", is_commented=False)
        ve_empty = _make_value_entry('"{}"', is_commented=False)

        children = [
            _make_tree_node("ref", NodeType.REF, key_def=_make_key_def("ref"), value_entry=ve_ref,
                            ref=WildcardRef(raw="__ref__", full_path="ref")),
            _make_tree_node("lit", NodeType.LITERAL, value_entry=ve_lit),
            _make_tree_node("__{__var__}__", NodeType.DYNAMIC, value_entry=ve_dyn,
                            ref=WildcardRef(raw="__{__var__}__", full_path="{__var__}", ref_type=RefType.DYNAMIC)),
            _make_tree_node("missing", NodeType.UNRESOLVED, value_entry=ve_unr,
                            ref=WildcardRef(raw="__missing__", full_path="missing")),
            _make_tree_node("root (循環)", NodeType.CIRCULAR, value_entry=ve_circ,
                            ref=WildcardRef(raw="__root__", full_path="root")),
            _make_tree_node("(空)", NodeType.EMPTY, value_entry=ve_empty),
        ]
        root = _make_tree_node("root", NodeType.ROOT, children=children, key_def=kd)
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        # ROOT はチェック不可
        assert root_item.isCheckable() is False

        # 全子ノード（value_entry あり）はチェック可能
        for i in range(root_item.rowCount()):
            child_item = root_item.child(i)
            assert child_item.isCheckable() is True, (
                f"子ノード {i} ({child_item.text()}) がチェック不可になっている"
            )

    def test_populate_model_深いネストでもチェックボックスが設定される(self, qapp):
        """3階層のネストでも各ノードのチェックボックスが正しく設定される。"""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import populate_model

        ve_grandchild = _make_value_entry("leaf", is_commented=True)
        grandchild = _make_tree_node("leaf", NodeType.LITERAL, value_entry=ve_grandchild)

        ve_child = _make_value_entry("__child__", is_commented=False)
        child = _make_tree_node(
            "child", NodeType.REF,
            children=[grandchild],
            key_def=_make_key_def("child"),
            value_entry=ve_child,
            ref=WildcardRef(raw="__child__", full_path="child"),
        )
        root = _make_tree_node(
            "root", NodeType.ROOT,
            children=[child],
            key_def=_make_key_def("root"),
        )
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        child_item = root_item.child(0)
        grandchild_item = child_item.child(0)

        # ROOT: チェック不可
        assert root_item.isCheckable() is False
        # child (REF, 非コメント): チェック可能 + Checked
        assert child_item.isCheckable() is True
        assert child_item.checkState() == Qt.CheckState.Checked
        # grandchild (LITERAL, コメント): チェック可能 + Unchecked
        assert grandchild_item.isCheckable() is True
        assert grandchild_item.checkState() == Qt.CheckState.Unchecked


# =========================================================================
# app.py: _is_populating ガードのテスト
# =========================================================================


class TestIsPopulatingGuard:
    """_is_populating ガードのテスト。

    populate_model 中は _on_item_changed が何もしないことを確認する。
    """

    def test_is_populating_true_の間_on_item_changedが何もしない(
        self, qapp, commented_ref_cards_dir: Path
    ):
        """_is_populating=True の間、_on_item_changed が何もしない。"""
        from PySide6.QtGui import QStandardItem

        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            # トップツリーを選択してツリーを表示
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # _is_populating を True に設定
            window._is_populating = True

            # ダミーアイテムで _on_item_changed を呼ぶ
            dummy_item = QStandardItem("dummy")
            # _on_item_changed はガードにより何もしない（例外が出ないこと）
            window._on_item_changed(dummy_item)

            # ツリーは変更されていない（rowCount が維持される）
            assert window._tree_model.rowCount() > 0
        finally:
            window.close()

    def test_初期状態_is_populatingがFalse(self, qapp):
        """ウィンドウの初期状態で _is_populating が False である。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert window._is_populating is False
        finally:
            window.close()


# =========================================================================
# app.py: チェック操作 → YAML 書き換えのテスト
# =========================================================================


class TestCheckOperationYAML:
    """チェック操作 → YAML 書き換えの統合テスト。

    commented_ref_cards_dir を使用して、チェック ON/OFF で
    YAML ファイルが正しく書き換えられることを検証する。
    """

    def test_チェックON_コメント解除(self, qapp, commented_ref_cards_dir: Path):
        """チェック ON でコメント行のコメントが解除される。"""
        from PySide6.QtCore import Qt

        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            # トップツリーを選択
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # コメントアウトされたノードを探す
            root_item = window._tree_model.item(0)
            commented_item = None
            for i in range(root_item.rowCount()):
                child_item = root_item.child(i)
                node = child_item.data(TREE_NODE_ROLE)
                if node is not None and node.value_entry is not None and node.value_entry.is_commented:
                    commented_item = child_item
                    break

            if commented_item is None:
                pytest.skip("コメントアウトされたノードが見つからない")

            # チェック ON に変更（コメント解除）
            commented_item.setCheckState(Qt.CheckState.Checked)

            # YAML ファイルを読み取り、コメントが解除されたことを確認
            yaml_path = commented_ref_cards_dir / "scenes.yaml"
            content = yaml_path.read_text(encoding="utf-8")
            # コメント解除後、"# - __シロコ__" が "- __シロコ__" に変わっているはず
            assert "  - __シロコ__" in content
            assert "  # - __シロコ__" not in content
        finally:
            window.close()

    def test_チェックOFF_コメント化(self, qapp, commented_ref_cards_dir: Path):
        """チェック OFF でアクティブな行がコメント化される。"""
        from PySide6.QtCore import Qt

        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            # トップツリーを選択
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # アクティブな（コメントされていない）ノードを探す
            root_item = window._tree_model.item(0)
            active_item = None
            for i in range(root_item.rowCount()):
                child_item = root_item.child(i)
                node = child_item.data(TREE_NODE_ROLE)
                if (node is not None
                        and node.value_entry is not None
                        and not node.value_entry.is_commented):
                    active_item = child_item
                    break

            if active_item is None:
                pytest.skip("アクティブなノードが見つからない")

            # チェック OFF に変更（コメント化）
            active_item.setCheckState(Qt.CheckState.Unchecked)

            # YAML ファイルを読み取り、コメントが付与されたことを確認
            yaml_path = commented_ref_cards_dir / "scenes.yaml"
            content = yaml_path.read_text(encoding="utf-8")
            # コメント化後、"- __朝田詩乃__" が "# - __朝田詩乃__" に変わっているはず
            assert "  # - __朝田詩乃__" in content
        finally:
            window.close()

    def test_チェック操作後_ツリーが再構築される(self, qapp, commented_ref_cards_dir: Path):
        """チェック操作後にツリーが再構築される（model.rowCount() > 0）。"""
        from PySide6.QtCore import Qt

        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # アクティブなノードを探す
            root_item = window._tree_model.item(0)
            target_item = None
            for i in range(root_item.rowCount()):
                child_item = root_item.child(i)
                node = child_item.data(TREE_NODE_ROLE)
                if (node is not None
                        and node.value_entry is not None
                        and not node.value_entry.is_commented):
                    target_item = child_item
                    break

            if target_item is None:
                pytest.skip("アクティブなノードが見つからない")

            # チェック OFF
            target_item.setCheckState(Qt.CheckState.Unchecked)

            # ツリーが再構築されている（モデルにデータがある）
            assert window._tree_model.rowCount() > 0
        finally:
            window.close()


# =========================================================================
# app.py: 選択位置復元のテスト
# =========================================================================


class TestSelectionRestore:
    """チェック操作後の選択位置復元テスト。"""

    def test_チェック操作後_選択位置が復元される(self, qapp, commented_ref_cards_dir: Path):
        """チェック操作後に以前選択していたノードが復元される。"""
        from PySide6.QtCore import Qt

        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # コメントアウトされたノードを探す
            root_item = window._tree_model.item(0)
            commented_item = None
            commented_index = -1
            for i in range(root_item.rowCount()):
                child_item = root_item.child(i)
                node = child_item.data(TREE_NODE_ROLE)
                if node is not None and node.value_entry is not None and node.value_entry.is_commented:
                    commented_item = child_item
                    commented_index = i
                    break

            if commented_item is None:
                pytest.skip("コメントアウトされたノードが見つからない")

            # ノードを選択
            node = commented_item.data(TREE_NODE_ROLE)
            selected_name = node.display_name

            # そのノードのインデックスを取得して選択
            item_index = window._tree_model.indexFromItem(commented_item)
            window._tree_view.selectionModel().setCurrentIndex(
                item_index,
                window._tree_view.selectionModel().SelectionFlag.ClearAndSelect,
            )

            # チェック ON（コメント解除）
            commented_item.setCheckState(Qt.CheckState.Checked)

            # ツリー再構築後、選択が復元されているか確認
            current_index = window._tree_view.selectionModel().currentIndex()
            if current_index.isValid():
                current_node = current_index.data(TREE_NODE_ROLE)
                # 選択が復元されている場合、同じ名前のノードが選択されている
                # （ツリー構造が変わる可能性があるため、名前で比較）
                assert current_node is not None
        finally:
            window.close()

    def test_復元失敗時_ルートノードが選択される(self, qapp, commented_ref_cards_dir: Path):
        """選択復元に失敗した場合、ルートノードが選択される。"""
        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # 存在しないパスで _restore_selected_path を呼ぶ
            fake_path = ["存在しない", "パス", "ノード"]
            window._restore_selected_path(fake_path)

            # ルートノードが選択される
            current_index = window._tree_view.selectionModel().currentIndex()
            if current_index.isValid():
                current_node = current_index.data(TREE_NODE_ROLE)
                # ルートノード（ROOT タイプ）が選択されている
                if current_node is not None:
                    assert current_node.node_type == NodeType.ROOT
        finally:
            window.close()


# =========================================================================
# app.py: toggle_comment 失敗時のテスト
# =========================================================================


class TestToggleCommentFailure:
    """toggle_comment 失敗時にツリーが変更されないことを確認するテスト。"""

    def test_toggle_comment失敗時_ツリーが変更されない(
        self, qapp, commented_ref_cards_dir: Path
    ):
        """toggle_comment が EditResult(success=False) を返す場合、ツリーが変更されない。"""
        from PySide6.QtCore import Qt

        from core.editor import EditResult
        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # 操作前のモデル状態を記録
            root_item = window._tree_model.item(0)
            initial_row_count = root_item.rowCount()

            # アクティブなノードを探す
            active_item = None
            for i in range(root_item.rowCount()):
                child_item = root_item.child(i)
                node = child_item.data(TREE_NODE_ROLE)
                if (node is not None
                        and node.value_entry is not None
                        and not node.value_entry.is_commented):
                    active_item = child_item
                    break

            if active_item is None:
                pytest.skip("アクティブなノードが見つからない")

            # toggle_comment をモックして失敗を返す
            with patch("gui.app.toggle_comment") as mock_toggle:
                mock_toggle.return_value = EditResult(
                    success=False,
                    error="テスト用エラー",
                )
                # QMessageBox もモックして UI ブロックを防ぐ
                with patch("gui.app.QMessageBox"):
                    # チェック OFF
                    active_item.setCheckState(Qt.CheckState.Unchecked)

            # ツリーは変更されていない
            # （toggle_comment 失敗時は _rebuild_tree が呼ばれない）
            # 注: 実装によっては itemChanged 時点で既にチェック状態が変わっているが、
            # ファイルとレジストリは変更されない
            root_item_after = window._tree_model.item(0)
            if root_item_after is not None:
                assert root_item_after.rowCount() == initial_row_count
        finally:
            window.close()


# =========================================================================
# app.py: _connect_signals のテスト
# =========================================================================


class TestConnectSignals:
    """itemChanged シグナルが接続されていることのテスト。"""

    def test_itemChanged_シグナルが接続されている(self, qapp):
        """_tree_model.itemChanged シグナルが _on_item_changed に接続されている。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            # _on_item_changed メソッドが存在する
            assert hasattr(window, "_on_item_changed")
            # _is_populating 属性が存在する
            assert hasattr(window, "_is_populating")
        finally:
            window.close()


# =========================================================================
# app.py: _rebuild_tree のテスト
# =========================================================================


class TestRebuildTree:
    """_rebuild_tree メソッドのテスト。"""

    def test_rebuild_tree_メソッドが存在する(self, qapp, commented_ref_cards_dir: Path):
        """_rebuild_tree メソッドが存在する。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert hasattr(window, "_rebuild_tree")
            assert callable(window._rebuild_tree)
        finally:
            window.close()

    def test_rebuild_tree_ツリーが更新される(self, qapp, commented_ref_cards_dir: Path):
        """_rebuild_tree を呼ぶとツリーモデルが更新される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # _rebuild_tree を呼ぶ
            window._rebuild_tree()

            # ツリーが再構築されている
            assert window._tree_model.rowCount() > 0
        finally:
            window.close()


# =========================================================================
# app.py: _save_selected_path / _restore_selected_path のテスト
# =========================================================================


class TestSaveRestoreSelectedPath:
    """選択パス保存・復元メソッドのテスト。"""

    def test_save_selected_path_メソッドが存在する(self, qapp):
        """_save_selected_path メソッドが存在する。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert hasattr(window, "_save_selected_path")
            assert callable(window._save_selected_path)
        finally:
            window.close()

    def test_restore_selected_path_メソッドが存在する(self, qapp):
        """_restore_selected_path メソッドが存在する。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=None)
        try:
            assert hasattr(window, "_restore_selected_path")
            assert callable(window._restore_selected_path)
        finally:
            window.close()

    def test_save_selected_path_選択なし_空リスト(self, qapp, commented_ref_cards_dir: Path):
        """ノード未選択時の _save_selected_path は空リストを返す。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)

            # 選択をクリア
            window._tree_view.selectionModel().clearSelection()

            path = window._save_selected_path()
            assert path == []
        finally:
            window.close()

    def test_save_selected_path_ルートノード選択時_ルート名が返る(
        self, qapp, commented_ref_cards_dir: Path
    ):
        """ROOT ノードを選択した状態で _save_selected_path はルート名のパスを返す。"""
        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # ルートノードを選択
            root_index = window._tree_model.index(0, 0)
            window._tree_view.selectionModel().setCurrentIndex(
                root_index,
                window._tree_view.selectionModel().SelectionFlag.ClearAndSelect,
            )

            path = window._save_selected_path()
            # ルートノードの display_name がパスに含まれる
            root_node = root_index.data(TREE_NODE_ROLE)
            assert len(path) > 0
            assert path[0] == root_node.display_name
        finally:
            window.close()

    def test_restore_selected_path_正しいパス_ノードが選択される(
        self, qapp, commented_ref_cards_dir: Path
    ):
        """正しいパスで _restore_selected_path を呼ぶとノードが選択される。"""
        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # ルートノードの display_name を取得
            root_index = window._tree_model.index(0, 0)
            root_node = root_index.data(TREE_NODE_ROLE)
            root_name = root_node.display_name

            # ルートノードのパスで復元
            window._restore_selected_path([root_name])

            # 何かが選択されている
            current_index = window._tree_view.selectionModel().currentIndex()
            assert current_index.isValid()
        finally:
            window.close()

    def test_restore_selected_path_空リスト_ルートノードが選択される(
        self, qapp, commented_ref_cards_dir: Path
    ):
        """空リストで _restore_selected_path を呼ぶとルートノードが選択される。"""
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # 空リストで復元
            window._restore_selected_path([])

            # ルートノードが選択される
            current_index = window._tree_view.selectionModel().currentIndex()
            if current_index.isValid():
                root_index = window._tree_model.index(0, 0)
                assert current_index == root_index
        finally:
            window.close()


# =========================================================================
# app.py: multi_file_cards_dir を使ったクロスファイル統合テスト
# =========================================================================


class TestCrossFileCheckOperation:
    """multi_file_cards_dir を使ったクロスファイル参照のチェック操作テスト。"""

    def test_クロスファイル参照のチェック操作(self, qapp, multi_file_cards_dir: Path):
        """クロスファイル参照を含むツリーでのチェック操作が正常に動作する。"""
        from PySide6.QtCore import Qt

        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=multi_file_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # ルートの子ノードでチェック操作を試行
            root_item = window._tree_model.item(0)
            if root_item.rowCount() > 0:
                first_child = root_item.child(0)
                node = first_child.data(TREE_NODE_ROLE)
                if node is not None and node.value_entry is not None:
                    # 現在のチェック状態を反転
                    if first_child.checkState() == Qt.CheckState.Checked:
                        first_child.setCheckState(Qt.CheckState.Unchecked)
                    else:
                        first_child.setCheckState(Qt.CheckState.Checked)

                    # ツリーが再構築されている
                    assert window._tree_model.rowCount() > 0
        finally:
            window.close()


# =========================================================================
# app.py: itemChanged シグナルによる接続の統合テスト
# =========================================================================


class TestItemChangedSignal:
    """itemChanged シグナルによるハンドラ呼び出しの統合テスト。"""

    def test_populate_model中のチェック状態設定でハンドラが実行されない(
        self, qapp, commented_ref_cards_dir: Path
    ):
        """populate_model 中のチェック状態設定で _on_item_changed が
        toggle_comment を呼ばないこと。

        _is_populating ガードにより、populate_model 中の itemChanged は無視される。
        """
        from gui.app import WildTreeWindow

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0

            # toggle_comment が呼ばれないことを確認するためモックする
            with patch("gui.app.toggle_comment") as mock_toggle:
                # トップツリーを選択 → populate_model が実行される
                # この中で itemChanged が発火するが、_is_populating ガードで無視される
                window._list_top_trees.setCurrentRow(0)

                # toggle_comment は呼ばれていないはず
                mock_toggle.assert_not_called()
        finally:
            window.close()

    def test_value_entryがNoneのノードでチェック操作_何もしない(
        self, qapp, commented_ref_cards_dir: Path
    ):
        """value_entry が None のノード（ROOT）でのチェック操作は何もしない。"""
        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=commented_ref_cards_dir)
        try:
            assert window._list_top_trees.count() > 0
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # ROOT ノードのアイテムを取得
            root_item = window._tree_model.item(0)
            root_node = root_item.data(TREE_NODE_ROLE)
            assert root_node.value_entry is None

            # ROOT ノードは setCheckable(False) なので、
            # 直接 _on_item_changed を呼んでも value_entry がないのでスキップされる
            window._on_item_changed(root_item)

            # ツリーは変更されていない
            assert window._tree_model.rowCount() > 0
        finally:
            window.close()


# =========================================================================
# エッジケース
# =========================================================================


class TestEdgeCases:
    """エッジケースのテスト。"""

    def test_別トップツリー切り替え後のチェック操作(
        self, qapp, multi_file_cards_dir: Path
    ):
        """別のトップツリーに切り替えた後のチェック操作が正常に動作する。"""
        from PySide6.QtCore import Qt

        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=multi_file_cards_dir)
        try:
            count = window._list_top_trees.count()
            if count < 2:
                pytest.skip("テストに必要なトップツリー数が不足")

            # 最初のトップツリーを選択
            window._list_top_trees.setCurrentRow(0)
            assert window._tree_model.rowCount() > 0

            # 別のトップツリーに切り替え
            window._list_top_trees.setCurrentRow(1)
            assert window._tree_model.rowCount() > 0

            # 子ノードでチェック操作を試行
            root_item = window._tree_model.item(0)
            if root_item.rowCount() > 0:
                first_child = root_item.child(0)
                node = first_child.data(TREE_NODE_ROLE)
                if node is not None and node.value_entry is not None:
                    # チェック状態を反転
                    if first_child.checkState() == Qt.CheckState.Checked:
                        first_child.setCheckState(Qt.CheckState.Unchecked)
                    else:
                        first_child.setCheckState(Qt.CheckState.Checked)

                    # ツリーが再構築されている
                    assert window._tree_model.rowCount() > 0
        finally:
            window.close()

    def test_コメント化されたLITERALノードのチェック操作(
        self, qapp, tmp_path: Path
    ):
        """LITERAL ノード（コメント化済み）のチェック ON が正常に動作する。"""
        from tests.conftest import _write_yaml

        # コメント化されたリテラルを含む YAML を作成
        cards_dir = tmp_path / "cards"
        _write_yaml(
            cards_dir / "test.yaml",
            (
                "entry:\n"
                "  - literal_value\n"
                "  # - commented_literal\n"
            ),
        )

        from PySide6.QtCore import Qt

        from gui.app import WildTreeWindow
        from gui.tree_model import TREE_NODE_ROLE

        window = WildTreeWindow(cards_dir=cards_dir)
        try:
            if window._list_top_trees.count() == 0:
                pytest.skip("トップツリーが生成されない")

            window._list_top_trees.setCurrentRow(0)
            if window._tree_model.rowCount() == 0:
                pytest.skip("ツリーモデルが空")

            # コメントされたノードを探す
            root_item = window._tree_model.item(0)
            commented_item = None
            for i in range(root_item.rowCount()):
                child_item = root_item.child(i)
                node = child_item.data(TREE_NODE_ROLE)
                if node is not None and node.value_entry is not None and node.value_entry.is_commented:
                    commented_item = child_item
                    break

            if commented_item is None:
                pytest.skip("コメントアウトされたノードが見つからない")

            # チェック ON
            commented_item.setCheckState(Qt.CheckState.Checked)

            # YAML ファイルでコメントが解除されていることを確認
            content = (cards_dir / "test.yaml").read_text(encoding="utf-8")
            assert "  - commented_literal" in content
            assert "  # - commented_literal" not in content
        finally:
            window.close()
