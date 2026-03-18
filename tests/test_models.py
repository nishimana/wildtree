"""Unit tests for core/models.py — データモデル定義のテスト。

設計意図ドキュメント (docs/design/s1-data-models.md) に基づいて、
データクラス群・Enum・型エイリアスの構造と振る舞いを検証する。

テスト対象:
  - RefType (Enum)
  - NodeType (Enum)
  - WildcardRef (frozen dataclass + name プロパティ)
  - ValueEntry (dataclass)
  - KeyDefinition (dataclass)
  - TreeNode (dataclass)
  - KeyRegistry (型エイリアス)

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models import (
    KeyDefinition,
    KeyRegistry,
    NodeType,
    RefType,
    TreeNode,
    ValueEntry,
    WildcardRef,
)


# =========================================================================
# RefType Enum
# =========================================================================


class TestRefType:
    """RefType Enum の定義テスト。"""

    def test_RefType_NORMAL値が定義されている(self):
        """RefType.NORMAL is defined with value 'normal'."""
        assert RefType.NORMAL.value == "normal"

    def test_RefType_DYNAMIC値が定義されている(self):
        """RefType.DYNAMIC is defined with value 'dynamic'."""
        assert RefType.DYNAMIC.value == "dynamic"

    def test_RefType_全値が2つである(self):
        """RefType has exactly 2 members (NORMAL, DYNAMIC)."""
        assert len(RefType) == 2

    def test_RefType_メンバー名の一覧(self):
        """RefType members are NORMAL and DYNAMIC."""
        member_names = {m.name for m in RefType}
        assert member_names == {"NORMAL", "DYNAMIC"}


# =========================================================================
# NodeType Enum
# =========================================================================


class TestNodeType:
    """NodeType Enum の定義テスト。"""

    def test_NodeType_ROOT値が定義されている(self):
        """NodeType.ROOT is defined with value 'root'."""
        assert NodeType.ROOT.value == "root"

    def test_NodeType_REF値が定義されている(self):
        """NodeType.REF is defined with value 'ref'."""
        assert NodeType.REF.value == "ref"

    def test_NodeType_LITERAL値が定義されている(self):
        """NodeType.LITERAL is defined with value 'literal'."""
        assert NodeType.LITERAL.value == "literal"

    def test_NodeType_DYNAMIC値が定義されている(self):
        """NodeType.DYNAMIC is defined with value 'dynamic'."""
        assert NodeType.DYNAMIC.value == "dynamic"

    def test_NodeType_UNRESOLVED値が定義されている(self):
        """NodeType.UNRESOLVED is defined with value 'unresolved'."""
        assert NodeType.UNRESOLVED.value == "unresolved"

    def test_NodeType_CIRCULAR値が定義されている(self):
        """NodeType.CIRCULAR is defined with value 'circular'."""
        assert NodeType.CIRCULAR.value == "circular"

    def test_NodeType_EMPTY値が定義されている(self):
        """NodeType.EMPTY is defined with value 'empty'."""
        assert NodeType.EMPTY.value == "empty"

    def test_NodeType_全値が7つである(self):
        """NodeType has exactly 7 members."""
        assert len(NodeType) == 7

    def test_NodeType_メンバー名の一覧(self):
        """NodeType members are ROOT, REF, LITERAL, DYNAMIC, UNRESOLVED, CIRCULAR, EMPTY."""
        member_names = {m.name for m in NodeType}
        expected = {"ROOT", "REF", "LITERAL", "DYNAMIC", "UNRESOLVED", "CIRCULAR", "EMPTY"}
        assert member_names == expected


# =========================================================================
# WildcardRef (frozen dataclass)
# =========================================================================


class TestWildcardRef:
    """WildcardRef の生成・プロパティ・frozen 性のテスト。"""

    # -- 正常系: 生成と初期値 --

    def test_WildcardRef_必須フィールドで生成できる(self):
        """WildcardRef can be created with required fields (raw, full_path)."""
        ref = WildcardRef(raw="__greeting__", full_path="greeting")
        assert ref.raw == "__greeting__"
        assert ref.full_path == "greeting"

    def test_WildcardRef_デフォルト値が正しい(self):
        """Default values: ref_type=NORMAL, inner_refs=()."""
        ref = WildcardRef(raw="__test__", full_path="test")
        assert ref.ref_type == RefType.NORMAL
        assert ref.inner_refs == ()

    def test_WildcardRef_全フィールドを指定して生成できる(self):
        """WildcardRef can be created with all fields explicitly set."""
        inner = WildcardRef(raw="__inner__", full_path="inner")
        ref = WildcardRef(
            raw="__outer__",
            full_path="outer",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner,),
        )
        assert ref.raw == "__outer__"
        assert ref.full_path == "outer"
        assert ref.ref_type == RefType.DYNAMIC
        assert len(ref.inner_refs) == 1
        assert ref.inner_refs[0] is inner

    # -- 正常系: name プロパティ --

    def test_WildcardRef_name_フルパスの最後の要素を返す(self):
        """name property returns last segment after '/'."""
        ref = WildcardRef(raw="__cards/SAO/キー名__", full_path="cards/SAO/キー名")
        assert ref.name == "キー名"

    def test_WildcardRef_name_深いパスの最後の要素を返す(self):
        """name property works with deeply nested paths."""
        ref = WildcardRef(
            raw="__cards/SAO/CH_asada_shino/キー名__",
            full_path="cards/SAO/CH_asada_shino/キー名",
        )
        assert ref.name == "キー名"

    def test_WildcardRef_name_スラッシュなしの場合はfull_path全体を返す(self):
        """name property returns full_path when no '/' is present."""
        ref = WildcardRef(raw="__キー名__", full_path="キー名")
        assert ref.name == "キー名"

    def test_WildcardRef_name_空文字列の場合は空文字列を返す(self):
        """name property returns empty string when full_path is empty."""
        ref = WildcardRef(raw="____", full_path="")
        assert ref.name == ""

    def test_WildcardRef_name_英語のパスでも動作する(self):
        """name property works with ASCII-only paths."""
        ref = WildcardRef(
            raw="__cards/scenes/main_scene__",
            full_path="cards/scenes/main_scene",
        )
        assert ref.name == "main_scene"

    def test_WildcardRef_name_末尾スラッシュの場合は空文字列を返す(self):
        """name property returns empty string when full_path ends with '/'."""
        ref = WildcardRef(raw="__cards/__", full_path="cards/")
        assert ref.name == ""

    # -- 正常系: frozen 性 (hashable / セット対応) --

    def test_WildcardRef_hashableである(self):
        """WildcardRef is hashable (frozen dataclass)."""
        ref = WildcardRef(raw="__test__", full_path="test")
        # hash() が例外を投げないことを確認
        h = hash(ref)
        assert isinstance(h, int)

    def test_WildcardRef_セットに追加できる(self):
        """WildcardRef can be added to a set."""
        ref1 = WildcardRef(raw="__a__", full_path="a")
        ref2 = WildcardRef(raw="__b__", full_path="b")
        ref_set = {ref1, ref2}
        assert len(ref_set) == 2
        assert ref1 in ref_set
        assert ref2 in ref_set

    def test_WildcardRef_同じ値のインスタンスはセットで重複排除される(self):
        """Two WildcardRef instances with same values are equal and deduplicated in set."""
        ref1 = WildcardRef(raw="__test__", full_path="test")
        ref2 = WildcardRef(raw="__test__", full_path="test")
        ref_set = {ref1, ref2}
        assert len(ref_set) == 1

    def test_WildcardRef_辞書のキーとして使用できる(self):
        """WildcardRef can be used as a dictionary key."""
        ref = WildcardRef(raw="__key__", full_path="key")
        d = {ref: "value"}
        assert d[ref] == "value"

    # -- 異常系: frozen なので属性変更でエラー --

    def test_WildcardRef_属性変更でFrozenInstanceError(self):
        """Assigning to a frozen WildcardRef attribute raises an error."""
        ref = WildcardRef(raw="__test__", full_path="test")
        # frozen=True の dataclass は属性変更時に FrozenInstanceError を投げる
        with pytest.raises(AttributeError):
            ref.raw = "modified"  # type: ignore[misc]

    def test_WildcardRef_full_path変更でFrozenInstanceError(self):
        """Assigning to full_path on a frozen WildcardRef raises an error."""
        ref = WildcardRef(raw="__test__", full_path="test")
        with pytest.raises(AttributeError):
            ref.full_path = "modified"  # type: ignore[misc]

    def test_WildcardRef_ref_type変更でFrozenInstanceError(self):
        """Assigning to ref_type on a frozen WildcardRef raises an error."""
        ref = WildcardRef(raw="__test__", full_path="test")
        with pytest.raises(AttributeError):
            ref.ref_type = RefType.DYNAMIC  # type: ignore[misc]

    def test_WildcardRef_inner_refs変更でFrozenInstanceError(self):
        """Assigning to inner_refs on a frozen WildcardRef raises an error."""
        ref = WildcardRef(raw="__test__", full_path="test")
        with pytest.raises(AttributeError):
            ref.inner_refs = ()  # type: ignore[misc]

    # -- エッジケース: 動的参照 --

    def test_WildcardRef_動的参照_inner_refsが設定できる(self):
        """Dynamic reference with inner_refs tuple."""
        inner1 = WildcardRef(raw="__season__", full_path="season")
        inner2 = WildcardRef(raw="__character__", full_path="character")
        ref = WildcardRef(
            raw="__{__season__}_{__character__}__",
            full_path="{season}_{character}",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner1, inner2),
        )
        assert ref.ref_type == RefType.DYNAMIC
        assert len(ref.inner_refs) == 2
        assert ref.inner_refs[0].full_path == "season"
        assert ref.inner_refs[1].full_path == "character"

    def test_WildcardRef_inner_refsが空タプルの場合(self):
        """inner_refs defaults to empty tuple for normal references."""
        ref = WildcardRef(raw="__normal__", full_path="normal")
        assert ref.inner_refs == ()
        assert len(ref.inner_refs) == 0

    def test_WildcardRef_inner_refsはtupleでlistではない(self):
        """inner_refs is a tuple, not a list (for frozen hashability)."""
        inner = WildcardRef(raw="__inner__", full_path="inner")
        ref = WildcardRef(
            raw="__outer__",
            full_path="outer",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner,),
        )
        assert isinstance(ref.inner_refs, tuple)


# =========================================================================
# ValueEntry
# =========================================================================


class TestValueEntry:
    """ValueEntry データクラスのテスト。"""

    # -- 正常系: 生成と初期値 --

    def test_ValueEntry_必須フィールドで生成できる(self):
        """ValueEntry can be created with required fields (raw_text, line_number)."""
        ve = ValueEntry(raw_text="__cards/xxx__,literal_tag", line_number=5)
        assert ve.raw_text == "__cards/xxx__,literal_tag"
        assert ve.line_number == 5

    def test_ValueEntry_デフォルト値が正しい(self):
        """Default values: is_commented=False, refs=[], literals=[]."""
        ve = ValueEntry(raw_text="value", line_number=1)
        assert ve.is_commented is False
        assert ve.refs == []
        assert ve.literals == []

    def test_ValueEntry_全フィールドを指定して生成できる(self):
        """ValueEntry can be created with all fields explicitly set."""
        ref = WildcardRef(raw="__tag__", full_path="tag")
        ve = ValueEntry(
            raw_text="__tag__,literal_part",
            line_number=10,
            is_commented=True,
            refs=[ref],
            literals=["literal_part"],
        )
        assert ve.raw_text == "__tag__,literal_part"
        assert ve.line_number == 10
        assert ve.is_commented is True
        assert len(ve.refs) == 1
        assert ve.refs[0] is ref
        assert ve.literals == ["literal_part"]

    # -- 正常系: リストフィールドの独立性 --

    def test_ValueEntry_refsリストのデフォルトが独立している(self):
        """Default refs list is independent between instances (no shared mutable default)."""
        ve1 = ValueEntry(raw_text="a", line_number=1)
        ve2 = ValueEntry(raw_text="b", line_number=2)
        ref = WildcardRef(raw="__test__", full_path="test")
        ve1.refs.append(ref)
        # ve2.refs は影響を受けない
        assert len(ve2.refs) == 0

    def test_ValueEntry_literalsリストのデフォルトが独立している(self):
        """Default literals list is independent between instances."""
        ve1 = ValueEntry(raw_text="a", line_number=1)
        ve2 = ValueEntry(raw_text="b", line_number=2)
        ve1.literals.append("tag1")
        # ve2.literals は影響を受けない
        assert len(ve2.literals) == 0

    # -- エッジケース --

    def test_ValueEntry_コメント行の生成(self):
        """ValueEntry with is_commented=True represents a commented-out value line."""
        ve = ValueEntry(
            raw_text="__disabled_ref__",
            line_number=3,
            is_commented=True,
        )
        assert ve.is_commented is True
        assert ve.raw_text == "__disabled_ref__"

    def test_ValueEntry_空のraw_text(self):
        """ValueEntry with empty raw_text."""
        ve = ValueEntry(raw_text="", line_number=1)
        assert ve.raw_text == ""

    def test_ValueEntry_複数の参照を持つ値行(self):
        """ValueEntry with multiple refs in a single line."""
        ref1 = WildcardRef(raw="__a__", full_path="a")
        ref2 = WildcardRef(raw="__b__", full_path="b")
        ref3 = WildcardRef(raw="__c__", full_path="c")
        ve = ValueEntry(
            raw_text="__a__,__b__,__c__",
            line_number=7,
            refs=[ref1, ref2, ref3],
        )
        assert len(ve.refs) == 3

    def test_ValueEntry_参照とリテラルが混在(self):
        """ValueEntry with both refs and literals."""
        ref = WildcardRef(raw="__cards/シネマシャドウ__", full_path="cards/シネマシャドウ")
        ve = ValueEntry(
            raw_text="dynamic_angle,dynamic_pose,__cards/シネマシャドウ__",
            line_number=15,
            refs=[ref],
            literals=["dynamic_angle", "dynamic_pose"],
        )
        assert len(ve.refs) == 1
        assert len(ve.literals) == 2

    def test_ValueEntry_ミュータブルなのでフィールド変更可能(self):
        """ValueEntry is mutable (not frozen), so fields can be modified."""
        ve = ValueEntry(raw_text="original", line_number=1)
        ve.raw_text = "modified"
        ve.line_number = 99
        ve.is_commented = True
        assert ve.raw_text == "modified"
        assert ve.line_number == 99
        assert ve.is_commented is True


# =========================================================================
# KeyDefinition
# =========================================================================


class TestKeyDefinition:
    """KeyDefinition データクラスのテスト。"""

    # -- 正常系: 生成と初期値 --

    def test_KeyDefinition_必須フィールドで生成できる(self):
        """KeyDefinition can be created with required fields."""
        kd = KeyDefinition(
            name="メイン",
            file_path=Path("cards/main.yaml"),
            line_number=1,
        )
        assert kd.name == "メイン"
        assert kd.file_path == Path("cards/main.yaml")
        assert kd.line_number == 1

    def test_KeyDefinition_valuesデフォルトは空リスト(self):
        """Default values is an empty list."""
        kd = KeyDefinition(
            name="test",
            file_path=Path("test.yaml"),
            line_number=1,
        )
        assert kd.values == []
        assert isinstance(kd.values, list)

    def test_KeyDefinition_valuesリストのデフォルトが独立している(self):
        """Default values list is independent between instances."""
        kd1 = KeyDefinition(name="a", file_path=Path("a.yaml"), line_number=1)
        kd2 = KeyDefinition(name="b", file_path=Path("b.yaml"), line_number=1)
        kd1.values.append(ValueEntry(raw_text="val", line_number=2))
        # kd2.values は影響を受けない
        assert len(kd2.values) == 0

    def test_KeyDefinition_全フィールドを指定して生成できる(self):
        """KeyDefinition can be created with all fields explicitly set."""
        ve1 = ValueEntry(raw_text="__朝田詩乃体格__", line_number=2)
        ve2 = ValueEntry(raw_text="__朝田詩乃髪型__", line_number=3)
        kd = KeyDefinition(
            name="朝田詩乃",
            file_path=Path("cards/SAO/CH_asada/asada.yaml"),
            line_number=1,
            values=[ve1, ve2],
        )
        assert kd.name == "朝田詩乃"
        assert len(kd.values) == 2
        assert kd.values[0].raw_text == "__朝田詩乃体格__"
        assert kd.values[1].raw_text == "__朝田詩乃髪型__"

    # -- エッジケース --

    def test_KeyDefinition_空のvaluesリスト(self):
        """KeyDefinition with empty values list is valid (rare but possible)."""
        kd = KeyDefinition(
            name="empty_key",
            file_path=Path("test.yaml"),
            line_number=1,
            values=[],
        )
        assert kd.values == []

    def test_KeyDefinition_日本語キー名(self):
        """KeyDefinition with Japanese key name."""
        kd = KeyDefinition(
            name="朝田詩乃SSNN0001脱00",
            file_path=Path("cards/SAO/asada.yaml"),
            line_number=5,
        )
        assert kd.name == "朝田詩乃SSNN0001脱00"

    def test_KeyDefinition_file_pathはPathオブジェクト(self):
        """file_path is a Path object."""
        kd = KeyDefinition(
            name="test",
            file_path=Path("cards/test.yaml"),
            line_number=1,
        )
        assert isinstance(kd.file_path, Path)

    def test_KeyDefinition_ミュータブルなのでフィールド変更可能(self):
        """KeyDefinition is mutable, so fields can be modified."""
        kd = KeyDefinition(
            name="original",
            file_path=Path("original.yaml"),
            line_number=1,
        )
        kd.name = "modified"
        kd.line_number = 42
        assert kd.name == "modified"
        assert kd.line_number == 42


# =========================================================================
# KeyRegistry 型エイリアス
# =========================================================================


class TestKeyRegistry:
    """KeyRegistry 型エイリアスのテスト。"""

    def test_KeyRegistry_dictベースの型エイリアスである(self):
        """KeyRegistry is a type alias based on dict."""
        # KeyRegistry = dict[str, list[KeyDefinition]] は GenericAlias
        # __origin__ が dict であることを確認
        assert getattr(KeyRegistry, "__origin__", KeyRegistry) is dict

    def test_KeyRegistry_正しい構造で使用できる(self):
        """KeyRegistry can hold str keys mapping to list[KeyDefinition]."""
        kd1 = KeyDefinition(name="style", file_path=Path("a.yaml"), line_number=1)
        kd2 = KeyDefinition(name="style", file_path=Path("b.yaml"), line_number=1)
        registry: KeyRegistry = {
            "style": [kd1, kd2],
        }
        assert "style" in registry
        assert len(registry["style"]) == 2
        assert isinstance(registry["style"][0], KeyDefinition)

    def test_KeyRegistry_空の辞書で初期化できる(self):
        """KeyRegistry can be an empty dict."""
        registry: KeyRegistry = {}
        assert len(registry) == 0

    def test_KeyRegistry_同名キーに複数のKeyDefinitionを格納できる(self):
        """Multiple KeyDefinition for the same key name (duplicate key scenario)."""
        kd_a = KeyDefinition(name="common", file_path=Path("file_a.yaml"), line_number=1)
        kd_b = KeyDefinition(name="common", file_path=Path("file_b.yaml"), line_number=1)
        registry: KeyRegistry = {"common": [kd_a, kd_b]}
        assert len(registry["common"]) == 2


# =========================================================================
# TreeNode
# =========================================================================


class TestTreeNode:
    """TreeNode データクラスのテスト。"""

    # -- 正常系: 生成と初期値 --

    def test_TreeNode_必須フィールドで生成できる(self):
        """TreeNode can be created with required fields (display_name, node_type)."""
        node = TreeNode(display_name="メイン", node_type=NodeType.ROOT)
        assert node.display_name == "メイン"
        assert node.node_type == NodeType.ROOT

    def test_TreeNode_デフォルト値が正しい(self):
        """Default values: children=[], key_def=None, value_entry=None, ref=None."""
        node = TreeNode(display_name="test", node_type=NodeType.LITERAL)
        assert node.children == []
        assert node.key_def is None
        assert node.value_entry is None
        assert node.ref is None

    def test_TreeNode_childrenリストのデフォルトが独立している(self):
        """Default children list is independent between instances."""
        node1 = TreeNode(display_name="a", node_type=NodeType.LITERAL)
        node2 = TreeNode(display_name="b", node_type=NodeType.LITERAL)
        node1.children.append(TreeNode(display_name="child", node_type=NodeType.LITERAL))
        # node2.children は影響を受けない
        assert len(node2.children) == 0

    def test_TreeNode_全フィールドを指定して生成できる(self):
        """TreeNode can be created with all fields explicitly set."""
        ref = WildcardRef(raw="__シネマシャドウ__", full_path="シネマシャドウ")
        ve = ValueEntry(raw_text="__シネマシャドウ__", line_number=5)
        kd = KeyDefinition(
            name="シネマシャドウ",
            file_path=Path("cards/scenes.yaml"),
            line_number=10,
        )
        child = TreeNode(display_name="(cinematic_shadow:1.1)", node_type=NodeType.LITERAL)
        node = TreeNode(
            display_name="シネマシャドウ",
            node_type=NodeType.REF,
            children=[child],
            key_def=kd,
            value_entry=ve,
            ref=ref,
        )
        assert node.display_name == "シネマシャドウ"
        assert node.node_type == NodeType.REF
        assert len(node.children) == 1
        assert node.children[0].display_name == "(cinematic_shadow:1.1)"
        assert node.key_def is kd
        assert node.value_entry is ve
        assert node.ref is ref

    # -- 正常系: 各 NodeType で生成 --

    def test_TreeNode_ROOTノード生成(self):
        """TreeNode with NodeType.ROOT (entry point of top tree)."""
        kd = KeyDefinition(name="メイン", file_path=Path("main.yaml"), line_number=1)
        node = TreeNode(
            display_name="メイン",
            node_type=NodeType.ROOT,
            key_def=kd,
        )
        assert node.node_type == NodeType.ROOT
        assert node.key_def is kd
        # ルートノードは value_entry と ref が None
        assert node.value_entry is None
        assert node.ref is None

    def test_TreeNode_REFノード生成(self):
        """TreeNode with NodeType.REF (resolved reference with children)."""
        ref = WildcardRef(raw="__朝田詩乃__", full_path="朝田詩乃")
        ve = ValueEntry(raw_text="__朝田詩乃__", line_number=2)
        kd = KeyDefinition(name="朝田詩乃", file_path=Path("asada.yaml"), line_number=1)
        node = TreeNode(
            display_name="朝田詩乃",
            node_type=NodeType.REF,
            key_def=kd,
            value_entry=ve,
            ref=ref,
        )
        assert node.node_type == NodeType.REF

    def test_TreeNode_LITERALノード生成(self):
        """TreeNode with NodeType.LITERAL (leaf node with prompt tag)."""
        ve = ValueEntry(raw_text="(cinematic_shadow:1.1)", line_number=3)
        node = TreeNode(
            display_name="(cinematic_shadow:1.1)",
            node_type=NodeType.LITERAL,
            value_entry=ve,
        )
        assert node.node_type == NodeType.LITERAL
        assert node.children == []
        assert node.key_def is None

    def test_TreeNode_DYNAMICノード生成(self):
        """TreeNode with NodeType.DYNAMIC (variable expansion reference)."""
        inner = WildcardRef(raw="__season__", full_path="season")
        ref = WildcardRef(
            raw="__{__season__}_scene__",
            full_path="{season}_scene",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner,),
        )
        node = TreeNode(
            display_name="{season}_scene",
            node_type=NodeType.DYNAMIC,
            ref=ref,
        )
        assert node.node_type == NodeType.DYNAMIC
        assert node.ref is ref

    def test_TreeNode_UNRESOLVEDノード生成(self):
        """TreeNode with NodeType.UNRESOLVED (broken reference, red text)."""
        ref = WildcardRef(raw="__non_existent__", full_path="non_existent")
        node = TreeNode(
            display_name="non_existent",
            node_type=NodeType.UNRESOLVED,
            ref=ref,
        )
        assert node.node_type == NodeType.UNRESOLVED
        assert node.key_def is None
        assert node.children == []

    def test_TreeNode_CIRCULARノード生成(self):
        """TreeNode with NodeType.CIRCULAR (circular reference detected)."""
        node = TreeNode(
            display_name="alpha(循環)",
            node_type=NodeType.CIRCULAR,
        )
        assert node.node_type == NodeType.CIRCULAR
        assert node.key_def is None
        assert node.children == []

    def test_TreeNode_EMPTYノード生成(self):
        """TreeNode with NodeType.EMPTY (empty definition '{}')."""
        node = TreeNode(
            display_name="(空)",
            node_type=NodeType.EMPTY,
        )
        assert node.node_type == NodeType.EMPTY
        assert node.key_def is None
        assert node.children == []

    # -- 正常系: ミュータブル性 --

    def test_TreeNode_childrenに段階的に追加できる(self):
        """Children can be appended incrementally (tree building use case)."""
        parent = TreeNode(display_name="parent", node_type=NodeType.REF)
        child1 = TreeNode(display_name="child1", node_type=NodeType.LITERAL)
        child2 = TreeNode(display_name="child2", node_type=NodeType.LITERAL)
        parent.children.append(child1)
        parent.children.append(child2)
        assert len(parent.children) == 2
        assert parent.children[0].display_name == "child1"
        assert parent.children[1].display_name == "child2"

    def test_TreeNode_ミュータブルなのでフィールド変更可能(self):
        """TreeNode is mutable, fields can be reassigned."""
        node = TreeNode(display_name="original", node_type=NodeType.LITERAL)
        node.display_name = "modified"
        node.node_type = NodeType.REF
        assert node.display_name == "modified"
        assert node.node_type == NodeType.REF

    # -- エッジケース: ツリー構造 --

    def test_TreeNode_ネストした子ノードのツリー構造(self):
        """TreeNode can form a nested tree structure."""
        leaf = TreeNode(display_name="leaf", node_type=NodeType.LITERAL)
        mid = TreeNode(
            display_name="mid",
            node_type=NodeType.REF,
            children=[leaf],
        )
        root = TreeNode(
            display_name="root",
            node_type=NodeType.ROOT,
            children=[mid],
        )
        assert len(root.children) == 1
        assert root.children[0].display_name == "mid"
        assert len(root.children[0].children) == 1
        assert root.children[0].children[0].display_name == "leaf"

    def test_TreeNode_空のchildrenリスト(self):
        """TreeNode with explicitly empty children list."""
        node = TreeNode(
            display_name="leaf",
            node_type=NodeType.LITERAL,
            children=[],
        )
        assert node.children == []
        assert len(node.children) == 0
