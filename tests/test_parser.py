"""Unit tests for core/wildcard_parser.py.

Tests are organized by pipeline stage (Stage 1-5) and cover normal,
error, and edge cases as specified in the design documents.

Test naming convention: test_<subject>_<condition>_<expected_result>
Using Japanese names where they reflect actual use cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.wildcard_parser import (
    KeyDefinition,
    TreeNode,
    WildcardRef,
    WildcardResolver,
    _scan_closing_underscores,
    build_key_registry,
    build_tree,
    extract_keys_from_file,
    extract_refs_from_line,
    scan_yaml_files,
)


# =========================================================================
# Stage 1: scan_yaml_files()
# =========================================================================


class TestScanYamlFiles:
    """Tests for Stage 1: YAML file scanning."""

    # -- Normal cases --

    def test_YAMLファイルスキャン_yaml拡張子を再帰取得(
        self, multi_file_cards_dir: Path
    ):
        """Recursively finds all .yaml files under the directory."""
        result = scan_yaml_files(multi_file_cards_dir)
        assert len(result) > 0
        assert all(isinstance(p, Path) for p in result)
        assert all(p.suffix in (".yaml", ".yml") for p in result)

    def test_YAMLファイルスキャン_yml拡張子も取得(
        self, tmp_path: Path, yaml_factory
    ):
        """Finds .yml extension files as well."""
        cards = tmp_path / "cards"
        cards.mkdir()
        yaml_factory("cards/test.yml", "key:\n  - value\n")
        result = scan_yaml_files(cards)
        assert len(result) == 1
        assert result[0].suffix == ".yml"

    def test_YAMLファイルスキャン_結果がソートされている(
        self, multi_file_cards_dir: Path
    ):
        """Results are sorted by path for stable scan order."""
        result = scan_yaml_files(multi_file_cards_dir)
        assert result == sorted(result)

    def test_YAMLファイルスキャン_サブディレクトリの再帰走査(
        self, multi_file_cards_dir: Path
    ):
        """Scans subdirectories recursively."""
        result = scan_yaml_files(multi_file_cards_dir)
        # Should find files in SAO/CH_asada/, SAO/options/, BA/CH_shiroko/
        deep_files = [p for p in result if len(p.relative_to(multi_file_cards_dir).parts) > 1]
        assert len(deep_files) >= 3

    # -- Error cases --

    def test_YAMLファイルスキャン_存在しないディレクトリ_FileNotFoundError(
        self, tmp_path: Path
    ):
        """Raises FileNotFoundError for non-existent directory."""
        non_existent = tmp_path / "non_existent"
        with pytest.raises(FileNotFoundError):
            scan_yaml_files(non_existent)

    def test_YAMLファイルスキャン_ファイルパス_NotADirectoryError(
        self, tmp_path: Path, yaml_factory
    ):
        """Raises NotADirectoryError when given a file path."""
        file_path = yaml_factory("not_a_dir.yaml", "key:\n  - value\n")
        with pytest.raises(NotADirectoryError):
            scan_yaml_files(file_path)

    # -- Edge cases --

    def test_YAMLファイルスキャン_空ディレクトリ_空リスト(self, tmp_path: Path):
        """Returns empty list for an empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = scan_yaml_files(empty_dir)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_YAMLファイルスキャン_非YAMLファイルは除外(
        self, tmp_path: Path
    ):
        """Non-YAML files are excluded from results."""
        cards = tmp_path / "cards"
        cards.mkdir()
        (cards / "readme.txt").write_text("not yaml", encoding="utf-8")
        (cards / "data.json").write_text("{}", encoding="utf-8")
        (cards / "actual.yaml").write_text("key:\n  - val\n", encoding="utf-8")
        result = scan_yaml_files(cards)
        assert len(result) == 1
        assert result[0].name == "actual.yaml"


# =========================================================================
# Stage 2: extract_keys_from_file()
# =========================================================================


class TestExtractKeysFromFile:
    """Tests for Stage 2: Key extraction from YAML files."""

    # -- Normal cases --

    def test_キー抽出_トップレベルキーと値行を抽出(
        self, yaml_factory, tmp_path: Path
    ):
        """Extracts top-level keys and their value lines."""
        path = yaml_factory(
            "test.yaml",
            "greeting:\n"
            "  - hello\n"
            "  - world\n",
        )
        result = extract_keys_from_file(path)
        assert len(result) == 1
        assert result[0].name == "greeting"
        assert result[0].file_path == path
        assert "hello" in result[0].raw_values
        assert "world" in result[0].raw_values

    def test_キー抽出_コメント行がスキップされる(
        self, yaml_factory, tmp_path: Path
    ):
        """Comment lines (starting with #) are excluded from raw_values."""
        path = yaml_factory(
            "test.yaml",
            "scenes:\n"
            "  - __active_scene__\n"
            "  # - __commented_scene__\n"
            "  - __another_scene__\n",
        )
        result = extract_keys_from_file(path)
        assert len(result) == 1
        values = result[0].raw_values
        # The commented line should be excluded
        for v in values:
            assert "__commented_scene__" not in v
        # Active and another scenes should be present
        assert any("__active_scene__" in v for v in values)
        assert any("__another_scene__" in v for v in values)

    def test_キー抽出_リストプレフィックスが除去される(
        self, yaml_factory, tmp_path: Path
    ):
        """The '  - ' list item prefix is stripped from value lines."""
        path = yaml_factory(
            "test.yaml",
            "key:\n"
            "  - some value\n",
        )
        result = extract_keys_from_file(path)
        assert len(result) == 1
        # The value should not start with "- "
        assert result[0].raw_values[0] == "some value"

    def test_キー抽出_日本語キー名(self, yaml_factory, tmp_path: Path):
        """Japanese key names are correctly extracted."""
        path = yaml_factory(
            "japanese.yaml",
            "朝田詩乃体格:\n"
            "  - slender body\n"
            "  - __options/エイジスライダー__\n",
        )
        result = extract_keys_from_file(path)
        assert len(result) == 1
        assert result[0].name == "朝田詩乃体格"

    # -- Error cases --

    def test_キー抽出_存在しないファイル_空リスト(self, tmp_path: Path):
        """Returns empty list for a non-existent file (no exception)."""
        non_existent = tmp_path / "does_not_exist.yaml"
        result = extract_keys_from_file(non_existent)
        assert isinstance(result, list)
        assert len(result) == 0

    # -- Edge cases --

    def test_キー抽出_空ファイル_空リスト(self, yaml_factory, tmp_path: Path):
        """Returns empty list for an empty file."""
        path = yaml_factory("empty.yaml", "")
        result = extract_keys_from_file(path)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_キー抽出_複数キーが1ファイルに存在(
        self, yaml_factory, tmp_path: Path
    ):
        """Multiple keys in a single file are all extracted."""
        path = yaml_factory(
            "multi.yaml",
            "first_key:\n"
            "  - value1\n"
            "\n"
            "second_key:\n"
            "  - value2\n"
            "\n"
            "third_key:\n"
            "  - value3\n",
        )
        result = extract_keys_from_file(path)
        assert len(result) == 3
        names = [k.name for k in result]
        assert "first_key" in names
        assert "second_key" in names
        assert "third_key" in names

    def test_キー抽出_コメント行のみのキー(
        self, yaml_factory, tmp_path: Path
    ):
        """A key with only comment value lines has empty raw_values."""
        path = yaml_factory(
            "comments_only.yaml",
            "disabled_key:\n"
            "  # - __disabled_ref1__\n"
            "  # - __disabled_ref2__\n",
        )
        result = extract_keys_from_file(path)
        assert len(result) == 1
        assert result[0].name == "disabled_key"
        assert len(result[0].raw_values) == 0

    def test_キー抽出_トップレベルコメント行はキーとして扱わない(
        self, yaml_factory, tmp_path: Path
    ):
        """Lines starting with # at column 0 are not treated as keys."""
        path = yaml_factory(
            "top_comment.yaml",
            "# This is a comment\n"
            "actual_key:\n"
            "  - value\n",
        )
        result = extract_keys_from_file(path)
        assert len(result) == 1
        assert result[0].name == "actual_key"

    def test_キー抽出_値行にコロンを含む(
        self, yaml_factory, tmp_path: Path
    ):
        """Value lines containing colons are correctly parsed (not treated as keys)."""
        path = yaml_factory(
            "colon_in_value.yaml",
            "prompt:\n"
            "  - masterpiece, best quality, 1girl: sitting\n",
        )
        result = extract_keys_from_file(path)
        assert len(result) == 1
        assert result[0].name == "prompt"
        assert len(result[0].raw_values) == 1


# =========================================================================
# Stage 3: extract_refs_from_line()
# =========================================================================


class TestExtractRefsFromLine:
    """Tests for Stage 3: Reference extraction from a single line."""

    # -- Normal cases --

    def test_参照抽出_単一参照(self):
        """Extracts a single __name__ reference."""
        result = extract_refs_from_line("__greeting__")
        assert len(result) == 1
        assert result[0].name == "greeting"
        assert result[0].raw == "__greeting__"

    def test_参照抽出_1行に複数の参照(self):
        """Extracts multiple __name__ references from one line."""
        result = extract_refs_from_line("__first__ and __second__")
        assert len(result) == 2
        names = [r.name for r in result]
        assert "first" in names
        assert "second" in names

    def test_参照抽出_フルパス参照(self):
        """Extracts full-path reference like __cards/dir/key__."""
        result = extract_refs_from_line(
            "__cards/SAO/CH_asada/朝田詩乃体格__"
        )
        assert len(result) == 1
        assert result[0].name == "cards/SAO/CH_asada/朝田詩乃体格"

    def test_参照抽出_ネスト参照_内側と外側の両方が抽出される(self):
        """Nested references extract both inner and outer refs.

        For ``__{__inner__}outer__``, both the outer reference and
        the inner ``__inner__`` reference should be extracted.
        """
        result = extract_refs_from_line("__{__season__}_{__character__}__")
        names = [r.name for r in result]
        # Inner references should be extracted
        assert "season" in names
        assert "character" in names
        # The outer reference should also be present
        assert len(result) >= 3  # outer + 2 inner

    def test_参照抽出_テキスト混在行(self):
        """Extracts refs from a line containing non-reference text."""
        result = extract_refs_from_line("hello __world__ and __universe__")
        assert len(result) == 2
        names = [r.name for r in result]
        assert "world" in names
        assert "universe" in names

    def test_参照抽出_日本語参照名(self):
        """Extracts references with Japanese names."""
        result = extract_refs_from_line("__朝田詩乃体格__")
        assert len(result) == 1
        assert result[0].name == "朝田詩乃体格"

    # -- Edge cases --

    def test_参照抽出_参照なしの行_空リスト(self):
        """Returns empty list for a line without any references."""
        result = extract_refs_from_line("just plain text")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_参照抽出_不完全な参照_閉じなし_空リスト(self):
        """Returns empty list for incomplete reference (no closing __)."""
        result = extract_refs_from_line("__incomplete")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_参照抽出_空文字列_空リスト(self):
        """Returns empty list for an empty string."""
        result = extract_refs_from_line("")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_参照抽出_アンダースコア1つ_空リスト(self):
        """A single underscore is not a reference delimiter."""
        result = extract_refs_from_line("_not_a_ref_")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_参照抽出_空の参照名(self):
        """Empty reference ``____`` -- four underscores with no body.

        Behavior depends on implementation, but it should not crash.
        """
        result = extract_refs_from_line("____")
        # Should either return empty list or a ref with empty name
        assert isinstance(result, list)


# =========================================================================
# Stage 3 internal: _scan_closing_underscores()
# =========================================================================


class TestScanClosingUnderscores:
    """Tests for the internal helper _scan_closing_underscores()."""

    # -- Normal cases --

    def test_閉じアンダースコア検出_単純なケース(self):
        """Finds closing __ in a simple reference body."""
        # For "__hello__", body_start would be at index 2 (after opening __)
        text = "__hello__"
        pos = _scan_closing_underscores(text, 2)
        # Should return the index of the first _ of closing __
        assert pos == 7

    def test_閉じアンダースコア検出_ブレース内のアンダースコアをスキップ(self):
        """Skips __ inside braces {} when tracking brace depth."""
        # __{__inner__}outer__
        text = "__{__inner__}outer__"
        pos = _scan_closing_underscores(text, 2)
        # Should find the closing __ after "outer", not the one after "inner"
        assert pos == 18

    # -- Edge cases --

    def test_閉じアンダースコア検出_閉じなし_マイナス1(self):
        """Returns -1 when no valid closing __ is found."""
        text = "__noclosing"
        pos = _scan_closing_underscores(text, 2)
        assert pos == -1

    def test_閉じアンダースコア検出_空のボディ(self):
        """Handles empty body (body_start points to closing __)."""
        text = "____"
        pos = _scan_closing_underscores(text, 2)
        # Position 2 is '_', position 3 is '_' -- these form the closing __
        assert pos == 2 or pos == -1  # depends on empty body handling


# =========================================================================
# Stage 4: WildcardResolver
# =========================================================================


class TestWildcardResolver:
    """Tests for Stage 4: Name resolution."""

    # -- Helper --

    @staticmethod
    def _make_resolver(
        cards_dir: Path,
        key_defs: list[KeyDefinition],
    ) -> WildcardResolver:
        """Build a WildcardResolver from a list of KeyDefinitions."""
        registry: dict[str, list[KeyDefinition]] = {}
        for kd in key_defs:
            registry.setdefault(kd.name, []).append(kd)
        return WildcardResolver(registry, cards_dir)

    # -- Normal: short form --

    def test_短縮形解決_キー名で解決(self, tmp_path: Path):
        """Resolves short-form reference __keyname__ by key name."""
        cards_dir = tmp_path / "cards"
        kd = KeyDefinition(
            name="greeting",
            file_path=cards_dir / "test.yaml",
            raw_values=["hello"],
        )
        resolver = self._make_resolver(cards_dir, [kd])
        resolved = resolver.resolve("greeting")
        assert resolved is not None
        assert resolved.name == "greeting"

    def test_短縮形解決_同名キーの後勝ち(self, tmp_path: Path):
        """For duplicate key names, the last one wins (last-wins)."""
        cards_dir = tmp_path / "cards"
        kd_a = KeyDefinition(
            name="style",
            file_path=cards_dir / "a.yaml",
            raw_values=["style A"],
        )
        kd_b = KeyDefinition(
            name="style",
            file_path=cards_dir / "b.yaml",
            raw_values=["style B"],
        )
        resolver = self._make_resolver(cards_dir, [kd_a, kd_b])
        resolved = resolver.resolve("style")
        assert resolved is not None
        # Last entry wins
        assert resolved.file_path == kd_b.file_path
        assert resolved.raw_values == ["style B"]

    # -- Normal: full path --

    def test_フルパス解決_パスとキー名で解決(self, tmp_path: Path):
        """Resolves full-path reference by matching file path."""
        cards_dir = tmp_path / "cards"
        kd = KeyDefinition(
            name="朝田詩乃体格",
            file_path=cards_dir / "SAO" / "CH_asada" / "asada.yaml",
            raw_values=["slender body"],
        )
        resolver = self._make_resolver(cards_dir, [kd])
        resolved = resolver.resolve("cards/SAO/CH_asada/朝田詩乃体格")
        assert resolved is not None
        assert resolved.name == "朝田詩乃体格"

    def test_フルパス解決_同名キーを正しいファイルパスに解決(
        self, tmp_path: Path
    ):
        """Full-path resolves to the correct file when duplicate key names exist."""
        cards_dir = tmp_path / "cards"
        kd_sao = KeyDefinition(
            name="体格",
            file_path=cards_dir / "SAO" / "asada.yaml",
            raw_values=["slender"],
        )
        kd_ba = KeyDefinition(
            name="体格",
            file_path=cards_dir / "BA" / "shiroko.yaml",
            raw_values=["athletic"],
        )
        resolver = self._make_resolver(cards_dir, [kd_sao, kd_ba])

        resolved_sao = resolver.resolve("cards/SAO/体格")
        assert resolved_sao is not None
        assert resolved_sao.raw_values == ["slender"]

        resolved_ba = resolver.resolve("cards/BA/体格")
        assert resolved_ba is not None
        assert resolved_ba.raw_values == ["athletic"]

    # -- Normal: get_all_key_names() --

    def test_全キー名取得_ソート済みリスト(self, tmp_path: Path):
        """get_all_key_names() returns a sorted list."""
        cards_dir = tmp_path / "cards"
        kd_c = KeyDefinition(name="charlie", file_path=cards_dir / "c.yaml", raw_values=[])
        kd_a = KeyDefinition(name="alpha", file_path=cards_dir / "a.yaml", raw_values=[])
        kd_b = KeyDefinition(name="beta", file_path=cards_dir / "b.yaml", raw_values=[])
        resolver = self._make_resolver(cards_dir, [kd_c, kd_a, kd_b])
        names = resolver.get_all_key_names()
        assert names == ["alpha", "beta", "charlie"]

    def test_全キー名取得_重複なし(self, tmp_path: Path):
        """get_all_key_names() returns unique names even with duplicates."""
        cards_dir = tmp_path / "cards"
        kd1 = KeyDefinition(name="style", file_path=cards_dir / "a.yaml", raw_values=[])
        kd2 = KeyDefinition(name="style", file_path=cards_dir / "b.yaml", raw_values=[])
        resolver = self._make_resolver(cards_dir, [kd1, kd2])
        names = resolver.get_all_key_names()
        assert names == ["style"]

    # -- Normal: get_refs_for_key() --

    def test_キーの参照取得_値行から参照を抽出(self, tmp_path: Path):
        """get_refs_for_key() extracts references from value lines."""
        cards_dir = tmp_path / "cards"
        kd = KeyDefinition(
            name="scenes",
            file_path=cards_dir / "scenes.yaml",
            raw_values=[
                "__cards/SAO/CH_asada/朝田詩乃__",
                "literal text without refs",
                "__デフォルト__",
            ],
        )
        resolver = self._make_resolver(cards_dir, [kd])
        refs = resolver.get_refs_for_key(kd)
        ref_names = [r.name for r in refs]
        assert "cards/SAO/CH_asada/朝田詩乃" in ref_names
        assert "デフォルト" in ref_names

    # -- Error cases --

    def test_存在しない参照_Noneを返す(self, tmp_path: Path):
        """Returns None for a non-existent reference."""
        cards_dir = tmp_path / "cards"
        resolver = self._make_resolver(cards_dir, [])
        result = resolver.resolve("non_existent_key")
        assert result is None

    def test_存在しないフルパス参照_Noneを返す(self, tmp_path: Path):
        """Returns None for a non-existent full-path reference."""
        cards_dir = tmp_path / "cards"
        kd = KeyDefinition(
            name="体格",
            file_path=cards_dir / "SAO" / "asada.yaml",
            raw_values=["slender"],
        )
        resolver = self._make_resolver(cards_dir, [kd])
        # Wrong directory path
        result = resolver.resolve("cards/WRONG/体格")
        assert result is None


# =========================================================================
# Stage 4 auxiliary: build_key_registry()
# =========================================================================


class TestBuildKeyRegistry:
    """Tests for the build_key_registry() function."""

    def test_キーレジストリ構築_複数ファイルから構築(
        self, multi_file_cards_dir: Path
    ):
        """Builds key registry from multiple YAML files."""
        yaml_files = scan_yaml_files(multi_file_cards_dir)
        registry = build_key_registry(yaml_files)
        assert isinstance(registry, dict)
        # Should contain keys from all files
        assert "メイン" in registry
        assert "朝田詩乃" in registry
        assert "朝田詩乃体格" in registry

    def test_キーレジストリ構築_同名キーがリストに蓄積(
        self, duplicate_key_cards_dir: Path
    ):
        """Same key name from different files accumulates in a list."""
        yaml_files = scan_yaml_files(duplicate_key_cards_dir)
        registry = build_key_registry(yaml_files)
        assert "common_style" in registry
        assert len(registry["common_style"]) == 2

    def test_キーレジストリ構築_空のファイルリスト(self):
        """Empty file list returns empty registry."""
        registry = build_key_registry([])
        assert isinstance(registry, dict)
        assert len(registry) == 0

    def test_キーレジストリ構築_戻り値の型チェック(
        self, simple_cards_dir: Path
    ):
        """Return type is dict[str, list[KeyDefinition]]."""
        yaml_files = scan_yaml_files(simple_cards_dir)
        registry = build_key_registry(yaml_files)
        for key_name, key_defs in registry.items():
            assert isinstance(key_name, str)
            assert isinstance(key_defs, list)
            for kd in key_defs:
                assert isinstance(kd, KeyDefinition)


# =========================================================================
# Stage 5: build_tree()
# =========================================================================


class TestBuildTree:
    """Tests for Stage 5: Tree construction."""

    # -- Helper --

    @staticmethod
    def _make_resolver_from_dir(cards_dir: Path) -> WildcardResolver:
        """Create a WildcardResolver from a cards directory."""
        yaml_files = scan_yaml_files(cards_dir)
        registry = build_key_registry(yaml_files)
        return WildcardResolver(registry, cards_dir)

    # -- Normal cases --

    def test_ツリー構築_エントリポイントから再帰的に構築(
        self, simple_cards_dir: Path
    ):
        """Builds a tree recursively from the entry point."""
        resolver = self._make_resolver_from_dir(simple_cards_dir)
        tree = build_tree("greeting", resolver)
        assert isinstance(tree, TreeNode)
        assert tree.name == "greeting"
        assert tree.is_leaf is False
        assert tree.is_circular is False
        # "greeting" references "farewell", which is a leaf
        assert len(tree.children) >= 1
        farewell_children = [c for c in tree.children if c.name == "farewell"]
        assert len(farewell_children) == 1
        assert farewell_children[0].is_leaf is True

    def test_ツリー構築_循環参照検出(self, circular_ref_cards_dir: Path):
        """Detects circular references and marks them with is_circular=True."""
        resolver = self._make_resolver_from_dir(circular_ref_cards_dir)
        tree = build_tree("alpha", resolver)
        assert isinstance(tree, TreeNode)
        assert tree.name == "alpha"

        # alpha -> beta -> alpha (circular)
        beta_nodes = [c for c in tree.children if c.name == "beta"]
        assert len(beta_nodes) == 1
        beta = beta_nodes[0]
        assert beta.is_circular is False

        # beta's child should be alpha with is_circular=True
        circular_nodes = [c for c in beta.children if c.is_circular]
        assert len(circular_nodes) == 1
        assert circular_nodes[0].name == "alpha"

    def test_ツリー構築_未解決参照はツリーに含まれない(
        self, tmp_path: Path, yaml_factory
    ):
        """Unresolved references are not included in the tree."""
        cards_dir = tmp_path / "cards"
        yaml_factory(
            "cards/test.yaml",
            "entry:\n"
            "  - __existing_key__\n"
            "  - __non_existent_key__\n"
            "\n"
            "existing_key:\n"
            "  - leaf value\n",
        )
        resolver = self._make_resolver_from_dir(cards_dir)
        tree = build_tree("entry", resolver)
        # Only "existing_key" should appear; "non_existent_key" is unresolved
        child_names = [c.name for c in tree.children]
        assert "existing_key" in child_names
        assert "non_existent_key" not in child_names

    def test_ツリー構築_深い依存チェーン(
        self, multi_file_cards_dir: Path
    ):
        """Builds tree through multi-level dependencies."""
        resolver = self._make_resolver_from_dir(multi_file_cards_dir)
        tree = build_tree("メイン", resolver)
        assert tree.name == "メイン"
        assert tree.is_leaf is False
        # メイン -> シーンまとめ and デフォルト
        child_names = [c.name for c in tree.children]
        assert "シーンまとめ" in child_names

    # -- Edge cases --

    def test_ツリー構築_存在しないエントリキー_リーフノード(
        self, simple_cards_dir: Path
    ):
        """Non-existent entry key returns a leaf TreeNode."""
        resolver = self._make_resolver_from_dir(simple_cards_dir)
        tree = build_tree("does_not_exist", resolver)
        assert isinstance(tree, TreeNode)
        assert tree.is_leaf is True

    def test_ツリー構築_同じキーが異なるブランチに出現_循環ではない(
        self, diamond_ref_cards_dir: Path
    ):
        """Same key in different branches is allowed (not circular).

        root -> branch_a -> shared
        root -> branch_b -> shared

        'shared' appears in both branches but is NOT circular.
        """
        resolver = self._make_resolver_from_dir(diamond_ref_cards_dir)
        tree = build_tree("root", resolver)

        # Both branches should contain 'shared'
        for child in tree.children:
            if child.name in ("branch_a", "branch_b"):
                shared_nodes = [c for c in child.children if c.name == "shared"]
                assert len(shared_nodes) == 1
                assert shared_nodes[0].is_circular is False
                assert shared_nodes[0].is_leaf is True

    def test_ツリー構築_コメントアウトされた参照はスキップ(
        self, multi_file_cards_dir: Path
    ):
        """Commented-out references in values are not in the tree.

        scenes.yaml has:
          シーンまとめ:
            - __cards/SAO/CH_asada/朝田詩乃__
            # - __cards/BA/CH_shiroko/シロコ__  <- commented out
        """
        resolver = self._make_resolver_from_dir(multi_file_cards_dir)
        tree = build_tree("シーンまとめ", resolver)
        child_names = [c.name for c in tree.children]
        # シロコ should NOT be in the tree (commented out)
        assert "シロコ" not in child_names

    def test_ツリー構築_リーフノードの属性(
        self, simple_cards_dir: Path
    ):
        """Leaf nodes have correct attributes."""
        resolver = self._make_resolver_from_dir(simple_cards_dir)
        tree = build_tree("farewell", resolver)
        # farewell has only literal value "goodbye", no refs
        assert tree.is_leaf is True
        assert tree.is_circular is False
        assert len(tree.children) == 0

    def test_ツリー構築_TreeNodeのref_nameフィールド(
        self, simple_cards_dir: Path
    ):
        """TreeNode has ref_name field for reference tracking."""
        resolver = self._make_resolver_from_dir(simple_cards_dir)
        tree = build_tree("greeting", resolver)
        assert isinstance(tree.ref_name, str)
        assert len(tree.ref_name) > 0


# =========================================================================
# Integration: Full pipeline
# =========================================================================


class TestFullPipeline:
    """Integration tests covering the full Stage 1-5 pipeline."""

    def test_完全パイプライン_日本語コンテンツで動作(
        self, multi_file_cards_dir: Path
    ):
        """Full pipeline works with Japanese content end-to-end."""
        # Stage 1
        yaml_files = scan_yaml_files(multi_file_cards_dir)
        assert len(yaml_files) > 0

        # Stage 2 + 4 aux
        registry = build_key_registry(yaml_files)
        assert "メイン" in registry

        # Stage 4
        resolver = WildcardResolver(registry, multi_file_cards_dir)
        all_keys = resolver.get_all_key_names()
        assert "メイン" in all_keys
        assert all_keys == sorted(all_keys)

        # Stage 5
        tree = build_tree("メイン", resolver)
        assert tree.name == "メイン"
        assert tree.is_leaf is False

    def test_完全パイプライン_フルパス参照の解決(
        self, multi_file_cards_dir: Path
    ):
        """Full-path references are correctly resolved through the pipeline."""
        yaml_files = scan_yaml_files(multi_file_cards_dir)
        registry = build_key_registry(yaml_files)
        resolver = WildcardResolver(registry, multi_file_cards_dir)

        # scenes.yaml references __cards/SAO/CH_asada/朝田詩乃__
        tree = build_tree("シーンまとめ", resolver)
        child_names = [c.name for c in tree.children]
        assert "朝田詩乃" in child_names

    def test_完全パイプライン_後勝ちの動作確認(
        self, duplicate_key_cards_dir: Path
    ):
        """Last-wins semantics work through the full pipeline."""
        yaml_files = scan_yaml_files(duplicate_key_cards_dir)
        registry = build_key_registry(yaml_files)
        resolver = WildcardResolver(registry, duplicate_key_cards_dir)

        # "user" references __common_style__ which exists in both files
        resolved = resolver.resolve("common_style")
        assert resolved is not None
        # file_b.yaml should win (sorted after file_a.yaml)
        assert "file_b" in str(resolved.file_path)

    def test_完全パイプライン_ネスト参照のツリー構築(
        self, nested_ref_cards_dir: Path
    ):
        """Nested (brace) references are handled in tree building."""
        yaml_files = scan_yaml_files(nested_ref_cards_dir)
        registry = build_key_registry(yaml_files)
        resolver = WildcardResolver(registry, nested_ref_cards_dir)

        tree = build_tree("scene", resolver)
        assert tree.name == "scene"
        # The inner refs (season, character) should appear in the tree
        all_child_names = self._collect_child_names(tree)
        assert "season" in all_child_names
        assert "character" in all_child_names

    @staticmethod
    def _collect_child_names(node: TreeNode) -> list[str]:
        """Recursively collect all descendant names."""
        names: list[str] = []
        for child in node.children:
            names.append(child.name)
            names.extend(TestFullPipeline._collect_child_names(child))
        return names
