"""Unit tests for core/resolver.py -- 名前解決モジュールのテスト。

設計意図ドキュメント (docs/design/s3-resolver.md) に基づいて、
resolver の各関数を検証する。

テスト対象:
  - build_full_path_index(registry, cards_dir) -> FullPathIndex
  - resolve(full_path, full_path_index, registry) -> ResolveResult | None
  - resolve_dynamic_inner_refs(ref, full_path_index, registry)
      -> dict[WildcardRef, ResolveResult | None]
  - find_unresolved_refs(registry, full_path_index) -> list[UnresolvedRef]
  - find_duplicate_keys(registry) -> dict[str, list[KeyDefinition]]

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models import (
    FullPathIndex,
    KeyDefinition,
    KeyRegistry,
    RefType,
    ValueEntry,
    WildcardRef,
)
from core.resolver import (
    ResolveResult,
    UnresolvedRef,
    build_full_path_index,
    find_duplicate_keys,
    find_unresolved_refs,
    resolve,
    resolve_dynamic_inner_refs,
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
# build_full_path_index -- 正常系
# =========================================================================


class TestBuildFullPathIndex正常系:
    """build_full_path_index の正常系テスト。"""

    def test_build_full_path_index_サブディレクトリのキーからフルパスを構築する(self):
        """サブディレクトリ内のキー定義から "dir/subdir/キー名" 形式の
        フルパスインデックスを構築する。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def(
            "朝田詩乃",
            cards_dir / "SAO" / "CH_asada" / "asada.yaml",
        )
        registry: KeyRegistry = {"朝田詩乃": [kd]}

        index = build_full_path_index(registry, cards_dir)

        assert "SAO/CH_asada/朝田詩乃" in index
        assert index["SAO/CH_asada/朝田詩乃"] is kd

    def test_build_full_path_index_直下ファイルのキーはキー名のみがフルパスになる(self):
        """cards_dir 直下のファイルに定義されたキーは、
        full_path がキー名のみ（ディレクトリ部分なし）になる。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("メイン", cards_dir / "main.yaml")
        registry: KeyRegistry = {"メイン": [kd]}

        index = build_full_path_index(registry, cards_dir)

        assert "メイン" in index
        assert index["メイン"] is kd

    def test_build_full_path_index_複数キーを含むレジストリ(self):
        """複数のキー定義からフルパスインデックスを正しく構築する。"""
        cards_dir = Path("C:/cards")
        kd1 = _make_key_def("朝田詩乃", cards_dir / "SAO" / "asada.yaml")
        kd2 = _make_key_def("シロコ", cards_dir / "BA" / "shiroko.yaml")
        kd3 = _make_key_def("メイン", cards_dir / "main.yaml")
        registry: KeyRegistry = {
            "朝田詩乃": [kd1],
            "シロコ": [kd2],
            "メイン": [kd3],
        }

        index = build_full_path_index(registry, cards_dir)

        assert len(index) == 3
        assert "SAO/朝田詩乃" in index
        assert "BA/シロコ" in index
        assert "メイン" in index

    def test_build_full_path_index_戻り値がFullPathIndex型(self):
        """戻り値が FullPathIndex（dict[str, KeyDefinition]）であることを確認する。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("key", cards_dir / "test.yaml")
        registry: KeyRegistry = {"key": [kd]}

        index = build_full_path_index(registry, cards_dir)

        assert isinstance(index, dict)
        for fp, key_def in index.items():
            assert isinstance(fp, str)
            assert isinstance(key_def, KeyDefinition)

    def test_build_full_path_index_同一full_pathの後勝ちルール(self):
        """同じ full_path を持つ複数の KeyDefinition がある場合、
        後のエントリで上書き（後勝ち）する。"""
        cards_dir = Path("C:/cards")
        kd_first = _make_key_def("dup_key", cards_dir / "sub" / "a.yaml", line_number=1)
        kd_last = _make_key_def("dup_key", cards_dir / "sub" / "b.yaml", line_number=1)
        # 同名キーなのでリストに両方入る
        registry: KeyRegistry = {"dup_key": [kd_first, kd_last]}

        index = build_full_path_index(registry, cards_dir)

        # 同一ディレクトリ・同一キー名の場合、ファイルが異なるため
        # full_path は親ディレクトリ + キー名 = "sub/dup_key" で重複する
        # 後勝ちルールにより kd_last が格納される
        assert index["sub/dup_key"] is kd_last


# =========================================================================
# build_full_path_index -- 異常系
# =========================================================================


class TestBuildFullPathIndex異常系:
    """build_full_path_index の異常系テスト。"""

    def test_build_full_path_index_file_pathがcards_dir外の場合スキップする(self):
        """file_path が cards_dir の外にある KeyDefinition はスキップする。
        例外は投げない。"""
        cards_dir = Path("C:/cards")
        kd_outside = _make_key_def(
            "外部キー",
            Path("D:/other/external.yaml"),
        )
        kd_inside = _make_key_def(
            "内部キー",
            cards_dir / "test.yaml",
        )
        registry: KeyRegistry = {
            "外部キー": [kd_outside],
            "内部キー": [kd_inside],
        }

        # 例外が発生しないことを確認
        index = build_full_path_index(registry, cards_dir)

        # 外部キーはスキップされ、内部キーのみがインデックスに含まれる
        assert "内部キー" in index
        assert len(index) == 1


# =========================================================================
# build_full_path_index -- エッジケース
# =========================================================================


class TestBuildFullPathIndexエッジケース:
    """build_full_path_index のエッジケーステスト。"""

    def test_build_full_path_index_空のレジストリ_空のインデックス(self):
        """空のレジストリからは空のフルパスインデックスを返す。"""
        cards_dir = Path("C:/cards")
        registry: KeyRegistry = {}

        index = build_full_path_index(registry, cards_dir)

        assert isinstance(index, dict)
        assert len(index) == 0

    def test_build_full_path_index_Windowsパスのバックスラッシュが正規化される(self):
        """Windows パスの \\ は / に正規化される。"""
        cards_dir = Path("C:\\cards")
        # Windows 環境では Path がバックスラッシュを使うが、
        # フルパスインデックスのキーは / で統一される
        kd = _make_key_def(
            "テストキー",
            Path("C:\\cards\\SAO\\CH_asada\\test.yaml"),
        )
        registry: KeyRegistry = {"テストキー": [kd]}

        index = build_full_path_index(registry, cards_dir)

        # フルパスのキーには "/" が使われる（"\\" ではない）
        matching_keys = [k for k in index if "テストキー" in k]
        assert len(matching_keys) == 1
        assert "\\" not in matching_keys[0]
        assert "/" in matching_keys[0] or matching_keys[0] == "テストキー"

    def test_build_full_path_index_深くネストされたディレクトリ(self):
        """深くネストされたディレクトリのキー定義も正しく処理する。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def(
            "深いキー",
            cards_dir / "a" / "b" / "c" / "d" / "deep.yaml",
        )
        registry: KeyRegistry = {"深いキー": [kd]}

        index = build_full_path_index(registry, cards_dir)

        assert "a/b/c/d/深いキー" in index


# =========================================================================
# resolve -- 正常系
# =========================================================================


class TestResolve正常系:
    """resolve の正常系テスト。"""

    def test_resolve_フルパス参照_cardsプレフィックス付き_インデックスで解決(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """cards/ プレフィックス付きのフルパス参照がフルパスインデックスで解決される。"""
        result = resolve(
            "cards/SAO/CH_asada/朝田詩乃",
            sample_full_path_index,
            sample_registry,
        )

        assert result is not None
        assert isinstance(result, ResolveResult)
        assert result.key_def.name == "朝田詩乃"
        assert result.method == "full_path"
        assert result.is_ambiguous is False

    def test_resolve_フルパス参照_cardsプレフィックスなし_インデックスで解決(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """cards/ プレフィックスなしのフルパス参照もインデックスで解決される。"""
        result = resolve(
            "SAO/CH_asada/朝田詩乃",
            sample_full_path_index,
            sample_registry,
        )

        assert result is not None
        assert result.key_def.name == "朝田詩乃"
        assert result.method == "full_path"

    def test_resolve_短縮形参照_ユニークキー_shortメソッドで解決(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """短縮形参照（キー名のみ）でユニークなキーが短縮形で解決される。"""
        result = resolve(
            "朝田詩乃",
            sample_full_path_index,
            sample_registry,
        )

        assert result is not None
        assert result.key_def.name == "朝田詩乃"
        assert result.method == "short"
        assert result.is_ambiguous is False

    def test_resolve_フルパスで見つからず短縮形でフォールバック(self):
        """フルパスインデックスにないが短縮形で見つかる場合、
        method="short" で解決される。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("テストキー", cards_dir / "sub" / "test.yaml")
        registry: KeyRegistry = {"テストキー": [kd]}
        # フルパスインデックスは空（マッチしない）
        index: FullPathIndex = {}

        result = resolve("テストキー", index, registry)

        assert result is not None
        assert result.key_def.name == "テストキー"
        assert result.method == "short"

    def test_resolve_cardsプレフィックス付き参照で直下ファイルのキー解決(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """cards/ プレフィックス付きで直下ファイルのキーを解決する。
        "cards/メイン" → "メイン" で検索。"""
        result = resolve(
            "cards/メイン",
            sample_full_path_index,
            sample_registry,
        )

        assert result is not None
        assert result.key_def.name == "メイン"

    def test_resolve_短縮形参照_重複キー_後勝ちでis_ambiguousTrue(self):
        """短縮形参照で同名キーが複数ある場合、
        後勝ち（リストの最後）で解決され is_ambiguous=True。"""
        cards_dir = Path("C:/cards")
        kd_a = _make_key_def("common", cards_dir / "a.yaml", line_number=1)
        kd_b = _make_key_def("common", cards_dir / "b.yaml", line_number=1)
        registry: KeyRegistry = {"common": [kd_a, kd_b]}
        index: FullPathIndex = {}

        result = resolve("common", index, registry)

        assert result is not None
        assert result.key_def is kd_b  # 後勝ち
        assert result.method == "short"
        assert result.is_ambiguous is True

    def test_resolve_短縮形参照_スラッシュ付きパスのキー名部分で検索(self):
        """full_path にスラッシュが含まれる場合、最後のスラッシュ以降がキー名として
        短縮形検索に使われる。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("ターゲットキー", cards_dir / "test.yaml")
        registry: KeyRegistry = {"ターゲットキー": [kd]}
        # フルパスインデックスにはマッチしない別パス
        index: FullPathIndex = {}

        result = resolve("wrong/path/ターゲットキー", index, registry)

        assert result is not None
        assert result.key_def.name == "ターゲットキー"
        assert result.method == "short"


# =========================================================================
# resolve -- 異常系
# =========================================================================


class TestResolve異常系:
    """resolve の異常系テスト。"""

    def test_resolve_存在しない参照_Noneを返す(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """フルパスでも短縮形でも見つからない参照には None を返す。"""
        result = resolve(
            "cards/存在しない/参照",
            sample_full_path_index,
            sample_registry,
        )

        assert result is None

    def test_resolve_動的参照のfull_path_Noneを返す(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """動的参照の full_path（{__...}__ を含む）はマッチしないため None を返す。"""
        result = resolve(
            "{__cards/姦キー__}{__cards/鬼キー__}",
            sample_full_path_index,
            sample_registry,
        )

        assert result is None

    def test_resolve_空のインデックスと空のレジストリ_Noneを返す(self):
        """空のインデックスと空のレジストリでは None を返す。"""
        result = resolve("any_key", {}, {})

        assert result is None


# =========================================================================
# resolve -- エッジケース
# =========================================================================


class TestResolveエッジケース:
    """resolve のエッジケーステスト。"""

    def test_resolve_空文字列のfull_path_Noneを返す(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """空文字列の full_path に対して None を返す。"""
        result = resolve("", sample_full_path_index, sample_registry)

        assert result is None

    def test_resolve_cardsプレフィックスのみ_Noneを返す(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """'cards/' のみの full_path に対して None を返す（キー名部分がない）。"""
        result = resolve("cards/", sample_full_path_index, sample_registry)

        assert result is None

    def test_resolve_フルパス解決はis_ambiguousが常にFalse(self):
        """フルパス解決の場合、同名キーが複数あっても is_ambiguous は False。
        フルパスは一意に特定するため。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("unique_by_path", cards_dir / "sub" / "test.yaml")
        index: FullPathIndex = {"sub/unique_by_path": kd}
        # レジストリに同名キーが複数あっても関係ない
        kd_other = _make_key_def("unique_by_path", cards_dir / "other" / "test.yaml")
        registry: KeyRegistry = {"unique_by_path": [kd, kd_other]}

        result = resolve("sub/unique_by_path", index, registry)

        assert result is not None
        assert result.method == "full_path"
        assert result.is_ambiguous is False

    def test_resolve_直下ファイルのキーが短縮形と同じパスになる(self):
        """cards_dir 直下のファイルのキーは、full_path にディレクトリ部分がない。
        短縮形参照と同じパスになるが、フルパスインデックスで先に解決される。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("直下キー", cards_dir / "root.yaml")
        index: FullPathIndex = {"直下キー": kd}
        registry: KeyRegistry = {"直下キー": [kd]}

        result = resolve("直下キー", index, registry)

        assert result is not None
        # フルパスインデックスにヒットするため full_path メソッド
        assert result.method == "full_path"


# =========================================================================
# ResolveResult -- データクラスの基本確認
# =========================================================================


class TestResolveResult:
    """ResolveResult データクラスのテスト。"""

    def test_ResolveResult_フルパス解決結果を生成できる(self):
        """ResolveResult をフルパス解決結果として生成できる。"""
        kd = _make_key_def("key", Path("test.yaml"))
        result = ResolveResult(key_def=kd, method="full_path")

        assert result.key_def is kd
        assert result.method == "full_path"
        assert result.is_ambiguous is False  # デフォルト値

    def test_ResolveResult_短縮形解決結果を生成できる(self):
        """ResolveResult を短縮形解決結果として生成できる。"""
        kd = _make_key_def("key", Path("test.yaml"))
        result = ResolveResult(key_def=kd, method="short", is_ambiguous=True)

        assert result.key_def is kd
        assert result.method == "short"
        assert result.is_ambiguous is True


# =========================================================================
# UnresolvedRef -- データクラスの基本確認
# =========================================================================


class TestUnresolvedRef:
    """UnresolvedRef データクラスのテスト。"""

    def test_UnresolvedRef_文脈情報を含む(self):
        """UnresolvedRef は参照元のキー名・ファイル・行番号を含む。"""
        ref = WildcardRef(raw="__missing__", full_path="missing")
        unresolved = UnresolvedRef(
            ref=ref,
            key_name="parent_key",
            file_path=Path("test.yaml"),
            line_number=5,
        )

        assert unresolved.ref is ref
        assert unresolved.key_name == "parent_key"
        assert unresolved.file_path == Path("test.yaml")
        assert unresolved.line_number == 5


# =========================================================================
# resolve_dynamic_inner_refs -- 正常系
# =========================================================================


class TestResolveDynamicInnerRefs正常系:
    """resolve_dynamic_inner_refs の正常系テスト。"""

    def test_resolve_dynamic_inner_refs_全inner_refsが解決可能(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """動的参照の inner_refs が全て解決可能な場合、
        全ての内部参照に ResolveResult が設定される。"""
        inner1 = WildcardRef(raw="__朝田詩乃__", full_path="朝田詩乃")
        inner2 = WildcardRef(raw="__シロコ__", full_path="シロコ")
        dynamic_ref = WildcardRef(
            raw="__{__朝田詩乃__}_{__シロコ__}__",
            full_path="{__朝田詩乃__}_{__シロコ__}",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner1, inner2),
        )

        results = resolve_dynamic_inner_refs(
            dynamic_ref, sample_full_path_index, sample_registry
        )

        assert len(results) == 2
        assert inner1 in results
        assert inner2 in results
        assert results[inner1] is not None
        assert results[inner1].key_def.name == "朝田詩乃"
        assert results[inner2] is not None
        assert results[inner2].key_def.name == "シロコ"

    def test_resolve_dynamic_inner_refs_一部のinner_refsが未解決(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """動的参照の inner_refs の一部が未解決の場合、
        該当する内部参照は None になる。"""
        inner_ok = WildcardRef(raw="__朝田詩乃__", full_path="朝田詩乃")
        inner_ng = WildcardRef(raw="__存在しない__", full_path="存在しない")
        dynamic_ref = WildcardRef(
            raw="__{__朝田詩乃__}_{__存在しない__}__",
            full_path="{__朝田詩乃__}_{__存在しない__}",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner_ok, inner_ng),
        )

        results = resolve_dynamic_inner_refs(
            dynamic_ref, sample_full_path_index, sample_registry
        )

        assert results[inner_ok] is not None
        assert results[inner_ng] is None

    def test_resolve_dynamic_inner_refs_inner_refsが空_空辞書(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """動的参照だが inner_refs が空の場合、空辞書を返す。"""
        dynamic_ref = WildcardRef(
            raw="__dynamic_empty__",
            full_path="dynamic_empty",
            ref_type=RefType.DYNAMIC,
            inner_refs=(),
        )

        results = resolve_dynamic_inner_refs(
            dynamic_ref, sample_full_path_index, sample_registry
        )

        assert isinstance(results, dict)
        assert len(results) == 0


# =========================================================================
# resolve_dynamic_inner_refs -- 異常系
# =========================================================================


class TestResolveDynamicInnerRefs異常系:
    """resolve_dynamic_inner_refs の異常系テスト。"""

    def test_resolve_dynamic_inner_refs_通常参照が渡された場合_空辞書(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """通常参照（RefType.NORMAL）が渡された場合は空辞書を返す。"""
        normal_ref = WildcardRef(
            raw="__normal_ref__",
            full_path="normal_ref",
            ref_type=RefType.NORMAL,
        )

        results = resolve_dynamic_inner_refs(
            normal_ref, sample_full_path_index, sample_registry
        )

        assert isinstance(results, dict)
        assert len(results) == 0


# =========================================================================
# resolve_dynamic_inner_refs -- エッジケース
# =========================================================================


class TestResolveDynamicInnerRefsエッジケース:
    """resolve_dynamic_inner_refs のエッジケーステスト。"""

    def test_resolve_dynamic_inner_refs_内部参照がcardsプレフィックス付き(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """動的参照の inner_refs に cards/ プレフィックス付き参照がある場合、
        resolve の通常ロジックで解決される。"""
        inner = WildcardRef(
            raw="__cards/SAO/CH_asada/朝田詩乃__",
            full_path="cards/SAO/CH_asada/朝田詩乃",
        )
        dynamic_ref = WildcardRef(
            raw="__{__cards/SAO/CH_asada/朝田詩乃__}suffix__",
            full_path="{__cards/SAO/CH_asada/朝田詩乃__}suffix",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner,),
        )

        results = resolve_dynamic_inner_refs(
            dynamic_ref, sample_full_path_index, sample_registry
        )

        assert len(results) == 1
        assert results[inner] is not None
        assert results[inner].key_def.name == "朝田詩乃"

    def test_resolve_dynamic_inner_refs_戻り値のキーがWildcardRef(
        self,
        sample_full_path_index: FullPathIndex,
        sample_registry: KeyRegistry,
    ):
        """戻り値の辞書のキーが WildcardRef であることを確認する。"""
        inner = WildcardRef(raw="__朝田詩乃__", full_path="朝田詩乃")
        dynamic_ref = WildcardRef(
            raw="__{__朝田詩乃__}__",
            full_path="{__朝田詩乃__}",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner,),
        )

        results = resolve_dynamic_inner_refs(
            dynamic_ref, sample_full_path_index, sample_registry
        )

        for key in results:
            assert isinstance(key, WildcardRef)


# =========================================================================
# find_unresolved_refs -- 正常系
# =========================================================================


class TestFindUnresolvedRefs正常系:
    """find_unresolved_refs の正常系テスト。"""

    def test_find_unresolved_refs_全参照が解決可能_空リスト(self):
        """全参照が解決可能な場合、空リストを返す。"""
        cards_dir = Path("C:/cards")
        ref = WildcardRef(raw="__target__", full_path="target")
        ve = ValueEntry(raw_text="__target__", line_number=2, refs=[ref])
        kd_source = _make_key_def("source", cards_dir / "s.yaml", values=[ve])
        kd_target = _make_key_def("target", cards_dir / "t.yaml")
        registry: KeyRegistry = {
            "source": [kd_source],
            "target": [kd_target],
        }
        index: FullPathIndex = {"target": kd_target}

        result = find_unresolved_refs(registry, index)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_find_unresolved_refs_一部の参照が未解決(self):
        """一部の参照が未解決の場合、未解決参照のみがリストに含まれる。"""
        cards_dir = Path("C:/cards")
        ref_ok = WildcardRef(raw="__existing__", full_path="existing")
        ref_ng = WildcardRef(raw="__missing__", full_path="missing")
        ve = ValueEntry(
            raw_text="__existing__,__missing__",
            line_number=2,
            refs=[ref_ok, ref_ng],
        )
        kd_source = _make_key_def(
            "source", cards_dir / "s.yaml", values=[ve]
        )
        kd_existing = _make_key_def("existing", cards_dir / "e.yaml")
        registry: KeyRegistry = {
            "source": [kd_source],
            "existing": [kd_existing],
        }
        index: FullPathIndex = {"existing": kd_existing}

        result = find_unresolved_refs(registry, index)

        assert len(result) == 1
        assert result[0].ref.full_path == "missing"

    def test_find_unresolved_refs_未解決参照に文脈情報が含まれる(self):
        """UnresolvedRef にキー名・ファイル・行番号の文脈情報が含まれる。"""
        cards_dir = Path("C:/cards")
        ref_ng = WildcardRef(raw="__broken__", full_path="broken")
        ve = ValueEntry(raw_text="__broken__", line_number=10, refs=[ref_ng])
        source_path = cards_dir / "source.yaml"
        kd_source = _make_key_def(
            "親キー", source_path, line_number=8, values=[ve]
        )
        registry: KeyRegistry = {"親キー": [kd_source]}
        index: FullPathIndex = {}

        result = find_unresolved_refs(registry, index)

        assert len(result) == 1
        unresolved = result[0]
        assert unresolved.key_name == "親キー"
        assert unresolved.file_path == source_path
        assert unresolved.line_number == 10
        assert unresolved.ref is ref_ng


# =========================================================================
# find_unresolved_refs -- 動的参照
# =========================================================================


class TestFindUnresolvedRefs動的参照:
    """find_unresolved_refs の動的参照に関するテスト。"""

    def test_find_unresolved_refs_動的参照自体は未解決として記録しない(self):
        """動的参照（RefType.DYNAMIC）自体は「未解決」として記録しない。
        展開前なので判定不能。"""
        cards_dir = Path("C:/cards")
        inner = WildcardRef(raw="__existing__", full_path="existing")
        dynamic = WildcardRef(
            raw="__{__existing__}__",
            full_path="{__existing__}",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner,),
        )
        ve = ValueEntry(raw_text="__{__existing__}__", line_number=2, refs=[dynamic])
        kd = _make_key_def("source", cards_dir / "s.yaml", values=[ve])
        kd_existing = _make_key_def("existing", cards_dir / "e.yaml")
        registry: KeyRegistry = {
            "source": [kd],
            "existing": [kd_existing],
        }
        index: FullPathIndex = {"existing": kd_existing}

        result = find_unresolved_refs(registry, index)

        # 動的参照自体は未解決にならない。inner_refs の "existing" は解決可能
        assert len(result) == 0

    def test_find_unresolved_refs_動的参照のinner_refsが未解決_記録される(self):
        """動的参照の inner_refs 内の参照が解決できない場合、
        「未解決」として記録される。"""
        cards_dir = Path("C:/cards")
        inner_missing = WildcardRef(raw="__not_found__", full_path="not_found")
        dynamic = WildcardRef(
            raw="__{__not_found__}__",
            full_path="{__not_found__}",
            ref_type=RefType.DYNAMIC,
            inner_refs=(inner_missing,),
        )
        ve = ValueEntry(
            raw_text="__{__not_found__}__", line_number=3, refs=[dynamic]
        )
        kd = _make_key_def("source", cards_dir / "s.yaml", values=[ve])
        registry: KeyRegistry = {"source": [kd]}
        index: FullPathIndex = {}

        result = find_unresolved_refs(registry, index)

        assert len(result) == 1
        assert result[0].ref.full_path == "not_found"


# =========================================================================
# find_unresolved_refs -- エッジケース
# =========================================================================


class TestFindUnresolvedRefsエッジケース:
    """find_unresolved_refs のエッジケーステスト。"""

    def test_find_unresolved_refs_空のレジストリ_空リスト(self):
        """空のレジストリでは空リストを返す。"""
        result = find_unresolved_refs({}, {})

        assert isinstance(result, list)
        assert len(result) == 0

    def test_find_unresolved_refs_参照のないキー定義_空リスト(self):
        """参照を含まないキー定義のみの場合、空リストを返す。"""
        cards_dir = Path("C:/cards")
        ve = ValueEntry(raw_text="plain text", line_number=2, refs=[])
        kd = _make_key_def("leaf", cards_dir / "leaf.yaml", values=[ve])
        registry: KeyRegistry = {"leaf": [kd]}
        index: FullPathIndex = {}

        result = find_unresolved_refs(registry, index)

        assert len(result) == 0

    def test_find_unresolved_refs_複数キー定義にまたがる未解決参照(self):
        """複数のキー定義にまたがる未解決参照をすべて収集する。"""
        cards_dir = Path("C:/cards")
        ref_a = WildcardRef(raw="__missing_a__", full_path="missing_a")
        ref_b = WildcardRef(raw="__missing_b__", full_path="missing_b")
        ve_a = ValueEntry(raw_text="__missing_a__", line_number=2, refs=[ref_a])
        ve_b = ValueEntry(raw_text="__missing_b__", line_number=2, refs=[ref_b])
        kd_a = _make_key_def("key_a", cards_dir / "a.yaml", values=[ve_a])
        kd_b = _make_key_def("key_b", cards_dir / "b.yaml", values=[ve_b])
        registry: KeyRegistry = {
            "key_a": [kd_a],
            "key_b": [kd_b],
        }
        index: FullPathIndex = {}

        result = find_unresolved_refs(registry, index)

        assert len(result) == 2
        full_paths = {r.ref.full_path for r in result}
        assert "missing_a" in full_paths
        assert "missing_b" in full_paths

    def test_find_unresolved_refs_同一キー定義内に複数の未解決参照(self):
        """同一キー定義内の複数の値行にまたがる未解決参照をすべて収集する。"""
        cards_dir = Path("C:/cards")
        ref1 = WildcardRef(raw="__miss1__", full_path="miss1")
        ref2 = WildcardRef(raw="__miss2__", full_path="miss2")
        ve1 = ValueEntry(raw_text="__miss1__", line_number=2, refs=[ref1])
        ve2 = ValueEntry(raw_text="__miss2__", line_number=3, refs=[ref2])
        kd = _make_key_def(
            "parent", cards_dir / "p.yaml", values=[ve1, ve2]
        )
        registry: KeyRegistry = {"parent": [kd]}
        index: FullPathIndex = {}

        result = find_unresolved_refs(registry, index)

        assert len(result) == 2
        line_numbers = {r.line_number for r in result}
        assert 2 in line_numbers
        assert 3 in line_numbers


# =========================================================================
# find_duplicate_keys -- 正常系
# =========================================================================


class TestFindDuplicateKeys正常系:
    """find_duplicate_keys の正常系テスト。"""

    def test_find_duplicate_keys_重複あり(
        self, duplicate_key_registry: KeyRegistry
    ):
        """重複キーがある場合、該当するキー名と KeyDefinition リストを返す。"""
        result = find_duplicate_keys(duplicate_key_registry)

        assert isinstance(result, dict)
        assert "common_style" in result
        assert len(result["common_style"]) == 2

    def test_find_duplicate_keys_ユニークキーは含まない(
        self, duplicate_key_registry: KeyRegistry
    ):
        """定義が1つしかないキーは重複キーに含まない。"""
        result = find_duplicate_keys(duplicate_key_registry)

        assert "unique_key" not in result

    def test_find_duplicate_keys_重複なし(self):
        """重複がない場合、空辞書を返す。"""
        cards_dir = Path("C:/cards")
        registry: KeyRegistry = {
            "key_a": [_make_key_def("key_a", cards_dir / "a.yaml")],
            "key_b": [_make_key_def("key_b", cards_dir / "b.yaml")],
        }

        result = find_duplicate_keys(registry)

        assert isinstance(result, dict)
        assert len(result) == 0


# =========================================================================
# find_duplicate_keys -- エッジケース
# =========================================================================


class TestFindDuplicateKeysエッジケース:
    """find_duplicate_keys のエッジケーステスト。"""

    def test_find_duplicate_keys_空のレジストリ_空辞書(self):
        """空のレジストリでは空辞書を返す。"""
        result = find_duplicate_keys({})

        assert isinstance(result, dict)
        assert len(result) == 0

    def test_find_duplicate_keys_3件以上の重複も検出(self):
        """同名キーが3件以上ある場合もすべてリストに含まれる。"""
        cards_dir = Path("C:/cards")
        kd_a = _make_key_def("triple", cards_dir / "a.yaml")
        kd_b = _make_key_def("triple", cards_dir / "b.yaml")
        kd_c = _make_key_def("triple", cards_dir / "c.yaml")
        registry: KeyRegistry = {"triple": [kd_a, kd_b, kd_c]}

        result = find_duplicate_keys(registry)

        assert "triple" in result
        assert len(result["triple"]) == 3

    def test_find_duplicate_keys_複数のキーが重複(self):
        """複数の異なるキーがそれぞれ重複している場合、すべて検出する。"""
        cards_dir = Path("C:/cards")
        registry: KeyRegistry = {
            "dup_a": [
                _make_key_def("dup_a", cards_dir / "a1.yaml"),
                _make_key_def("dup_a", cards_dir / "a2.yaml"),
            ],
            "dup_b": [
                _make_key_def("dup_b", cards_dir / "b1.yaml"),
                _make_key_def("dup_b", cards_dir / "b2.yaml"),
            ],
            "unique": [
                _make_key_def("unique", cards_dir / "u.yaml"),
            ],
        }

        result = find_duplicate_keys(registry)

        assert len(result) == 2
        assert "dup_a" in result
        assert "dup_b" in result
        assert "unique" not in result

    def test_find_duplicate_keys_戻り値のリストにKeyDefinitionが含まれる(self):
        """戻り値の各リストに KeyDefinition が含まれることを確認する。"""
        cards_dir = Path("C:/cards")
        registry: KeyRegistry = {
            "dup": [
                _make_key_def("dup", cards_dir / "x.yaml"),
                _make_key_def("dup", cards_dir / "y.yaml"),
            ],
        }

        result = find_duplicate_keys(registry)

        for key_name, defs in result.items():
            assert isinstance(key_name, str)
            for d in defs:
                assert isinstance(d, KeyDefinition)
