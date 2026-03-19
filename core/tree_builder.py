"""ツリー構築 — KeyDefinition から TreeNode ツリーを再帰的に構築する。

S5 — v2 パーサーパイプラインの最終段。
S1-S4 の全成果物（KeyDefinition, KeyRegistry, FullPathIndex, resolver）を
統合し、エントリポイントから参照を辿って TreeNode ツリーを生成する。

責務:
  - 指定された KeyDefinition からの再帰的ツリー展開
  - 循環参照の検出（パスごとの visited セット）
  - 深さ制限による安全停止
  - 全 NodeType の判定と TreeNode 構築

設計方針:
  - 関数ベース。状態を持たず、引数で全情報を受け取る
  - 例外を投げない。全ての入力に対して正常な TreeNode を返す
  - 全展開（eager expansion）。遅延展開は S6 で必要になったら検討
  - visited セットはパスごと（per-path）のスコープ。ダイヤモンド参照に対応
"""

from __future__ import annotations

from core.models import (
    FullPathIndex,
    KeyDefinition,
    KeyRegistry,
    NodeType,
    RefType,
    TreeNode,
    ValueEntry,
    WildcardRef,
)
from core.resolver import resolve
from core.top_tree import TopTreeInfo

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

MAX_DEPTH: int = 50
"""再帰の最大深さ。

実データの最大深度は 9。安全マージンを十分に取って 50 を上限とする。
超過時は CIRCULAR ノードとして安全停止する。
テスト時に差し替え可能。
"""

EMPTY_DISPLAY_NAME: str = "(空)"
"""空定義ノードの表示名。

値行が '"{}"' の場合に使用する。
"""

CIRCULAR_SUFFIX: str = " (循環)"
"""循環参照ノードの表示名サフィックス。

循環検出時にキー名の後ろに付与する。
"""


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------


def build_tree(
    key_def: KeyDefinition,
    registry: KeyRegistry,
    full_path_index: FullPathIndex,
) -> TreeNode:
    """指定された KeyDefinition をルートとしてツリーを構築する。

    エントリポイントの KeyDefinition から参照を再帰的に辿り、
    TreeNode のツリー構造を生成する。

    構築ルール:
      - ルートノードは NodeType.ROOT
      - 各 ValueEntry を処理し、参照・リテラル・空定義に応じた子ノードを生成
      - 循環参照はパスごとの visited セットで検出
      - 深さ制限（MAX_DEPTH）超過は CIRCULAR ノードとして安全停止

    Args:
        key_def: ツリーのルートとなるキー定義。
            通常は find_top_trees() の結果から取得した KeyDefinition。
            任意のキー定義からのツリー構築にも対応。
        registry: パーサーが構築したキーレジストリ。
            resolve() に渡す。
        full_path_index: build_full_path_index() が構築したインデックス。
            resolve() に渡す。

    Returns:
        ルートの TreeNode。node_type は NodeType.ROOT。
        子ノードとして key_def の値行群が再帰展開される。

    Note:
        この関数は例外を投げない。
        全ての入力に対して正常な TreeNode を返す。
    """
    # ルートノードを作成
    root = TreeNode(
        display_name=key_def.name,
        node_type=NodeType.ROOT,
        key_def=key_def,
        value_entry=None,
        ref=None,
    )

    # visited セットにルートのキー名を追加して子ノードを展開
    visited: set[str] = {key_def.name}
    root.children = _expand_key_def(
        key_def, registry, full_path_index, visited, depth=0
    )

    return root


def build_forest(
    top_trees: list[TopTreeInfo],
    registry: KeyRegistry,
    full_path_index: FullPathIndex,
) -> list[TreeNode]:
    """複数のトップツリーから一括でツリーを構築する。

    各 TopTreeInfo の key_def に対して build_tree() を呼び、
    結果を list[TreeNode] として返す。

    Args:
        top_trees: トップツリーの情報リスト。
            find_top_trees() の返却値をそのまま渡す。
        registry: パーサーが構築したキーレジストリ。
        full_path_index: build_full_path_index() が構築したインデックス。

    Returns:
        各トップツリーの ROOT ノードのリスト。
        入力の順序を保持する。
        空リストが渡された場合は空リストを返す。

    Note:
        この関数は例外を投げない。
    """
    # 各 TopTreeInfo の key_def に対して build_tree を呼び、順序を保持して返す
    return [
        build_tree(top.key_def, registry, full_path_index)
        for top in top_trees
    ]


# ---------------------------------------------------------------------------
# 内部関数
# ---------------------------------------------------------------------------


def _expand_key_def(
    key_def: KeyDefinition,
    registry: KeyRegistry,
    full_path_index: FullPathIndex,
    visited: set[str],
    depth: int,
) -> list[TreeNode]:
    """キー定義の値行群を子ノードに展開する。

    key_def の各 ValueEntry を _process_value_entry() で処理し、
    生成された TreeNode をフラットなリストとして返す。

    Args:
        key_def: 展開対象のキー定義。
        registry: キーレジストリ。
        full_path_index: フルパスインデックス。
        visited: 現在の探索パス上で訪問済みのキー名の集合。
            循環参照の検出に使用。パスごとのスコープ。
        depth: 現在の再帰の深さ（0始まり）。
            MAX_DEPTH に達したら安全停止する。

    Returns:
        子ノードのリスト。
        値行がない場合は空リスト。
    """
    children: list[TreeNode] = []
    for ve in key_def.values:
        children.extend(
            _process_value_entry(ve, registry, full_path_index, visited, depth)
        )
    return children


def _resolve_ref(
    ref: WildcardRef,
    value_entry: ValueEntry,
    registry: KeyRegistry,
    full_path_index: FullPathIndex,
    visited: set[str],
    depth: int,
) -> TreeNode:
    """参照を解決し、対応する TreeNode を生成する。

    通常参照・動的参照の inner_ref 共通のロジック。
    resolve() → 循環チェック → 深さチェック → REF ノード生成（再帰展開）
    の判定フローを一箇所にまとめる。

    Args:
        ref: 解決する参照。
        value_entry: この参照が属する値行。
        registry: キーレジストリ。
        full_path_index: フルパスインデックス。
        visited: 現在の探索パス上で訪問済みのキー名の集合。
        depth: 現在の再帰の深さ。

    Returns:
        解決結果に応じた TreeNode（REF / UNRESOLVED / CIRCULAR）。
    """
    result = resolve(ref.full_path, full_path_index, registry)
    if result is None:
        # 解決失敗 → UNRESOLVED ノード
        return TreeNode(
            display_name=ref.name,
            node_type=NodeType.UNRESOLVED,
            value_entry=value_entry,
            ref=ref,
        )

    resolved_kd = result.key_def
    if resolved_kd.name in visited or depth >= MAX_DEPTH:
        # 循環参照検出 or 深さ制限超過 → CIRCULAR ノード
        return TreeNode(
            display_name=resolved_kd.name + CIRCULAR_SUFFIX,
            node_type=NodeType.CIRCULAR,
            value_entry=value_entry,
            ref=ref,
        )

    # 正常: REF ノード → 再帰展開
    child_visited = visited | {resolved_kd.name}
    ref_node = TreeNode(
        display_name=resolved_kd.name,
        node_type=NodeType.REF,
        key_def=resolved_kd,
        value_entry=value_entry,
        ref=ref,
    )
    ref_node.children = _expand_key_def(
        resolved_kd, registry, full_path_index, child_visited, depth + 1
    )
    return ref_node


def _process_value_entry(
    value_entry: ValueEntry,
    registry: KeyRegistry,
    full_path_index: FullPathIndex,
    visited: set[str],
    depth: int,
) -> list[TreeNode]:
    """1つの値行から TreeNode 群を生成する。

    値行内の参照とリテラルを順に処理し、対応する TreeNode を生成する。
    1つの値行から複数のノードが生成されうる（参照 + リテラルの混在）。

    判定フロー:
      - RefType.NORMAL の参照:
        - resolve() 成功 + 循環検出 → CIRCULAR ノード
        - resolve() 成功 + 深さ制限 → CIRCULAR ノード
        - resolve() 成功 + 正常 → REF ノード（再帰展開）
        - resolve() 失敗 → UNRESOLVED ノード
      - RefType.DYNAMIC の参照:
        - DYNAMIC ノード + inner_refs の子ノード
      - リテラル:
        - '"{}"' → EMPTY ノード
        - それ以外 → LITERAL ノード

    Args:
        value_entry: 処理対象の値行。
        registry: キーレジストリ。
        full_path_index: フルパスインデックス。
        visited: 現在の探索パス上で訪問済みのキー名の集合。
        depth: 現在の再帰の深さ。

    Returns:
        生成された TreeNode のリスト。
        参照もリテラルもない値行の場合は空リスト。

    Note:
        生成される各 TreeNode の value_entry には、
        引数の value_entry がそのまま設定される。
        これにより GUI がチェックボックスの ON/OFF を
        元の値行に紐づけて操作できる。
    """
    nodes: list[TreeNode] = []

    # --- 参照の処理 ---
    for ref in value_entry.refs:
        if ref.ref_type == RefType.DYNAMIC:
            # 動的参照: DYNAMIC ノードを作成し、inner_refs を子ノードとして展開
            dynamic_node = TreeNode(
                display_name=ref.raw,
                node_type=NodeType.DYNAMIC,
                value_entry=value_entry,
                ref=ref,
            )
            for inner_ref in ref.inner_refs:
                dynamic_node.children.append(
                    _resolve_ref(
                        inner_ref, value_entry,
                        registry, full_path_index, visited, depth,
                    )
                )
            nodes.append(dynamic_node)
        else:
            # 通常参照 (RefType.NORMAL)
            nodes.append(
                _resolve_ref(
                    ref, value_entry,
                    registry, full_path_index, visited, depth,
                )
            )

    # --- リテラルの処理 ---
    for literal in value_entry.literals:
        if literal == '"{}"':
            # 空定義 → EMPTY ノード
            nodes.append(
                TreeNode(
                    display_name=EMPTY_DISPLAY_NAME,
                    node_type=NodeType.EMPTY,
                    value_entry=value_entry,
                )
            )
        else:
            # 通常リテラル → LITERAL ノード
            nodes.append(
                TreeNode(
                    display_name=literal,
                    node_type=NodeType.LITERAL,
                    value_entry=value_entry,
                )
            )

    return nodes
