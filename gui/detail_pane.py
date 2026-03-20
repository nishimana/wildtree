"""詳細ペイン — ノード選択時のキー定義・ノード情報の表示フォーマット。

S6 — v2 GUI の右ペインに表示する詳細情報を生成する。
TreeNode の情報（key_def, value_entry, ref, node_type）を
人間が読みやすいテキストにフォーマットする。

責務:
  - NodeType ごとの詳細表示テキスト生成
  - キー定義情報（キー名、ファイルパス、行番号、値行一覧）のフォーマット
  - コメント行の視覚的区別（"# " プレフィックス）

設計方針:
  - 関数ベース。状態を持たない
  - Qt のウィジェットには依存しない（テキストの生成のみ）
  - テスト容易：入力は TreeNode、出力は str
"""

from __future__ import annotations

from core.models import NodeType, TreeNode


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------


def format_node_detail(node: TreeNode) -> str:
    """TreeNode の情報を詳細表示用の文字列にフォーマットする。

    NodeType に応じて適切なフォーマッタを呼び出し、
    詳細ペインに表示する文字列を生成する。

    フォーマットの振り分け:
      - ROOT / REF → _format_ref_detail()
      - LITERAL → _format_literal_detail()
      - UNRESOLVED → _format_unresolved_detail()
      - CIRCULAR → _format_circular_detail()
      - DYNAMIC → _format_dynamic_detail()
      - EMPTY → _format_empty_detail()

    Args:
        node: 詳細を表示する TreeNode。

    Returns:
        詳細表示用の複数行テキスト。
    """
    # NodeType に応じてフォーマッタを振り分ける
    formatters = {
        NodeType.ROOT: _format_ref_detail,
        NodeType.REF: _format_ref_detail,
        NodeType.LITERAL: _format_literal_detail,
        NodeType.UNRESOLVED: _format_unresolved_detail,
        NodeType.CIRCULAR: _format_circular_detail,
        NodeType.DYNAMIC: _format_dynamic_detail,
        NodeType.EMPTY: _format_empty_detail,
    }
    formatter = formatters.get(node.node_type, _format_ref_detail)
    return formatter(node)


def _format_ref_detail(node: TreeNode) -> str:
    """REF / ROOT ノードの詳細をフォーマットする。

    表示内容:
      - キー名
      - ファイルパス（絶対パス）
      - 行番号
      - 値行一覧（コメント行は "# " プレフィックス付き）

    フォーマット例:
      ```
      キー名: メイン
      ファイル: C:/path/to/cards/main.yaml
      行番号: 1

      値:
        - __cards/デフォルト__
        # - __cards/無効化された参照__
        - literal_value
      ```

    key_def が None の場合（通常は発生しない防御コード）:
      "キー定義情報がありません" を返す。

    Args:
        node: REF または ROOT タイプの TreeNode。

    Returns:
        フォーマットされた詳細テキスト。
    """
    # key_def が None の場合は防御コード
    if node.key_def is None:
        return "キー定義情報がありません"

    kd = node.key_def
    lines: list[str] = []

    # キー名
    lines.append(f"キー名: {kd.name}")
    # ファイルパス（絶対パス）
    lines.append(f"ファイル: {kd.file_path}")
    # 行番号
    lines.append(f"行番号: {kd.line_number}")

    # 値行一覧
    if kd.values:
        lines.append("")
        lines.append("値:")
        for ve in kd.values:
            if ve.is_commented:
                # コメント行は "# " プレフィックス付き
                lines.append(f"  # - {ve.raw_text}")
            else:
                lines.append(f"  - {ve.raw_text}")

    return "\n".join(lines)


def _format_literal_detail(node: TreeNode) -> str:
    """LITERAL ノードの詳細をフォーマットする。

    表示内容:
      - リテラル値（display_name）
      - 所属キーの情報（key_def がある場合、value_entry 経由では
        直接キー名を取得できないため、表示しない）

    フォーマット例:
      ```
      リテラル値: (cinematic_shadow:1.1)
      ```

    Args:
        node: LITERAL タイプの TreeNode。

    Returns:
        フォーマットされた詳細テキスト。
    """
    # display_name をリテラル値として表示する
    return f"リテラル値: {node.display_name}"


def _format_unresolved_detail(node: TreeNode) -> str:
    """UNRESOLVED ノードの詳細をフォーマットする。

    表示内容:
      - ヘッダ: [未解決参照]
      - 参照テキスト（ref.raw）
      - 説明メッセージ

    フォーマット例:
      ```
      [未解決参照]
      参照: __cards/存在しないキー__

      この参照は解決できませんでした。
      参照先のキーが存在しないか、パスが正しくない可能性があります。
      ```

    Args:
        node: UNRESOLVED タイプの TreeNode。

    Returns:
        フォーマットされた詳細テキスト。
    """
    lines: list[str] = []
    lines.append("[未解決参照]")

    # 参照テキスト（ref.raw）。ref が None の場合は display_name で代替
    raw = node.ref.raw if node.ref is not None else node.display_name
    lines.append(f"参照: {raw}")

    lines.append("")
    lines.append("この参照は解決できませんでした。")
    lines.append("参照先のキーが存在しないか、パスが正しくない可能性があります。")

    return "\n".join(lines)


def _format_circular_detail(node: TreeNode) -> str:
    """CIRCULAR ノードの詳細をフォーマットする。

    表示内容:
      - ヘッダ: [循環参照]
      - 参照テキスト（ref.raw）
      - 説明メッセージ

    フォーマット例:
      ```
      [循環参照]
      参照: __cards/キー名__

      このノードは循環参照により展開が打ち切られました。
      ```

    Args:
        node: CIRCULAR タイプの TreeNode。

    Returns:
        フォーマットされた詳細テキスト。
    """
    lines: list[str] = []
    lines.append("[循環参照]")

    # 参照テキスト（ref.raw）。ref が None の場合は display_name で代替
    raw = node.ref.raw if node.ref is not None else node.display_name
    lines.append(f"参照: {raw}")

    lines.append("")
    lines.append("このノードは循環参照により展開が打ち切られました。")

    return "\n".join(lines)


def _format_dynamic_detail(node: TreeNode) -> str:
    """DYNAMIC ノードの詳細をフォーマットする。

    表示内容:
      - ヘッダ: [動的参照]
      - 参照テキスト（ref.raw）
      - 説明メッセージ

    フォーマット例:
      ```
      [動的参照]
      参照: __{__cards/キャラキー__}NP__

      変数参照を含む動的参照です。
      内部参照は子ノードとして展開されています。
      ```

    Args:
        node: DYNAMIC タイプの TreeNode。

    Returns:
        フォーマットされた詳細テキスト。
    """
    lines: list[str] = []
    lines.append("[動的参照]")

    # 参照テキスト（ref.raw）。ref が None の場合は display_name で代替
    raw = node.ref.raw if node.ref is not None else node.display_name
    lines.append(f"参照: {raw}")

    lines.append("")
    lines.append("変数参照を含む動的参照です。")
    lines.append("内部参照は子ノードとして展開されています。")

    return "\n".join(lines)


def _format_empty_detail(node: TreeNode) -> str:
    """EMPTY ノードの詳細をフォーマットする。

    表示内容:
      - ヘッダ: [空定義]
      - 値テキスト
      - 説明メッセージ

    フォーマット例:
      ```
      [空定義]
      値: "{}"

      このエントリは空定義です。
      ```

    Args:
        node: EMPTY タイプの TreeNode。

    Returns:
        フォーマットされた詳細テキスト。
    """
    lines: list[str] = []
    lines.append("[空定義]")

    # 値テキスト（value_entry がある場合は raw_text を使用）
    if node.value_entry is not None:
        lines.append(f'値: {node.value_entry.raw_text}')
    else:
        lines.append('値: "{}"')

    lines.append("")
    lines.append("このエントリは空定義です。")

    return "\n".join(lines)
