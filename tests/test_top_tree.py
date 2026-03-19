"""Unit tests for core/top_tree.py -- トップツリー検出モジュールのテスト。

設計意図ドキュメント (docs/design/s4-top-tree.md) に基づいて、
トップツリー検出の各関数を検証する。

テスト対象:
  - TopTreeInfo データクラス
  - collect_referenced_key_names(registry) -> set[str]
  - find_top_trees(registry) -> list[TopTreeInfo]

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path

from core.models import (
    KeyDefinition,
    KeyRegistry,
    RefType,
    ValueEntry,
    WildcardRef,
)
from core.top_tree import (
    TopTreeInfo,
    collect_referenced_key_names,
    find_top_trees,
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


# =========================================================================
# TopTreeInfo -- データクラスの基本確認
# =========================================================================


class TestTopTreeInfo:
    """TopTreeInfo データクラスのテスト。"""

    def test_TopTreeInfo_フィールドにアクセスできる(self):
        """TopTreeInfo の name, key_def, file_path にアクセスできる。"""
        fp = Path("C:/cards/test.yaml")
        kd = _make_key_def("メイン", fp)
        info = TopTreeInfo(name="メイン", key_def=kd, file_path=fp)

        assert info.name == "メイン"
        assert info.key_def is kd
        assert info.file_path == fp

    def test_TopTreeInfo_file_pathはkey_defのfile_pathと同じ(self):
        """TopTreeInfo.file_path は key_def.file_path と一致する。"""
        fp = Path("C:/cards/SAO/asada.yaml")
        kd = _make_key_def("朝田詩乃", fp)
        info = TopTreeInfo(name="朝田詩乃", key_def=kd, file_path=fp)

        assert info.file_path == info.key_def.file_path


# =========================================================================
# collect_referenced_key_names -- 正常系
# =========================================================================


class TestCollectReferencedKeyNames正常系:
    """collect_referenced_key_names の正常系テスト。"""

    def test_collect_referenced_key_names_通常参照のみ_参照されているキー名が収集される(self):
        """通常参照 (RefType.NORMAL) のみのレジストリで、
        ref.name が参照されているキー名として収集される。"""
        cards_dir = Path("C:/cards")
        ref_b = WildcardRef(raw="__B__", full_path="B")
        ref_c = WildcardRef(raw="__C__", full_path="C")
        ve = ValueEntry(
            raw_text="__B__,__C__",
            line_number=2,
            refs=[ref_b, ref_c],
        )
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve])
        kd_b = _make_key_def("B", cards_dir / "b.yaml")
        kd_c = _make_key_def("C", cards_dir / "c.yaml")
        registry = _make_registry(
            ("A", kd_a),
            ("B", kd_b),
            ("C", kd_c),
        )

        result = collect_referenced_key_names(registry)

        assert isinstance(result, set)
        assert "B" in result
        assert "C" in result
        # A 自体は誰からも参照されていないので含まれない
        assert "A" not in result

    def test_collect_referenced_key_names_動的参照あり_inner_refsのキー名がカウントされる(self):
        """動的参照 (RefType.DYNAMIC) の場合、inner_refs 内の各参照の name が
        カウントされ、動的参照自体の name はカウントされない。"""
        cards_dir = Path("C:/cards")
        inner1 = WildcardRef(raw="__季節__", full_path="季節")
        inner2 = WildcardRef(raw="__キャラ__", full_path="キャラ")
        dynamic_ref = WildcardRef(
            raw="__{__季節__}_{__キャラ__}__",
            full_path="{__季節__}_{__キャラ__}",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner1, inner2),
        )
        ve = ValueEntry(
            raw_text="__{__季節__}_{__キャラ__}__",
            line_number=2,
            refs=[dynamic_ref],
        )
        kd_scene = _make_key_def("シーン", cards_dir / "scene.yaml", values=[ve])
        kd_season = _make_key_def("季節", cards_dir / "season.yaml")
        kd_chara = _make_key_def("キャラ", cards_dir / "chara.yaml")
        registry = _make_registry(
            ("シーン", kd_scene),
            ("季節", kd_season),
            ("キャラ", kd_chara),
        )

        result = collect_referenced_key_names(registry)

        assert "季節" in result
        assert "キャラ" in result
        # 動的参照自体の name はカウントされない
        # (dynamic_ref.name == "}" の末尾部分 or テンプレート全体)
        assert "シーン" not in result

    def test_collect_referenced_key_names_コメント行内の参照もカウントされる(self):
        """コメント行 (is_commented=True) 内の参照も
        「参照されている」としてカウントされる。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(raw="__コメント先__", full_path="コメント先")
        ve = ValueEntry(
            raw_text="__コメント先__",
            line_number=3,
            is_commented=True,
            refs=[ref],
        )
        kd_parent = _make_key_def("親", cards_dir / "parent.yaml", values=[ve])
        kd_target = _make_key_def("コメント先", cards_dir / "target.yaml")
        registry = _make_registry(
            ("親", kd_parent),
            ("コメント先", kd_target),
        )

        result = collect_referenced_key_names(registry)

        assert "コメント先" in result

    def test_collect_referenced_key_names_複数キー定義からの参照が統合される(self):
        """複数のキー定義がそれぞれ異なるキーを参照する場合、
        全参照先が1つの集合に統合される。"""
        cards_dir = Path("C:/cards")
        ref_b = WildcardRef(raw="__B__", full_path="B")
        ref_c = WildcardRef(raw="__C__", full_path="C")
        ve_a = ValueEntry(raw_text="__B__", line_number=2, refs=[ref_b])
        ve_d = ValueEntry(raw_text="__C__", line_number=2, refs=[ref_c])
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve_a])
        kd_d = _make_key_def("D", cards_dir / "d.yaml", values=[ve_d])
        kd_b = _make_key_def("B", cards_dir / "b.yaml")
        kd_c = _make_key_def("C", cards_dir / "c.yaml")
        registry = _make_registry(
            ("A", kd_a),
            ("B", kd_b),
            ("C", kd_c),
            ("D", kd_d),
        )

        result = collect_referenced_key_names(registry)

        assert "B" in result
        assert "C" in result

    def test_collect_referenced_key_names_フルパス参照もnameプロパティで正しく収集される(self):
        """フルパス参照 (cards/SAO/CH_asada/朝田詩乃) でも
        WildcardRef.name プロパティにより正しくキー名が収集される。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(
            raw="__cards/SAO/CH_asada/朝田詩乃__",
            full_path="cards/SAO/CH_asada/朝田詩乃",
        )
        ve = ValueEntry(raw_text="__cards/SAO/CH_asada/朝田詩乃__", line_number=2, refs=[ref])
        kd_scene = _make_key_def("シーン", cards_dir / "scene.yaml", values=[ve])
        kd_asada = _make_key_def("朝田詩乃", cards_dir / "SAO" / "asada.yaml")
        registry = _make_registry(
            ("シーン", kd_scene),
            ("朝田詩乃", kd_asada),
        )

        result = collect_referenced_key_names(registry)

        assert "朝田詩乃" in result

    def test_collect_referenced_key_names_通常参照と動的参照が混在するケース(self):
        """1つの値行に通常参照と動的参照が混在する場合、
        両方のルールが正しく適用される。"""
        cards_dir = Path("C:/cards")
        normal_ref = WildcardRef(raw="__通常__", full_path="通常")
        inner = WildcardRef(raw="__変数__", full_path="変数")
        dynamic_ref = WildcardRef(
            raw="__{__変数__}サフィックス__",
            full_path="{__変数__}サフィックス",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner,),
        )
        ve = ValueEntry(
            raw_text="__通常__,__{__変数__}サフィックス__",
            line_number=2,
            refs=[normal_ref, dynamic_ref],
        )
        kd = _make_key_def("親", cards_dir / "p.yaml", values=[ve])
        registry = _make_registry(("親", kd))

        result = collect_referenced_key_names(registry)

        assert "通常" in result
        assert "変数" in result


# =========================================================================
# collect_referenced_key_names -- 異常系・エッジケース
# =========================================================================


class TestCollectReferencedKeyNamesエッジケース:
    """collect_referenced_key_names の異常系・エッジケーステスト。"""

    def test_collect_referenced_key_names_空のレジストリ_空集合(self):
        """空のレジストリに対して空の集合を返す。"""
        result = collect_referenced_key_names({})

        assert isinstance(result, set)
        assert len(result) == 0

    def test_collect_referenced_key_names_値行がゼロ個のキー定義_空集合(self):
        """値行を持たないキー定義のみのレジストリでは、
        参照が存在しないため空集合を返す。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("A", cards_dir / "a.yaml")  # values=[]
        registry = _make_registry(("A", kd))

        result = collect_referenced_key_names(registry)

        assert len(result) == 0

    def test_collect_referenced_key_names_リテラルのみの値行_何も追加されない(self):
        """参照を含まず、リテラルのみの値行からは何もカウントされない。"""
        cards_dir = Path("C:/cards")
        ve = ValueEntry(
            raw_text="plain text without any reference",
            line_number=2,
            refs=[],
        )
        kd = _make_key_def("leaf", cards_dir / "leaf.yaml", values=[ve])
        registry = _make_registry(("leaf", kd))

        result = collect_referenced_key_names(registry)

        assert len(result) == 0

    def test_collect_referenced_key_names_参照先がレジストリに存在しない場合も集合に含まれる(self):
        """参照先キー名がレジストリに存在しなくても、
        参照されているキー名の集合には含まれる。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(raw="__存在しない__", full_path="存在しない")
        ve = ValueEntry(raw_text="__存在しない__", line_number=2, refs=[ref])
        kd = _make_key_def("source", cards_dir / "s.yaml", values=[ve])
        registry = _make_registry(("source", kd))

        result = collect_referenced_key_names(registry)

        # 参照先がレジストリのキーになくても集合には含まれる
        assert "存在しない" in result

    def test_collect_referenced_key_names_動的参照のinner_refsが空_何もカウントされない(self):
        """動的参照の inner_refs が空の場合、何もカウントされない。"""
        cards_dir = Path("C:/cards")
        dynamic_ref = WildcardRef(
            raw="__dynamic_empty__",
            full_path="dynamic_empty",
            ref_type=RefType.DYNAMIC,
            inner_refs=(),
        )
        ve = ValueEntry(
            raw_text="__dynamic_empty__",
            line_number=2,
            refs=[dynamic_ref],
        )
        kd = _make_key_def("source", cards_dir / "s.yaml", values=[ve])
        registry = _make_registry(("source", kd))

        result = collect_referenced_key_names(registry)

        assert len(result) == 0

    def test_collect_referenced_key_names_同じキー名が複数箇所から参照されても集合なので重複しない(self):
        """同じキー名が複数のキー定義から参照されても、
        集合なので重複なく1つだけ含まれる。"""
        cards_dir = Path("C:/cards")
        ref1 = WildcardRef(raw="__shared__", full_path="shared")
        ref2 = WildcardRef(raw="__shared__", full_path="shared")
        ve1 = ValueEntry(raw_text="__shared__", line_number=2, refs=[ref1])
        ve2 = ValueEntry(raw_text="__shared__", line_number=2, refs=[ref2])
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve1])
        kd_b = _make_key_def("B", cards_dir / "b.yaml", values=[ve2])
        kd_shared = _make_key_def("shared", cards_dir / "shared.yaml")
        registry = _make_registry(
            ("A", kd_a),
            ("B", kd_b),
            ("shared", kd_shared),
        )

        result = collect_referenced_key_names(registry)

        assert "shared" in result


# =========================================================================
# find_top_trees -- 正常系
# =========================================================================


class TestFindTopTrees正常系:
    """find_top_trees の正常系テスト。"""

    def test_find_top_trees_基本的なトップツリー検出(self):
        """A → B の場合、A がトップツリーとして検出される。
        B は A から参照されているのでトップツリーにならない。"""
        cards_dir = Path("C:/cards")
        ref_b = WildcardRef(raw="__B__", full_path="B")
        ve = ValueEntry(raw_text="__B__", line_number=2, refs=[ref_b])
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve])
        kd_b = _make_key_def("B", cards_dir / "b.yaml")
        registry = _make_registry(
            ("A", kd_a),
            ("B", kd_b),
        )

        result = find_top_trees(registry)

        assert len(result) == 1
        assert result[0].name == "A"
        assert result[0].key_def is kd_a
        assert result[0].file_path == kd_a.file_path

    def test_find_top_trees_複数のトップツリーが存在する場合(self):
        """参照されていないキーが複数ある場合、
        全てがトップツリーとして返される。"""
        cards_dir = Path("C:/cards")
        ref_c = WildcardRef(raw="__C__", full_path="C")
        ve_a = ValueEntry(raw_text="__C__", line_number=2, refs=[ref_c])
        ve_b = ValueEntry(raw_text="__C__", line_number=2, refs=[ref_c])
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve_a])
        kd_b = _make_key_def("B", cards_dir / "b.yaml", values=[ve_b])
        kd_c = _make_key_def("C", cards_dir / "c.yaml")
        registry = _make_registry(
            ("A", kd_a),
            ("B", kd_b),
            ("C", kd_c),
        )

        result = find_top_trees(registry)

        names = [info.name for info in result]
        assert len(names) == 2
        assert "A" in names
        assert "B" in names

    def test_find_top_trees_名前順にソートされている(self):
        """結果リストが name のソート順になっている。"""
        cards_dir = Path("C:/cards")
        # A, B, C のいずれも参照されていない → 全てトップツリー
        kd_c = _make_key_def("C", cards_dir / "c.yaml")
        kd_a = _make_key_def("A", cards_dir / "a.yaml")
        kd_b = _make_key_def("B", cards_dir / "b.yaml")
        registry = _make_registry(
            ("C", kd_c),
            ("A", kd_a),
            ("B", kd_b),
        )

        result = find_top_trees(registry)

        names = [info.name for info in result]
        assert names == sorted(names)
        assert names == ["A", "B", "C"]

    def test_find_top_trees_戻り値がTopTreeInfoのリスト(self):
        """戻り値が list[TopTreeInfo] であることを確認する。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("root", cards_dir / "root.yaml")
        registry = _make_registry(("root", kd))

        result = find_top_trees(registry)

        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, TopTreeInfo)

    def test_find_top_trees_TopTreeInfoのkey_defとfile_pathが正しく設定される(self):
        """TopTreeInfo の key_def と file_path が正しく設定される。"""
        cards_dir = Path("C:/cards")
        fp = cards_dir / "SAO" / "scene.yaml"
        kd = _make_key_def("シーン", fp)
        registry = _make_registry(("シーン", kd))

        result = find_top_trees(registry)

        assert len(result) == 1
        assert result[0].key_def is kd
        assert result[0].file_path == fp

    def test_find_top_trees_チェーン参照でルートのみがトップツリー(self):
        """A → B → C のチェーン参照では、A のみがトップツリー。"""
        cards_dir = Path("C:/cards")
        ref_b = WildcardRef(raw="__B__", full_path="B")
        ref_c = WildcardRef(raw="__C__", full_path="C")
        ve_a = ValueEntry(raw_text="__B__", line_number=2, refs=[ref_b])
        ve_b = ValueEntry(raw_text="__C__", line_number=2, refs=[ref_c])
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve_a])
        kd_b = _make_key_def("B", cards_dir / "b.yaml", values=[ve_b])
        kd_c = _make_key_def("C", cards_dir / "c.yaml")
        registry = _make_registry(
            ("A", kd_a),
            ("B", kd_b),
            ("C", kd_c),
        )

        result = find_top_trees(registry)

        assert len(result) == 1
        assert result[0].name == "A"


# =========================================================================
# find_top_trees -- 異常系・エッジケース
# =========================================================================


class TestFindTopTreesエッジケース:
    """find_top_trees の異常系・エッジケーステスト。"""

    def test_find_top_trees_空のレジストリ_空リスト(self):
        """空のレジストリに対して空リストを返す。"""
        result = find_top_trees({})

        assert isinstance(result, list)
        assert len(result) == 0

    def test_find_top_trees_全キーが何かから参照されている_空リスト(self):
        """全てのキーが他のキーから参照されている場合、
        トップツリーは存在しない（空リスト）。"""
        cards_dir = Path("C:/cards")
        ref_b = WildcardRef(raw="__B__", full_path="B")
        ref_a = WildcardRef(raw="__A__", full_path="A")
        ref_c = WildcardRef(raw="__C__", full_path="C")
        ve_a = ValueEntry(raw_text="__B__", line_number=2, refs=[ref_b])
        ve_b = ValueEntry(raw_text="__C__", line_number=2, refs=[ref_c])
        ve_c = ValueEntry(raw_text="__A__", line_number=2, refs=[ref_a])
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve_a])
        kd_b = _make_key_def("B", cards_dir / "b.yaml", values=[ve_b])
        kd_c = _make_key_def("C", cards_dir / "c.yaml", values=[ve_c])
        registry = _make_registry(
            ("A", kd_a),
            ("B", kd_b),
            ("C", kd_c),
        )

        result = find_top_trees(registry)

        assert len(result) == 0

    def test_find_top_trees_全キーがどこからも参照されていない_全キーがトップツリー(self):
        """参照が一切ない場合、全キーがトップツリーとして返される。"""
        cards_dir = Path("C:/cards")
        kd_a = _make_key_def("A", cards_dir / "a.yaml")
        kd_b = _make_key_def("B", cards_dir / "b.yaml")
        kd_c = _make_key_def("C", cards_dir / "c.yaml")
        registry = _make_registry(
            ("A", kd_a),
            ("B", kd_b),
            ("C", kd_c),
        )

        result = find_top_trees(registry)

        names = [info.name for info in result]
        assert len(names) == 3
        assert "A" in names
        assert "B" in names
        assert "C" in names

    def test_find_top_trees_自己参照のみのキー_トップツリーにならない(self):
        """キー A が自分自身のみを参照する場合、
        A は参照されているのでトップツリーにならない。"""
        cards_dir = Path("C:/cards")
        ref_a = WildcardRef(raw="__A__", full_path="A")
        ve = ValueEntry(raw_text="__A__", line_number=2, refs=[ref_a])
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve])
        registry = _make_registry(("A", kd_a))

        result = find_top_trees(registry)

        assert len(result) == 0

    def test_find_top_trees_相互参照_両方ともトップツリーにならない(self):
        """A → B, B → A の相互参照では、
        両方とも参照されているためトップツリーなし。"""
        cards_dir = Path("C:/cards")
        ref_b = WildcardRef(raw="__B__", full_path="B")
        ref_a = WildcardRef(raw="__A__", full_path="A")
        ve_a = ValueEntry(raw_text="__B__", line_number=2, refs=[ref_b])
        ve_b = ValueEntry(raw_text="__A__", line_number=2, refs=[ref_a])
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve_a])
        kd_b = _make_key_def("B", cards_dir / "b.yaml", values=[ve_b])
        registry = _make_registry(
            ("A", kd_a),
            ("B", kd_b),
        )

        result = find_top_trees(registry)

        assert len(result) == 0

    def test_find_top_trees_同名キーが複数ファイルに存在_後勝ちのKeyDefinitionが使われる(self):
        """同名キーが複数ファイルに存在し、いずれも参照されていない場合、
        1つの TopTreeInfo として返される。key_def は後勝ち（リストの最後）。"""
        cards_dir = Path("C:/cards")
        kd_first = _make_key_def("dup", cards_dir / "a.yaml", line_number=1)
        kd_last = _make_key_def("dup", cards_dir / "b.yaml", line_number=5)
        # 同名キーなのでリストに両方入る
        registry: KeyRegistry = {"dup": [kd_first, kd_last]}

        result = find_top_trees(registry)

        assert len(result) == 1
        assert result[0].name == "dup"
        assert result[0].key_def is kd_last  # 後勝ち
        assert result[0].file_path == kd_last.file_path

    def test_find_top_trees_動的参照のinner_refsがトップツリー判定に影響する(self):
        """動的参照の inner_refs で参照されたキーは、
        トップツリー判定で「参照されている」と扱われる。"""
        cards_dir = Path("C:/cards")
        inner = WildcardRef(raw="__target__", full_path="target")
        dynamic_ref = WildcardRef(
            raw="__{__target__}suffix__",
            full_path="{__target__}suffix",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner,),
        )
        ve = ValueEntry(
            raw_text="__{__target__}suffix__",
            line_number=2,
            refs=[dynamic_ref],
        )
        kd_source = _make_key_def("source", cards_dir / "s.yaml", values=[ve])
        kd_target = _make_key_def("target", cards_dir / "t.yaml")
        registry = _make_registry(
            ("source", kd_source),
            ("target", kd_target),
        )

        result = find_top_trees(registry)

        # source はトップツリー（参照されていない）
        # target は inner_refs で参照されているのでトップツリーにならない
        assert len(result) == 1
        assert result[0].name == "source"

    def test_find_top_trees_キー定義が1つだけ_参照なし_そのキーがトップツリー(self):
        """レジストリにキー定義が1つだけあり、参照がない場合、
        そのキーがトップツリーとして返される。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("only_key", cards_dir / "only.yaml")
        registry = _make_registry(("only_key", kd))

        result = find_top_trees(registry)

        assert len(result) == 1
        assert result[0].name == "only_key"

    def test_find_top_trees_キー定義が1つだけ_自己参照あり_空リスト(self):
        """レジストリにキー定義が1つだけで自己参照する場合、
        トップツリーは存在しない。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(raw="__solo__", full_path="solo")
        ve = ValueEntry(raw_text="__solo__", line_number=2, refs=[ref])
        kd = _make_key_def("solo", cards_dir / "solo.yaml", values=[ve])
        registry = _make_registry(("solo", kd))

        result = find_top_trees(registry)

        assert len(result) == 0

    def test_find_top_trees_値行がゼロ個のキー定義_他から参照されていなければトップツリー(self):
        """値行を持たないキー定義は参照を出していないが、
        他のキーから参照されていなければトップツリーになる。"""
        cards_dir = Path("C:/cards")
        kd_empty = _make_key_def("empty_key", cards_dir / "empty.yaml")
        ref_empty = WildcardRef(raw="__other__", full_path="other")
        ve = ValueEntry(raw_text="__other__", line_number=2, refs=[ref_empty])
        kd_parent = _make_key_def("parent", cards_dir / "parent.yaml", values=[ve])
        kd_other = _make_key_def("other", cards_dir / "other.yaml")
        registry = _make_registry(
            ("empty_key", kd_empty),
            ("parent", kd_parent),
            ("other", kd_other),
        )

        result = find_top_trees(registry)

        names = [info.name for info in result]
        assert "empty_key" in names
        assert "parent" in names
        # other は parent から参照されているのでトップツリーにならない
        assert "other" not in names

    def test_find_top_trees_コメント行のみで構成されたキーの参照もトップツリー判定に影響する(self):
        """コメント行のみで構成されたキー定義でも、
        コメント行内の参照がトップツリー判定に影響する。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(raw="__leaf__", full_path="leaf")
        ve = ValueEntry(
            raw_text="__leaf__",
            line_number=2,
            is_commented=True,
            refs=[ref],
        )
        kd_parent = _make_key_def("parent", cards_dir / "p.yaml", values=[ve])
        kd_leaf = _make_key_def("leaf", cards_dir / "l.yaml")
        registry = _make_registry(
            ("parent", kd_parent),
            ("leaf", kd_leaf),
        )

        result = find_top_trees(registry)

        # parent はトップツリー（参照されていない）
        # leaf はコメント行からでも参照されているのでトップツリーにならない
        assert len(result) == 1
        assert result[0].name == "parent"

    def test_find_top_trees_日本語名のキーがソートされる(self):
        """日本語名を含むキーも名前順でソートされる。"""
        cards_dir = Path("C:/cards")
        kd1 = _make_key_def("メインNP", cards_dir / "np.yaml")
        kd2 = _make_key_def("メイン", cards_dir / "main.yaml")
        kd3 = _make_key_def("シーン", cards_dir / "scene.yaml")
        registry = _make_registry(
            ("メインNP", kd1),
            ("メイン", kd2),
            ("シーン", kd3),
        )

        result = find_top_trees(registry)

        names = [info.name for info in result]
        assert names == sorted(names)

    def test_find_top_trees_ダイヤモンド参照でルートのみがトップツリー(self):
        """root → branch_a → shared, root → branch_b → shared の
        ダイヤモンド参照では root のみがトップツリー。"""
        cards_dir = Path("C:/cards")
        ref_a = WildcardRef(raw="__branch_a__", full_path="branch_a")
        ref_b = WildcardRef(raw="__branch_b__", full_path="branch_b")
        ref_shared = WildcardRef(raw="__shared__", full_path="shared")
        ve_root = ValueEntry(
            raw_text="__branch_a__,__branch_b__",
            line_number=2,
            refs=[ref_a, ref_b],
        )
        ve_a = ValueEntry(raw_text="__shared__", line_number=2, refs=[ref_shared])
        ve_b = ValueEntry(raw_text="__shared__", line_number=2, refs=[ref_shared])
        kd_root = _make_key_def("root", cards_dir / "r.yaml", values=[ve_root])
        kd_a = _make_key_def("branch_a", cards_dir / "a.yaml", values=[ve_a])
        kd_b = _make_key_def("branch_b", cards_dir / "b.yaml", values=[ve_b])
        kd_shared = _make_key_def("shared", cards_dir / "s.yaml")
        registry = _make_registry(
            ("root", kd_root),
            ("branch_a", kd_a),
            ("branch_b", kd_b),
            ("shared", kd_shared),
        )

        result = find_top_trees(registry)

        assert len(result) == 1
        assert result[0].name == "root"

    def test_find_top_trees_未解決参照がトップツリー判定に影響しない(self):
        """参照先キー名がレジストリに存在しない場合（未解決参照）、
        差分計算に影響しない。"""
        cards_dir = Path("C:/cards")
        # A が存在しないキーを参照しているケース
        ref_missing = WildcardRef(raw="__missing__", full_path="missing")
        ve = ValueEntry(raw_text="__missing__", line_number=2, refs=[ref_missing])
        kd_a = _make_key_def("A", cards_dir / "a.yaml", values=[ve])
        kd_b = _make_key_def("B", cards_dir / "b.yaml")
        registry = _make_registry(
            ("A", kd_a),
            ("B", kd_b),
        )

        result = find_top_trees(registry)

        # A, B ともに参照されていないのでトップツリー
        # "missing" はレジストリの keys() に含まれないため差分計算に影響しない
        names = [info.name for info in result]
        assert "A" in names
        assert "B" in names
