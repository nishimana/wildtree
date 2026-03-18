"""Unit tests for core/parser.py — v2 パーサーのテスト。

設計意図ドキュメント (docs/design/s2-scanner-parser.md) に基づいて、
行ベース YAML パーサーの各関数を検証する。

テスト対象:
  - parse_yaml_file(file_path: Path) -> list[KeyDefinition]
  - extract_refs(text: str) -> list[WildcardRef]
  - extract_literals(text: str, refs: list[WildcardRef]) -> list[str]
  - build_registry(yaml_files: list[Path]) -> KeyRegistry

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models import KeyDefinition, KeyRegistry, RefType, ValueEntry, WildcardRef
from core.parser import build_registry, extract_literals, extract_refs, parse_yaml_file


# =========================================================================
# ヘルパー
# =========================================================================


def _write_yaml(path: Path, content: str) -> Path:
    """テスト用 YAML ファイルを作成するヘルパー。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# =========================================================================
# parse_yaml_file — 正常系
# =========================================================================


class TestParseYamlFile正常系:
    """parse_yaml_file の正常系テスト。"""

    def test_parse_yaml_file_トップレベルキーと値行を抽出する(self, tmp_path: Path):
        """基本的なキー定義と値行を正しく抽出する。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "greeting:\n"
            "  - hello\n"
            "  - world\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        kd = result[0]
        assert kd.name == "greeting"
        assert kd.file_path == path
        assert len(kd.values) == 2
        assert kd.values[0].raw_text == "hello"
        assert kd.values[1].raw_text == "world"

    def test_parse_yaml_file_複数キー定義を抽出する(self, tmp_path: Path):
        """1ファイルに複数のキー定義がある場合、すべて抽出する。"""
        path = _write_yaml(
            tmp_path / "multi.yaml",
            "first_key:\n"
            "  - value1\n"
            "\n"
            "second_key:\n"
            "  - value2\n"
            "\n"
            "third_key:\n"
            "  - value3\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 3
        names = [kd.name for kd in result]
        assert "first_key" in names
        assert "second_key" in names
        assert "third_key" in names

    def test_parse_yaml_file_行番号が1始まりで正確(self, tmp_path: Path):
        """キー定義と値行の行番号が1始まりで正確に記録される。"""
        path = _write_yaml(
            tmp_path / "lines.yaml",
            "key_a:\n"       # 行1
            "  - value_a\n"  # 行2
            "\n"             # 行3
            "key_b:\n"       # 行4
            "  - value_b\n", # 行5
        )

        result = parse_yaml_file(path)

        assert len(result) == 2
        # key_a は行1
        assert result[0].name == "key_a"
        assert result[0].line_number == 1
        # key_a の値行は行2
        assert result[0].values[0].line_number == 2
        # key_b は行4
        assert result[1].name == "key_b"
        assert result[1].line_number == 4
        # key_b の値行は行5
        assert result[1].values[0].line_number == 5

    def test_parse_yaml_file_戻り値がKeyDefinitionのリスト(self, tmp_path: Path):
        """戻り値の型が list[KeyDefinition] であることを確認する。"""
        path = _write_yaml(tmp_path / "type.yaml", "key:\n  - value\n")

        result = parse_yaml_file(path)

        assert isinstance(result, list)
        assert all(isinstance(kd, KeyDefinition) for kd in result)

    def test_parse_yaml_file_値行がValueEntryオブジェクト(self, tmp_path: Path):
        """値行が ValueEntry オブジェクトとして構造化されている。"""
        path = _write_yaml(tmp_path / "ve.yaml", "key:\n  - some_value\n")

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert len(result[0].values) == 1
        ve = result[0].values[0]
        assert isinstance(ve, ValueEntry)
        assert ve.raw_text == "some_value"
        assert ve.is_commented is False

    def test_parse_yaml_file_日本語キー名を正しく抽出する(self, tmp_path: Path):
        """日本語キー名が正しく抽出される。"""
        path = _write_yaml(
            tmp_path / "jp.yaml",
            "朝田詩乃体格:\n"
            "  - slender body\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert result[0].name == "朝田詩乃体格"

    def test_parse_yaml_file_参照を含む値行でrefsが設定される(self, tmp_path: Path):
        """参照パターンを含む値行で ValueEntry.refs が設定される。"""
        path = _write_yaml(
            tmp_path / "refs.yaml",
            "scene:\n"
            "  - __cards/SAO/朝田詩乃__\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        ve = result[0].values[0]
        assert len(ve.refs) == 1
        assert ve.refs[0].full_path == "cards/SAO/朝田詩乃"
        assert ve.refs[0].ref_type == RefType.NORMAL

    def test_parse_yaml_file_リテラルを含む値行でliteralsが設定される(self, tmp_path: Path):
        """リテラル値を含む値行で ValueEntry.literals が設定される。"""
        path = _write_yaml(
            tmp_path / "lits.yaml",
            "prompt:\n"
            "  - dynamic_angle,dynamic_pose\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        ve = result[0].values[0]
        assert "dynamic_angle" in ve.literals
        assert "dynamic_pose" in ve.literals

    def test_parse_yaml_file_raw_textからリストプレフィックスが除去される(self, tmp_path: Path):
        """値行の raw_text から '  - ' プレフィックスが除去される。"""
        path = _write_yaml(
            tmp_path / "prefix.yaml",
            "key:\n"
            "  - some value here\n",
        )

        result = parse_yaml_file(path)

        assert result[0].values[0].raw_text == "some value here"

    def test_parse_yaml_file_file_pathが正しく設定される(self, tmp_path: Path):
        """KeyDefinition.file_path にパース元のファイルパスが設定される。"""
        path = _write_yaml(tmp_path / "fp.yaml", "key:\n  - value\n")

        result = parse_yaml_file(path)

        assert result[0].file_path == path


# =========================================================================
# parse_yaml_file — コメント行
# =========================================================================


class TestParseYamlFileコメント行:
    """parse_yaml_file のコメント行に関するテスト。"""

    def test_parse_yaml_file_値行コメントをis_commentedTrueで保持する(self, tmp_path: Path):
        """値行のコメント（# - value）を is_commented=True の ValueEntry として保持する。"""
        path = _write_yaml(
            tmp_path / "commented.yaml",
            "scenes:\n"
            "  - __active_ref__\n"
            "  # - __commented_ref__\n"
            "  - __another_ref__\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        values = result[0].values
        assert len(values) == 3
        # 非コメント行
        assert values[0].is_commented is False
        assert values[0].raw_text == "__active_ref__"
        # コメント行
        assert values[1].is_commented is True
        assert values[1].raw_text == "__commented_ref__"
        # 非コメント行
        assert values[2].is_commented is False
        assert values[2].raw_text == "__another_ref__"

    def test_parse_yaml_file_コメント行のraw_textが正規化される(self, tmp_path: Path):
        """コメント行の raw_text は '# - ' を除去した中身になる。"""
        path = _write_yaml(
            tmp_path / "normalize.yaml",
            "key:\n"
            "  # - __cards/xxx/yyy__,__cards/xxx/zzz__\n",
        )

        result = parse_yaml_file(path)

        ve = result[0].values[0]
        assert ve.is_commented is True
        # "# - " を除去した中身
        assert ve.raw_text == "__cards/xxx/yyy__,__cards/xxx/zzz__"

    def test_parse_yaml_file_コメント行にも参照抽出が行われる(self, tmp_path: Path):
        """コメント行からも参照が抽出される（is_commented=True だが refs が設定される）。"""
        path = _write_yaml(
            tmp_path / "comm_refs.yaml",
            "key:\n"
            "  # - __ref1__,__ref2__,__ref3__\n",
        )

        result = parse_yaml_file(path)

        ve = result[0].values[0]
        assert ve.is_commented is True
        assert len(ve.refs) == 3

    def test_parse_yaml_file_セクション区切りコメントはスキップする(self, tmp_path: Path):
        """セクション区切りコメント（'# ---- 名前 ----'）は ValueEntry を生成しない。"""
        path = _write_yaml(
            tmp_path / "section.yaml",
            "key:\n"
            "  - value1\n"
            "  # ---- 白球少女 ----\n"
            "  - value2\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        values = result[0].values
        # セクション区切りはスキップされ、value1 と value2 のみ
        assert len(values) == 2
        assert values[0].raw_text == "value1"
        assert values[1].raw_text == "value2"

    def test_parse_yaml_file_キーレベルコメントはスキップする(self, tmp_path: Path):
        """キーレベルのコメント（インデントなし）はキー定義として扱わない。"""
        path = _write_yaml(
            tmp_path / "toplevel.yaml",
            "# これはコメント\n"
            "####################\n"
            "actual_key:\n"
            "  - value\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert result[0].name == "actual_key"

    def test_parse_yaml_file_セパレータ行はスキップする(self, tmp_path: Path):
        """セパレータ行（'####....'）はスキップする。"""
        path = _write_yaml(
            tmp_path / "separator.yaml",
            "############################################################################################\n"
            "key:\n"
            "  - value\n"
            "############################################################################################\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert result[0].name == "key"

    def test_parse_yaml_file_全値行がコメントのキー定義(self, tmp_path: Path):
        """全ての値行がコメントの場合、全 ValueEntry が is_commented=True で保持される。"""
        path = _write_yaml(
            tmp_path / "all_commented.yaml",
            "disabled_key:\n"
            "  # - __ref1__\n"
            "  # - __ref2__\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert result[0].name == "disabled_key"
        assert len(result[0].values) == 2
        assert all(ve.is_commented for ve in result[0].values)

    def test_parse_yaml_file_キー定義全体のコメントアウトはスキップ(self, tmp_path: Path):
        """キー定義全体がコメントアウトされている場合（インデントなし）はスキップする。"""
        path = _write_yaml(
            tmp_path / "commented_key.yaml",
            "# 朝田詩乃SSNN000400:\n"
            "#   - 1girl,asada_shino\n"
            "active_key:\n"
            "  - value\n",
        )

        result = parse_yaml_file(path)

        # コメントアウトされたキー定義はスキップされ、active_key のみ
        names = [kd.name for kd in result]
        assert "active_key" in names
        # コメントアウトされたキーは含まれない
        assert not any("朝田詩乃" in name for name in names)

    def test_parse_yaml_file_インデント付きの自由コメントはスキップ(self, tmp_path: Path):
        """インデント付きだが '- ' パターンを含まない自由コメントはスキップする。"""
        path = _write_yaml(
            tmp_path / "free_comment.yaml",
            "key:\n"
            "  - value1\n"
            "  # これはメモです\n"
            "  - value2\n",
        )

        result = parse_yaml_file(path)

        values = result[0].values
        # 自由コメントはスキップされ、value1 と value2 のみ
        assert len(values) == 2


# =========================================================================
# parse_yaml_file — 異常系
# =========================================================================


class TestParseYamlFile異常系:
    """parse_yaml_file の異常系テスト。"""

    def test_parse_yaml_file_存在しないファイル_空リスト(self, tmp_path: Path):
        """存在しないファイルを指定すると空リストを返す（例外なし）。"""
        non_existent = tmp_path / "does_not_exist.yaml"

        result = parse_yaml_file(non_existent)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_parse_yaml_file_空ファイル_空リスト(self, tmp_path: Path):
        """空ファイルは空リストを返す。"""
        path = _write_yaml(tmp_path / "empty.yaml", "")

        result = parse_yaml_file(path)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_parse_yaml_file_読めないファイル_空リスト(self, tmp_path: Path):
        """読み込めないファイル（エンコーディングエラー）は空リストを返す。"""
        path = tmp_path / "bad_encoding.yaml"
        # SHIFT-JIS でバイナリ書き込み（UTF-8 でデコード不可能なバイト列）
        path.write_bytes(b"key:\n  - \x82\xb1\x82\xf1\x82\xc9\x82\xbf\x82\xcd\n")

        result = parse_yaml_file(path)

        assert isinstance(result, list)
        assert len(result) == 0


# =========================================================================
# parse_yaml_file — エッジケース
# =========================================================================


class TestParseYamlFileエッジケース:
    """parse_yaml_file のエッジケーステスト。"""

    def test_parse_yaml_file_キー定義に値行がゼロ個(self, tmp_path: Path):
        """キー定義の後に値行がない場合、values が空リストの KeyDefinition を返す。"""
        path = _write_yaml(
            tmp_path / "no_values.yaml",
            "empty_key:\n"
            "\n"
            "next_key:\n"
            "  - value\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 2
        empty_key = [kd for kd in result if kd.name == "empty_key"][0]
        assert empty_key.values == []

    def test_parse_yaml_file_空行のみの値ブロック(self, tmp_path: Path):
        """キー定義の後に空行のみがある場合、values は空リスト。"""
        path = _write_yaml(
            tmp_path / "blank_lines.yaml",
            "key:\n"
            "\n"
            "\n"
            "\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert result[0].values == []

    def test_parse_yaml_file_キー定義行末のコメント処理(self, tmp_path: Path):
        """キー定義行末のコメント（'key: # comment'）でキー名のみ抽出する。"""
        path = _write_yaml(
            tmp_path / "key_comment.yaml",
            "動き構図: # まあほどほどに使える\n"
            "  - value1\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert result[0].name == "動き構図"

    def test_parse_yaml_file_空定義を含む値行(self, tmp_path: Path):
        """空定義 '"{}"' を含む値行のパース。"""
        path = _write_yaml(
            tmp_path / "empty_def.yaml",
            'key:\n'
            '  - "{}"\n',
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        ve = result[0].values[0]
        assert ve.raw_text == '"{}"'
        assert ve.refs == []
        assert '"{}"' in ve.literals

    def test_parse_yaml_file_クォート付き値(self, tmp_path: Path):
        """クォート付き値（'"00"', '"01"'）のパース。"""
        path = _write_yaml(
            tmp_path / "quoted.yaml",
            'key:\n'
            '  - "00"\n'
            '  - "01"\n',
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert result[0].values[0].raw_text == '"00"'
        assert result[0].values[1].raw_text == '"01"'

    def test_parse_yaml_file_空行はスキップされる(self, tmp_path: Path):
        """空行は ValueEntry を生成しない。"""
        path = _write_yaml(
            tmp_path / "blank.yaml",
            "key:\n"
            "  - value1\n"
            "\n"
            "  - value2\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        # 空行は含まれない
        raw_texts = [ve.raw_text for ve in result[0].values]
        assert "value1" in raw_texts
        assert "value2" in raw_texts

    def test_parse_yaml_file_値行にコロンを含む(self, tmp_path: Path):
        """値行にコロンを含む場合もキー定義行と混同しない（インデントで判別）。"""
        path = _write_yaml(
            tmp_path / "colon.yaml",
            "prompt:\n"
            "  - masterpiece, best quality, 1girl: sitting\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert result[0].name == "prompt"
        assert len(result[0].values) == 1

    def test_parse_yaml_file_CRLF改行に対応する(self, tmp_path: Path):
        """CRLF 改行コードのファイルを正しくパースする。"""
        path = tmp_path / "crlf.yaml"
        path.write_bytes(b"key:\r\n  - value1\r\n  - value2\r\n")

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert len(result[0].values) == 2
        assert result[0].values[0].raw_text == "value1"
        assert result[0].values[1].raw_text == "value2"

    def test_parse_yaml_file_参照とリテラルの混在する値行(self, tmp_path: Path):
        """参照とリテラルが混在する値行のパース。"""
        path = _write_yaml(
            tmp_path / "mixed.yaml",
            "key:\n"
            "  - dynamic_angle,dynamic_pose,__cards/シネマシャドウ__,__cards/バックライト__,\n",
        )

        result = parse_yaml_file(path)

        ve = result[0].values[0]
        # 参照が2件
        assert len(ve.refs) == 2
        ref_paths = [r.full_path for r in ve.refs]
        assert "cards/シネマシャドウ" in ref_paths
        assert "cards/バックライト" in ref_paths
        # リテラルが2件
        assert "dynamic_angle" in ve.literals
        assert "dynamic_pose" in ve.literals


# =========================================================================
# extract_refs — 正常系（通常参照）
# =========================================================================


class TestExtractRefs通常参照:
    """extract_refs の通常参照テスト。"""

    def test_extract_refs_短縮形参照を抽出する(self):
        """短縮形参照 __key__ を抽出する。"""
        result = extract_refs("__greeting__")

        assert len(result) == 1
        assert result[0].full_path == "greeting"
        assert result[0].raw == "__greeting__"
        assert result[0].ref_type == RefType.NORMAL

    def test_extract_refs_フルパス参照を抽出する(self):
        """フルパス参照 __cards/path/key__ を抽出する。"""
        result = extract_refs("__cards/SAO/CH_asada/朝田詩乃体格__")

        assert len(result) == 1
        assert result[0].full_path == "cards/SAO/CH_asada/朝田詩乃体格"
        assert result[0].ref_type == RefType.NORMAL

    def test_extract_refs_1行に複数の参照を抽出する(self):
        """1行に複数の参照がある場合、すべて抽出する。"""
        result = extract_refs("__first__,__second__,__third__")

        assert len(result) == 3
        paths = [r.full_path for r in result]
        assert "first" in paths
        assert "second" in paths
        assert "third" in paths

    def test_extract_refs_日本語参照名を抽出する(self):
        """日本語参照名を正しく抽出する。"""
        result = extract_refs("__朝田詩乃SinonGGOFight脱00__")

        assert len(result) == 1
        assert result[0].full_path == "朝田詩乃SinonGGOFight脱00"
        assert result[0].ref_type == RefType.NORMAL

    def test_extract_refs_テキストと参照が混在する行(self):
        """テキストと参照が混在する行から参照のみ抽出する。"""
        result = extract_refs("hello __world__ and __universe__")

        assert len(result) == 2
        paths = [r.full_path for r in result]
        assert "world" in paths
        assert "universe" in paths

    def test_extract_refs_参照のrawフィールドにデリミタが含まれる(self):
        """WildcardRef.raw にはデリミタ（__）が含まれる。"""
        result = extract_refs("__cards/シネマシャドウ__")

        assert result[0].raw == "__cards/シネマシャドウ__"

    def test_extract_refs_戻り値がWildcardRefのリスト(self):
        """戻り値の型が list[WildcardRef] であることを確認する。"""
        result = extract_refs("__test__")

        assert isinstance(result, list)
        assert all(isinstance(r, WildcardRef) for r in result)


# =========================================================================
# extract_refs — 動的参照
# =========================================================================


class TestExtractRefs動的参照:
    """extract_refs の動的参照テスト。"""

    def test_extract_refs_単一内部参照の動的参照(self):
        """動的参照（単一内部参照）を検出する。"""
        result = extract_refs("__{__cards/options/貧乳キャラ__}__")

        assert len(result) == 1
        ref = result[0]
        assert ref.ref_type == RefType.DYNAMIC
        assert len(ref.inner_refs) == 1
        assert ref.inner_refs[0].full_path == "cards/options/貧乳キャラ"

    def test_extract_refs_複数内部参照の動的参照(self):
        """動的参照（複数内部参照）を検出する。"""
        result = extract_refs("__{__cards/姦キー__}{__cards/鬼キー__}__")

        assert len(result) == 1
        ref = result[0]
        assert ref.ref_type == RefType.DYNAMIC
        assert len(ref.inner_refs) == 2
        inner_paths = [ir.full_path for ir in ref.inner_refs]
        assert "cards/姦キー" in inner_paths
        assert "cards/鬼キー" in inner_paths

    def test_extract_refs_サフィックス付き動的参照(self):
        """動的参照にサフィックスがある場合のパース。"""
        result = extract_refs("__{__cards/キャラキー__}NP__")

        assert len(result) == 1
        ref = result[0]
        assert ref.ref_type == RefType.DYNAMIC
        assert ref.full_path == "{__cards/キャラキー__}NP"
        assert len(ref.inner_refs) == 1

    def test_extract_refs_プレフィックス付き動的参照(self):
        """動的参照にプレフィックスがある場合のパース。"""
        text = "__cards/ソードアート・オンライン/CH朝田詩乃/朝田詩乃ステージSSNN0001_{__cards/姦キー__}{__cards/鬼キー__}__"
        result = extract_refs(text)

        assert len(result) == 1
        ref = result[0]
        assert ref.ref_type == RefType.DYNAMIC
        assert ref.full_path == "cards/ソードアート・オンライン/CH朝田詩乃/朝田詩乃ステージSSNN0001_{__cards/姦キー__}{__cards/鬼キー__}"
        assert len(ref.inner_refs) == 2

    def test_extract_refs_動的参照のinner_refsが通常参照である(self):
        """動的参照の inner_refs の各要素が RefType.NORMAL の WildcardRef である。"""
        result = extract_refs("__{__cards/a__}{__cards/b__}__")

        ref = result[0]
        for inner in ref.inner_refs:
            assert isinstance(inner, WildcardRef)
            assert inner.ref_type == RefType.NORMAL

    def test_extract_refs_動的参照は外側のみがリストに含まれる(self):
        """動的参照の場合、返却リストには外側の参照のみが含まれる。"""
        result = extract_refs("__{__cards/a__}{__cards/b__}__")

        # 外側の参照1つのみがリストに含まれる
        assert len(result) == 1
        assert result[0].ref_type == RefType.DYNAMIC

    def test_extract_refs_シーケンス行動の動的参照(self):
        """複雑なパスを含む動的参照のパース。"""
        text = "__cards/シーケンス{__cards/ソードアート・オンライン/CH朝田詩乃/シーン/朝田詩乃シーケンス行動種別キー__}行動00__"
        result = extract_refs(text)

        assert len(result) == 1
        ref = result[0]
        assert ref.ref_type == RefType.DYNAMIC
        assert len(ref.inner_refs) == 1


# =========================================================================
# extract_refs — エッジケース
# =========================================================================


class TestExtractRefsエッジケース:
    """extract_refs のエッジケーステスト。"""

    def test_extract_refs_参照なしテキスト_空リスト(self):
        """参照がないテキストは空リストを返す。"""
        result = extract_refs("just plain text without refs")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_refs_空文字列_空リスト(self):
        """空文字列は空リストを返す。"""
        result = extract_refs("")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_refs_閉じデリミタなし_参照として認識しない(self):
        """閉じ __ がない場合、参照として認識しない。"""
        result = extract_refs("__incomplete_ref")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_refs_アンダースコア1つ_参照でない(self):
        """アンダースコア1つは参照デリミタではない。"""
        result = extract_refs("_not_a_ref_")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_refs_空の参照名(self):
        """空の参照名 ____ はクラッシュしない。"""
        result = extract_refs("____")

        # クラッシュしないことが重要
        assert isinstance(result, list)

    def test_extract_refs_DP量指定子内の参照を抽出する(self):
        """DP 量指定子 {0-2$$...} 内の参照を抽出する。"""
        result = extract_refs("{0-2$$__cards/options/ライティング__}")

        assert len(result) == 1
        assert result[0].full_path == "cards/options/ライティング"

    def test_extract_refs_DP選択構文内の参照を抽出する(self):
        """DP 選択構文 {,...|} 内の参照を抽出する。"""
        result = extract_refs("{,__cards/options/アングル_from系2__|}")

        assert len(result) == 1
        assert result[0].full_path == "cards/options/アングル_from系2"

    def test_extract_refs_DP選択構文と参照の末尾パイプ(self):
        """DP 選択構文の末尾パイプ付き参照を抽出する。"""
        result = extract_refs("{,__cards/options/男序盤251007__|}")

        assert len(result) == 1
        assert result[0].full_path == "cards/options/男序盤251007"


# =========================================================================
# extract_literals — 正常系
# =========================================================================


class TestExtractLiterals正常系:
    """extract_literals の正常系テスト。"""

    def test_extract_literals_リテラルのみの行(self):
        """参照を含まないテキストはすべてリテラルとして返す。"""
        result = extract_literals("dynamic_angle,dynamic_pose", [])

        assert "dynamic_angle" in result
        assert "dynamic_pose" in result

    def test_extract_literals_参照を除外した残りをリテラルとして返す(self):
        """参照部分を除外した残りをリテラルとして返す。"""
        refs = [WildcardRef(raw="__cards/シネマシャドウ__", full_path="cards/シネマシャドウ")]
        result = extract_literals(
            "dynamic_angle,dynamic_pose,__cards/シネマシャドウ__",
            refs,
        )

        assert "dynamic_angle" in result
        assert "dynamic_pose" in result
        # 参照部分はリテラルに含まれない
        assert "__cards/シネマシャドウ__" not in result

    def test_extract_literals_参照のみの行_空リスト(self):
        """参照のみの行ではリテラルは空リストになる。"""
        refs = [
            WildcardRef(raw="__ref1__", full_path="ref1"),
            WildcardRef(raw="__ref2__", full_path="ref2"),
        ]
        result = extract_literals("__ref1__,__ref2__", refs)

        assert result == []

    def test_extract_literals_単一リテラル(self):
        """単一のリテラル値。"""
        result = extract_literals("slender body", [])

        assert len(result) == 1
        assert result[0] == "slender body"

    def test_extract_literals_リテラルがstripされる(self):
        """リテラルの前後の空白が strip される。"""
        result = extract_literals("  dynamic_angle , dynamic_pose  ", [])

        assert "dynamic_angle" in result
        assert "dynamic_pose" in result


# =========================================================================
# extract_literals — エッジケース
# =========================================================================


class TestExtractLiteralsエッジケース:
    """extract_literals のエッジケーステスト。"""

    def test_extract_literals_末尾カンマ_空セグメント除外(self):
        """末尾カンマ後の空セグメントは除外する。"""
        refs = [
            WildcardRef(raw="__cards/デフォルト__", full_path="cards/デフォルト"),
            WildcardRef(raw="__cards/アングル__", full_path="cards/アングル"),
        ]
        result = extract_literals(
            "__cards/デフォルト__,__cards/アングル__,",
            refs,
        )

        assert result == []

    def test_extract_literals_連続カンマ_空セグメント除外(self):
        """連続カンマ（,,）の空セグメントは除外する。"""
        result = extract_literals("a,,b", [])

        assert "a" in result
        assert "b" in result
        assert "" not in result

    def test_extract_literals_空定義(self):
        """空定義 '"{}"' はリテラルとして保持する。"""
        result = extract_literals('"{}"', [])

        assert len(result) == 1
        assert result[0] == '"{}"'

    def test_extract_literals_DP構文はリテラルとして保持(self):
        """DP 構文（{...|...}）はリテラルとして保持する。"""
        text = r"scenery{,(wide_shot:1.3)\|(very_wide_shot:1.3)\|}"
        result = extract_literals(text, [])

        assert len(result) == 1
        assert result[0] == text

    def test_extract_literals_loraタグはリテラルとして保持(self):
        """lora タグ (<lora:...>) はリテラルとして保持する。"""
        refs = []
        result = extract_literals(
            "<lora:SwordArtOnline_Sinon_IlluXL:0.8>,AsadaShino",
            refs,
        )

        assert "<lora:SwordArtOnline_Sinon_IlluXL:0.8>" in result
        assert "AsadaShino" in result

    def test_extract_literals_性格表現のDP構文(self):
        """性格表現の複雑な DP 構文はリテラルとして保持する。"""
        text = '"{{,(expressionless:0.7)}|}{{,(slight_smile:0.7)|}|}"'
        result = extract_literals(text, [])

        assert len(result) == 1
        assert result[0] == text

    def test_extract_literals_空文字列_空リスト(self):
        """空文字列は空リストを返す。"""
        result = extract_literals("", [])

        assert result == []

    def test_extract_literals_参照とリテラルが混在_実データパターン(self):
        """実データパターン: 参照とリテラルの混在（末尾カンマ付き）。"""
        refs = [
            WildcardRef(raw="__cards/シネマシャドウ__", full_path="cards/シネマシャドウ"),
            WildcardRef(raw="__cards/バックライト__", full_path="cards/バックライト"),
        ]
        result = extract_literals(
            "dynamic_angle,dynamic_pose,__cards/シネマシャドウ__,__cards/バックライト__,",
            refs,
        )

        assert "dynamic_angle" in result
        assert "dynamic_pose" in result
        assert len(result) == 2


# =========================================================================
# build_registry — 正常系
# =========================================================================


class TestBuildRegistry正常系:
    """build_registry の正常系テスト。"""

    def test_build_registry_複数ファイルからレジストリを構築する(self, tmp_path: Path):
        """複数の YAML ファイルからキーレジストリを構築する。"""
        path_a = _write_yaml(
            tmp_path / "a.yaml",
            "key_a:\n"
            "  - value_a\n",
        )
        path_b = _write_yaml(
            tmp_path / "b.yaml",
            "key_b:\n"
            "  - value_b\n",
        )

        registry = build_registry([path_a, path_b])

        assert isinstance(registry, dict)
        assert "key_a" in registry
        assert "key_b" in registry
        assert len(registry["key_a"]) == 1
        assert len(registry["key_b"]) == 1

    def test_build_registry_戻り値がKeyRegistryの形式(self, tmp_path: Path):
        """戻り値が dict[str, list[KeyDefinition]] の形式であることを確認する。"""
        path = _write_yaml(tmp_path / "test.yaml", "key:\n  - value\n")

        registry = build_registry([path])

        for key_name, key_defs in registry.items():
            assert isinstance(key_name, str)
            assert isinstance(key_defs, list)
            for kd in key_defs:
                assert isinstance(kd, KeyDefinition)

    def test_build_registry_1ファイルに複数キーがある場合(self, tmp_path: Path):
        """1ファイルに複数のキー定義がある場合、すべてレジストリに登録する。"""
        path = _write_yaml(
            tmp_path / "multi.yaml",
            "key_x:\n"
            "  - value_x\n"
            "\n"
            "key_y:\n"
            "  - value_y\n",
        )

        registry = build_registry([path])

        assert "key_x" in registry
        assert "key_y" in registry


# =========================================================================
# build_registry — 重複キー
# =========================================================================


class TestBuildRegistry重複キー:
    """build_registry の重複キーテスト。"""

    def test_build_registry_同名キーが複数ファイルでリストに蓄積される(self, tmp_path: Path):
        """同名キーが複数ファイルに存在する場合、list[KeyDefinition] に蓄積される。"""
        path_a = _write_yaml(
            tmp_path / "file_a.yaml",
            "common_style:\n"
            "  - style from file A\n",
        )
        path_b = _write_yaml(
            tmp_path / "file_b.yaml",
            "common_style:\n"
            "  - style from file B\n",
        )

        registry = build_registry([path_a, path_b])

        assert "common_style" in registry
        assert len(registry["common_style"]) == 2

    def test_build_registry_重複キーのファイル順序が保持される(self, tmp_path: Path):
        """重複キーの KeyDefinition リストの順序はファイルの処理順に従う。"""
        path_a = _write_yaml(
            tmp_path / "a.yaml",
            "dup:\n"
            "  - from_a\n",
        )
        path_b = _write_yaml(
            tmp_path / "b.yaml",
            "dup:\n"
            "  - from_b\n",
        )

        registry = build_registry([path_a, path_b])

        # path_a が先に処理されるので、リストの最初に来る
        assert registry["dup"][0].file_path == path_a
        assert registry["dup"][1].file_path == path_b


# =========================================================================
# build_registry — エッジケース
# =========================================================================


class TestBuildRegistryエッジケース:
    """build_registry のエッジケーステスト。"""

    def test_build_registry_空のファイルリスト_空辞書(self):
        """空のファイルリストは空の辞書を返す。"""
        registry = build_registry([])

        assert isinstance(registry, dict)
        assert len(registry) == 0

    def test_build_registry_パース失敗ファイルがあっても他は正常に処理(self, tmp_path: Path):
        """個別ファイルのパースが失敗しても、他のファイルは正常に処理される。"""
        good_path = _write_yaml(
            tmp_path / "good.yaml",
            "good_key:\n"
            "  - good_value\n",
        )
        bad_path = tmp_path / "bad.yaml"
        bad_path.write_bytes(b"key:\n  - \x82\xb1\x82\xf1\x82\xc9\n")

        registry = build_registry([good_path, bad_path])

        assert "good_key" in registry
        assert len(registry["good_key"]) == 1

    def test_build_registry_空ファイルのみ_空辞書(self, tmp_path: Path):
        """空ファイルのみの場合は空辞書を返す。"""
        path = _write_yaml(tmp_path / "empty.yaml", "")

        registry = build_registry([path])

        assert isinstance(registry, dict)
        assert len(registry) == 0


# =========================================================================
# エッジケース表の実データパターン — 統合テスト
# =========================================================================


class TestEdgeCasePatterns:
    """設計書のエッジケース表に記載された実データパターンのテスト。"""

    def test_カンマ区切りで参照とリテラルが混在(self):
        """実データ: dynamic_angle,dynamic_pose,__cards/シネマシャドウ__,__cards/バックライト__,"""
        text = "dynamic_angle,dynamic_pose,__cards/シネマシャドウ__,__cards/バックライト__,"

        refs = extract_refs(text)
        literals = extract_literals(text, refs)

        assert len(refs) == 2
        assert len(literals) == 2
        assert "dynamic_angle" in literals
        assert "dynamic_pose" in literals

    def test_行末のカンマ_参照のみ(self):
        """実データ: 行末にカンマがある参照のみの行。"""
        text = "__cards/デフォルト__,__cards/アングル__,__cards/options/ライティングxmdl__,__cards/シーンまとめ__"

        refs = extract_refs(text)
        literals = extract_literals(text, refs)

        assert len(refs) == 4
        assert literals == []

    def test_空定義_braces(self):
        """実データ: 空定義 '"{}"'。"""
        text = '"{}"'

        refs = extract_refs(text)
        literals = extract_literals(text, refs)

        assert refs == []
        assert len(literals) == 1
        assert literals[0] == '"{}"'

    def test_DP構文を含むリテラル(self):
        r"""実データ: DP 構文を含むリテラル。"""
        text = r"scenery{,(wide_shot:1.3)\|(very_wide_shot:1.3)\|}"

        refs = extract_refs(text)
        literals = extract_literals(text, refs)

        # DP 構文は参照ではない
        assert refs == []
        # 全体がリテラルとして保持される
        assert len(literals) == 1

    def test_loraタグ(self):
        """実データ: lora タグ。"""
        text = "<lora:SwordArtOnline_Sinon_IlluXL:0.8>,AsadaShino"

        refs = extract_refs(text)
        literals = extract_literals(text, refs)

        assert refs == []
        assert "<lora:SwordArtOnline_Sinon_IlluXL:0.8>" in literals
        assert "AsadaShino" in literals

    def test_動的参照_単一内部(self):
        """実データ: 動的参照（単一内部参照）。"""
        text = "__{__cards/options/貧乳キャラ__}__"

        refs = extract_refs(text)

        assert len(refs) == 1
        assert refs[0].ref_type == RefType.DYNAMIC
        assert len(refs[0].inner_refs) == 1

    def test_動的参照_複数内部(self):
        """実データ: 動的参照（複数内部参照）。"""
        text = "__{__cards/姦キー__}{__cards/鬼キー__}__"

        refs = extract_refs(text)

        assert len(refs) == 1
        assert refs[0].ref_type == RefType.DYNAMIC
        assert len(refs[0].inner_refs) == 2

    def test_動的参照_サフィックス付き(self):
        """実データ: 動的参照（サフィックス付き）。"""
        text = "__{__cards/キャラキー__}NP__"

        refs = extract_refs(text)

        assert len(refs) == 1
        assert refs[0].ref_type == RefType.DYNAMIC
        assert refs[0].full_path == "{__cards/キャラキー__}NP"

    def test_動的参照_プレフィックス付き(self):
        """実データ: 動的参照（プレフィックス付き）。"""
        text = "__cards/ソードアート・オンライン/CH朝田詩乃/朝田詩乃ステージSSNN0001_{__cards/姦キー__}{__cards/鬼キー__}__"

        refs = extract_refs(text)

        assert len(refs) == 1
        ref = refs[0]
        assert ref.ref_type == RefType.DYNAMIC
        expected_full_path = "cards/ソードアート・オンライン/CH朝田詩乃/朝田詩乃ステージSSNN0001_{__cards/姦キー__}{__cards/鬼キー__}"
        assert ref.full_path == expected_full_path
        assert len(ref.inner_refs) == 2

    def test_値行コメント内にカンマ区切り参照(self, tmp_path: Path):
        """実データ: 値行コメント内にカンマ区切り参照。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "key:\n"
            "  # - __ref1__,__ref2__,__ref3__\n",
        )

        result = parse_yaml_file(path)

        ve = result[0].values[0]
        assert ve.is_commented is True
        assert ve.raw_text == "__ref1__,__ref2__,__ref3__"
        assert len(ve.refs) == 3

    def test_クォート付き値(self, tmp_path: Path):
        """実データ: クォート付き値。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            'key:\n'
            '  - "00"\n'
            '  - "01"\n',
        )

        result = parse_yaml_file(path)

        assert result[0].values[0].raw_text == '"00"'
        # リテラルとしてクォートを含む
        assert '"00"' in result[0].values[0].literals

    def test_DP量指定子付き参照(self):
        """実データ: DP 量指定子付き参照。"""
        text = "{0-2$$__cards/options/ライティング__}"

        refs = extract_refs(text)

        assert len(refs) == 1
        assert refs[0].full_path == "cards/options/ライティング"

    def test_DP選択構文と参照の混在(self):
        """実データ: DP 選択構文と参照の混在。"""
        text = r"{,__cards/options/アングル_from系2__\|}"

        refs = extract_refs(text)

        assert len(refs) == 1
        assert refs[0].full_path == "cards/options/アングル_from系2"

    def test_短縮形参照_パスなし(self):
        """実データ: 短縮形参照（パスなし）。"""
        refs = extract_refs("__朝田詩乃SinonGGOFight脱00__")

        assert len(refs) == 1
        assert refs[0].full_path == "朝田詩乃SinonGGOFight脱00"
        assert refs[0].ref_type == RefType.NORMAL

    def test_セクション区切りコメント_スキップ(self, tmp_path: Path):
        """実データ: セクション区切りコメントはスキップされる。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "key:\n"
            "  - value_before\n"
            "  # ---- 白球少女 ----\n"
            "  - value_after\n",
        )

        result = parse_yaml_file(path)

        values = result[0].values
        assert len(values) == 2
        raw_texts = [v.raw_text for v in values]
        assert "value_before" in raw_texts
        assert "value_after" in raw_texts

    def test_セパレータ行_スキップ(self, tmp_path: Path):
        """実データ: セパレータ行はスキップされる。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "############################################################################################\n"
            "key:\n"
            "  - value\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert result[0].name == "key"

    def test_キー定義行末のコメント(self, tmp_path: Path):
        """実データ: キー定義行末のコメント。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "動き構図: # まあほどほどに使える\n"
            "  - value1\n",
        )

        result = parse_yaml_file(path)

        assert result[0].name == "動き構図"

    def test_ファイル先頭のコメント_スキップ(self, tmp_path: Path):
        """実データ: ファイル先頭のコメントはスキップ。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "#シーン／シーケンス定義\n"
            "key:\n"
            "  - value\n",
        )

        result = parse_yaml_file(path)

        assert len(result) == 1
        assert result[0].name == "key"

    def test_性格表現_DP構文の複雑な例(self):
        """実データ: 性格表現の複雑な DP 構文。"""
        text = '"{{,(expressionless:0.7)}|}{{,(slight_smile:0.7)|}|}"'

        refs = extract_refs(text)
        literals = extract_literals(text, refs)

        # DP 構文は参照ではない
        assert refs == []
        # リテラルとして保持される
        assert len(literals) == 1
