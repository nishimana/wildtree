"""Unit tests for gui/tree_model.py -- TreeNode → QStandardItemModel 変換のテスト。

設計意図ドキュメント (docs/design/s6-gui-tree-view.md) に基づいて、
tree_model の各関数を検証する。

テスト対象:
  - populate_model(tree_node, model) -> None
  - _create_item(node) -> QStandardItem
  - _populate_children(parent_item, node) -> None
  - 定数: TREE_NODE_ROLE, COLOR_*, PREFIX_*

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path

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


def _make_root_with_all_types() -> TreeNode:
    """全 NodeType の子ノードを持つ ROOT ノードを生成するヘルパー。

    テストで使いやすいよう、各 NodeType の典型的なノードを子に持つ。
    """
    kd = _make_key_def("ルートキー")
    ve_normal = _make_value_entry("__参照先__", is_commented=False)
    ve_commented = _make_value_entry("__コメント参照__", is_commented=True)
    ve_literal = _make_value_entry("literal_value", is_commented=False)
    ve_literal_commented = _make_value_entry("commented_literal", is_commented=True)

    ref_normal = WildcardRef(raw="__参照先__", full_path="参照先")
    ref_unresolved = WildcardRef(raw="__存在しないキー__", full_path="存在しないキー")
    ref_circular = WildcardRef(raw="__ルートキー__", full_path="ルートキー")
    ref_dynamic = WildcardRef(
        raw="__{__変数__}サフィックス__",
        full_path="{__変数__}サフィックス",
        ref_type=RefType.DYNAMIC,
    )

    children = [
        # REF ノード（通常）
        _make_tree_node(
            "参照先",
            NodeType.REF,
            key_def=_make_key_def("参照先"),
            value_entry=ve_normal,
            ref=ref_normal,
        ),
        # REF ノード（コメントアウト）
        _make_tree_node(
            "コメント参照",
            NodeType.REF,
            key_def=_make_key_def("コメント参照"),
            value_entry=ve_commented,
            ref=WildcardRef(raw="__コメント参照__", full_path="コメント参照"),
        ),
        # LITERAL ノード（通常）
        _make_tree_node(
            "literal_value",
            NodeType.LITERAL,
            value_entry=ve_literal,
        ),
        # LITERAL ノード（コメントアウト）
        _make_tree_node(
            "commented_literal",
            NodeType.LITERAL,
            value_entry=ve_literal_commented,
        ),
        # DYNAMIC ノード
        _make_tree_node(
            ref_dynamic.raw,
            NodeType.DYNAMIC,
            value_entry=_make_value_entry(ref_dynamic.raw),
            ref=ref_dynamic,
        ),
        # UNRESOLVED ノード
        _make_tree_node(
            "存在しないキー",
            NodeType.UNRESOLVED,
            value_entry=_make_value_entry("__存在しないキー__"),
            ref=ref_unresolved,
        ),
        # CIRCULAR ノード
        _make_tree_node(
            "ルートキー (循環)",
            NodeType.CIRCULAR,
            value_entry=_make_value_entry("__ルートキー__"),
            ref=ref_circular,
        ),
        # EMPTY ノード
        _make_tree_node(
            "(空)",
            NodeType.EMPTY,
            value_entry=_make_value_entry('"{}"'),
        ),
    ]

    return _make_tree_node(
        "ルートキー",
        NodeType.ROOT,
        children=children,
        key_def=kd,
    )


# =========================================================================
# 定数のテスト
# =========================================================================


class TestTreeModelConstants:
    """tree_model.py の定数テスト。"""

    def test_TREE_NODE_ROLE_はUserRole(self, qapp):
        """TREE_NODE_ROLE が Qt.ItemDataRole.UserRole である。"""
        from PySide6.QtCore import Qt

        from gui.tree_model import TREE_NODE_ROLE

        assert TREE_NODE_ROLE == Qt.ItemDataRole.UserRole

    def test_COLOR_DEFAULT_は黒(self, qapp):
        """COLOR_DEFAULT が黒 (#000000) である。"""
        from PySide6.QtGui import QColor

        from gui.tree_model import COLOR_DEFAULT

        assert COLOR_DEFAULT == QColor("#000000")

    def test_COLOR_LITERAL_はダークグリーン(self, qapp):
        """COLOR_LITERAL がダークグリーン (#006400) である。"""
        from PySide6.QtGui import QColor

        from gui.tree_model import COLOR_LITERAL

        assert COLOR_LITERAL == QColor("#006400")

    def test_COLOR_DYNAMIC_はダークオレンジ(self, qapp):
        """COLOR_DYNAMIC がダークオレンジ (#FF8C00) である。"""
        from PySide6.QtGui import QColor

        from gui.tree_model import COLOR_DYNAMIC

        assert COLOR_DYNAMIC == QColor("#FF8C00")

    def test_COLOR_UNRESOLVED_は赤(self, qapp):
        """COLOR_UNRESOLVED が赤 (#FF0000) である。"""
        from PySide6.QtGui import QColor

        from gui.tree_model import COLOR_UNRESOLVED

        assert COLOR_UNRESOLVED == QColor("#FF0000")

    def test_COLOR_COMMENTED_はグレー(self, qapp):
        """COLOR_COMMENTED がグレー (#888888) である。"""
        from PySide6.QtGui import QColor

        from gui.tree_model import COLOR_COMMENTED

        assert COLOR_COMMENTED == QColor("#888888")

    def test_PREFIX_DYNAMIC_の値(self, qapp):
        """PREFIX_DYNAMIC が "[動的] " である。"""
        from gui.tree_model import PREFIX_DYNAMIC

        assert PREFIX_DYNAMIC == "[動的] "

    def test_PREFIX_UNRESOLVED_の値(self, qapp):
        """PREFIX_UNRESOLVED が "[未解決] " である。"""
        from gui.tree_model import PREFIX_UNRESOLVED

        assert PREFIX_UNRESOLVED == "[未解決] "


# =========================================================================
# _create_item のテスト
# =========================================================================


class TestCreateItem:
    """_create_item のテスト。"""

    def test_create_item_ROOTノード_表示名がdisplay_name(self, qapp):
        """ROOT ノードの表示テキストが display_name そのまま。"""
        from gui.tree_model import _create_item

        node = _make_tree_node("ルートキー", NodeType.ROOT, key_def=_make_key_def("ルートキー"))
        item = _create_item(node)

        assert item.text() == "ルートキー"

    def test_create_item_ROOTノード_太字(self, qapp):
        """ROOT ノードのフォントが太字。"""
        from gui.tree_model import _create_item

        node = _make_tree_node("ルートキー", NodeType.ROOT, key_def=_make_key_def("ルートキー"))
        item = _create_item(node)

        assert item.font().bold() is True

    def test_create_item_ROOTノード_デフォルト色(self, qapp):
        """ROOT ノードのテキスト色がデフォルト（黒）。"""
        from gui.tree_model import COLOR_DEFAULT, _create_item

        node = _make_tree_node("ルートキー", NodeType.ROOT, key_def=_make_key_def("ルートキー"))
        item = _create_item(node)

        assert item.foreground().color() == COLOR_DEFAULT

    def test_create_item_ROOTノード_編集不可(self, qapp):
        """ROOT ノードのアイテムが編集不可。"""
        from gui.tree_model import _create_item

        node = _make_tree_node("ルートキー", NodeType.ROOT, key_def=_make_key_def("ルートキー"))
        item = _create_item(node)

        assert item.isEditable() is False

    def test_create_item_ROOTノード_TREE_NODE_ROLEにTreeNode格納(self, qapp):
        """ROOT ノードの TREE_NODE_ROLE に TreeNode が格納される。"""
        from gui.tree_model import TREE_NODE_ROLE, _create_item

        node = _make_tree_node("ルートキー", NodeType.ROOT, key_def=_make_key_def("ルートキー"))
        item = _create_item(node)

        stored = item.data(TREE_NODE_ROLE)
        assert stored is node

    def test_create_item_REFノード_デフォルト色(self, qapp):
        """REF ノードのテキスト色がデフォルト（黒）。"""
        from gui.tree_model import COLOR_DEFAULT, _create_item

        ve = _make_value_entry("__target__")
        ref = WildcardRef(raw="__target__", full_path="target")
        node = _make_tree_node(
            "target", NodeType.REF,
            key_def=_make_key_def("target"),
            value_entry=ve,
            ref=ref,
        )
        item = _create_item(node)

        assert item.foreground().color() == COLOR_DEFAULT

    def test_create_item_REFノード_通常フォント(self, qapp):
        """REF ノードのフォントは太字でもイタリックでもない。"""
        from gui.tree_model import _create_item

        ve = _make_value_entry("__target__")
        ref = WildcardRef(raw="__target__", full_path="target")
        node = _make_tree_node(
            "target", NodeType.REF,
            key_def=_make_key_def("target"),
            value_entry=ve,
            ref=ref,
        )
        item = _create_item(node)

        assert item.font().bold() is False
        assert item.font().italic() is False

    def test_create_item_LITERALノード_ダークグリーン色(self, qapp):
        """LITERAL ノードのテキスト色がダークグリーン。"""
        from gui.tree_model import COLOR_LITERAL, _create_item

        ve = _make_value_entry("tag_value")
        node = _make_tree_node("tag_value", NodeType.LITERAL, value_entry=ve)
        item = _create_item(node)

        assert item.foreground().color() == COLOR_LITERAL

    def test_create_item_LITERALノード_イタリック(self, qapp):
        """LITERAL ノードのフォントがイタリック。"""
        from gui.tree_model import _create_item

        ve = _make_value_entry("tag_value")
        node = _make_tree_node("tag_value", NodeType.LITERAL, value_entry=ve)
        item = _create_item(node)

        assert item.font().italic() is True

    def test_create_item_LITERALノード_表示名がdisplay_name(self, qapp):
        """LITERAL ノードの表示テキストが display_name そのまま（プレフィックスなし）。"""
        from gui.tree_model import _create_item

        ve = _make_value_entry("(cinematic_shadow:1.1)")
        node = _make_tree_node("(cinematic_shadow:1.1)", NodeType.LITERAL, value_entry=ve)
        item = _create_item(node)

        assert item.text() == "(cinematic_shadow:1.1)"

    def test_create_item_DYNAMICノード_ダークオレンジ色(self, qapp):
        """DYNAMIC ノードのテキスト色がダークオレンジ。"""
        from gui.tree_model import COLOR_DYNAMIC, _create_item

        ref = WildcardRef(
            raw="__{__var__}suffix__",
            full_path="{__var__}suffix",
            ref_type=RefType.DYNAMIC,
        )
        ve = _make_value_entry(ref.raw)
        node = _make_tree_node(ref.raw, NodeType.DYNAMIC, value_entry=ve, ref=ref)
        item = _create_item(node)

        assert item.foreground().color() == COLOR_DYNAMIC

    def test_create_item_DYNAMICノード_プレフィックス付き(self, qapp):
        """DYNAMIC ノードの表示テキストに PREFIX_DYNAMIC が付与される。"""
        from gui.tree_model import PREFIX_DYNAMIC, _create_item

        ref = WildcardRef(
            raw="__{__var__}suffix__",
            full_path="{__var__}suffix",
            ref_type=RefType.DYNAMIC,
        )
        ve = _make_value_entry(ref.raw)
        node = _make_tree_node(ref.raw, NodeType.DYNAMIC, value_entry=ve, ref=ref)
        item = _create_item(node)

        assert item.text() == PREFIX_DYNAMIC + ref.raw

    def test_create_item_UNRESOLVEDノード_赤色(self, qapp):
        """UNRESOLVED ノードのテキスト色が赤。"""
        from gui.tree_model import COLOR_UNRESOLVED, _create_item

        ref = WildcardRef(raw="__missing__", full_path="missing")
        ve = _make_value_entry("__missing__")
        node = _make_tree_node("missing", NodeType.UNRESOLVED, value_entry=ve, ref=ref)
        item = _create_item(node)

        assert item.foreground().color() == COLOR_UNRESOLVED

    def test_create_item_UNRESOLVEDノード_プレフィックス付き(self, qapp):
        """UNRESOLVED ノードの表示テキストに PREFIX_UNRESOLVED が付与される。"""
        from gui.tree_model import PREFIX_UNRESOLVED, _create_item

        ref = WildcardRef(raw="__missing__", full_path="missing")
        ve = _make_value_entry("__missing__")
        node = _make_tree_node("missing", NodeType.UNRESOLVED, value_entry=ve, ref=ref)
        item = _create_item(node)

        assert item.text() == PREFIX_UNRESOLVED + "missing"

    def test_create_item_CIRCULARノード_グレー色(self, qapp):
        """CIRCULAR ノードのテキスト色がグレー。"""
        from gui.tree_model import COLOR_COMMENTED, _create_item

        ref = WildcardRef(raw="__キー名__", full_path="キー名")
        ve = _make_value_entry("__キー名__")
        node = _make_tree_node("キー名 (循環)", NodeType.CIRCULAR, value_entry=ve, ref=ref)
        item = _create_item(node)

        assert item.foreground().color() == COLOR_COMMENTED

    def test_create_item_CIRCULARノード_表示名がdisplay_name(self, qapp):
        """CIRCULAR ノードの表示テキストが display_name そのまま。"""
        from gui.tree_model import _create_item

        ref = WildcardRef(raw="__キー名__", full_path="キー名")
        ve = _make_value_entry("__キー名__")
        node = _make_tree_node("キー名 (循環)", NodeType.CIRCULAR, value_entry=ve, ref=ref)
        item = _create_item(node)

        assert item.text() == "キー名 (循環)"

    def test_create_item_EMPTYノード_グレー色(self, qapp):
        """EMPTY ノードのテキスト色がグレー。"""
        from gui.tree_model import COLOR_COMMENTED, _create_item

        ve = _make_value_entry('"{}"')
        node = _make_tree_node("(空)", NodeType.EMPTY, value_entry=ve)
        item = _create_item(node)

        assert item.foreground().color() == COLOR_COMMENTED

    def test_create_item_EMPTYノード_表示名がdisplay_name(self, qapp):
        """EMPTY ノードの表示テキストが display_name そのまま。"""
        from gui.tree_model import _create_item

        ve = _make_value_entry('"{}"')
        node = _make_tree_node("(空)", NodeType.EMPTY, value_entry=ve)
        item = _create_item(node)

        assert item.text() == "(空)"

    def test_create_item_全ノードタイプが編集不可(self, qapp):
        """全 NodeType のアイテムが編集不可。"""
        from gui.tree_model import _create_item

        root = _make_root_with_all_types()

        # ROOT ノード自身
        item = _create_item(root)
        assert item.isEditable() is False

        # 全子ノード
        for child in root.children:
            child_item = _create_item(child)
            assert child_item.isEditable() is False, (
                f"NodeType {child.node_type} のアイテムが編集可能になっている"
            )

    def test_create_item_全ノードタイプでTREE_NODE_ROLEにTreeNode格納(self, qapp):
        """全 NodeType の TREE_NODE_ROLE に TreeNode が格納される。"""
        from gui.tree_model import TREE_NODE_ROLE, _create_item

        root = _make_root_with_all_types()

        # ROOT ノード自身
        item = _create_item(root)
        assert item.data(TREE_NODE_ROLE) is root

        # 全子ノード
        for child in root.children:
            child_item = _create_item(child)
            assert child_item.data(TREE_NODE_ROLE) is child, (
                f"NodeType {child.node_type} の TREE_NODE_ROLE が正しくない"
            )


# =========================================================================
# コメントアウトノードのテスト
# =========================================================================


class TestCreateItemCommented:
    """_create_item のコメントアウトノードテスト。"""

    def test_create_item_コメントREFノード_グレー色(self, qapp):
        """is_commented=True の REF ノードのテキスト色がグレー。"""
        from gui.tree_model import COLOR_COMMENTED, _create_item

        ve = _make_value_entry("__target__", is_commented=True)
        ref = WildcardRef(raw="__target__", full_path="target")
        node = _make_tree_node(
            "target", NodeType.REF,
            key_def=_make_key_def("target"),
            value_entry=ve,
            ref=ref,
        )
        item = _create_item(node)

        assert item.foreground().color() == COLOR_COMMENTED

    def test_create_item_コメントREFノード_取り消し線(self, qapp):
        """is_commented=True の REF ノードのフォントに取り消し線がある。"""
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

        assert item.font().strikeOut() is True

    def test_create_item_コメントLITERALノード_グレー色(self, qapp):
        """is_commented=True の LITERAL ノードのテキスト色がグレー（ダークグリーンではない）。"""
        from gui.tree_model import COLOR_COMMENTED, COLOR_LITERAL, _create_item

        ve = _make_value_entry("commented_tag", is_commented=True)
        node = _make_tree_node("commented_tag", NodeType.LITERAL, value_entry=ve)
        item = _create_item(node)

        # コメント色はノードタイプ固有の色を上書きする
        assert item.foreground().color() == COLOR_COMMENTED
        assert item.foreground().color() != COLOR_LITERAL

    def test_create_item_コメントLITERALノード_取り消し線とイタリック(self, qapp):
        """is_commented=True の LITERAL ノードは取り消し線かつイタリック。"""
        from gui.tree_model import _create_item

        ve = _make_value_entry("commented_tag", is_commented=True)
        node = _make_tree_node("commented_tag", NodeType.LITERAL, value_entry=ve)
        item = _create_item(node)

        assert item.font().strikeOut() is True
        # LITERAL のイタリックは維持されることが望ましいが、
        # 設計書では is_commented の場合「取り消し線を追加」としている
        # イタリック + 取り消し線の組み合わせを確認

    def test_create_item_非コメントノード_取り消し線なし(self, qapp):
        """is_commented=False のノードには取り消し線がない。"""
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

        assert item.font().strikeOut() is False

    def test_create_item_value_entryがNoneのノード_取り消し線なし(self, qapp):
        """value_entry が None の ROOT ノードには取り消し線がない。"""
        from gui.tree_model import _create_item

        node = _make_tree_node("ルートキー", NodeType.ROOT, key_def=_make_key_def("ルートキー"))
        item = _create_item(node)

        assert item.font().strikeOut() is False


# =========================================================================
# populate_model のテスト
# =========================================================================


class TestPopulateModel:
    """populate_model のテスト。"""

    def test_populate_model_ルートノードがモデルに追加される(self, qapp):
        """populate_model 後、モデルのルートにアイテムが1つ追加される。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import populate_model

        kd = _make_key_def("ルートキー")
        root = _make_tree_node("ルートキー", NodeType.ROOT, key_def=kd)
        model = QStandardItemModel()

        populate_model(root, model)

        # ルートアイテムが1つ追加されている
        assert model.rowCount() == 1
        root_item = model.item(0)
        assert root_item is not None
        assert root_item.text() == "ルートキー"

    def test_populate_model_既存データがクリアされる(self, qapp):
        """populate_model はモデルをクリアしてから追加する。"""
        from PySide6.QtGui import QStandardItem, QStandardItemModel

        from gui.tree_model import populate_model

        kd = _make_key_def("ルートキー")
        root = _make_tree_node("ルートキー", NodeType.ROOT, key_def=kd)
        model = QStandardItemModel()

        # 事前にダミーデータを追加
        model.appendRow(QStandardItem("dummy1"))
        model.appendRow(QStandardItem("dummy2"))
        assert model.rowCount() == 2

        populate_model(root, model)

        # クリアされて新しいルートのみ
        assert model.rowCount() == 1
        assert model.item(0).text() == "ルートキー"

    def test_populate_model_子ノードが再帰的に追加される(self, qapp):
        """populate_model で子ノードが再帰的にモデルに追加される。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import populate_model

        kd = _make_key_def("root")
        child1 = _make_tree_node("child1", NodeType.LITERAL, value_entry=_make_value_entry("c1"))
        grandchild = _make_tree_node("grandchild", NodeType.LITERAL, value_entry=_make_value_entry("gc"))
        child2 = _make_tree_node(
            "child2", NodeType.REF,
            children=[grandchild],
            key_def=_make_key_def("child2"),
            value_entry=_make_value_entry("__child2__"),
            ref=WildcardRef(raw="__child2__", full_path="child2"),
        )
        root = _make_tree_node("root", NodeType.ROOT, children=[child1, child2], key_def=kd)
        model = QStandardItemModel()

        populate_model(root, model)

        # ルートの子は2つ
        root_item = model.item(0)
        assert root_item.rowCount() == 2
        # child1
        child1_item = root_item.child(0)
        assert child1_item.text() == "child1"
        assert child1_item.rowCount() == 0
        # child2 → grandchild
        child2_item = root_item.child(1)
        assert child2_item.text() == "child2"
        assert child2_item.rowCount() == 1
        grandchild_item = child2_item.child(0)
        assert grandchild_item.text() == "grandchild"

    def test_populate_model_TREE_NODE_ROLEが全ノードに設定される(self, qapp):
        """populate_model 後、全ノードの TREE_NODE_ROLE に TreeNode が格納されている。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import TREE_NODE_ROLE, populate_model

        kd = _make_key_def("root")
        child = _make_tree_node("child", NodeType.LITERAL, value_entry=_make_value_entry("val"))
        root = _make_tree_node("root", NodeType.ROOT, children=[child], key_def=kd)
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        assert root_item.data(TREE_NODE_ROLE) is root
        child_item = root_item.child(0)
        assert child_item.data(TREE_NODE_ROLE) is child

    def test_populate_model_全NodeTypeの色が正しい(self, qapp):
        """populate_model で生成される各 NodeType のアイテムの色が正しい。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import (
            COLOR_COMMENTED,
            COLOR_DEFAULT,
            COLOR_DYNAMIC,
            COLOR_LITERAL,
            COLOR_UNRESOLVED,
            populate_model,
        )

        root = _make_root_with_all_types()
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        # ROOT → デフォルト色
        assert root_item.foreground().color() == COLOR_DEFAULT

        # 子ノードの色を確認
        # children[0]: REF（通常）→ デフォルト色
        assert root_item.child(0).foreground().color() == COLOR_DEFAULT
        # children[1]: REF（コメント）→ グレー
        assert root_item.child(1).foreground().color() == COLOR_COMMENTED
        # children[2]: LITERAL（通常）→ ダークグリーン
        assert root_item.child(2).foreground().color() == COLOR_LITERAL
        # children[3]: LITERAL（コメント）→ グレー
        assert root_item.child(3).foreground().color() == COLOR_COMMENTED
        # children[4]: DYNAMIC → ダークオレンジ
        assert root_item.child(4).foreground().color() == COLOR_DYNAMIC
        # children[5]: UNRESOLVED → 赤
        assert root_item.child(5).foreground().color() == COLOR_UNRESOLVED
        # children[6]: CIRCULAR → グレー
        assert root_item.child(6).foreground().color() == COLOR_COMMENTED
        # children[7]: EMPTY → グレー
        assert root_item.child(7).foreground().color() == COLOR_COMMENTED

    def test_populate_model_子なしノード_rowCountが0(self, qapp):
        """子ノードのないノードの rowCount が 0。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import populate_model

        kd = _make_key_def("leaf")
        root = _make_tree_node("leaf", NodeType.ROOT, key_def=kd)
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        assert root_item.rowCount() == 0

    def test_populate_model_深いネスト_3階層が正しく構築される(self, qapp):
        """3階層（root → child → grandchild → great_grandchild）が正しく構築される。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import populate_model

        great_grandchild = _make_tree_node(
            "great_grandchild", NodeType.LITERAL,
            value_entry=_make_value_entry("val"),
        )
        grandchild = _make_tree_node(
            "grandchild", NodeType.REF,
            children=[great_grandchild],
            key_def=_make_key_def("grandchild"),
            value_entry=_make_value_entry("__grandchild__"),
            ref=WildcardRef(raw="__grandchild__", full_path="grandchild"),
        )
        child = _make_tree_node(
            "child", NodeType.REF,
            children=[grandchild],
            key_def=_make_key_def("child"),
            value_entry=_make_value_entry("__child__"),
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
        great_grandchild_item = grandchild_item.child(0)

        assert root_item.text() == "root"
        assert child_item.text() == "child"
        assert grandchild_item.text() == "grandchild"
        assert great_grandchild_item.text() == "great_grandchild"

    def test_populate_model_複数の子ノード_順序が保持される(self, qapp):
        """複数の子ノードの順序が保持される。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import populate_model

        children = [
            _make_tree_node(f"child_{i}", NodeType.LITERAL, value_entry=_make_value_entry(f"val_{i}"))
            for i in range(5)
        ]
        root = _make_tree_node("root", NodeType.ROOT, children=children, key_def=_make_key_def("root"))
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        assert root_item.rowCount() == 5
        for i in range(5):
            assert root_item.child(i).text() == f"child_{i}"


# =========================================================================
# DYNAMICとUNRESOLVEDのプレフィックス確認
# =========================================================================


class TestPrefixes:
    """DYNAMIC / UNRESOLVED ノードのプレフィックステスト。"""

    def test_populate_model_DYNAMICノードにプレフィックスが付く(self, qapp):
        """populate_model 後、DYNAMIC ノードに "[動的] " プレフィックスが付く。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import PREFIX_DYNAMIC, populate_model

        ref = WildcardRef(
            raw="__{__var__}__",
            full_path="{__var__}",
            ref_type=RefType.DYNAMIC,
        )
        dynamic_child = _make_tree_node(
            ref.raw, NodeType.DYNAMIC,
            value_entry=_make_value_entry(ref.raw),
            ref=ref,
        )
        root = _make_tree_node(
            "root", NodeType.ROOT,
            children=[dynamic_child],
            key_def=_make_key_def("root"),
        )
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        dynamic_item = root_item.child(0)
        assert dynamic_item.text().startswith(PREFIX_DYNAMIC)

    def test_populate_model_UNRESOLVEDノードにプレフィックスが付く(self, qapp):
        """populate_model 後、UNRESOLVED ノードに "[未解決] " プレフィックスが付く。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import PREFIX_UNRESOLVED, populate_model

        ref = WildcardRef(raw="__missing__", full_path="missing")
        unresolved_child = _make_tree_node(
            "missing", NodeType.UNRESOLVED,
            value_entry=_make_value_entry("__missing__"),
            ref=ref,
        )
        root = _make_tree_node(
            "root", NodeType.ROOT,
            children=[unresolved_child],
            key_def=_make_key_def("root"),
        )
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        unresolved_item = root_item.child(0)
        assert unresolved_item.text().startswith(PREFIX_UNRESOLVED)

    def test_populate_model_REFノードにはプレフィックスが付かない(self, qapp):
        """populate_model 後、REF ノードにはプレフィックスが付かない。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.tree_model import PREFIX_DYNAMIC, PREFIX_UNRESOLVED, populate_model

        ref = WildcardRef(raw="__target__", full_path="target")
        ref_child = _make_tree_node(
            "target", NodeType.REF,
            key_def=_make_key_def("target"),
            value_entry=_make_value_entry("__target__"),
            ref=ref,
        )
        root = _make_tree_node(
            "root", NodeType.ROOT,
            children=[ref_child],
            key_def=_make_key_def("root"),
        )
        model = QStandardItemModel()

        populate_model(root, model)

        root_item = model.item(0)
        ref_item = root_item.child(0)
        assert not ref_item.text().startswith(PREFIX_DYNAMIC)
        assert not ref_item.text().startswith(PREFIX_UNRESOLVED)
        assert ref_item.text() == "target"
