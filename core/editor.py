"""YAML エディタ — 行ベースでワイルドカード YAML ファイルを編集する。

S7 — コメント切り替え（値行の有効化/無効化）を行うコアモジュール。
S8（GUI 編集機能）のバックエンドとして機能する。

責務:
  - 値行のコメント状態の切り替え（# プレフィックスの付与/除去）
  - ファイルの改行コード検出と保持
  - 行リストの読み書き
  - 変更されたファイルのレジストリ更新

設計方針:
  - PyYAML を使わず、行単位で操作する（S2 パーサーと同じ方針）
  - 最小限の行書き換えでフォーマットを崩さない
  - 改行コード（CRLF/LF）を保持する
  - 例外を投げない（EditResult で結果を返す）
  - 冪等操作: 同じ enable 値での連続呼び出しは安全

データフロー:
  S8 (GUI)
    → toggle_comment(file_path, value_entry, enable)
      → read_lines(file_path) → 行の書き換え → write_lines(file_path, ...)
      → EditResult
    → refresh_registry(file_path, registry)
      → parser.parse_yaml_file(file_path) → レジストリ差し替え
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.models import KeyRegistry, ValueEntry

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

LINE_ENDING_CRLF: str = "\r\n"
"""Windows 改行コード。"""

LINE_ENDING_LF: str = "\n"
"""Unix 改行コード。"""

DEFAULT_LINE_ENDING: str = "\n"
"""改行コードが検出できない場合のデフォルト。

ファイル内に改行が存在しない場合（1行ファイルや空ファイル）に使用する。
"""

# コメント化用の正規表現: インデント + 値行パターン
_COMMENT_PATTERN = re.compile(r"^(\s*)(- .*)$")
"""値行をコメント化する際のマッチパターン。

グループ1: インデント部分（スペース/タブ）
グループ2: 値行本体（"- " で始まる部分）
"""

# コメント解除用の正規表現: インデント + ハッシュ + 値行パターン
_UNCOMMENT_PATTERN = re.compile(r"^(\s*)#+\s*(- .*)$")
"""コメント行を解除する際のマッチパターン。

グループ1: インデント部分（スペース/タブ）
グループ2: 値行本体（"- " で始まる部分。"# " プレフィックス除去後）
複数の "#"（"##"、"###" 等）にも対応する。
"""


# ---------------------------------------------------------------------------
# 編集結果データ
# ---------------------------------------------------------------------------


@dataclass
class EditResult:
    """編集操作の結果。

    toggle_comment() が返す構造化データ。
    成功時は success=True、失敗時は success=False と error メッセージ。

    Attributes:
        success: 操作が成功したかどうか。
        error: エラーメッセージ。success=True の場合は None。
    """

    success: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# 改行コード検出
# ---------------------------------------------------------------------------


def detect_line_ending(content: str) -> str:
    """ファイル内容から改行コードを検出する。

    最初に出現する改行文字を調べ、CRLF か LF かを判定する。
    改行文字が存在しない場合（1行ファイル、空ファイル）は
    DEFAULT_LINE_ENDING を返す。

    Args:
        content: ファイルの内容（バイナリモードではなくテキスト）。

    Returns:
        検出された改行コード。LINE_ENDING_CRLF または LINE_ENDING_LF。
        改行が見つからない場合は DEFAULT_LINE_ENDING。
    """
    # 最初の \n の位置を探す
    lf_pos = content.find("\n")
    if lf_pos < 0:
        # 改行文字が存在しない
        return DEFAULT_LINE_ENDING

    # \n の直前が \r なら CRLF
    if lf_pos > 0 and content[lf_pos - 1] == "\r":
        return LINE_ENDING_CRLF

    return LINE_ENDING_LF


# ---------------------------------------------------------------------------
# ファイル読み書き
# ---------------------------------------------------------------------------


def read_lines(file_path: Path) -> tuple[list[str], str]:
    """ファイルを行リストと改行コードのタプルとして読み込む。

    ファイルを UTF-8 でバイナリモードで読み込み、改行コードを検出した後、
    splitlines() で行リストに分割する。

    Args:
        file_path: 読み込み対象のファイルパス。

    Returns:
        (行リスト, 改行コード) のタプル。
        行リストの各要素は改行文字を含まない。

    Raises:
        FileNotFoundError: ファイルが存在しない場合。
        UnicodeDecodeError: UTF-8 で読めない場合。
        OSError: その他の I/O エラー。

    Note:
        改行コードの検出は detect_line_ending() に委譲する。
        splitlines() で分割するため、各行には改行文字が含まれない。
    """
    # バイナリモードで読み込み、改行コードの自動変換を防ぐ
    raw = file_path.read_bytes()
    content = raw.decode("utf-8")

    # 改行コードを検出
    line_ending = detect_line_ending(content)

    # 行リストに分割
    # splitlines() は末尾の改行を無視するため、
    # 末尾改行がある場合は空文字列を追加して保持する
    if content == "":
        lines: list[str] = []
    else:
        lines = content.splitlines()
        # 末尾が改行で終わっている場合、空文字列を追加
        if content.endswith("\n") or content.endswith("\r"):
            lines.append("")

    return lines, line_ending


def write_lines(file_path: Path, lines: list[str], line_ending: str) -> None:
    """行リストをファイルに書き戻す。

    改行コードで join し、ファイルの末尾改行状態を保持する。
    バイナリモードで書き込み、改行コードの自動変換を防ぐ。

    Args:
        file_path: 書き込み対象のファイルパス。
        lines: 書き込む行のリスト。各要素は改行文字を含まない。
        line_ending: 使用する改行コード。
            detect_line_ending() で検出した値をそのまま渡す。

    Raises:
        OSError: 書き込み権限なし等の I/O エラー。

    Note:
        元のファイルの末尾改行状態は read_lines 側で最後の要素として
        保持される設計。write_lines は渡された lines をそのまま書き戻す。
    """
    # 行リストを改行コードで結合
    content = line_ending.join(lines)
    # バイナリモードで書き込み、改行コードの自動変換を防ぐ
    file_path.write_bytes(content.encode("utf-8"))


# ---------------------------------------------------------------------------
# 行変換
# ---------------------------------------------------------------------------


def _is_commented_line(line: str) -> bool:
    """行がコメント行かどうかを判定する。

    パーサーと同じ判定ロジック: strip() が "#" で始まり、
    lstrip("#").strip() が "- " で始まる場合にコメント行と判定する。

    Args:
        line: 判定対象の行テキスト（改行なし）。

    Returns:
        コメント行の場合 True。
    """
    stripped = line.strip()
    if not stripped.startswith("#"):
        return False
    # "#" を除去した後、空白を除去して "- " で始まるか確認
    after_hash = stripped.lstrip("#").strip()
    return after_hash.startswith("- ")


def _comment_line(line: str) -> str:
    """値行をコメント化する（# プレフィックスの付与）。

    インデントを保持し、インデント直後に "# " を挿入する。

    変換例:
        "  - __ref__"     → "  # - __ref__"
        "    - value"     → "    # - value"
        "\\t- __ref__"    → "\\t# - __ref__"

    Args:
        line: コメント化する値行テキスト（改行なし）。

    Returns:
        コメント化された行テキスト。
        行が値行パターンに一致しない場合はそのまま返す。
    """
    match = _COMMENT_PATTERN.match(line)
    if not match:
        return line
    indent = match.group(1)
    body = match.group(2)
    return f"{indent}# {body}"


def _uncomment_line(line: str) -> str:
    """値行のコメントを解除する（# プレフィックスの除去）。

    インデントを保持し、"# "（複数 "#" を含む）を除去する。

    変換例:
        "  # - __ref__"   → "  - __ref__"
        "  ## - __ref__"  → "  - __ref__"
        "    # - value"   → "    - value"

    Args:
        line: コメント解除する行テキスト（改行なし）。

    Returns:
        コメント解除された行テキスト。
        行がコメントパターンに一致しない場合はそのまま返す。
    """
    match = _UNCOMMENT_PATTERN.match(line)
    if not match:
        return line
    indent = match.group(1)
    body = match.group(2)
    return f"{indent}{body}"


# ---------------------------------------------------------------------------
# コメント切り替え
# ---------------------------------------------------------------------------


def toggle_comment(
    file_path: Path,
    value_entry: ValueEntry,
    enable: bool,
) -> EditResult:
    """値行のコメント状態を切り替える。

    enable=True の場合、コメント行を通常の値行にする（コメント解除）。
    enable=False の場合、通常の値行をコメント行にする（コメント化）。

    冪等操作: 既にコメント解除済みの行に enable=True を指定しても何もしない。
    既にコメント化済みの行に enable=False を指定しても何もしない。

    処理の流れ:
      1. read_lines() でファイルを読み込む
      2. value_entry.line_number で対象行を特定
      3. 対象行が値行パターンに一致するか検証
      4. enable に応じて _comment_line() または _uncomment_line() で変換
      5. 変換が発生した場合のみ write_lines() で書き戻す
      6. EditResult を返す

    Args:
        file_path: YAML ファイルのパス。
        value_entry: 切り替え対象の値行。
            line_number でファイル内の行位置を特定する。
        enable: True = コメント解除（有効化）、False = コメント化（無効化）。

    Returns:
        EditResult。成功時は success=True、失敗時は success=False と error。

    Note:
        この関数は例外を投げない。
        I/O エラーを含む全てのエラーを EditResult.error で報告する。
    """
    # ファイルの読み込み
    try:
        lines, line_ending = read_lines(file_path)
    except FileNotFoundError:
        return EditResult(
            success=False,
            error=f"ファイルが見つかりません: {file_path}",
        )
    except UnicodeDecodeError:
        return EditResult(
            success=False,
            error=f"ファイルの読み込みに失敗しました: {file_path}",
        )
    except OSError:
        return EditResult(
            success=False,
            error=f"ファイルの読み込みに失敗しました: {file_path}",
        )

    # 行番号の検証（1始まり）
    line_number = value_entry.line_number
    if line_number < 1:
        return EditResult(
            success=False,
            error=f"行番号が範囲外です: {line_number} (ファイル行数: {len(lines)})",
        )

    # 行リスト中の対象行のインデックス（0始まり）
    # read_lines は末尾改行がある場合に空文字列を追加するため、
    # 実際の行数は lines から末尾の空文字列を除いたもの
    # ただし line_number は元のファイルの行番号なので、
    # splitlines の結果に基づいて判定する
    line_index = line_number - 1

    # 末尾の空文字列は改行表現のためのもの。実際のコンテンツ行数を取得
    content_line_count = len(lines)
    if content_line_count > 0 and lines[-1] == "":
        content_line_count -= 1

    if line_index < 0 or line_index >= content_line_count:
        return EditResult(
            success=False,
            error=f"行番号が範囲外です: {line_number} (ファイル行数: {content_line_count})",
        )

    # 対象行を取得
    target_line = lines[line_index]

    # 対象行が値行パターンに一致するか検証
    # 値行: "- " で始まる行（インデント付き）、またはコメント化された値行
    is_value_line = bool(_COMMENT_PATTERN.match(target_line))
    is_commented = _is_commented_line(target_line)

    if not is_value_line and not is_commented:
        return EditResult(
            success=False,
            error=f"対象行が値行ではありません: {line_number}",
        )

    # 冪等操作: 既に目的の状態なら何もしない
    if enable and not is_commented:
        # 既にコメント解除済みで enable=True → 何もしない
        return EditResult(success=True)
    if not enable and is_commented:
        # 既にコメント化済みで enable=False → 何もしない
        return EditResult(success=True)

    # 行の変換
    if enable:
        # コメント解除
        new_line = _uncomment_line(target_line)
    else:
        # コメント化
        new_line = _comment_line(target_line)

    # 変換が発生しなかった場合は書き込み不要
    if new_line == target_line:
        return EditResult(success=True)

    # 行を置換
    lines[line_index] = new_line

    # ファイルに書き戻す
    try:
        write_lines(file_path, lines, line_ending)
    except OSError:
        return EditResult(
            success=False,
            error=f"ファイルの書き込みに失敗しました: {file_path}",
        )

    return EditResult(success=True)


# ---------------------------------------------------------------------------
# レジストリ更新
# ---------------------------------------------------------------------------


def refresh_registry(file_path: Path, registry: KeyRegistry) -> None:
    """変更されたファイルを再パースしてレジストリを更新する。

    指定されたファイルを parse_yaml_file() で再パースし、
    レジストリ内の該当ファイルの KeyDefinition を差し替える。

    処理の流れ:
      1. レジストリ内の全キーを走査し、file_path に一致する
         KeyDefinition を除去する
      2. parse_yaml_file(file_path) で新しい KeyDefinition リストを取得
      3. 新しい KeyDefinition をレジストリに追加する
      4. 空になったキーエントリをレジストリから削除する

    Args:
        file_path: 再パース対象のファイルパス。
        registry: 更新対象のキーレジストリ（in-place で変更される）。

    Note:
        この関数は例外を投げない。
        parse_yaml_file() が空リストを返した場合（I/O エラー含む）、
        レジストリから該当ファイルのキー定義が除去される。
    """
    from core.parser import parse_yaml_file

    # 1. レジストリ内の全キーを走査し、file_path に一致する KeyDefinition を除去
    # file_path の正規化（比較のため resolve する）
    target_path = file_path.resolve()
    empty_keys: list[str] = []

    for key_name, key_defs in registry.items():
        # file_path が一致する KeyDefinition を除外
        registry[key_name] = [
            kd for kd in key_defs
            if kd.file_path.resolve() != target_path
        ]
        # 空になったキーを記録
        if not registry[key_name]:
            empty_keys.append(key_name)

    # 空になったキーエントリを削除
    for key_name in empty_keys:
        del registry[key_name]

    # 2. ファイルを再パース
    new_key_defs = parse_yaml_file(file_path)

    # 3. 新しい KeyDefinition をレジストリに追加
    for kd in new_key_defs:
        registry.setdefault(kd.name, []).append(kd)
