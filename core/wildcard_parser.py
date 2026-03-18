"""Wildcard YAML parser and dependency tree builder.

5-stage pipeline:
  Stage 1: scan_yaml_files     - Recursively find .yaml/.yml files
  Stage 2: extract_keys_from_file - Extract top-level keys and their value lines
  Stage 3: extract_refs_from_line - Extract __name__ references (with nesting)
  Stage 4: WildcardResolver     - Resolve reference names to KeyDefinition
  Stage 5: build_tree           - Build dependency tree from entry point

This module has no GUI dependencies. PySide6 is not imported here.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class KeyDefinition:
    """A top-level key extracted from a YAML file.

    Attributes:
        name: Key name (e.g. "asada_shino_body_type").
        file_path: Path to the YAML file where this key is defined.
        raw_values: List of value lines under this key, excluding comment lines.
            Each line is stripped of the leading "  - " prefix.
    """

    name: str
    file_path: Path
    raw_values: list[str]


@dataclass
class WildcardRef:
    """A __name__ reference found in a value line.

    Attributes:
        name: The resolved reference name, without surrounding __ delimiters.
            Example: "cards/SAO/CH_asada_shino/asada_shino_body_type"
        raw: The original text including __ delimiters.
            Example: "__cards/SAO/CH_asada_shino/asada_shino_body_type__"
    """

    name: str
    raw: str


@dataclass
class TreeNode:
    """A node in the dependency tree.

    Attributes:
        name: Display name (the key name portion, not the full path).
        ref_name: Full reference name used for resolution.
        children: Child nodes (references found in this key's values).
        is_leaf: True if no references were found in this key's values,
            OR if the reference could not be resolved.
        is_circular: True if this node was cut off due to circular reference
            detection.
        is_unresolved: True if this node's reference could not be resolved
            (resolve() returned None). These nodes have no children and
            are displayed with a red highlight in the GUI.
    """

    name: str
    ref_name: str
    children: list[TreeNode] = field(default_factory=list)
    is_leaf: bool = False
    is_circular: bool = False
    is_unresolved: bool = False


# ---------------------------------------------------------------------------
# Stage 1: YAML file scanning
# ---------------------------------------------------------------------------


def scan_yaml_files(cards_dir: Path) -> list[Path]:
    """Recursively find all .yaml and .yml files under cards_dir.

    Files are returned sorted by path (using Path's default ordering)
    to ensure stable scan order, which affects last-wins behavior for
    duplicate key names.

    Args:
        cards_dir: Root directory to scan.

    Returns:
        Sorted list of Path objects for each YAML file found.

    Raises:
        FileNotFoundError: If cards_dir does not exist.
        NotADirectoryError: If cards_dir exists but is not a directory.
    """
    if not cards_dir.exists():
        raise FileNotFoundError(f"ディレクトリが存在しません: {cards_dir}")
    if not cards_dir.is_dir():
        raise NotADirectoryError(f"ディレクトリではありません: {cards_dir}")

    # .yaml と .yml を再帰的に収集し、ソートして返す
    yaml_files: list[Path] = []
    for p in cards_dir.rglob("*"):
        if p.is_file() and p.suffix in (".yaml", ".yml"):
            yaml_files.append(p)

    return sorted(yaml_files)


# ---------------------------------------------------------------------------
# Stage 2: Key extraction (line-based parser)
# ---------------------------------------------------------------------------


def extract_keys_from_file(file_path: Path) -> list[KeyDefinition]:
    """Extract top-level keys and their value lines from a YAML file.

    Uses a line-based parser (not PyYAML) because Dynamic Prompts YAML
    contains prompt strings with special characters that break strict
    YAML parsing.

    Parsing rules:
    - A top-level key is a line that starts at column 0 (no indent),
      is not empty, does not start with '#', and matches the pattern
      ``^([^:]+):``.
    - Value lines are indented lines (starting with space or tab)
      that follow a key line.
    - Comment value lines (where stripped content starts with '#')
      are excluded from raw_values.
    - The "  - " list item prefix is stripped from value lines.

    Args:
        file_path: Path to the YAML file to parse.

    Returns:
        List of KeyDefinition objects, one per top-level key found.
        Returns an empty list if the file cannot be read.

    Note:
        This function does not raise exceptions on I/O errors;
        it returns an empty list instead. This follows the pattern
        from dynamic_linter's extractKeysFromFile().
        File is read with UTF-8 encoding explicitly.
    """
    # I/O エラー時は空リストを返す（個別ファイルの問題でスキャン全体を止めない）
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    # トップレベルキーを検出する正規表現
    key_pattern = re.compile(r"^([^:]+):")

    keys: list[KeyDefinition] = []
    current_key_name: str | None = None
    current_values: list[str] = []

    for line in content.splitlines():
        # インデントされた行 = 値行
        if line.startswith(" ") or line.startswith("\t"):
            if current_key_name is not None:
                stripped = line.strip()
                # 空行はスキップ
                if stripped == "":
                    continue
                # コメント行（先頭空白を除去後に # で始まる）はスキップ
                if stripped.startswith("#"):
                    continue
                # リストアイテムプレフィックス "- " を除去
                if stripped.startswith("- "):
                    stripped = stripped[2:]
                current_values.append(stripped)
            continue

        # インデントなしの行 = 新しいキーの可能性
        # まず前のキーを保存
        if current_key_name is not None:
            keys.append(KeyDefinition(
                name=current_key_name,
                file_path=file_path,
                raw_values=current_values,
            ))
            current_key_name = None
            current_values = []

        trimmed = line.strip()
        # 空行やコメント行はキーではない
        if trimmed == "" or trimmed.startswith("#"):
            continue

        match = key_pattern.match(trimmed)
        if match:
            current_key_name = match.group(1).strip()
            current_values = []

    # ファイル末尾の最後のキーを保存
    if current_key_name is not None:
        keys.append(KeyDefinition(
            name=current_key_name,
            file_path=file_path,
            raw_values=current_values,
        ))

    return keys


# ---------------------------------------------------------------------------
# Stage 3: Reference extraction
# ---------------------------------------------------------------------------


def _scan_closing_underscores(text: str, body_start: int) -> int:
    """Find the position of the closing __ for a wildcard reference.

    Tracks brace depth and inner wildcard depth to correctly handle
    nested patterns like ``__{__inner__}outer__``.

    This is the Python port of dynamic_linter's ``scanLineWildcard()``.

    Args:
        text: The full line text.
        body_start: Index of the first character after the opening __.

    Returns:
        Index of the first underscore of the closing __, or -1 if
        no valid closing __ is found.
    """
    i = body_start
    inner_wildcard_depth = 0
    brace_depth = 0
    # 開始位置の直前の文字を取得（TypeScript 版と同じ初期化）
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


def extract_refs_from_line(line: str) -> list[WildcardRef]:
    """Extract all __name__ references from a single line.

    Handles nested references like ``__{__inner__}outer__`` by
    recursively parsing the body of each wildcard span.

    For nested references:
    - The outer reference (which contains dynamic parts) is included
    - Inner references (__inner__) are also included as separate entries

    This is the Python port of dynamic_linter's
    ``parseWildcardSpansOnLine()``.

    Args:
        line: A single line of text to scan for references.

    Returns:
        List of WildcardRef objects for each __name__ reference found.
        Outer references appear before their inner references.
    """
    refs: list[WildcardRef] = []
    i = 0

    while i < len(line):
        # 開きアンダースコア __ を検出
        if line[i] == "_" and i + 1 < len(line) and line[i + 1] == "_":
            wc_start = i
            body_start = i + 2

            close_pos = _scan_closing_underscores(line, body_start)
            if close_pos >= 0:
                name = line[body_start:close_pos]
                raw = line[wc_start:close_pos + 2]

                # 外側の参照を追加
                refs.append(WildcardRef(name=name, raw=raw))

                # ボディ部分を再帰的にパースしてインナー参照を抽出
                body = line[body_start:close_pos]
                inner_refs = extract_refs_from_line(body)
                refs.extend(inner_refs)

                # 閉じ __ の後に移動
                i = close_pos + 2
                continue

        i += 1

    return refs


# ---------------------------------------------------------------------------
# Stage 4: Name resolution
# ---------------------------------------------------------------------------


class WildcardResolver:
    """Resolves wildcard reference names to KeyDefinition objects.

    Supports two reference formats:
    - Full path: ``__cards/dir/subdir/keyname__`` - resolved by matching
      both key name and file path.
    - Short form: ``__keyname__`` - resolved by key name lookup,
      last-wins if multiple definitions exist.

    The ``cards/`` prefix in full-path references corresponds to the
    cards_dir root and is stripped during resolution.

    Attributes:
        _key_registry: Maps key names to a list of KeyDefinition objects.
            Multiple entries for the same key name are possible when
            the same key is defined in different files.
        _cards_dir: Root directory path, used to compute relative paths
            for full-path reference resolution.
    """

    def __init__(
        self,
        keys: dict[str, list[KeyDefinition]],
        cards_dir: Path,
    ) -> None:
        """Initialize the resolver.

        Args:
            keys: Registry mapping key names to lists of KeyDefinition.
                Built by build_key_registry().
            cards_dir: The root cards directory path.
        """
        self._key_registry = keys
        self._cards_dir = cards_dir

    def resolve(self, ref_name: str) -> KeyDefinition | None:
        """Resolve a reference name to a KeyDefinition.

        Resolution strategy:
        1. If ref_name starts with "cards/", treat as full-path reference:
           - Strip "cards/" prefix
           - Split by "/" - last element is key name, preceding elements
             form the directory path
           - Look up key name in registry, filter by file path matching
             the directory path
        2. Otherwise, treat as short-form reference:
           - Look up key name in registry
           - Return the last entry (last-wins semantics)

        Args:
            ref_name: The reference name (without __ delimiters).

        Returns:
            The resolved KeyDefinition, or None if not found.
        """
        # フルパス参照: "cards/" で始まる場合
        if ref_name.startswith("cards/"):
            # "cards/" プレフィックスを除去
            path_part = ref_name[len("cards/"):]
            parts = path_part.split("/")
            key_name = parts[-1]
            dir_parts = parts[:-1]  # キー名を除いたディレクトリパス

            candidates = self._key_registry.get(key_name)
            if candidates is None:
                return None

            # ファイルパスの相対パスにディレクトリパスが含まれるものを選択
            dir_path = "/".join(dir_parts)
            for kd in candidates:
                # cards_dir からの相対パスを取得し、スラッシュ区切りに正規化
                try:
                    rel = kd.file_path.relative_to(self._cards_dir)
                except ValueError:
                    continue
                rel_str = str(rel.parent).replace("\\", "/")
                if rel_str == dir_path:
                    return kd

            return None

        # 短縮形参照: キー名で検索（後勝ち）
        candidates = self._key_registry.get(ref_name)
        if candidates is None:
            return None
        return candidates[-1]

    def get_all_key_names(self) -> list[str]:
        """Return a sorted list of all registered key names.

        Used by the GUI to populate the entry point selector.

        Returns:
            Sorted list of unique key names.
        """
        return sorted(self._key_registry.keys())

    def get_refs_for_key(self, key_def: KeyDefinition) -> list[WildcardRef]:
        """Extract all references from a key's value lines.

        Iterates over key_def.raw_values and calls extract_refs_from_line()
        on each line.

        Args:
            key_def: The key definition whose values to scan.

        Returns:
            List of all WildcardRef objects found across all value lines.
        """
        refs: list[WildcardRef] = []
        for value_line in key_def.raw_values:
            refs.extend(extract_refs_from_line(value_line))
        return refs


# ---------------------------------------------------------------------------
# Key registry builder
# ---------------------------------------------------------------------------


def build_key_registry(
    yaml_files: list[Path],
) -> dict[str, list[KeyDefinition]]:
    """Build a key registry from a list of YAML files.

    Processes files in the order given (which should be sorted for
    stable last-wins behavior). For each file, extracts keys and
    appends them to the registry under their name.

    Args:
        yaml_files: Sorted list of YAML file paths to process.

    Returns:
        Dictionary mapping key names to lists of KeyDefinition objects.
        Keys with the same name from different files appear in scan order.
    """
    registry: dict[str, list[KeyDefinition]] = defaultdict(list)
    for file_path in yaml_files:
        for key_def in extract_keys_from_file(file_path):
            registry[key_def.name].append(key_def)
    # defaultdict を通常の dict に変換して返す
    return dict(registry)


# ---------------------------------------------------------------------------
# Stage 5: Tree construction
# ---------------------------------------------------------------------------


def build_tree(
    entry_key: str,
    resolver: WildcardResolver,
) -> TreeNode:
    """Build a dependency tree starting from an entry point key.

    Recursively resolves references from the entry key's values,
    building a tree of TreeNode objects. Circular references are
    detected by tracking visited keys in the current path, and
    marked with is_circular=True.

    References that cannot be resolved (no matching KeyDefinition)
    are included in the tree as nodes with is_unresolved=True and
    is_leaf=True. These nodes are displayed with a red highlight
    in the GUI to indicate broken references.

    Args:
        entry_key: Name of the key to use as tree root.
        resolver: WildcardResolver instance for name resolution.

    Returns:
        Root TreeNode. If entry_key cannot be resolved, returns a
        leaf node with is_leaf=True.

    Note:
        The visited set tracks ref_name (not display name) to correctly
        handle cases where the same key name exists in different files.
        The visited set is path-scoped (not global) to allow the same
        key to appear in different branches of the tree.
    """

    def _build_node(
        ref_name: str,
        display_name: str,
        visited: set[str],
    ) -> TreeNode:
        """再帰的にツリーノードを構築する内部関数。"""
        # 循環参照検出
        if ref_name in visited:
            return TreeNode(
                name=display_name,
                ref_name=ref_name,
                is_circular=True,
            )

        # 名前解決
        key_def = resolver.resolve(ref_name)
        if key_def is None:
            return TreeNode(
                name=display_name,
                ref_name=ref_name,
                is_leaf=True,
            )

        # 訪問済みセットにこのキーを追加（パススコープ）
        visited_with_current = visited | {ref_name}

        # 子ノードを構築
        refs = resolver.get_refs_for_key(key_def)
        children: list[TreeNode] = []
        for ref in refs:
            child_key_def = resolver.resolve(ref.name)
            if child_key_def is None:
                # 壊れた参照: ツリーに含め、is_unresolved=True にする
                # 表示名は ref.name の最後のスラッシュ以降
                child_display = ref.name.rsplit("/", 1)[-1]
                children.append(TreeNode(
                    name=child_display,
                    ref_name=ref.name,
                    is_leaf=True,
                    is_unresolved=True,
                ))
                continue
            child_node = _build_node(
                ref_name=ref.name,
                display_name=child_key_def.name,
                visited=visited_with_current,
            )
            children.append(child_node)

        is_leaf = len(children) == 0
        return TreeNode(
            name=display_name,
            ref_name=ref_name,
            children=children,
            is_leaf=is_leaf,
        )

    return _build_node(
        ref_name=entry_key,
        display_name=entry_key,
        visited=set(),
    )
