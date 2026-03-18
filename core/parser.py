"""行ベース YAML パーサー — キー定義の抽出と参照パターンの解析。

Stage 2-3 of the v2 パーサーパイプライン。
Dynamic Prompts の YAML は PyYAML でパースできない特殊文字を含むため、
行ベースでキーと値を抽出する。

責務:
  - YAML ファイルからトップレベルキーと値行を抽出する（コメント行も保持）
  - 値行テキストからワイルドカード参照（__name__ パターン）を抽出する
  - 値行テキストからリテラル部分を抽出する
  - キーレジストリ（名前 → KeyDefinition リスト）を構築する
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from core.models import KeyDefinition, KeyRegistry, RefType, ValueEntry, WildcardRef

# トップレベルキーを検出する正規表現（モジュールレベルで1度だけコンパイル）
_KEY_PATTERN = re.compile(r"^([^:]+):")


def parse_yaml_file(file_path: Path) -> list[KeyDefinition]:
    """YAML ファイルからキー定義を抽出する。

    行ベースパーサーを使用し、以下のルールでキーと値を判別する:
    - インデントなしの行で `key:` パターンに一致 → トップレベルキー
    - インデントされた行 → 現在のキーの値行
    - コメント行（strip 後に # で始まる）の扱い:
      - インデントなし: キーレベルコメント → スキップ
      - インデントあり + `# - ` パターン: 値行コメント → ValueEntry(is_commented=True)
      - インデントあり + 上記以外: セクション区切り等 → スキップ

    各値行は ValueEntry として構造化され、refs と literals が
    参照抽出・リテラル抽出によって設定される。

    Args:
        file_path: パース対象の YAML ファイルパス。

    Returns:
        キー定義のリスト。各 KeyDefinition は name, file_path,
        line_number, values を持つ。
        ファイルが読めない場合は空リスト。

    Note:
        I/O エラー (OSError) やエンコーディングエラー (UnicodeDecodeError) は
        例外を raise せず、空リストを返す。個別ファイルの問題で
        全体スキャンを止めない設計。
    """
    # I/O エラー時は空リストを返す
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    keys: list[KeyDefinition] = []
    current_key_name: str | None = None
    current_key_line: int = 0
    current_values: list[ValueEntry] = []

    # CRLF 対応: splitlines() を使う
    lines = content.splitlines()

    for line_idx, line in enumerate(lines):
        line_number = line_idx + 1  # 1始まり

        # インデントされた行 = 値行の候補
        if line.startswith(" ") or line.startswith("\t"):
            if current_key_name is not None:
                stripped = line.strip()

                # 空行はスキップ
                if stripped == "":
                    continue

                # コメント行の処理
                if stripped.startswith("#"):
                    # 先頭の連続する "#" を全て除去して中身を確認する。
                    # lstrip("#") は "##" や "###" も除去するが、これは意図的な動作。
                    # "## - value" のようなダブルハッシュパターンも値行コメントとして扱う。
                    after_hash = stripped.lstrip("#").strip()
                    if after_hash.startswith("- "):
                        # 値行のコメントアウト → ValueEntry(is_commented=True)
                        raw_text = after_hash[2:]  # "- " を除去
                        refs, literals = _parse_value_line(raw_text)
                        current_values.append(ValueEntry(
                            raw_text=raw_text,
                            line_number=line_number,
                            is_commented=True,
                            refs=refs,
                            literals=literals,
                        ))
                    # それ以外（セクション区切り・メモ）はスキップ
                    continue

                # 通常の値行: "- " プレフィックスを除去
                if stripped.startswith("- "):
                    raw_text = stripped[2:]
                else:
                    raw_text = stripped

                refs, literals = _parse_value_line(raw_text)
                current_values.append(ValueEntry(
                    raw_text=raw_text,
                    line_number=line_number,
                    is_commented=False,
                    refs=refs,
                    literals=literals,
                ))
            continue

        # インデントなしの行 = 新しいキーの可能性
        trimmed = line.strip()

        # 空行はスキップ（現在のキーを閉じない）
        if trimmed == "":
            continue

        # コメント行はスキップ（現在のキーを閉じない）
        if trimmed.startswith("#"):
            continue

        # キー定義行の候補: まず前のキーを保存
        if current_key_name is not None:
            keys.append(KeyDefinition(
                name=current_key_name,
                file_path=file_path,
                line_number=current_key_line,
                values=current_values,
            ))
            current_key_name = None
            current_values = []

        # キー定義行のマッチ
        match = _KEY_PATTERN.match(trimmed)
        if match:
            current_key_name = match.group(1).strip()
            current_key_line = line_number
            current_values = []

    # ファイル末尾の最後のキーを保存
    if current_key_name is not None:
        keys.append(KeyDefinition(
            name=current_key_name,
            file_path=file_path,
            line_number=current_key_line,
            values=current_values,
        ))

    return keys


def extract_refs(text: str) -> list[WildcardRef]:
    """テキストからワイルドカード参照（__name__ パターン）を抽出する。

    ネストされた参照（動的参照）にも対応する。
    例: `__{__cards/a__}{__cards/b__}suffix__` → 外側は DYNAMIC、
    inner_refs に内部参照が格納される。

    通常参照と動的参照の判定:
    - ボディ部分に `{__` を含む → RefType.DYNAMIC
    - それ以外 → RefType.NORMAL

    Args:
        text: 参照を検索するテキスト。通常は値行の raw_text。

    Returns:
        検出された WildcardRef のリスト。
        参照が見つからない場合は空リスト。
        動的参照の場合、外側の WildcardRef の inner_refs に
        内部参照が tuple として格納される。

    Note:
        v1 では外側の参照とインナー参照を同一リストに
        フラットに追加していた。v2 では親子関係を保持し、
        外側の WildcardRef.inner_refs に構造化する。
        返却リストには外側の参照のみが含まれる。
    """
    # 早期リターン: "__" を含まなければ参照なし
    if "__" not in text:
        return []

    refs: list[WildcardRef] = []
    i = 0

    while i < len(text):
        # 開き __ を検出
        if text[i] == "_" and i + 1 < len(text) and text[i + 1] == "_":
            wc_start = i
            body_start = i + 2

            # 閉じ __ の位置を検出
            close_pos = _scan_closing_delimiters(text, body_start)
            if close_pos >= 0:
                body = text[body_start:close_pos]
                raw = text[wc_start:close_pos + 2]

                # 動的参照の判定: ボディ部分に "{__" を含む
                if "{__" in body:
                    # 内部参照を再帰的に抽出
                    inner_refs = _extract_inner_refs(body)
                    ref = WildcardRef(
                        raw=raw,
                        full_path=body,
                        ref_type=RefType.DYNAMIC,
                        inner_refs=tuple(inner_refs),
                    )
                else:
                    ref = WildcardRef(
                        raw=raw,
                        full_path=body,
                        ref_type=RefType.NORMAL,
                    )

                refs.append(ref)
                # 閉じ __ の後に移動
                i = close_pos + 2
                continue

        i += 1

    return refs


def _extract_inner_refs(body: str) -> list[WildcardRef]:
    """動的参照のボディ部分から内部の __name__ 参照を抽出する。

    ブレース内の __name__ パターンを検出し、通常参照として返す。

    Args:
        body: 外側の参照のボディ部分テキスト。

    Returns:
        内部参照の WildcardRef リスト。
    """
    inner_refs: list[WildcardRef] = []
    i = 0

    while i < len(body):
        # ブレース内の __ を検出
        if body[i] == "{" and i + 1 < len(body):
            # ブレース内の参照パターン {__name__} を探す
            j = i + 1
            if j < len(body) and body[j] == "_" and j + 1 < len(body) and body[j + 1] == "_":
                # __ の開始位置
                inner_body_start = j + 2
                # 閉じ __ を探す（ブレース内なので単純に __ を探す）
                k = inner_body_start
                while k < len(body):
                    if body[k] == "_" and k + 1 < len(body) and body[k + 1] == "_":
                        # 閉じ __ を検出 — 内部参照として追加
                        inner_full_path = body[inner_body_start:k]
                        inner_raw = body[j:k + 2]  # "__name__" 部分
                        inner_refs.append(WildcardRef(
                            raw=inner_raw,
                            full_path=inner_full_path,
                            ref_type=RefType.NORMAL,
                        ))
                        i = k + 2
                        # } をスキップ
                        if i < len(body) and body[i] == "}":
                            i += 1
                        break
                    k += 1
                else:
                    i += 1
                continue
        i += 1

    return inner_refs


def extract_literals(text: str, refs: list[WildcardRef]) -> list[str]:
    """テキストから参照部分を除いたリテラルを抽出する。

    カンマ区切りで分割し、各セグメントから参照（__name__ パターン）の
    raw テキストを除いた残りをリテラルとして収集する。

    Args:
        text: 元の値行テキスト（raw_text）。
        refs: extract_refs() で抽出済みの参照リスト。
            各 WildcardRef.raw を使ってテキストから参照部分を除去する。

    Returns:
        リテラル文字列のリスト。空文字列のセグメントは除外される。
        各リテラルは前後の空白が strip される。

    Examples:
        >>> extract_literals("dynamic_angle,__cards/シネマ__,tag", refs)
        ["dynamic_angle", "tag"]
        >>> extract_literals("__ref1__,__ref2__", refs)
        []
        >>> extract_literals('"{}"', [])
        ['"{}"']
    """
    if not text:
        return []

    # 参照の raw テキストをテキストから除去
    remaining = text
    for ref in refs:
        remaining = remaining.replace(ref.raw, "")

    # ブレース深度を追跡してトップレベルのカンマのみで分割
    # DP 構文 {...|...} 内のカンマは区切りとして扱わない
    segments = _split_top_level_commas(remaining)

    # 空セグメントを除外し、各セグメントを strip
    literals: list[str] = []
    for segment in segments:
        stripped = segment.strip()
        if stripped:
            literals.append(stripped)

    return literals


def _split_top_level_commas(text: str) -> list[str]:
    """ブレース深度を追跡してトップレベルのカンマのみで文字列を分割する。

    DP 構文 {...|...} 内のカンマは区切りとして扱わない。
    クォート内のブレースも考慮する。

    Args:
        text: 分割対象のテキスト。

    Returns:
        トップレベルのカンマで分割されたセグメントのリスト。
    """
    segments: list[str] = []
    current: list[str] = []
    brace_depth = 0
    in_quotes = False
    quote_char = ""

    for idx, ch in enumerate(text):
        # クォートの追跡
        # バックスラッシュエスケープされたクォート（\" や \'）は無視する
        is_escaped = idx > 0 and text[idx - 1] == "\\"
        if ch in ('"', "'") and not in_quotes and not is_escaped:
            in_quotes = True
            quote_char = ch
            current.append(ch)
            continue
        if in_quotes and ch == quote_char and not is_escaped:
            in_quotes = False
            current.append(ch)
            continue

        # クォート内ではすべて通過
        if in_quotes:
            current.append(ch)
            continue

        # ブレース深度の追跡
        if ch == "{":
            brace_depth += 1
            current.append(ch)
            continue
        if ch == "}":
            brace_depth -= 1
            if brace_depth < 0:
                brace_depth = 0
            current.append(ch)
            continue

        # トップレベルのカンマで分割
        if ch == "," and brace_depth == 0:
            segments.append("".join(current))
            current = []
            continue

        current.append(ch)

    # 最後のセグメントを追加
    segments.append("".join(current))

    return segments


def build_registry(yaml_files: list[Path]) -> KeyRegistry:
    """YAML ファイルリストからキーレジストリを構築する。

    各ファイルを parse_yaml_file() でパースし、キー名をキーとした
    辞書に KeyDefinition を蓄積する。同名キーが複数ファイルに
    存在する場合、リストに追加される（後のファイルが後に来る）。

    Args:
        yaml_files: パース対象の YAML ファイルパスリスト。
            scan_yaml_files() の返却値をそのまま渡すことを想定。
            ソート順がレジストリの「後勝ち」動作に影響する。

    Returns:
        キーレジストリ。キー名 → list[KeyDefinition] のマッピング。
        空のファイルリストの場合は空辞書。
    """
    registry: dict[str, list[KeyDefinition]] = defaultdict(list)
    for file_path in yaml_files:
        for key_def in parse_yaml_file(file_path):
            registry[key_def.name].append(key_def)
    # defaultdict を通常の dict に変換して返す
    return dict(registry)


def _scan_closing_delimiters(text: str, body_start: int) -> int:
    """閉じ __ デリミタの位置を検出する。

    ブレース深度とインナーワイルドカード深度を追跡し、
    ネストされた参照パターン（`__{__inner__}outer__`）を
    正しくハンドリングする。

    v1 の _scan_closing_underscores() を参考にした実装。

    Args:
        text: スキャン対象のテキスト全体。
        body_start: 開き __ の直後のインデックス（ボディの先頭位置）。

    Returns:
        閉じ __ の最初のアンダースコアのインデックス。
        見つからない場合は -1。
    """
    i = body_start
    inner_wildcard_depth = 0
    brace_depth = 0
    # 開始位置の直前の文字を取得（v1 と同じ初期化）
    prev_char = text[body_start - 1] if body_start > 0 else ""

    while i < len(text):
        ch = text[i]

        # ブレース深度の追跡（インナーワイルドカード深度が0のときのみ）
        if ch == "{" and inner_wildcard_depth == 0:
            brace_depth += 1
            prev_char = ch
            i += 1
            continue

        if ch == "}" and inner_wildcard_depth == 0:
            brace_depth -= 1
            if brace_depth < 0:
                brace_depth = 0
            prev_char = ch
            i += 1
            continue

        # ダブルアンダースコアの検出
        if ch == "_" and i + 1 < len(text) and text[i + 1] == "_":
            after_uu = text[i + 2] if i + 2 < len(text) else ""

            # ブレース内部のダブルアンダースコア
            if brace_depth > 0:
                if inner_wildcard_depth == 0:
                    inner_wildcard_depth += 1
                else:
                    inner_wildcard_depth -= 1
                i += 2
                prev_char = "_"
                continue

            # ブレース外のダブルアンダースコア
            # 連結パターン: }__{ の中間部分をスキップ
            if after_uu == "{" and prev_char == "}":
                i += 2
                prev_char = "_"
                continue

            # インナーワイルドカードの閉じ
            if inner_wildcard_depth > 0:
                inner_wildcard_depth -= 1
                i += 2
                prev_char = "_"
                continue

            # 外側の閉じアンダースコアを発見
            return i

        prev_char = ch
        i += 1

    return -1


def _parse_value_line(raw_text: str) -> tuple[list[WildcardRef], list[str]]:
    """値行テキストから参照とリテラルを抽出する。

    extract_refs() と extract_literals() を組み合わせて、
    1つの値行テキストから参照リストとリテラルリストを同時に取得する。
    parse_yaml_file() 内で ValueEntry を構築する際に使用する。

    Args:
        raw_text: 正規化済みの値行テキスト
            （"  - " プレフィックス除去後、コメント行なら "# " も除去後）。

    Returns:
        (refs, literals) のタプル。
        refs: 抽出された WildcardRef のリスト。
        literals: 参照部分を除いたリテラル文字列のリスト。
    """
    refs = extract_refs(raw_text)
    literals = extract_literals(raw_text, refs)
    return refs, literals
