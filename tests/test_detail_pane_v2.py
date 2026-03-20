"""Unit tests for gui/detail_pane.py -- v2 詳細ペインのテスト。

設計意図ドキュメント (docs/design/s6-gui-tree-view.md) に基づいて、
detail_pane の各関数を検証する。

テスト対象:
  - format_node_detail(node) -> str
  - _format_ref_detail(node) -> str
  - _format_literal_detail(node) -> str
  - _format_unresolved_detail(node) -> str
  - _format_circular_detail(node) -> str
  - _format_dynamic_detail(node) -> str
  - _format_empty_detail(node) -> str

テスト命名規則: test_<対象>_<条件>_<期待結果>

Note:
  このモジュールは Qt に依存しないため、qapp フィクスチャは不要。
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


# =========================================================================
# format_node_detail の振り分けテスト
# =========================================================================


class TestFormatNodeDetail振り分け:
    """format_node_detail が NodeType に応じて正しいフォーマッタを呼ぶことのテスト。"""

    def test_format_node_detail_ROOTノード_キー情報が含まれる(self):
        """ROOT ノードの場合、_format_ref_detail が呼ばれキー情報が含まれる。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry("__ref__", line_number=2, refs=[
            WildcardRef(raw="__ref__", full_path="ref"),
        ])
        kd = _make_key_def(
            "メイン",
            file_path=Path("C:/cards/main.yaml"),
            line_number=1,
            values=[ve],
        )
        node = _make_tree_node("メイン", NodeType.ROOT, key_def=kd)

        result = format_node_detail(node)

        assert "キー名:" in result
        assert "メイン" in result

    def test_format_node_detail_REFノード_キー情報が含まれる(self):
        """REF ノードの場合、_format_ref_detail が呼ばれキー情報が含まれる。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry("__参照先__", refs=[
            WildcardRef(raw="__参照先__", full_path="参照先"),
        ])
        kd = _make_key_def(
            "参照先",
            file_path=Path("C:/cards/sub/ref.yaml"),
            line_number=3,
            values=[_make_value_entry("leaf", literals=["leaf"])],
        )
        ref = WildcardRef(raw="__参照先__", full_path="参照先")
        node = _make_tree_node(
            "参照先", NodeType.REF,
            key_def=kd,
            value_entry=ve,
            ref=ref,
        )

        result = format_node_detail(node)

        assert "キー名:" in result
        assert "参照先" in result

    def test_format_node_detail_LITERALノード_リテラル値が含まれる(self):
        """LITERAL ノードの場合、_format_literal_detail が呼ばれリテラル値が含まれる。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry("(cinematic_shadow:1.1)")
        node = _make_tree_node("(cinematic_shadow:1.1)", NodeType.LITERAL, value_entry=ve)

        result = format_node_detail(node)

        assert "リテラル値:" in result
        assert "(cinematic_shadow:1.1)" in result

    def test_format_node_detail_UNRESOLVEDノード_未解決参照ヘッダが含まれる(self):
        """UNRESOLVED ノードの場合、[未解決参照] ヘッダが含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(raw="__cards/存在しないキー__", full_path="cards/存在しないキー")
        ve = _make_value_entry("__cards/存在しないキー__")
        node = _make_tree_node("存在しないキー", NodeType.UNRESOLVED, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "[未解決参照]" in result

    def test_format_node_detail_CIRCULARノード_循環参照ヘッダが含まれる(self):
        """CIRCULAR ノードの場合、[循環参照] ヘッダが含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(raw="__cards/キー名__", full_path="cards/キー名")
        ve = _make_value_entry("__cards/キー名__")
        node = _make_tree_node("キー名 (循環)", NodeType.CIRCULAR, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "[循環参照]" in result

    def test_format_node_detail_DYNAMICノード_動的参照ヘッダが含まれる(self):
        """DYNAMIC ノードの場合、[動的参照] ヘッダが含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(
            raw="__{__cards/キャラキー__}NP__",
            full_path="{__cards/キャラキー__}NP",
            ref_type=RefType.DYNAMIC,
        )
        ve = _make_value_entry(ref.raw)
        node = _make_tree_node(ref.raw, NodeType.DYNAMIC, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "[動的参照]" in result

    def test_format_node_detail_EMPTYノード_空定義ヘッダが含まれる(self):
        """EMPTY ノードの場合、[空定義] ヘッダが含まれる。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry('"{}"')
        node = _make_tree_node("(空)", NodeType.EMPTY, value_entry=ve)

        result = format_node_detail(node)

        assert "[空定義]" in result


# =========================================================================
# _format_ref_detail のテスト
# =========================================================================


class TestFormatRefDetail:
    """_format_ref_detail のテスト（ROOT / REF ノード共通）。"""

    def test_REFノード_キー名が含まれる(self):
        """REF ノードの詳細にキー名が含まれる。"""
        from gui.detail_pane import format_node_detail

        kd = _make_key_def(
            "シーンまとめ",
            file_path=Path("C:/cards/scenes.yaml"),
            line_number=5,
            values=[
                _make_value_entry("__cards/SAO/CH_asada/朝田詩乃__", line_number=6),
            ],
        )
        ref = WildcardRef(raw="__シーンまとめ__", full_path="シーンまとめ")
        ve = _make_value_entry("__シーンまとめ__")
        node = _make_tree_node("シーンまとめ", NodeType.REF, key_def=kd, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "キー名:" in result
        assert "シーンまとめ" in result

    def test_REFノード_ファイルパスが含まれる(self):
        """REF ノードの詳細にファイルパスが含まれる。"""
        from gui.detail_pane import format_node_detail

        kd = _make_key_def(
            "シーンまとめ",
            file_path=Path("C:/cards/scenes.yaml"),
            line_number=5,
            values=[],
        )
        ref = WildcardRef(raw="__シーンまとめ__", full_path="シーンまとめ")
        ve = _make_value_entry("__シーンまとめ__")
        node = _make_tree_node("シーンまとめ", NodeType.REF, key_def=kd, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "ファイル:" in result
        # パスの区切りは環境依存だが、ファイル名は含まれるはず
        assert "scenes.yaml" in result

    def test_REFノード_行番号が含まれる(self):
        """REF ノードの詳細に行番号が含まれる。"""
        from gui.detail_pane import format_node_detail

        kd = _make_key_def(
            "シーンまとめ",
            file_path=Path("C:/cards/scenes.yaml"),
            line_number=5,
            values=[],
        )
        ref = WildcardRef(raw="__シーンまとめ__", full_path="シーンまとめ")
        ve = _make_value_entry("__シーンまとめ__")
        node = _make_tree_node("シーンまとめ", NodeType.REF, key_def=kd, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "行番号:" in result
        assert "5" in result

    def test_REFノード_値行一覧が含まれる(self):
        """REF ノードの詳細に値行一覧が含まれる。"""
        from gui.detail_pane import format_node_detail

        ve1 = _make_value_entry(
            "__cards/デフォルト__", line_number=2,
            refs=[WildcardRef(raw="__cards/デフォルト__", full_path="cards/デフォルト")],
        )
        ve2 = _make_value_entry("literal_value", line_number=3, literals=["literal_value"])
        kd = _make_key_def(
            "メイン",
            file_path=Path("C:/cards/main.yaml"),
            line_number=1,
            values=[ve1, ve2],
        )
        node = _make_tree_node("メイン", NodeType.ROOT, key_def=kd)

        result = format_node_detail(node)

        assert "値:" in result
        assert "__cards/デフォルト__" in result
        assert "literal_value" in result

    def test_REFノード_コメント行にプレフィックス表示(self):
        """コメント行（is_commented=True）の値行に "# " プレフィックスが付く。"""
        from gui.detail_pane import format_node_detail

        ve_active = _make_value_entry(
            "__cards/デフォルト__", line_number=2, is_commented=False,
            refs=[WildcardRef(raw="__cards/デフォルト__", full_path="cards/デフォルト")],
        )
        ve_commented = _make_value_entry(
            "__cards/無効化された参照__", line_number=3, is_commented=True,
            refs=[WildcardRef(raw="__cards/無効化された参照__", full_path="cards/無効化された参照")],
        )
        kd = _make_key_def(
            "メイン",
            file_path=Path("C:/cards/main.yaml"),
            line_number=1,
            values=[ve_active, ve_commented],
        )
        node = _make_tree_node("メイン", NodeType.ROOT, key_def=kd)

        result = format_node_detail(node)

        # コメント行は "# " プレフィックスが付く
        assert "# " in result
        # 通常行はプレフィックスなし（ "- " で始まる）
        lines = result.split("\n")
        # コメント行と通常行を区別して確認
        has_commented_line = False
        has_active_line = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# ") and "__cards/無効化された参照__" in stripped:
                has_commented_line = True
            if stripped.startswith("- ") and "__cards/デフォルト__" in stripped:
                has_active_line = True
        assert has_commented_line, "コメント行が見つからない"
        assert has_active_line, "通常行が見つからない"

    def test_ROOTノード_key_defがNone_防御コード(self):
        """key_def が None の ROOT ノードで防御コードが働く。"""
        from gui.detail_pane import format_node_detail

        # key_def=None の ROOT ノード（通常は発生しないが防御コード）
        node = _make_tree_node("不正ノード", NodeType.ROOT, key_def=None)

        result = format_node_detail(node)

        # 例外を投げずに文字列を返す
        assert isinstance(result, str)
        assert "キー定義情報がありません" in result

    def test_REFノード_key_defがNone_防御コード(self):
        """key_def が None の REF ノードで防御コードが働く。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry("__ref__")
        ref = WildcardRef(raw="__ref__", full_path="ref")
        node = _make_tree_node("ref", NodeType.REF, key_def=None, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert isinstance(result, str)
        assert "キー定義情報がありません" in result

    def test_REFノード_値行ゼロ_キー名のみ表示(self):
        """値行がゼロ個のキーの場合、キー名のみ表示される。"""
        from gui.detail_pane import format_node_detail

        kd = _make_key_def(
            "空キー",
            file_path=Path("C:/cards/empty.yaml"),
            line_number=10,
            values=[],
        )
        ref = WildcardRef(raw="__空キー__", full_path="空キー")
        ve = _make_value_entry("__空キー__")
        node = _make_tree_node("空キー", NodeType.REF, key_def=kd, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "キー名:" in result
        assert "空キー" in result
        assert "ファイル:" in result
        assert "行番号:" in result


# =========================================================================
# _format_literal_detail のテスト
# =========================================================================


class TestFormatLiteralDetail:
    """_format_literal_detail のテスト。"""

    def test_LITERALノード_リテラル値ヘッダ付き(self):
        """LITERAL ノードの詳細に "リテラル値:" ヘッダとリテラル値が含まれる。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry("(cinematic_shadow:1.1)")
        node = _make_tree_node("(cinematic_shadow:1.1)", NodeType.LITERAL, value_entry=ve)

        result = format_node_detail(node)

        assert "リテラル値:" in result
        assert "(cinematic_shadow:1.1)" in result

    def test_LITERALノード_日本語リテラル値(self):
        """日本語を含むリテラル値が正しく表示される。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry("朝の光, 逆光")
        node = _make_tree_node("朝の光, 逆光", NodeType.LITERAL, value_entry=ve)

        result = format_node_detail(node)

        assert "リテラル値:" in result
        assert "朝の光, 逆光" in result

    def test_LITERALノード_特殊文字を含むリテラル(self):
        """特殊文字（括弧、コロン、アンダースコア）を含むリテラル値が正しく表示される。"""
        from gui.detail_pane import format_node_detail

        text = "masterpiece, (best quality:1.4), 1girl"
        ve = _make_value_entry(text)
        node = _make_tree_node(text, NodeType.LITERAL, value_entry=ve)

        result = format_node_detail(node)

        assert text in result


# =========================================================================
# _format_unresolved_detail のテスト
# =========================================================================


class TestFormatUnresolvedDetail:
    """_format_unresolved_detail のテスト。"""

    def test_UNRESOLVEDノード_ヘッダ含む(self):
        """UNRESOLVED ノードの詳細に [未解決参照] ヘッダが含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(raw="__cards/存在しないキー__", full_path="cards/存在しないキー")
        ve = _make_value_entry("__cards/存在しないキー__")
        node = _make_tree_node("存在しないキー", NodeType.UNRESOLVED, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "[未解決参照]" in result

    def test_UNRESOLVEDノード_参照テキスト含む(self):
        """UNRESOLVED ノードの詳細に参照テキスト（ref.raw）が含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(raw="__cards/存在しないキー__", full_path="cards/存在しないキー")
        ve = _make_value_entry("__cards/存在しないキー__")
        node = _make_tree_node("存在しないキー", NodeType.UNRESOLVED, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "参照:" in result
        assert "__cards/存在しないキー__" in result

    def test_UNRESOLVEDノード_説明メッセージ含む(self):
        """UNRESOLVED ノードの詳細に説明メッセージが含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(raw="__cards/存在しないキー__", full_path="cards/存在しないキー")
        ve = _make_value_entry("__cards/存在しないキー__")
        node = _make_tree_node("存在しないキー", NodeType.UNRESOLVED, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "この参照は解決できませんでした。" in result
        assert "参照先のキーが存在しないか、パスが正しくない可能性があります。" in result


# =========================================================================
# _format_circular_detail のテスト
# =========================================================================


class TestFormatCircularDetail:
    """_format_circular_detail のテスト。"""

    def test_CIRCULARノード_ヘッダ含む(self):
        """CIRCULAR ノードの詳細に [循環参照] ヘッダが含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(raw="__cards/キー名__", full_path="cards/キー名")
        ve = _make_value_entry("__cards/キー名__")
        node = _make_tree_node("キー名 (循環)", NodeType.CIRCULAR, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "[循環参照]" in result

    def test_CIRCULARノード_参照テキスト含む(self):
        """CIRCULAR ノードの詳細に参照テキスト（ref.raw）が含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(raw="__cards/キー名__", full_path="cards/キー名")
        ve = _make_value_entry("__cards/キー名__")
        node = _make_tree_node("キー名 (循環)", NodeType.CIRCULAR, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "参照:" in result
        assert "__cards/キー名__" in result

    def test_CIRCULARノード_説明メッセージ含む(self):
        """CIRCULAR ノードの詳細に説明メッセージが含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(raw="__cards/キー名__", full_path="cards/キー名")
        ve = _make_value_entry("__cards/キー名__")
        node = _make_tree_node("キー名 (循環)", NodeType.CIRCULAR, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "このノードは循環参照により展開が打ち切られました。" in result


# =========================================================================
# _format_dynamic_detail のテスト
# =========================================================================


class TestFormatDynamicDetail:
    """_format_dynamic_detail のテスト。"""

    def test_DYNAMICノード_ヘッダ含む(self):
        """DYNAMIC ノードの詳細に [動的参照] ヘッダが含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(
            raw="__{__cards/キャラキー__}NP__",
            full_path="{__cards/キャラキー__}NP",
            ref_type=RefType.DYNAMIC,
        )
        ve = _make_value_entry(ref.raw)
        node = _make_tree_node(ref.raw, NodeType.DYNAMIC, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "[動的参照]" in result

    def test_DYNAMICノード_参照テキスト含む(self):
        """DYNAMIC ノードの詳細に参照テキスト（ref.raw）が含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(
            raw="__{__cards/キャラキー__}NP__",
            full_path="{__cards/キャラキー__}NP",
            ref_type=RefType.DYNAMIC,
        )
        ve = _make_value_entry(ref.raw)
        node = _make_tree_node(ref.raw, NodeType.DYNAMIC, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "参照:" in result
        assert "__{__cards/キャラキー__}NP__" in result

    def test_DYNAMICノード_説明メッセージ含む(self):
        """DYNAMIC ノードの詳細に説明メッセージが含まれる。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(
            raw="__{__cards/キャラキー__}NP__",
            full_path="{__cards/キャラキー__}NP",
            ref_type=RefType.DYNAMIC,
        )
        ve = _make_value_entry(ref.raw)
        node = _make_tree_node(ref.raw, NodeType.DYNAMIC, value_entry=ve, ref=ref)

        result = format_node_detail(node)

        assert "変数参照を含む動的参照です。" in result
        assert "内部参照は子ノードとして展開されています。" in result


# =========================================================================
# _format_empty_detail のテスト
# =========================================================================


class TestFormatEmptyDetail:
    """_format_empty_detail のテスト。"""

    def test_EMPTYノード_ヘッダ含む(self):
        """EMPTY ノードの詳細に [空定義] ヘッダが含まれる。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry('"{}"')
        node = _make_tree_node("(空)", NodeType.EMPTY, value_entry=ve)

        result = format_node_detail(node)

        assert "[空定義]" in result

    def test_EMPTYノード_値テキスト含む(self):
        """EMPTY ノードの詳細に値テキスト '"{}"' が含まれる。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry('"{}"')
        node = _make_tree_node("(空)", NodeType.EMPTY, value_entry=ve)

        result = format_node_detail(node)

        assert '"{}"' in result

    def test_EMPTYノード_説明メッセージ含む(self):
        """EMPTY ノードの詳細に説明メッセージが含まれる。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry('"{}"')
        node = _make_tree_node("(空)", NodeType.EMPTY, value_entry=ve)

        result = format_node_detail(node)

        assert "このエントリは空定義です。" in result


# =========================================================================
# format_node_detail のフォーマット形式テスト
# =========================================================================


class TestFormatNodeDetailフォーマット:
    """format_node_detail の出力フォーマットが設計書通りかのテスト。"""

    def test_ROOTノード_設計書のフォーマットに従う(self):
        """ROOT ノードの出力が設計書のフォーマットに従う。

        期待フォーマット:
          キー名: メイン
          ファイル: C:/path/to/cards/main.yaml
          行番号: 1

          値:
            - __cards/デフォルト__
            # - __cards/無効化された参照__
            - literal_value
        """
        from gui.detail_pane import format_node_detail

        ve1 = _make_value_entry(
            "__cards/デフォルト__", line_number=2, is_commented=False,
            refs=[WildcardRef(raw="__cards/デフォルト__", full_path="cards/デフォルト")],
        )
        ve2 = _make_value_entry(
            "__cards/無効化された参照__", line_number=3, is_commented=True,
            refs=[WildcardRef(raw="__cards/無効化された参照__", full_path="cards/無効化された参照")],
        )
        ve3 = _make_value_entry("literal_value", line_number=4, literals=["literal_value"])
        kd = _make_key_def(
            "メイン",
            file_path=Path("C:/path/to/cards/main.yaml"),
            line_number=1,
            values=[ve1, ve2, ve3],
        )
        node = _make_tree_node("メイン", NodeType.ROOT, key_def=kd)

        result = format_node_detail(node)

        # 各行の内容を確認（厳密な行位置ではなく、含まれるかどうかで検証）
        assert "キー名: メイン" in result
        assert "行番号: 1" in result
        assert "値:" in result

    def test_UNRESOLVEDノード_設計書のフォーマットに従う(self):
        """UNRESOLVED ノードの出力が設計書のフォーマットに従う。

        期待フォーマット:
          [未解決参照]
          参照: __cards/存在しないキー__

          この参照は解決できませんでした。
          参照先のキーが存在しないか、パスが正しくない可能性があります。
        """
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(raw="__cards/存在しないキー__", full_path="cards/存在しないキー")
        ve = _make_value_entry("__cards/存在しないキー__")
        node = _make_tree_node("存在しないキー", NodeType.UNRESOLVED, value_entry=ve, ref=ref)

        result = format_node_detail(node)
        lines = result.strip().split("\n")

        # 1行目: [未解決参照]
        assert lines[0].strip() == "[未解決参照]"
        # 2行目: 参照: ...
        assert "参照: __cards/存在しないキー__" in lines[1]

    def test_CIRCULARノード_設計書のフォーマットに従う(self):
        """CIRCULAR ノードの出力が設計書のフォーマットに従う。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(raw="__cards/キー名__", full_path="cards/キー名")
        ve = _make_value_entry("__cards/キー名__")
        node = _make_tree_node("キー名 (循環)", NodeType.CIRCULAR, value_entry=ve, ref=ref)

        result = format_node_detail(node)
        lines = result.strip().split("\n")

        assert lines[0].strip() == "[循環参照]"
        assert "参照: __cards/キー名__" in lines[1]

    def test_DYNAMICノード_設計書のフォーマットに従う(self):
        """DYNAMIC ノードの出力が設計書のフォーマットに従う。"""
        from gui.detail_pane import format_node_detail

        ref = WildcardRef(
            raw="__{__cards/キャラキー__}NP__",
            full_path="{__cards/キャラキー__}NP",
            ref_type=RefType.DYNAMIC,
        )
        ve = _make_value_entry(ref.raw)
        node = _make_tree_node(ref.raw, NodeType.DYNAMIC, value_entry=ve, ref=ref)

        result = format_node_detail(node)
        lines = result.strip().split("\n")

        assert lines[0].strip() == "[動的参照]"
        assert "参照: __{__cards/キャラキー__}NP__" in lines[1]

    def test_EMPTYノード_設計書のフォーマットに従う(self):
        """EMPTY ノードの出力が設計書のフォーマットに従う。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry('"{}"')
        node = _make_tree_node("(空)", NodeType.EMPTY, value_entry=ve)

        result = format_node_detail(node)
        lines = result.strip().split("\n")

        assert lines[0].strip() == "[空定義]"

    def test_LITERALノード_設計書のフォーマットに従う(self):
        """LITERAL ノードの出力が設計書のフォーマットに従う。

        期待フォーマット:
          リテラル値: (cinematic_shadow:1.1)
        """
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry("(cinematic_shadow:1.1)")
        node = _make_tree_node("(cinematic_shadow:1.1)", NodeType.LITERAL, value_entry=ve)

        result = format_node_detail(node)

        # 1行目にリテラル値が表示される
        assert "リテラル値: (cinematic_shadow:1.1)" in result


# =========================================================================
# エッジケース
# =========================================================================


class TestFormatNodeDetailエッジケース:
    """format_node_detail のエッジケーステスト。"""

    def test_refがNoneのUNRESOLVEDノード_例外を投げない(self):
        """ref が None の UNRESOLVED ノードでも例外を投げない。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry("__missing__")
        node = _make_tree_node("missing", NodeType.UNRESOLVED, value_entry=ve, ref=None)

        # 例外を投げずに文字列を返す
        result = format_node_detail(node)
        assert isinstance(result, str)

    def test_refがNoneのCIRCULARノード_例外を投げない(self):
        """ref が None の CIRCULAR ノードでも例外を投げない。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry("__キー名__")
        node = _make_tree_node("キー名 (循環)", NodeType.CIRCULAR, value_entry=ve, ref=None)

        result = format_node_detail(node)
        assert isinstance(result, str)

    def test_refがNoneのDYNAMICノード_例外を投げない(self):
        """ref が None の DYNAMIC ノードでも例外を投げない。"""
        from gui.detail_pane import format_node_detail

        ve = _make_value_entry("__{__var__}__")
        node = _make_tree_node("__{__var__}__", NodeType.DYNAMIC, value_entry=ve, ref=None)

        result = format_node_detail(node)
        assert isinstance(result, str)

    def test_value_entryがNoneのLITERALノード_例外を投げない(self):
        """value_entry が None の LITERAL ノードでも例外を投げない。"""
        from gui.detail_pane import format_node_detail

        node = _make_tree_node("literal_value", NodeType.LITERAL, value_entry=None)

        result = format_node_detail(node)
        assert isinstance(result, str)
        assert "literal_value" in result

    def test_ROOTノード_多数の値行_全て表示される(self):
        """値行が多数ある ROOT ノードで全値行が表示される。"""
        from gui.detail_pane import format_node_detail

        values = [
            _make_value_entry(f"value_{i}", line_number=i + 2, literals=[f"value_{i}"])
            for i in range(20)
        ]
        kd = _make_key_def(
            "大量値キー",
            file_path=Path("C:/cards/many.yaml"),
            line_number=1,
            values=values,
        )
        node = _make_tree_node("大量値キー", NodeType.ROOT, key_def=kd)

        result = format_node_detail(node)

        for i in range(20):
            assert f"value_{i}" in result
