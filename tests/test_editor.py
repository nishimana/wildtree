"""Unit tests for core/editor.py — S7 YAML エディタのテスト。

設計意図ドキュメント (docs/design/s7-yaml-editor.md) に基づいて、
行ベース YAML エディタの各関数を検証する。

テスト対象:
  - toggle_comment(file_path, value_entry, enable) -> EditResult
  - refresh_registry(file_path, registry) -> None
  - detect_line_ending(content) -> str
  - read_lines(file_path) -> tuple[list[str], str]
  - write_lines(file_path, lines, line_ending) -> None
  - _comment_line(line) -> str
  - _uncomment_line(line) -> str
  - _is_commented_line(line) -> bool

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.editor import (
    DEFAULT_LINE_ENDING,
    LINE_ENDING_CRLF,
    LINE_ENDING_LF,
    EditResult,
    _comment_line,
    _is_commented_line,
    _uncomment_line,
    detect_line_ending,
    read_lines,
    refresh_registry,
    toggle_comment,
    write_lines,
)
from core.models import KeyDefinition, KeyRegistry, ValueEntry


# =========================================================================
# ヘルパー
# =========================================================================


def _write_yaml(path: Path, content: str) -> Path:
    """テスト用 YAML ファイルを作成するヘルパー。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_yaml_binary(path: Path, content: bytes) -> Path:
    """テスト用 YAML ファイルをバイナリモードで作成するヘルパー。

    改行コードを明示的に制御するために使用する。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# =========================================================================
# detect_line_ending — 改行コード検出
# =========================================================================


class TestDetectLineEnding:
    """detect_line_ending の検出テスト。"""

    def test_detect_line_ending_CRLFを検出する(self):
        """CRLF を含むコンテンツから CRLF を検出する。"""
        content = "line1\r\nline2\r\nline3"
        result = detect_line_ending(content)
        assert result == LINE_ENDING_CRLF

    def test_detect_line_ending_LFを検出する(self):
        """LF を含むコンテンツから LF を検出する。"""
        content = "line1\nline2\nline3"
        result = detect_line_ending(content)
        assert result == LINE_ENDING_LF

    def test_detect_line_ending_空文字列_デフォルトを返す(self):
        """空文字列の場合はデフォルト改行コードを返す。"""
        result = detect_line_ending("")
        assert result == DEFAULT_LINE_ENDING

    def test_detect_line_ending_改行なし1行_デフォルトを返す(self):
        """改行を含まない1行テキストの場合はデフォルト改行コードを返す。"""
        result = detect_line_ending("single line without newline")
        assert result == DEFAULT_LINE_ENDING

    def test_detect_line_ending_CRLFとLF混在_最初の改行で判定(self):
        """CRLF と LF が混在する場合、最初に出現する改行コードで判定する。"""
        content = "line1\r\nline2\nline3"
        result = detect_line_ending(content)
        assert result == LINE_ENDING_CRLF

    def test_detect_line_ending_LFが先に出現_LFを返す(self):
        """LF が先に出現する場合は LF を返す。"""
        content = "line1\nline2\r\nline3"
        result = detect_line_ending(content)
        assert result == LINE_ENDING_LF


# =========================================================================
# read_lines — ファイル読み込み
# =========================================================================


class TestReadLines:
    """read_lines のテスト。"""

    def test_read_lines_LFファイルを読み込む(self, tmp_path: Path):
        """LF ファイルを行リストと改行コードのタプルとして読み込む。"""
        path = _write_yaml_binary(
            tmp_path / "lf.yaml",
            b"key:\n  - value1\n  - value2\n",
        )

        lines, line_ending = read_lines(path)

        assert line_ending == LINE_ENDING_LF
        assert lines == ["key:", "  - value1", "  - value2", ""]

    def test_read_lines_CRLFファイルを読み込む(self, tmp_path: Path):
        """CRLF ファイルを行リストと改行コードのタプルとして読み込む。"""
        path = _write_yaml_binary(
            tmp_path / "crlf.yaml",
            b"key:\r\n  - value1\r\n  - value2\r\n",
        )

        lines, line_ending = read_lines(path)

        assert line_ending == LINE_ENDING_CRLF
        assert lines == ["key:", "  - value1", "  - value2", ""]

    def test_read_lines_末尾改行なしのファイル(self, tmp_path: Path):
        """末尾に改行がないファイルも正しく読み込む。"""
        path = _write_yaml_binary(
            tmp_path / "no_trailing.yaml",
            b"key:\n  - value1",
        )

        lines, line_ending = read_lines(path)

        assert line_ending == LINE_ENDING_LF
        assert lines == ["key:", "  - value1"]

    def test_read_lines_空ファイル(self, tmp_path: Path):
        """空ファイルも正しく読み込む。"""
        path = _write_yaml_binary(tmp_path / "empty.yaml", b"")

        lines, line_ending = read_lines(path)

        assert line_ending == DEFAULT_LINE_ENDING
        # 空ファイルの場合、splitlines() は空リストを返す
        assert lines == [] or lines == [""]

    def test_read_lines_ファイル不存在_FileNotFoundError(self, tmp_path: Path):
        """存在しないファイルの場合 FileNotFoundError を送出する。"""
        non_existent = tmp_path / "non_existent.yaml"

        with pytest.raises(FileNotFoundError):
            read_lines(non_existent)

    def test_read_lines_日本語コンテンツ(self, tmp_path: Path):
        """日本語を含むファイルを正しく読み込む。"""
        content = "朝田詩乃:\n  - slender body\n  - __朝田詩乃体格__\n"
        path = _write_yaml_binary(
            tmp_path / "japanese.yaml", content.encode("utf-8")
        )

        lines, line_ending = read_lines(path)

        assert line_ending == LINE_ENDING_LF
        assert "朝田詩乃:" in lines


# =========================================================================
# write_lines — ファイル書き込み
# =========================================================================


class TestWriteLines:
    """write_lines のテスト。"""

    def test_write_lines_LFで書き込む(self, tmp_path: Path):
        """LF 改行コードで行リストをファイルに書き込む。"""
        path = tmp_path / "output.yaml"
        lines = ["key:", "  - value1", "  - value2", ""]

        write_lines(path, lines, LINE_ENDING_LF)

        raw = path.read_bytes()
        assert raw == b"key:\n  - value1\n  - value2\n"

    def test_write_lines_CRLFで書き込む(self, tmp_path: Path):
        """CRLF 改行コードで行リストをファイルに書き込む。"""
        path = tmp_path / "output.yaml"
        lines = ["key:", "  - value1", "  - value2", ""]

        write_lines(path, lines, LINE_ENDING_CRLF)

        raw = path.read_bytes()
        assert raw == b"key:\r\n  - value1\r\n  - value2\r\n"

    def test_write_lines_末尾改行なし(self, tmp_path: Path):
        """末尾に空行がない場合、改行なしで書き込む。"""
        path = tmp_path / "output.yaml"
        lines = ["key:", "  - value1"]

        write_lines(path, lines, LINE_ENDING_LF)

        raw = path.read_bytes()
        assert raw == b"key:\n  - value1"

    def test_write_lines_read_linesとの往復一致_LF(self, tmp_path: Path):
        """read_lines で読み込んだデータを write_lines で書き戻すと元と一致する（LF）。"""
        original = b"key:\n  - value1\n  - value2\n"
        path = _write_yaml_binary(tmp_path / "round_trip.yaml", original)

        lines, line_ending = read_lines(path)
        write_lines(path, lines, line_ending)

        assert path.read_bytes() == original

    def test_write_lines_read_linesとの往復一致_CRLF(self, tmp_path: Path):
        """read_lines で読み込んだデータを write_lines で書き戻すと元と一致する（CRLF）。"""
        original = b"key:\r\n  - value1\r\n  - value2\r\n"
        path = _write_yaml_binary(tmp_path / "round_trip.yaml", original)

        lines, line_ending = read_lines(path)
        write_lines(path, lines, line_ending)

        assert path.read_bytes() == original

    def test_write_lines_read_linesとの往復一致_末尾改行なし(self, tmp_path: Path):
        """末尾改行なしのファイルも往復で保持される。"""
        original = b"key:\n  - value1"
        path = _write_yaml_binary(tmp_path / "round_trip.yaml", original)

        lines, line_ending = read_lines(path)
        write_lines(path, lines, line_ending)

        assert path.read_bytes() == original


# =========================================================================
# _is_commented_line — コメント行判定
# =========================================================================


class TestIsCommentedLine:
    """_is_commented_line のテスト。"""

    def test_is_commented_line_コメント行を検出する(self):
        """'# - value' パターンをコメント行と判定する。"""
        assert _is_commented_line("  # - __ref__") is True

    def test_is_commented_line_ダブルハッシュもコメント行(self):
        """'## - value' パターンもコメント行と判定する。"""
        assert _is_commented_line("  ## - __ref__") is True

    def test_is_commented_line_トリプルハッシュもコメント行(self):
        """'### - value' パターンもコメント行と判定する。"""
        assert _is_commented_line("  ### - __ref__") is True

    def test_is_commented_line_通常の値行はコメント行ではない(self):
        """'- value' パターンはコメント行ではないと判定する。"""
        assert _is_commented_line("  - __ref__") is False

    def test_is_commented_line_セクション区切りはコメント行ではない(self):
        """'# ---- 区切り ----' パターンはコメント行ではないと判定する。"""
        assert _is_commented_line("  # ---- セクション区切り ----") is False

    def test_is_commented_line_キー定義行はコメント行ではない(self):
        """'key:' パターンはコメント行ではないと判定する。"""
        assert _is_commented_line("key:") is False

    def test_is_commented_line_空行はコメント行ではない(self):
        """空行はコメント行ではないと判定する。"""
        assert _is_commented_line("") is False
        assert _is_commented_line("   ") is False

    def test_is_commented_line_リテラル値のコメント(self):
        """リテラル値のコメントもコメント行と判定する。"""
        assert _is_commented_line("  # - literal_value") is True

    def test_is_commented_line_タブインデントのコメント行(self):
        """タブインデントのコメント行もコメント行と判定する。"""
        assert _is_commented_line("\t# - __ref__") is True


# =========================================================================
# _comment_line — コメント化
# =========================================================================


class TestCommentLine:
    """_comment_line のテスト。"""

    def test_comment_line_値行をコメント化する(self):
        """'  - __ref__' → '  # - __ref__' に変換する。"""
        result = _comment_line("  - __ref__")
        assert result == "  # - __ref__"

    def test_comment_line_リテラル値をコメント化する(self):
        """'  - literal_value' → '  # - literal_value' に変換する。"""
        result = _comment_line("  - literal_value")
        assert result == "  # - literal_value"

    def test_comment_line_4スペースインデントを保持する(self):
        """4スペースインデントでもインデントを保持する。"""
        result = _comment_line("    - value")
        assert result == "    # - value"

    def test_comment_line_タブインデントを保持する(self):
        """タブインデントでもインデントを保持する。"""
        result = _comment_line("\t- __ref__")
        assert result == "\t# - __ref__"

    def test_comment_line_インデントなし(self):
        """インデントなしの値行もコメント化する。"""
        result = _comment_line("- value")
        assert result == "# - value"

    def test_comment_line_値行パターンに一致しない場合はそのまま(self):
        """値行パターンに一致しない行はそのまま返す。"""
        result = _comment_line("key:")
        assert result == "key:"

    def test_comment_line_複合的な値(self):
        """参照とリテラルを含む複合的な値行もコメント化する。"""
        result = _comment_line("  - dynamic_angle,__cards/シネマシャドウ__")
        assert result == "  # - dynamic_angle,__cards/シネマシャドウ__"


# =========================================================================
# _uncomment_line — コメント解除
# =========================================================================


class TestUncommentLine:
    """_uncomment_line のテスト。"""

    def test_uncomment_line_コメントを解除する(self):
        """'  # - __ref__' → '  - __ref__' に変換する。"""
        result = _uncomment_line("  # - __ref__")
        assert result == "  - __ref__"

    def test_uncomment_line_ダブルハッシュを解除する(self):
        """'  ## - __ref__' → '  - __ref__' に変換する。"""
        result = _uncomment_line("  ## - __ref__")
        assert result == "  - __ref__"

    def test_uncomment_line_トリプルハッシュを解除する(self):
        """'  ### - __ref__' → '  - __ref__' に変換する。"""
        result = _uncomment_line("  ### - __ref__")
        assert result == "  - __ref__"

    def test_uncomment_line_リテラル値のコメント解除(self):
        """'  # - literal_value' → '  - literal_value' に変換する。"""
        result = _uncomment_line("  # - literal_value")
        assert result == "  - literal_value"

    def test_uncomment_line_4スペースインデントを保持する(self):
        """4スペースインデントでもインデントを保持する。"""
        result = _uncomment_line("    # - value")
        assert result == "    - value"

    def test_uncomment_line_タブインデントを保持する(self):
        """タブインデントでもインデントを保持する。"""
        result = _uncomment_line("\t# - __ref__")
        assert result == "\t- __ref__"

    def test_uncomment_line_コメントパターンに一致しない場合はそのまま(self):
        """コメントパターンに一致しない行はそのまま返す。"""
        result = _uncomment_line("  - value")
        assert result == "  - value"

    def test_uncomment_line_セクション区切りはそのまま(self):
        """セクション区切りコメントはコメント解除対象外でそのまま返す。"""
        line = "  # ---- セクション区切り ----"
        result = _uncomment_line(line)
        assert result == line


# =========================================================================
# toggle_comment — 正常系
# =========================================================================


class TestToggleComment正常系:
    """toggle_comment の正常系テスト。"""

    def test_toggle_comment_コメント解除_参照行(self, tmp_path: Path):
        """コメント化された参照行を有効化する。
        enable=True, is_commented=True → コメント解除。
        """
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n  # - __ref__\n",
        )
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=True)

        result = toggle_comment(path, ve, enable=True)

        assert result.success is True
        assert result.error is None
        content = path.read_text(encoding="utf-8")
        assert "  - __ref__" in content
        assert "# - __ref__" not in content

    def test_toggle_comment_コメント化_参照行(self, tmp_path: Path):
        """通常の参照行をコメント化する。
        enable=False, is_commented=False → コメント化。
        """
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n  - __ref__\n",
        )
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is True
        assert result.error is None
        content = path.read_text(encoding="utf-8")
        assert "  # - __ref__" in content

    def test_toggle_comment_ダブルハッシュのコメント解除(self, tmp_path: Path):
        """ダブルハッシュコメントのコメント解除。
        '## - __ref__' → '- __ref__'
        """
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n  ## - __ref__\n",
        )
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=True)

        result = toggle_comment(path, ve, enable=True)

        assert result.success is True
        content = path.read_text(encoding="utf-8")
        assert "  - __ref__" in content
        assert "#" not in content.split("\n")[1]

    def test_toggle_comment_リテラル値のコメント化(self, tmp_path: Path):
        """リテラル値行のコメント化。"""
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n  - literal_value\n",
        )
        ve = ValueEntry(raw_text="literal_value", line_number=2, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is True
        content = path.read_text(encoding="utf-8")
        assert "  # - literal_value" in content

    def test_toggle_comment_冪等_既にコメント化済みでenableFalse(self, tmp_path: Path):
        """既にコメント化済みの行に enable=False → 何もしない（冪等）。"""
        original = b"key:\n  # - __ref__\n"
        path = _write_yaml_binary(tmp_path / "test.yaml", original)
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=True)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is True
        assert path.read_bytes() == original

    def test_toggle_comment_冪等_既にコメント解除済みでenableTrue(self, tmp_path: Path):
        """既にコメント解除済みの行に enable=True → 何もしない（冪等）。"""
        original = b"key:\n  - __ref__\n"
        path = _write_yaml_binary(tmp_path / "test.yaml", original)
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=False)

        result = toggle_comment(path, ve, enable=True)

        assert result.success is True
        assert path.read_bytes() == original

    def test_toggle_comment_インデント保持_スペース4個(self, tmp_path: Path):
        """スペース4個のインデントが保持される。"""
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n    - __ref__\n",
        )
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is True
        content = path.read_text(encoding="utf-8")
        assert "    # - __ref__" in content

    def test_toggle_comment_インデント保持_タブ(self, tmp_path: Path):
        """タブインデントが保持される。"""
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n\t- __ref__\n",
        )
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is True
        content = path.read_text(encoding="utf-8")
        assert "\t# - __ref__" in content

    def test_toggle_comment_複数値行の中間行を切り替え(self, tmp_path: Path):
        """複数の値行がある中間行だけを切り替えた場合、他の行に影響しない。"""
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n  - value1\n  - value2\n  - value3\n",
        )
        ve = ValueEntry(raw_text="value2", line_number=3, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is True
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[1] == "  - value1"
        assert lines[2] == "  # - value2"
        assert lines[3] == "  - value3"


# =========================================================================
# toggle_comment — 改行コード保持
# =========================================================================


class TestToggleComment改行コード保持:
    """toggle_comment の改行コード保持テスト。"""

    def test_toggle_comment_CRLFファイルの保持(self, tmp_path: Path):
        """CRLF ファイルでコメント切り替え後も CRLF が保持される。"""
        original = b"key:\r\n  - __ref__\r\n"
        path = _write_yaml_binary(tmp_path / "crlf.yaml", original)
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is True
        raw = path.read_bytes()
        # CRLF が保持されている
        assert b"\r\n" in raw
        # LF 単体は含まれない（CRLF 内の LF は OK）
        stripped = raw.replace(b"\r\n", b"")
        assert b"\n" not in stripped

    def test_toggle_comment_LFファイルの保持(self, tmp_path: Path):
        """LF ファイルでコメント切り替え後も LF が保持される。"""
        path = _write_yaml_binary(
            tmp_path / "lf.yaml",
            b"key:\n  - __ref__\n",
        )
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is True
        raw = path.read_bytes()
        assert b"\r\n" not in raw
        assert b"\n" in raw

    def test_toggle_comment_末尾改行有りの保持(self, tmp_path: Path):
        """ファイル末尾の改行が保持される。"""
        original = b"key:\n  - __ref__\n"
        path = _write_yaml_binary(tmp_path / "trailing.yaml", original)
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is True
        raw = path.read_bytes()
        assert raw.endswith(b"\n")

    def test_toggle_comment_末尾改行無しの保持(self, tmp_path: Path):
        """ファイル末尾に改行がない場合、改行なしのまま保持される。"""
        original = b"key:\n  - __ref__"
        path = _write_yaml_binary(tmp_path / "no_trailing.yaml", original)
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is True
        raw = path.read_bytes()
        assert not raw.endswith(b"\n")

    def test_toggle_comment_CRLFファイルでコメント解除(self, tmp_path: Path):
        """CRLF ファイルでのコメント解除でも CRLF が保持される。"""
        original = b"key:\r\n  # - __ref__\r\n"
        path = _write_yaml_binary(tmp_path / "crlf_uncomment.yaml", original)
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=True)

        result = toggle_comment(path, ve, enable=True)

        assert result.success is True
        raw = path.read_bytes()
        assert b"\r\n" in raw
        content = raw.decode("utf-8")
        assert "  - __ref__" in content


# =========================================================================
# toggle_comment — 異常系
# =========================================================================


class TestToggleComment異常系:
    """toggle_comment の異常系テスト。"""

    def test_toggle_comment_ファイル不存在_失敗(self, tmp_path: Path):
        """存在しないファイルの場合 EditResult(success=False) を返す。"""
        non_existent = tmp_path / "non_existent.yaml"
        ve = ValueEntry(raw_text="__ref__", line_number=1, is_commented=False)

        result = toggle_comment(non_existent, ve, enable=False)

        assert result.success is False
        assert result.error is not None
        assert str(non_existent) in result.error or "ファイル" in result.error

    def test_toggle_comment_行番号が範囲外_大きすぎる(self, tmp_path: Path):
        """行番号がファイルの行数を超える場合 EditResult(success=False) を返す。"""
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n  - value\n",
        )
        ve = ValueEntry(raw_text="value", line_number=100, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is False
        assert result.error is not None
        assert "範囲外" in result.error or "行番号" in result.error

    def test_toggle_comment_行番号が0以下(self, tmp_path: Path):
        """行番号が0以下の場合 EditResult(success=False) を返す。"""
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n  - value\n",
        )
        ve = ValueEntry(raw_text="value", line_number=0, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is False
        assert result.error is not None

    def test_toggle_comment_非値行_キー定義行(self, tmp_path: Path):
        """キー定義行（値行ではない行）の場合 EditResult(success=False) を返す。"""
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n  - value\n",
        )
        # line_number=1 はキー定義行 "key:"
        ve = ValueEntry(raw_text="key", line_number=1, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is False
        assert result.error is not None
        assert "値行" in result.error or "対象行" in result.error

    def test_toggle_comment_空ファイル(self, tmp_path: Path):
        """空ファイルに対して行番号指定 → EditResult(success=False)。"""
        path = _write_yaml_binary(tmp_path / "empty.yaml", b"")
        ve = ValueEntry(raw_text="value", line_number=1, is_commented=False)

        result = toggle_comment(path, ve, enable=False)

        assert result.success is False
        assert result.error is not None

    def test_toggle_comment_例外を投げない(self, tmp_path: Path):
        """toggle_comment はいかなる場合も例外を投げず EditResult で返す。"""
        non_existent = tmp_path / "non_existent.yaml"
        ve = ValueEntry(raw_text="value", line_number=1, is_commented=False)

        # 例外は発生しないことを確認
        result = toggle_comment(non_existent, ve, enable=False)
        assert isinstance(result, EditResult)
        assert result.success is False


# =========================================================================
# toggle_comment — 連続操作
# =========================================================================


class TestToggleComment連続操作:
    """toggle_comment の連続操作テスト。"""

    def test_toggle_comment_コメント化してからコメント解除_元に戻る(self, tmp_path: Path):
        """コメント化 → コメント解除で元の状態に戻る。"""
        original = b"key:\n  - __ref__\n"
        path = _write_yaml_binary(tmp_path / "test.yaml", original)
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=False)

        # コメント化
        result1 = toggle_comment(path, ve, enable=False)
        assert result1.success is True

        # 状態を更新して再度呼び出し
        ve_commented = ValueEntry(raw_text="__ref__", line_number=2, is_commented=True)
        result2 = toggle_comment(path, ve_commented, enable=True)
        assert result2.success is True

        # 元の内容に戻っている
        assert path.read_bytes() == original

    def test_toggle_comment_同じenableを2回呼ぶ_冪等(self, tmp_path: Path):
        """同じ enable 値で2回呼んでも結果は同じ（冪等）。"""
        path = _write_yaml_binary(
            tmp_path / "test.yaml",
            b"key:\n  - __ref__\n",
        )
        ve = ValueEntry(raw_text="__ref__", line_number=2, is_commented=False)

        result1 = toggle_comment(path, ve, enable=False)
        after_first = path.read_bytes()

        result2 = toggle_comment(path, ve, enable=False)
        after_second = path.read_bytes()

        assert result1.success is True
        assert result2.success is True
        assert after_first == after_second


# =========================================================================
# refresh_registry — レジストリ更新
# =========================================================================


class TestRefreshRegistry:
    """refresh_registry のテスト。"""

    def test_refresh_registry_ファイル再パースでレジストリ更新(self, tmp_path: Path):
        """ファイルを再パースしてレジストリが更新される。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "key1:\n"
            "  - value1\n"
            "  - value2\n",
        )

        # 初期レジストリを構築
        from core.parser import parse_yaml_file
        initial_keys = parse_yaml_file(path)
        registry: KeyRegistry = {}
        for kd in initial_keys:
            registry.setdefault(kd.name, []).append(kd)

        assert "key1" in registry
        assert len(registry["key1"][0].values) == 2

        # ファイルを書き換え（値行を追加）
        _write_yaml(
            path,
            "key1:\n"
            "  - value1\n"
            "  - value2\n"
            "  - value3\n",
        )

        # レジストリを更新
        refresh_registry(path, registry)

        # 更新されている
        assert "key1" in registry
        assert len(registry["key1"][0].values) == 3

    def test_refresh_registry_コメント切り替え後のis_commented更新(self, tmp_path: Path):
        """コメント切り替え後に is_commented フラグが更新される。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "key1:\n"
            "  - __ref__\n"
            "  # - __commented_ref__\n",
        )

        from core.parser import parse_yaml_file
        initial_keys = parse_yaml_file(path)
        registry: KeyRegistry = {}
        for kd in initial_keys:
            registry.setdefault(kd.name, []).append(kd)

        # 初期状態の確認
        values = registry["key1"][0].values
        assert values[0].is_commented is False  # - __ref__
        assert values[1].is_commented is True   # # - __commented_ref__

        # ファイルを書き換え（コメント解除）
        _write_yaml(
            path,
            "key1:\n"
            "  - __ref__\n"
            "  - __commented_ref__\n",
        )

        refresh_registry(path, registry)

        # is_commented が更新されている
        values = registry["key1"][0].values
        assert values[0].is_commented is False
        assert values[1].is_commented is False

    def test_refresh_registry_他のファイルのキーに影響しない(self, tmp_path: Path):
        """あるファイルの更新が他のファイルのキー定義に影響しない。"""
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

        from core.parser import parse_yaml_file
        registry: KeyRegistry = {}
        for kd in parse_yaml_file(path_a):
            registry.setdefault(kd.name, []).append(kd)
        for kd in parse_yaml_file(path_b):
            registry.setdefault(kd.name, []).append(kd)

        # path_a のみ書き換え
        _write_yaml(
            path_a,
            "key_a:\n"
            "  - value_a_modified\n",
        )

        refresh_registry(path_a, registry)

        # key_a は更新されている
        assert registry["key_a"][0].values[0].raw_text == "value_a_modified"
        # key_b は変更なし
        assert registry["key_b"][0].values[0].raw_text == "value_b"

    def test_refresh_registry_ファイル削除後はキーが除去される(self, tmp_path: Path):
        """ファイルが削除された場合、レジストリからそのファイルのキーが除去される。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "key1:\n"
            "  - value1\n",
        )

        from core.parser import parse_yaml_file
        registry: KeyRegistry = {}
        for kd in parse_yaml_file(path):
            registry.setdefault(kd.name, []).append(kd)

        assert "key1" in registry

        # ファイルを削除
        path.unlink()

        refresh_registry(path, registry)

        # key1 がレジストリから除去されている
        assert "key1" not in registry

    def test_refresh_registry_同名キーの他ファイル分は残る(self, tmp_path: Path):
        """同名キーが複数ファイルにある場合、更新対象ファイルの分だけ差し替わる。"""
        path_a = _write_yaml(
            tmp_path / "a.yaml",
            "shared_key:\n"
            "  - from_a\n",
        )
        path_b = _write_yaml(
            tmp_path / "b.yaml",
            "shared_key:\n"
            "  - from_b\n",
        )

        from core.parser import parse_yaml_file
        registry: KeyRegistry = {}
        for kd in parse_yaml_file(path_a):
            registry.setdefault(kd.name, []).append(kd)
        for kd in parse_yaml_file(path_b):
            registry.setdefault(kd.name, []).append(kd)

        assert len(registry["shared_key"]) == 2

        # path_a のみ更新
        _write_yaml(
            path_a,
            "shared_key:\n"
            "  - from_a_modified\n",
        )

        refresh_registry(path_a, registry)

        # 2つのキー定義が残っている
        assert len(registry["shared_key"]) == 2
        raw_texts = [
            kd.values[0].raw_text for kd in registry["shared_key"]
        ]
        assert "from_a_modified" in raw_texts
        assert "from_b" in raw_texts

    def test_refresh_registry_例外を投げない(self, tmp_path: Path):
        """refresh_registry は例外を投げない。"""
        non_existent = tmp_path / "non_existent.yaml"
        registry: KeyRegistry = {}

        # 例外は発生しない
        refresh_registry(non_existent, registry)

    def test_refresh_registry_空レジストリの更新(self, tmp_path: Path):
        """空のレジストリに対する更新も正常に動作する。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "new_key:\n"
            "  - new_value\n",
        )
        registry: KeyRegistry = {}

        refresh_registry(path, registry)

        assert "new_key" in registry
        assert registry["new_key"][0].values[0].raw_text == "new_value"


# =========================================================================
# toggle_comment + refresh_registry — 統合テスト
# =========================================================================


class TestToggleCommentとRefreshRegistryの統合:
    """toggle_comment と refresh_registry を組み合わせた統合テスト。"""

    def test_コメント化してレジストリ更新(self, tmp_path: Path):
        """値行をコメント化し、レジストリを更新すると is_commented が変わる。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "key1:\n"
            "  - __ref1__\n"
            "  - __ref2__\n",
        )

        from core.parser import parse_yaml_file
        registry: KeyRegistry = {}
        for kd in parse_yaml_file(path):
            registry.setdefault(kd.name, []).append(kd)

        # 初期状態: 両方 is_commented=False
        assert all(v.is_commented is False for v in registry["key1"][0].values)

        # ref2 をコメント化
        ve = registry["key1"][0].values[1]  # line_number=3, __ref2__
        result = toggle_comment(path, ve, enable=False)
        assert result.success is True

        # レジストリ更新
        refresh_registry(path, registry)

        # ref2 が is_commented=True に変わっている
        values = registry["key1"][0].values
        assert values[0].is_commented is False  # __ref1__ は変更なし
        assert values[1].is_commented is True   # __ref2__ がコメント化

    def test_コメント解除してレジストリ更新(self, tmp_path: Path):
        """コメント化された値行を解除し、レジストリを更新する。"""
        path = _write_yaml(
            tmp_path / "test.yaml",
            "key1:\n"
            "  - __ref1__\n"
            "  # - __ref2__\n",
        )

        from core.parser import parse_yaml_file
        registry: KeyRegistry = {}
        for kd in parse_yaml_file(path):
            registry.setdefault(kd.name, []).append(kd)

        # 初期状態
        assert registry["key1"][0].values[1].is_commented is True

        # ref2 のコメント解除
        ve = registry["key1"][0].values[1]
        result = toggle_comment(path, ve, enable=True)
        assert result.success is True

        # レジストリ更新
        refresh_registry(path, registry)

        # ref2 が is_commented=False に変わっている
        values = registry["key1"][0].values
        assert values[1].is_commented is False


# =========================================================================
# EditResult データクラス
# =========================================================================


class TestEditResult:
    """EditResult データクラスのテスト。"""

    def test_edit_result_成功(self):
        """成功時の EditResult。"""
        result = EditResult(success=True)
        assert result.success is True
        assert result.error is None

    def test_edit_result_失敗(self):
        """失敗時の EditResult。"""
        result = EditResult(success=False, error="エラーメッセージ")
        assert result.success is False
        assert result.error == "エラーメッセージ"

    def test_edit_result_デフォルトerrorはNone(self):
        """error のデフォルト値は None。"""
        result = EditResult(success=True)
        assert result.error is None


# =========================================================================
# 定数
# =========================================================================


class TestConstants:
    """定数値のテスト。"""

    def test_LINE_ENDING_CRLF(self):
        assert LINE_ENDING_CRLF == "\r\n"

    def test_LINE_ENDING_LF(self):
        assert LINE_ENDING_LF == "\n"

    def test_DEFAULT_LINE_ENDING(self):
        assert DEFAULT_LINE_ENDING == "\n"
