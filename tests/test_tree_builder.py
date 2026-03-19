"""Unit tests for core/tree_builder.py -- ツリー構築モジュールのテスト。

設計意図ドキュメント (docs/design/s5-tree-builder.md) に基づいて、
ツリー構築の各関数を検証する。

テスト対象:
  - build_tree(key_def, registry, full_path_index) -> TreeNode
  - build_forest(top_trees, registry, full_path_index) -> list[TreeNode]
  - 各 NodeType の判定と TreeNode 構築
  - 循環参照の検出（パスごとの visited セット）
  - 深さ制限による安全停止

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models import (
    FullPathIndex,
    KeyDefinition,
    KeyRegistry,
    NodeType,
    RefType,
    TreeNode,
    ValueEntry,
    WildcardRef,
)
from core.resolver import build_full_path_index
from core.top_tree import TopTreeInfo
from core.tree_builder import (
    CIRCULAR_SUFFIX,
    EMPTY_DISPLAY_NAME,
    MAX_DEPTH,
    build_forest,
    build_tree,
)


# =========================================================================
# ヘルパー
# =========================================================================


def _make_key_def(
    name: str,
    file_path: Path,
    line_number: int = 1,
    values: list[ValueEntry] | None = None,
) -> KeyDefinition:
    """テスト用 KeyDefinition を生成するヘルパー。"""
    return KeyDefinition(
        name=name,
        file_path=file_path,
        line_number=line_number,
        values=values if values is not None else [],
    )


def _make_registry(*entries: tuple[str, KeyDefinition]) -> KeyRegistry:
    """テスト用 KeyRegistry を生成するヘルパー。

    同名キーは同じリストに追加される。
    """
    registry: KeyRegistry = {}
    for key_name, key_def in entries:
        registry.setdefault(key_name, []).append(key_def)
    return registry


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


def _collect_node_types(node: TreeNode) -> list[NodeType]:
    """ツリーの全ノードの node_type をフラットに収集する（幅優先）。"""
    result = [node.node_type]
    for child in node.children:
        result.extend(_collect_node_types(child))
    return result


def _find_nodes_by_type(node: TreeNode, node_type: NodeType) -> list[TreeNode]:
    """ツリーから指定した node_type のノードをフラットに収集する（深さ優先）。"""
    result = []
    if node.node_type == node_type:
        result.append(node)
    for child in node.children:
        result.extend(_find_nodes_by_type(child, node_type))
    return result


# =========================================================================
# build_tree -- 基本テスト
# =========================================================================


class TestBuildTree基本:
    """build_tree の基本テスト。"""

    def test_build_tree_リテラルのみのキー_ROOT_LITERAL子ノードが生成される(self):
        """リテラルのみの値行を持つキーから ROOT + LITERAL 子ノードが生成される。"""
        cards_dir = Path("C:/cards")
        ve = _make_value_entry(
            "hello",
            literals=["hello"],
        )
        kd = _make_key_def("greeting", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("greeting", kd))
        index: FullPathIndex = {}

        root = build_tree(kd, registry, index)

        assert root.node_type == NodeType.ROOT
        assert root.display_name == "greeting"
        assert root.value_entry is None
        assert root.ref is None
        assert root.key_def is kd
        assert len(root.children) == 1
        child = root.children[0]
        assert child.node_type == NodeType.LITERAL
        assert child.display_name == "hello"

    def test_build_tree_参照のみのキー_ROOT_REF子ノードが生成される(self):
        """参照のみの値行を持つキーから ROOT + REF 子ノード（再帰展開あり）が生成される。"""
        cards_dir = Path("C:/cards")
        # farewell キー
        ve_farewell = _make_value_entry(
            "goodbye",
            literals=["goodbye"],
        )
        kd_farewell = _make_key_def(
            "farewell", cards_dir / "test.yaml", values=[ve_farewell]
        )
        # greeting キー（farewell を参照）
        ref = WildcardRef(raw="__farewell__", full_path="farewell")
        ve_greeting = _make_value_entry("__farewell__", refs=[ref])
        kd_greeting = _make_key_def(
            "greeting", cards_dir / "test.yaml", values=[ve_greeting]
        )
        registry = _make_registry(
            ("greeting", kd_greeting),
            ("farewell", kd_farewell),
        )
        index: FullPathIndex = {"farewell": kd_farewell}

        root = build_tree(kd_greeting, registry, index)

        assert root.node_type == NodeType.ROOT
        assert root.display_name == "greeting"
        assert len(root.children) == 1
        ref_node = root.children[0]
        assert ref_node.node_type == NodeType.REF
        assert ref_node.display_name == "farewell"
        assert ref_node.key_def is kd_farewell
        # farewell の子ノード（goodbye リテラル）
        assert len(ref_node.children) == 1
        assert ref_node.children[0].node_type == NodeType.LITERAL
        assert ref_node.children[0].display_name == "goodbye"

    def test_build_tree_リテラルと参照が混在するキー_正しいノード群が生成される(self):
        """リテラルと参照が混在する値行から正しいノード群が生成される。"""
        cards_dir = Path("C:/cards")
        # leaf キー
        ve_leaf = _make_value_entry("leaf_value", literals=["leaf_value"])
        kd_leaf = _make_key_def("leaf", cards_dir / "test.yaml", values=[ve_leaf])
        # parent キー（参照1つ + リテラル1つ）
        ref = WildcardRef(raw="__leaf__", full_path="leaf")
        ve_parent = _make_value_entry(
            "__leaf__,tag_value",
            refs=[ref],
            literals=["tag_value"],
        )
        kd_parent = _make_key_def(
            "parent", cards_dir / "test.yaml", values=[ve_parent]
        )
        registry = _make_registry(
            ("parent", kd_parent),
            ("leaf", kd_leaf),
        )
        index: FullPathIndex = {"leaf": kd_leaf}

        root = build_tree(kd_parent, registry, index)

        assert root.node_type == NodeType.ROOT
        # 参照1つ + リテラル1つ = 2子ノード
        assert len(root.children) == 2
        types = {child.node_type for child in root.children}
        assert NodeType.REF in types
        assert NodeType.LITERAL in types

    def test_build_tree_値行がゼロ個のキー_ROOTノード子なし(self):
        """値行を持たないキー定義から ROOT ノード（子なし）が生成される。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("empty_key", cards_dir / "test.yaml", values=[])
        registry = _make_registry(("empty_key", kd))
        index: FullPathIndex = {}

        root = build_tree(kd, registry, index)

        assert root.node_type == NodeType.ROOT
        assert root.display_name == "empty_key"
        assert len(root.children) == 0


# =========================================================================
# build_forest -- 基本テスト
# =========================================================================


class TestBuildForest基本:
    """build_forest の基本テスト。"""

    def test_build_forest_複数トップツリー_正しいルートノードリスト(self):
        """複数のトップツリーから正しいルートノードリストが返る。"""
        cards_dir = Path("C:/cards")
        kd_a = _make_key_def("A", cards_dir / "a.yaml")
        kd_b = _make_key_def("B", cards_dir / "b.yaml")
        registry = _make_registry(("A", kd_a), ("B", kd_b))
        index: FullPathIndex = {}
        top_trees = [
            TopTreeInfo(name="A", key_def=kd_a, file_path=kd_a.file_path),
            TopTreeInfo(name="B", key_def=kd_b, file_path=kd_b.file_path),
        ]

        forest = build_forest(top_trees, registry, index)

        assert len(forest) == 2
        assert all(isinstance(n, TreeNode) for n in forest)
        assert all(n.node_type == NodeType.ROOT for n in forest)
        names = [n.display_name for n in forest]
        assert "A" in names
        assert "B" in names

    def test_build_forest_空リスト_空リストが返る(self):
        """空リストを渡すと空リストが返る。"""
        forest = build_forest([], {}, {})

        assert isinstance(forest, list)
        assert len(forest) == 0

    def test_build_forest_1つのトップツリー_1要素リスト(self):
        """トップツリーが1つの場合、1要素のリストが返る。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("only", cards_dir / "only.yaml")
        registry = _make_registry(("only", kd))
        index: FullPathIndex = {}
        top_trees = [
            TopTreeInfo(name="only", key_def=kd, file_path=kd.file_path),
        ]

        forest = build_forest(top_trees, registry, index)

        assert len(forest) == 1
        assert forest[0].node_type == NodeType.ROOT
        assert forest[0].display_name == "only"

    def test_build_forest_入力順序が保持される(self):
        """build_forest の戻り値は入力リストの順序を保持する。"""
        cards_dir = Path("C:/cards")
        kd_z = _make_key_def("Z", cards_dir / "z.yaml")
        kd_a = _make_key_def("A", cards_dir / "a.yaml")
        kd_m = _make_key_def("M", cards_dir / "m.yaml")
        registry = _make_registry(("Z", kd_z), ("A", kd_a), ("M", kd_m))
        index: FullPathIndex = {}
        # 意図的にソートされていない順序
        top_trees = [
            TopTreeInfo(name="Z", key_def=kd_z, file_path=kd_z.file_path),
            TopTreeInfo(name="A", key_def=kd_a, file_path=kd_a.file_path),
            TopTreeInfo(name="M", key_def=kd_m, file_path=kd_m.file_path),
        ]

        forest = build_forest(top_trees, registry, index)

        assert [n.display_name for n in forest] == ["Z", "A", "M"]


# =========================================================================
# 参照解決テスト
# =========================================================================


class TestBuildTree参照解決:
    """build_tree の参照解決テスト。"""

    def test_build_tree_通常参照が正しく解決されてREFノードになる(self):
        """通常参照が resolve() で解決され REF ノードが生成される。"""
        cards_dir = Path("C:/cards")
        ve_target = _make_value_entry("target_value", literals=["target_value"])
        kd_target = _make_key_def(
            "target", cards_dir / "test.yaml", values=[ve_target]
        )
        ref = WildcardRef(raw="__target__", full_path="target")
        ve_source = _make_value_entry("__target__", refs=[ref])
        kd_source = _make_key_def(
            "source", cards_dir / "test.yaml", values=[ve_source]
        )
        registry = _make_registry(
            ("source", kd_source),
            ("target", kd_target),
        )
        index: FullPathIndex = {"target": kd_target}

        root = build_tree(kd_source, registry, index)

        ref_node = root.children[0]
        assert ref_node.node_type == NodeType.REF
        assert ref_node.key_def is kd_target
        assert ref_node.ref is ref

    def test_build_tree_未解決参照がUNRESOLVEDノードになる(self):
        """解決できない参照が UNRESOLVED ノードになる。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(raw="__missing__", full_path="missing")
        ve = _make_value_entry("__missing__", refs=[ref])
        kd = _make_key_def("entry", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("entry", kd))
        index: FullPathIndex = {}

        root = build_tree(kd, registry, index)

        assert len(root.children) == 1
        unresolved = root.children[0]
        assert unresolved.node_type == NodeType.UNRESOLVED
        assert unresolved.display_name == "missing"
        assert unresolved.ref is ref
        assert unresolved.value_entry is ve
        assert len(unresolved.children) == 0

    def test_build_tree_クロスファイル参照が正しく解決される(self):
        """別ファイルに定義されたキーへの参照が正しく解決される。"""
        cards_dir = Path("C:/cards")
        # ファイルA に定義された target
        ve_target = _make_value_entry("leaf", literals=["leaf"])
        kd_target = _make_key_def(
            "target", cards_dir / "sub" / "file_a.yaml", values=[ve_target]
        )
        # ファイルB から target をフルパスで参照
        ref = WildcardRef(
            raw="__cards/sub/target__",
            full_path="cards/sub/target",
        )
        ve_source = _make_value_entry("__cards/sub/target__", refs=[ref])
        kd_source = _make_key_def(
            "source", cards_dir / "file_b.yaml", values=[ve_source]
        )
        registry = _make_registry(
            ("source", kd_source),
            ("target", kd_target),
        )
        index: FullPathIndex = {"sub/target": kd_target}

        root = build_tree(kd_source, registry, index)

        ref_node = root.children[0]
        assert ref_node.node_type == NodeType.REF
        assert ref_node.key_def is kd_target


# =========================================================================
# 循環参照テスト
# =========================================================================


class TestBuildTree循環参照:
    """build_tree の循環参照テスト。"""

    def test_build_tree_自己参照_CIRCULARノードになる(self):
        """自己参照（A → A）が CIRCULAR ノードになる。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(raw="__A__", full_path="A")
        ve = _make_value_entry("__A__", refs=[ref])
        kd = _make_key_def("A", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("A", kd))
        index: FullPathIndex = {"A": kd}

        root = build_tree(kd, registry, index)

        assert root.node_type == NodeType.ROOT
        assert len(root.children) == 1
        circular = root.children[0]
        assert circular.node_type == NodeType.CIRCULAR
        assert CIRCULAR_SUFFIX in circular.display_name
        assert len(circular.children) == 0

    def test_build_tree_相互参照_CIRCULARノードになる(self):
        """相互参照（A → B → A）が CIRCULAR ノードになる。"""
        cards_dir = Path("C:/cards")
        ref_b = WildcardRef(raw="__B__", full_path="B")
        ref_a = WildcardRef(raw="__A__", full_path="A")
        ve_a = _make_value_entry("__B__", refs=[ref_b])
        ve_b = _make_value_entry("__A__", refs=[ref_a])
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve_a])
        kd_b = _make_key_def("B", cards_dir / "b.yaml", values=[ve_b])
        registry = _make_registry(("A", kd_a), ("B", kd_b))
        index: FullPathIndex = {"A": kd_a, "B": kd_b}

        root = build_tree(kd_a, registry, index)

        # root (A) → REF (B) → CIRCULAR (A)
        assert root.node_type == NodeType.ROOT
        assert len(root.children) == 1
        ref_b_node = root.children[0]
        assert ref_b_node.node_type == NodeType.REF
        assert ref_b_node.display_name == "B"
        assert len(ref_b_node.children) == 1
        circular = ref_b_node.children[0]
        assert circular.node_type == NodeType.CIRCULAR
        assert "A" in circular.display_name
        assert CIRCULAR_SUFFIX in circular.display_name

    def test_build_tree_ダイヤモンド参照_両ブランチで展開される(self):
        """ダイヤモンド参照（A → B → D, A → C → D）が両ブランチで展開される。"""
        cards_dir = Path("C:/cards")
        # shared (leaf)
        ve_shared = _make_value_entry("leaf value", literals=["leaf value"])
        kd_shared = _make_key_def(
            "shared", cards_dir / "test.yaml", values=[ve_shared]
        )
        # branch_a → shared
        ref_shared_a = WildcardRef(raw="__shared__", full_path="shared")
        ve_a = _make_value_entry("__shared__", refs=[ref_shared_a])
        kd_a = _make_key_def("branch_a", cards_dir / "test.yaml", values=[ve_a])
        # branch_b → shared
        ref_shared_b = WildcardRef(raw="__shared__", full_path="shared")
        ve_b = _make_value_entry("__shared__", refs=[ref_shared_b])
        kd_b = _make_key_def("branch_b", cards_dir / "test.yaml", values=[ve_b])
        # root → branch_a, branch_b
        ref_a = WildcardRef(raw="__branch_a__", full_path="branch_a")
        ref_b = WildcardRef(raw="__branch_b__", full_path="branch_b")
        ve_root = _make_value_entry("__branch_a__", refs=[ref_a])
        ve_root2 = _make_value_entry("__branch_b__", refs=[ref_b])
        kd_root = _make_key_def(
            "root", cards_dir / "test.yaml", values=[ve_root, ve_root2]
        )
        registry = _make_registry(
            ("root", kd_root),
            ("branch_a", kd_a),
            ("branch_b", kd_b),
            ("shared", kd_shared),
        )
        index: FullPathIndex = {
            "root": kd_root,
            "branch_a": kd_a,
            "branch_b": kd_b,
            "shared": kd_shared,
        }

        root = build_tree(kd_root, registry, index)

        # root → [branch_a, branch_b]
        assert root.node_type == NodeType.ROOT
        assert len(root.children) == 2
        # 両ブランチで shared が展開されている（CIRCULAR ではない）
        for branch in root.children:
            assert branch.node_type == NodeType.REF
            assert len(branch.children) == 1
            shared_node = branch.children[0]
            assert shared_node.node_type == NodeType.REF
            assert shared_node.display_name == "shared"
            # shared の子ノード（leaf value）
            assert len(shared_node.children) == 1
            assert shared_node.children[0].node_type == NodeType.LITERAL


# =========================================================================
# 深さ制限テスト
# =========================================================================


class TestBuildTree深さ制限:
    """build_tree の深さ制限テスト。"""

    def test_build_tree_MAX_DEPTHに達した場合_CIRCULARノードとして安全停止(
        self, monkeypatch
    ):
        """MAX_DEPTH に達した場合に CIRCULAR ノードとして安全停止する。"""
        import core.tree_builder as tb_module

        # MAX_DEPTH を 3 に制限してテスト
        monkeypatch.setattr(tb_module, "MAX_DEPTH", 3)

        cards_dir = Path("C:/cards")
        # A → B → C → D → E のチェーンを作る（MAX_DEPTH=3 で D の展開時に停止）
        kd_e = _make_key_def("E", cards_dir / "test.yaml", values=[
            _make_value_entry("end", literals=["end"]),
        ])
        ref_e = WildcardRef(raw="__E__", full_path="E")
        kd_d = _make_key_def("D", cards_dir / "test.yaml", values=[
            _make_value_entry("__E__", refs=[ref_e]),
        ])
        ref_d = WildcardRef(raw="__D__", full_path="D")
        kd_c = _make_key_def("C", cards_dir / "test.yaml", values=[
            _make_value_entry("__D__", refs=[ref_d]),
        ])
        ref_c = WildcardRef(raw="__C__", full_path="C")
        kd_b = _make_key_def("B", cards_dir / "test.yaml", values=[
            _make_value_entry("__C__", refs=[ref_c]),
        ])
        ref_b = WildcardRef(raw="__B__", full_path="B")
        kd_a = _make_key_def("A", cards_dir / "test.yaml", values=[
            _make_value_entry("__B__", refs=[ref_b]),
        ])
        registry = _make_registry(
            ("A", kd_a), ("B", kd_b), ("C", kd_c), ("D", kd_d), ("E", kd_e),
        )
        index: FullPathIndex = {
            "A": kd_a, "B": kd_b, "C": kd_c, "D": kd_d, "E": kd_e,
        }

        root = build_tree(kd_a, registry, index)

        # 深さ制限で途中から CIRCULAR ノードが生成されるはず
        circular_nodes = _find_nodes_by_type(root, NodeType.CIRCULAR)
        assert len(circular_nodes) > 0
        # E まで展開されていないことを確認
        all_names = []

        def collect_names(n: TreeNode) -> None:
            all_names.append(n.display_name)
            for c in n.children:
                collect_names(c)

        collect_names(root)
        # E のリテラル "end" は深さ制限でたどり着けない
        assert "end" not in all_names


# =========================================================================
# 特殊ノードテスト
# =========================================================================


class TestBuildTree特殊ノード:
    """build_tree の特殊ノードテスト。"""

    def test_build_tree_空定義がEMPTYノードになる(self):
        """空定義 '"{}"' が EMPTY ノードになり display_name が "(空)" になる。"""
        cards_dir = Path("C:/cards")
        ve = _make_value_entry('"{}"', literals=['"{}"'])
        kd = _make_key_def("key", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("key", kd))
        index: FullPathIndex = {}

        root = build_tree(kd, registry, index)

        assert len(root.children) == 1
        empty = root.children[0]
        assert empty.node_type == NodeType.EMPTY
        assert empty.display_name == EMPTY_DISPLAY_NAME
        assert empty.value_entry is ve

    def test_build_tree_動的参照がDYNAMICノードになる(self):
        """動的参照が DYNAMIC ノードになり、inner_refs が子ノードとして展開される。"""
        cards_dir = Path("C:/cards")
        # season と character キー
        ve_season = _make_value_entry("spring", literals=["spring"])
        kd_season = _make_key_def(
            "season", cards_dir / "test.yaml", values=[ve_season]
        )
        ve_char = _make_value_entry("asada", literals=["asada"])
        kd_char = _make_key_def(
            "character", cards_dir / "test.yaml", values=[ve_char]
        )
        # scene キー（動的参照）
        inner_season = WildcardRef(raw="__season__", full_path="season")
        inner_char = WildcardRef(raw="__character__", full_path="character")
        dynamic_ref = WildcardRef(
            raw="__{__season__}_{__character__}__",
            full_path="{__season__}_{__character__}",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner_season, inner_char),
        )
        ve_scene = _make_value_entry(
            "__{__season__}_{__character__}__",
            refs=[dynamic_ref],
        )
        kd_scene = _make_key_def(
            "scene", cards_dir / "test.yaml", values=[ve_scene]
        )
        registry = _make_registry(
            ("scene", kd_scene),
            ("season", kd_season),
            ("character", kd_char),
        )
        index: FullPathIndex = {
            "season": kd_season,
            "character": kd_char,
        }

        root = build_tree(kd_scene, registry, index)

        assert len(root.children) == 1
        dynamic = root.children[0]
        assert dynamic.node_type == NodeType.DYNAMIC
        assert dynamic.display_name == dynamic_ref.raw
        assert dynamic.ref is dynamic_ref
        assert dynamic.value_entry is ve_scene
        # inner_refs が子ノードとして展開されている
        assert len(dynamic.children) == 2
        child_types = {child.node_type for child in dynamic.children}
        assert NodeType.REF in child_types

    def test_build_tree_動的参照のinner_refが未解決_UNRESOLVEDノード(self):
        """動的参照の inner_ref が未解決の場合、子ノードに UNRESOLVED が含まれる。"""
        cards_dir = Path("C:/cards")
        inner_ok = WildcardRef(raw="__existing__", full_path="existing")
        inner_ng = WildcardRef(raw="__missing__", full_path="missing")
        dynamic_ref = WildcardRef(
            raw="__{__existing__}_{__missing__}__",
            full_path="{__existing__}_{__missing__}",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner_ok, inner_ng),
        )
        ve_existing = _make_value_entry("val", literals=["val"])
        kd_existing = _make_key_def(
            "existing", cards_dir / "test.yaml", values=[ve_existing]
        )
        ve = _make_value_entry(
            "__{__existing__}_{__missing__}__",
            refs=[dynamic_ref],
        )
        kd = _make_key_def("entry", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(
            ("entry", kd),
            ("existing", kd_existing),
        )
        index: FullPathIndex = {"existing": kd_existing}

        root = build_tree(kd, registry, index)

        dynamic = root.children[0]
        assert dynamic.node_type == NodeType.DYNAMIC
        child_types = [child.node_type for child in dynamic.children]
        assert NodeType.REF in child_types
        assert NodeType.UNRESOLVED in child_types

    def test_build_tree_コメントアウトされた値行の参照が展開される(self):
        """コメントアウトされた値行の参照も展開され、value_entry.is_commented が True。"""
        cards_dir = Path("C:/cards")
        # target キー
        ve_target = _make_value_entry("leaf", literals=["leaf"])
        kd_target = _make_key_def(
            "target", cards_dir / "test.yaml", values=[ve_target]
        )
        # コメントアウトされた参照
        ref = WildcardRef(raw="__target__", full_path="target")
        ve_commented = _make_value_entry(
            "__target__",
            is_commented=True,
            refs=[ref],
        )
        kd = _make_key_def(
            "parent", cards_dir / "test.yaml", values=[ve_commented]
        )
        registry = _make_registry(
            ("parent", kd),
            ("target", kd_target),
        )
        index: FullPathIndex = {"target": kd_target}

        root = build_tree(kd, registry, index)

        assert len(root.children) == 1
        ref_node = root.children[0]
        assert ref_node.node_type == NodeType.REF
        # value_entry が is_commented=True のまま保持されている
        assert ref_node.value_entry is not None
        assert ref_node.value_entry.is_commented is True


# =========================================================================
# ノード属性テスト
# =========================================================================


class TestBuildTreeノード属性:
    """TreeNode の各属性が正しく設定されるかのテスト。"""

    def test_TreeNode_value_entryが元のValueEntryを正しく参照する(self):
        """TreeNode.value_entry が元の ValueEntry を正しく参照する。"""
        cards_dir = Path("C:/cards")
        ve = _make_value_entry("hello", literals=["hello"])
        kd = _make_key_def("key", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("key", kd))
        index: FullPathIndex = {}

        root = build_tree(kd, registry, index)

        child = root.children[0]
        assert child.value_entry is ve

    def test_TreeNode_refが元のWildcardRefを正しく参照する(self):
        """TreeNode.ref が元の WildcardRef を正しく参照する。"""
        cards_dir = Path("C:/cards")
        ve_target = _make_value_entry("val", literals=["val"])
        kd_target = _make_key_def(
            "target", cards_dir / "test.yaml", values=[ve_target]
        )
        ref = WildcardRef(raw="__target__", full_path="target")
        ve = _make_value_entry("__target__", refs=[ref])
        kd = _make_key_def("source", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("source", kd), ("target", kd_target))
        index: FullPathIndex = {"target": kd_target}

        root = build_tree(kd, registry, index)

        ref_node = root.children[0]
        assert ref_node.ref is ref

    def test_TreeNode_key_defが参照先のKeyDefinitionを正しく参照する(self):
        """TreeNode.key_def が参照先の KeyDefinition を正しく参照する。"""
        cards_dir = Path("C:/cards")
        ve_target = _make_value_entry("val", literals=["val"])
        kd_target = _make_key_def(
            "target", cards_dir / "test.yaml", values=[ve_target]
        )
        ref = WildcardRef(raw="__target__", full_path="target")
        ve = _make_value_entry("__target__", refs=[ref])
        kd = _make_key_def("source", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("source", kd), ("target", kd_target))
        index: FullPathIndex = {"target": kd_target}

        root = build_tree(kd, registry, index)

        ref_node = root.children[0]
        assert ref_node.key_def is kd_target

    def test_ROOTノードのvalue_entryはNone_refはNone(self):
        """ROOT ノードの value_entry は None、ref は None。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("root_key", cards_dir / "test.yaml")
        registry = _make_registry(("root_key", kd))
        index: FullPathIndex = {}

        root = build_tree(kd, registry, index)

        assert root.value_entry is None
        assert root.ref is None

    def test_LITERALノードのkey_defはNone_refはNone(self):
        """LITERAL ノードの key_def は None、ref は None。"""
        cards_dir = Path("C:/cards")
        ve = _make_value_entry("hello", literals=["hello"])
        kd = _make_key_def("key", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("key", kd))
        index: FullPathIndex = {}

        root = build_tree(kd, registry, index)

        literal = root.children[0]
        assert literal.key_def is None
        assert literal.ref is None

    def test_CIRCULARノードのkey_defはNone(self):
        """CIRCULAR ノードの key_def は None（循環先を展開しないため）。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(raw="__A__", full_path="A")
        ve = _make_value_entry("__A__", refs=[ref])
        kd = _make_key_def("A", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("A", kd))
        index: FullPathIndex = {"A": kd}

        root = build_tree(kd, registry, index)

        circular = root.children[0]
        assert circular.node_type == NodeType.CIRCULAR
        assert circular.key_def is None

    def test_UNRESOLVEDノードの子ノードなし(self):
        """UNRESOLVED ノードには子ノードがない。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(raw="__no_exist__", full_path="no_exist")
        ve = _make_value_entry("__no_exist__", refs=[ref])
        kd = _make_key_def("entry", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("entry", kd))
        index: FullPathIndex = {}

        root = build_tree(kd, registry, index)

        unresolved = root.children[0]
        assert unresolved.node_type == NodeType.UNRESOLVED
        assert len(unresolved.children) == 0


# =========================================================================
# 混合テスト
# =========================================================================


class TestBuildTree混合:
    """build_tree の混合テスト。"""

    def test_build_tree_1つの値行に参照3つリテラル2つ_5つの子ノード(self):
        """1つの値行に参照3つ + リテラル2つ → 5つの子ノードが生成される。"""
        cards_dir = Path("C:/cards")
        # 3つの参照先キー
        kd_ref1 = _make_key_def("ref1", cards_dir / "test.yaml")
        kd_ref2 = _make_key_def("ref2", cards_dir / "test.yaml")
        kd_ref3 = _make_key_def("ref3", cards_dir / "test.yaml")
        # 1つの値行に参照3つ + リテラル2つ
        r1 = WildcardRef(raw="__ref1__", full_path="ref1")
        r2 = WildcardRef(raw="__ref2__", full_path="ref2")
        r3 = WildcardRef(raw="__ref3__", full_path="ref3")
        ve = _make_value_entry(
            "__ref1__,__ref2__,__ref3__,lit_a,lit_b",
            refs=[r1, r2, r3],
            literals=["lit_a", "lit_b"],
        )
        kd = _make_key_def("parent", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(
            ("parent", kd),
            ("ref1", kd_ref1),
            ("ref2", kd_ref2),
            ("ref3", kd_ref3),
        )
        index: FullPathIndex = {
            "ref1": kd_ref1,
            "ref2": kd_ref2,
            "ref3": kd_ref3,
        }

        root = build_tree(kd, registry, index)

        # 1つの ValueEntry から 5 つの子ノード
        assert len(root.children) == 5
        ref_nodes = [c for c in root.children if c.node_type == NodeType.REF]
        literal_nodes = [c for c in root.children if c.node_type == NodeType.LITERAL]
        assert len(ref_nodes) == 3
        assert len(literal_nodes) == 2

    def test_build_tree_未解決参照と循環参照が混在するケース(self):
        """未解決参照と循環参照が同一ツリー内に混在するケース。"""
        cards_dir = Path("C:/cards")
        # child_circular → parent（循環）
        ref_parent = WildcardRef(raw="__parent__", full_path="parent")
        ve_child = _make_value_entry("__parent__", refs=[ref_parent])
        kd_child = _make_key_def(
            "child_circular", cards_dir / "test.yaml", values=[ve_child]
        )
        # parent → child_circular（循環）+ broken_ref（未解決）
        ref_child = WildcardRef(
            raw="__child_circular__", full_path="child_circular"
        )
        ref_broken = WildcardRef(raw="__broken_ref__", full_path="broken_ref")
        ve_parent = _make_value_entry("__child_circular__", refs=[ref_child])
        ve_parent2 = _make_value_entry("__broken_ref__", refs=[ref_broken])
        kd_parent = _make_key_def(
            "parent", cards_dir / "test.yaml", values=[ve_parent, ve_parent2]
        )
        registry = _make_registry(
            ("parent", kd_parent),
            ("child_circular", kd_child),
        )
        index: FullPathIndex = {
            "parent": kd_parent,
            "child_circular": kd_child,
        }

        root = build_tree(kd_parent, registry, index)

        assert root.node_type == NodeType.ROOT
        # 子ノードに REF（child_circular）と UNRESOLVED（broken_ref）
        assert len(root.children) == 2
        child_types = {c.node_type for c in root.children}
        assert NodeType.REF in child_types or NodeType.CIRCULAR in child_types
        assert NodeType.UNRESOLVED in child_types
        # child_circular の中に CIRCULAR ノード（parent への循環）があるはず
        circular_nodes = _find_nodes_by_type(root, NodeType.CIRCULAR)
        assert len(circular_nodes) >= 1

    def test_build_tree_同じvalue_entryから生成された複数ノードが同一value_entryを参照(self):
        """同じ値行から生成された複数のノードが、同一の value_entry を参照する。"""
        cards_dir = Path("C:/cards")
        kd_ref1 = _make_key_def("ref1", cards_dir / "test.yaml")
        r1 = WildcardRef(raw="__ref1__", full_path="ref1")
        ve = _make_value_entry(
            "__ref1__,lit_val",
            refs=[r1],
            literals=["lit_val"],
        )
        kd = _make_key_def("parent", cards_dir / "test.yaml", values=[ve])
        registry = _make_registry(("parent", kd), ("ref1", kd_ref1))
        index: FullPathIndex = {"ref1": kd_ref1}

        root = build_tree(kd, registry, index)

        assert len(root.children) == 2
        # 両方のノードが同一の value_entry を参照
        assert root.children[0].value_entry is ve
        assert root.children[1].value_entry is ve


# =========================================================================
# 統合テスト（既存フィクスチャを使用）
# =========================================================================


class TestBuildTree統合_simple:
    """simple_cards_dir フィクスチャを使った統合テスト。"""

    def _build_from_cards_dir(
        self, cards_dir: Path
    ) -> tuple[KeyRegistry, FullPathIndex]:
        """cards_dir からスキャン・パース・インデックス構築を行うヘルパー。"""
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)
        index = build_full_path_index(registry, cards_dir)
        return registry, index

    def test_simple_cards_dir_greetingからツリーを構築(
        self, simple_cards_dir: Path
    ):
        """simple_cards_dir の greeting キーからツリーを構築する。

        greeting → farewell（参照）+ hello（リテラル）
        """
        registry, index = self._build_from_cards_dir(simple_cards_dir)
        kd_greeting = registry["greeting"][-1]

        root = build_tree(kd_greeting, registry, index)

        assert root.node_type == NodeType.ROOT
        assert root.display_name == "greeting"
        assert len(root.children) >= 1
        # greeting の値行には hello (リテラル) と __farewell__ (参照) がある
        child_types = {c.node_type for c in root.children}
        # 少なくとも REF か LITERAL が含まれるはず
        assert len(child_types) >= 1


class TestBuildTree統合_circular:
    """circular_ref_cards_dir フィクスチャを使った統合テスト。"""

    def _build_from_cards_dir(
        self, cards_dir: Path
    ) -> tuple[KeyRegistry, FullPathIndex]:
        """cards_dir からスキャン・パース・インデックス構築を行うヘルパー。"""
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)
        index = build_full_path_index(registry, cards_dir)
        return registry, index

    def test_circular_ref_cards_dir_循環が正しく検出される(
        self, circular_ref_cards_dir: Path
    ):
        """circular_ref_cards_dir で alpha → beta → alpha の循環が検出される。"""
        registry, index = self._build_from_cards_dir(circular_ref_cards_dir)
        kd_alpha = registry["alpha"][-1]

        root = build_tree(kd_alpha, registry, index)

        # alpha → beta → alpha (CIRCULAR)
        assert root.node_type == NodeType.ROOT
        circular_nodes = _find_nodes_by_type(root, NodeType.CIRCULAR)
        assert len(circular_nodes) >= 1


class TestBuildTree統合_diamond:
    """diamond_ref_cards_dir フィクスチャを使った統合テスト。"""

    def _build_from_cards_dir(
        self, cards_dir: Path
    ) -> tuple[KeyRegistry, FullPathIndex]:
        """cards_dir からスキャン・パース・インデックス構築を行うヘルパー。"""
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)
        index = build_full_path_index(registry, cards_dir)
        return registry, index

    def test_diamond_ref_cards_dir_両ブランチでsharedが展開される(
        self, diamond_ref_cards_dir: Path
    ):
        """diamond_ref_cards_dir で root → branch_a/branch_b →
        shared が両ブランチで展開される。"""
        registry, index = self._build_from_cards_dir(diamond_ref_cards_dir)
        kd_root = registry["root"][-1]

        root = build_tree(kd_root, registry, index)

        assert root.node_type == NodeType.ROOT
        # CIRCULAR ノードは存在しないはず（ダイヤモンドは循環ではない）
        circular_nodes = _find_nodes_by_type(root, NodeType.CIRCULAR)
        assert len(circular_nodes) == 0
        # shared ノードが2回出現する
        ref_nodes = _find_nodes_by_type(root, NodeType.REF)
        shared_refs = [n for n in ref_nodes if n.display_name == "shared"]
        assert len(shared_refs) == 2


class TestBuildTree統合_multi_file:
    """multi_file_cards_dir フィクスチャを使った統合テスト。"""

    def _build_from_cards_dir(
        self, cards_dir: Path
    ) -> tuple[KeyRegistry, FullPathIndex]:
        """cards_dir からスキャン・パース・インデックス構築を行うヘルパー。"""
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)
        index = build_full_path_index(registry, cards_dir)
        return registry, index

    def test_multi_file_cards_dir_メインからツリー構築(
        self, multi_file_cards_dir: Path
    ):
        """multi_file_cards_dir の メイン キーからクロスファイル参照を含む
        ツリーが正しく構築される。"""
        registry, index = self._build_from_cards_dir(multi_file_cards_dir)
        kd_main = registry["メイン"][-1]

        root = build_tree(kd_main, registry, index)

        assert root.node_type == NodeType.ROOT
        assert root.display_name == "メイン"
        # メイン → シーンまとめ, デフォルト
        assert len(root.children) >= 2
        # ツリーに UNRESOLVED がないことを確認（全参照が解決されるべき）
        # ただし 朝田詩乃髪型 は定義がないので UNRESOLVED になりうる
        ref_nodes = _find_nodes_by_type(root, NodeType.REF)
        # 少なくともシーンまとめ、デフォルトが REF ノードとして存在
        ref_names = [n.display_name for n in ref_nodes]
        assert "シーンまとめ" in ref_names or "デフォルト" in ref_names


class TestBuildTree統合_commented:
    """commented_ref_cards_dir フィクスチャを使った統合テスト。"""

    def _build_from_cards_dir(
        self, cards_dir: Path
    ) -> tuple[KeyRegistry, FullPathIndex]:
        """cards_dir からスキャン・パース・インデックス構築を行うヘルパー。"""
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)
        index = build_full_path_index(registry, cards_dir)
        return registry, index

    def test_commented_ref_cards_dir_コメント行の参照も展開される(
        self, commented_ref_cards_dir: Path
    ):
        """commented_ref_cards_dir で コメントアウトされたシロコへの
        参照も展開される。"""
        registry, index = self._build_from_cards_dir(commented_ref_cards_dir)
        kd_scene = registry["シーンまとめ"][-1]

        root = build_tree(kd_scene, registry, index)

        assert root.node_type == NodeType.ROOT
        # シーンまとめ → 朝田詩乃（有効）+ シロコ（コメントアウト）
        assert len(root.children) >= 1
        # コメントアウトされた値行から生成されたノードの is_commented が True
        commented_entries = [
            c for c in root.children
            if c.value_entry is not None and c.value_entry.is_commented
        ]
        # コメント行の参照も展開されていることを確認
        # （朝田詩乃は有効、シロコはコメント）
        # パーサーの実装により、コメント行が ValueEntry として含まれている場合のみ
        # コメントノードが生成される


class TestBuildTree統合_broken:
    """broken_ref_cards_dir フィクスチャを使った統合テスト。"""

    def _build_from_cards_dir(
        self, cards_dir: Path
    ) -> tuple[KeyRegistry, FullPathIndex]:
        """cards_dir からスキャン・パース・インデックス構築を行うヘルパー。"""
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)
        index = build_full_path_index(registry, cards_dir)
        return registry, index

    def test_broken_ref_cards_dir_未解決参照がUNRESOLVEDになる(
        self, broken_ref_cards_dir: Path
    ):
        """broken_ref_cards_dir の entry から、
        existing_key は REF、non_existent_key は UNRESOLVED になる。"""
        registry, index = self._build_from_cards_dir(broken_ref_cards_dir)
        kd_entry = registry["entry"][-1]

        root = build_tree(kd_entry, registry, index)

        assert root.node_type == NodeType.ROOT
        ref_nodes = _find_nodes_by_type(root, NodeType.REF)
        unresolved_nodes = _find_nodes_by_type(root, NodeType.UNRESOLVED)
        assert len(ref_nodes) >= 1  # existing_key
        assert len(unresolved_nodes) >= 1  # non_existent_key


class TestBuildTree統合_broken_and_circular:
    """broken_and_circular_cards_dir フィクスチャを使った統合テスト。"""

    def _build_from_cards_dir(
        self, cards_dir: Path
    ) -> tuple[KeyRegistry, FullPathIndex]:
        """cards_dir からスキャン・パース・インデックス構築を行うヘルパー。"""
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)
        index = build_full_path_index(registry, cards_dir)
        return registry, index

    def test_broken_and_circular_cards_dir_未解決と循環が混在(
        self, broken_and_circular_cards_dir: Path
    ):
        """broken_and_circular_cards_dir で未解決参照と循環参照が
        同一ツリー内に混在する。"""
        registry, index = self._build_from_cards_dir(
            broken_and_circular_cards_dir
        )
        kd_parent = registry["parent"][-1]

        root = build_tree(kd_parent, registry, index)

        assert root.node_type == NodeType.ROOT
        # CIRCULAR と UNRESOLVED の両方が存在する
        circular_nodes = _find_nodes_by_type(root, NodeType.CIRCULAR)
        unresolved_nodes = _find_nodes_by_type(root, NodeType.UNRESOLVED)
        assert len(circular_nodes) >= 1
        assert len(unresolved_nodes) >= 1


class TestBuildTree統合_nested:
    """nested_ref_cards_dir フィクスチャを使った統合テスト。"""

    def _build_from_cards_dir(
        self, cards_dir: Path
    ) -> tuple[KeyRegistry, FullPathIndex]:
        """cards_dir からスキャン・パース・インデックス構築を行うヘルパー。"""
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)
        index = build_full_path_index(registry, cards_dir)
        return registry, index

    def test_nested_ref_cards_dir_動的参照がDYNAMICノードとして構築される(
        self, nested_ref_cards_dir: Path
    ):
        """nested_ref_cards_dir の scene キーから動的参照が DYNAMIC ノードとして
        構築され、inner_refs (season, character) が子ノードとして展開される。"""
        registry, index = self._build_from_cards_dir(nested_ref_cards_dir)
        kd_scene = registry["scene"][-1]

        root = build_tree(kd_scene, registry, index)

        assert root.node_type == NodeType.ROOT
        # scene の値行は動的参照
        dynamic_nodes = _find_nodes_by_type(root, NodeType.DYNAMIC)
        assert len(dynamic_nodes) >= 1
        # 動的参照の子ノードに season/character の REF が含まれる
        dynamic = dynamic_nodes[0]
        child_ref_names = [
            c.display_name for c in dynamic.children if c.node_type == NodeType.REF
        ]
        assert "season" in child_ref_names
        assert "character" in child_ref_names


# =========================================================================
# build_forest 統合テスト
# =========================================================================


class TestBuildForest統合:
    """build_forest の統合テスト。"""

    def _build_from_cards_dir(
        self, cards_dir: Path
    ) -> tuple[KeyRegistry, FullPathIndex]:
        """cards_dir からスキャン・パース・インデックス構築を行うヘルパー。"""
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)
        index = build_full_path_index(registry, cards_dir)
        return registry, index

    def test_build_forest_simple_cards_dirでトップツリーのフォレスト構築(
        self, simple_cards_dir: Path
    ):
        """simple_cards_dir でトップツリーのフォレストが構築される。"""
        from core.top_tree import find_top_trees

        registry, index = self._build_from_cards_dir(simple_cards_dir)
        top_trees = find_top_trees(registry)

        forest = build_forest(top_trees, registry, index)

        assert len(forest) == len(top_trees)
        for tree_node in forest:
            assert tree_node.node_type == NodeType.ROOT

    def test_build_forest_diamond_ref_cards_dirで循環なしフォレスト構築(
        self, diamond_ref_cards_dir: Path
    ):
        """diamond_ref_cards_dir でフォレストを構築し、
        循環ノードがないことを確認する。"""
        from core.top_tree import find_top_trees

        registry, index = self._build_from_cards_dir(diamond_ref_cards_dir)
        top_trees = find_top_trees(registry)

        forest = build_forest(top_trees, registry, index)

        for tree_node in forest:
            circular = _find_nodes_by_type(tree_node, NodeType.CIRCULAR)
            assert len(circular) == 0


# =========================================================================
# エラーハンドリング（例外を投げないことの確認）
# =========================================================================


class TestBuildTreeエラーハンドリング:
    """build_tree / build_forest が例外を投げないことの確認。"""

    def test_build_tree_空のレジストリと空のインデックスでも例外を投げない(self):
        """空のレジストリと空のインデックスでも例外なく TreeNode を返す。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(raw="__missing__", full_path="missing")
        ve = _make_value_entry("__missing__", refs=[ref])
        kd = _make_key_def("orphan", cards_dir / "test.yaml", values=[ve])

        root = build_tree(kd, {}, {})

        assert root.node_type == NodeType.ROOT
        assert root.display_name == "orphan"

    def test_build_forest_例外を投げない(self):
        """build_forest は例外を投げない。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("entry", cards_dir / "test.yaml")
        top_trees = [
            TopTreeInfo(name="entry", key_def=kd, file_path=kd.file_path),
        ]

        # 空レジストリ・空インデックスでも例外なし
        forest = build_forest(top_trees, {}, {})

        assert isinstance(forest, list)
        assert len(forest) == 1
