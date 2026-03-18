"""Unit tests for core/scanner.py — v2 スキャナのテスト。

設計意図ドキュメント (docs/design/s2-scanner-parser.md) に基づいて、
scan_yaml_files() のファイルシステム操作を検証する。

テスト対象:
  - scan_yaml_files(cards_dir: Path) -> list[Path]

テスト方針:
  - tmp_path を使ったファイルシステムテスト
  - 正常系: YAML ファイルの検出、.yaml と .yml 両方、サブディレクトリの再帰探索、ソート順
  - 異常系: 存在しないディレクトリ(FileNotFoundError)、ファイルパス指定(NotADirectoryError)
  - エッジケース: 空ディレクトリ、日本語ファイル名、非YAMLファイルの混在

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scanner import scan_yaml_files


# =========================================================================
# ヘルパー
# =========================================================================


def _write_file(path: Path, content: str = "key:\n  - value\n") -> Path:
    """テスト用ファイルを作成するヘルパー。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# =========================================================================
# 正常系
# =========================================================================


class TestScanYamlFiles正常系:
    """scan_yaml_files の正常系テスト。"""

    def test_scan_yaml_files_yaml拡張子のファイルを検出する(self, tmp_path: Path):
        """cards ディレクトリ内の .yaml ファイルを検出する。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "test.yaml")

        result = scan_yaml_files(cards_dir)

        assert len(result) == 1
        assert result[0].suffix == ".yaml"
        assert result[0].name == "test.yaml"

    def test_scan_yaml_files_yml拡張子のファイルも検出する(self, tmp_path: Path):
        """cards ディレクトリ内の .yml ファイルも検出する。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "test.yml")

        result = scan_yaml_files(cards_dir)

        assert len(result) == 1
        assert result[0].suffix == ".yml"

    def test_scan_yaml_files_yamlとyml両方を検出する(self, tmp_path: Path):
        """.yaml と .yml の両方の拡張子を収集する。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "file1.yaml")
        _write_file(cards_dir / "file2.yml")

        result = scan_yaml_files(cards_dir)

        assert len(result) == 2
        suffixes = {p.suffix for p in result}
        assert suffixes == {".yaml", ".yml"}

    def test_scan_yaml_files_サブディレクトリを再帰的に探索する(self, tmp_path: Path):
        """サブディレクトリ内の YAML ファイルも再帰的に検出する。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "root.yaml")
        _write_file(cards_dir / "sub1" / "child.yaml")
        _write_file(cards_dir / "sub1" / "sub2" / "grandchild.yaml")

        result = scan_yaml_files(cards_dir)

        assert len(result) == 3
        names = {p.name for p in result}
        assert names == {"root.yaml", "child.yaml", "grandchild.yaml"}

    def test_scan_yaml_files_深くネストされたディレクトリも探索する(self, tmp_path: Path):
        """深いネスト（4階層以上）のディレクトリも再帰的に探索する。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "a" / "b" / "c" / "d" / "deep.yaml")

        result = scan_yaml_files(cards_dir)

        assert len(result) == 1
        assert result[0].name == "deep.yaml"

    def test_scan_yaml_files_結果がソートされている(self, tmp_path: Path):
        """結果がパスのデフォルト順序でソートされている。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "c_file.yaml")
        _write_file(cards_dir / "a_file.yaml")
        _write_file(cards_dir / "b_file.yaml")

        result = scan_yaml_files(cards_dir)

        assert result == sorted(result)

    def test_scan_yaml_files_複数ディレクトリにまたがるソート(self, tmp_path: Path):
        """サブディレクトリを含む場合もソート順が保証される。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "z_dir" / "first.yaml")
        _write_file(cards_dir / "a_dir" / "second.yaml")
        _write_file(cards_dir / "root.yaml")

        result = scan_yaml_files(cards_dir)

        assert result == sorted(result)
        assert len(result) == 3

    def test_scan_yaml_files_戻り値がPathオブジェクトのリスト(self, tmp_path: Path):
        """戻り値が list[Path] であることを確認する。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "test.yaml")

        result = scan_yaml_files(cards_dir)

        assert isinstance(result, list)
        assert all(isinstance(p, Path) for p in result)

    def test_scan_yaml_files_YAMLファイルがない場合は空リスト(self, tmp_path: Path):
        """YAML ファイルが存在しない（非YAML ファイルのみ）場合は空リストを返す。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        _write_file(cards_dir / "readme.txt", "not yaml")
        _write_file(cards_dir / "data.json", "{}")

        result = scan_yaml_files(cards_dir)

        assert isinstance(result, list)
        assert len(result) == 0


# =========================================================================
# 異常系
# =========================================================================


class TestScanYamlFiles異常系:
    """scan_yaml_files の異常系テスト。"""

    def test_scan_yaml_files_存在しないディレクトリ_FileNotFoundError(self, tmp_path: Path):
        """存在しないディレクトリを指定すると FileNotFoundError を raise する。"""
        non_existent = tmp_path / "non_existent_dir"

        with pytest.raises(FileNotFoundError):
            scan_yaml_files(non_existent)

    def test_scan_yaml_files_ファイルパス指定_NotADirectoryError(self, tmp_path: Path):
        """ディレクトリではなくファイルパスを指定すると NotADirectoryError を raise する。"""
        file_path = _write_file(tmp_path / "not_a_dir.yaml")

        with pytest.raises(NotADirectoryError):
            scan_yaml_files(file_path)


# =========================================================================
# エッジケース
# =========================================================================


class TestScanYamlFilesエッジケース:
    """scan_yaml_files のエッジケーステスト。"""

    def test_scan_yaml_files_空ディレクトリ_空リスト(self, tmp_path: Path):
        """空のディレクトリでは空リストを返す。"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = scan_yaml_files(empty_dir)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_scan_yaml_files_日本語ファイル名を正常に検出する(self, tmp_path: Path):
        """日本語ファイル名の YAML ファイルを正常に検出する。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "朝田詩乃.yaml")
        _write_file(cards_dir / "シロコ.yml")

        result = scan_yaml_files(cards_dir)

        assert len(result) == 2
        names = {p.stem for p in result}
        assert "朝田詩乃" in names
        assert "シロコ" in names

    def test_scan_yaml_files_日本語ディレクトリ名を正常に処理する(self, tmp_path: Path):
        """日本語ディレクトリ名を含むパスを正常に処理する。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "ソードアート・オンライン" / "キャラ設定.yaml")

        result = scan_yaml_files(cards_dir)

        assert len(result) == 1
        assert "ソードアート・オンライン" in str(result[0])

    def test_scan_yaml_files_非YAMLファイルが混在していても除外する(self, tmp_path: Path):
        """非YAML ファイルが混在している場合、YAML ファイルのみを返す。"""
        cards_dir = tmp_path / "cards"
        _write_file(cards_dir / "valid.yaml")
        _write_file(cards_dir / "also_valid.yml")
        _write_file(cards_dir / "readme.txt", "text file")
        _write_file(cards_dir / "data.json", "{}")
        _write_file(cards_dir / "image.png", "binary")
        _write_file(cards_dir / "script.py", "print('hello')")

        result = scan_yaml_files(cards_dir)

        assert len(result) == 2
        assert all(p.suffix in (".yaml", ".yml") for p in result)

    def test_scan_yaml_files_空のサブディレクトリが混在しても問題ない(self, tmp_path: Path):
        """空のサブディレクトリがあっても正常に動作する。"""
        cards_dir = tmp_path / "cards"
        (cards_dir / "empty_sub").mkdir(parents=True)
        _write_file(cards_dir / "test.yaml")

        result = scan_yaml_files(cards_dir)

        assert len(result) == 1
        assert result[0].name == "test.yaml"
