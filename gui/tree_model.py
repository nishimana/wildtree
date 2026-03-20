"""TreeNode → QStandardItemModel 変換モジュール。

S6 — v2 GUI のツリー表示で使用するモデル構築ロジック。
TreeNode ツリーを QStandardItemModel に変換し、
QTreeView で表示可能な形にマッピングする。

責務:
  - TreeNode → QStandardItem の変換
  - NodeType ごとの色・フォント・プレフィックスの設定
  - is_commented ノードのグレーアウト表示
  - QStandardItem への TreeNode 参照の格納

設計方針:
  - 関数ベース。状態を持たない
  - 全展開（eager）。TreeNode ツリーの全ノードを一括でモデルに追加
  - 3,476 ノードでも 50ms 以内に完了する見込み
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel

from core.models import NodeType, TreeNode

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

TREE_NODE_ROLE: int = Qt.ItemDataRole.UserRole
"""QStandardItem に TreeNode を格納するためのカスタムデータロール。

QStandardItem.setData(tree_node, TREE_NODE_ROLE) で格納し、
QStandardItem.data(TREE_NODE_ROLE) で取得する。
"""

COLOR_DEFAULT: QColor = QColor("#000000")
"""デフォルトのテキスト色（黒）。ROOT / REF ノードに使用。"""

COLOR_LITERAL: QColor = QColor("#006400")
"""リテラルノードのテキスト色（ダークグリーン）。"""

COLOR_DYNAMIC: QColor = QColor("#FF8C00")
"""動的参照ノードのテキスト色（ダークオレンジ）。"""

COLOR_UNRESOLVED: QColor = QColor("#FF0000")
"""未解決参照ノードのテキスト色（赤）。"""

COLOR_COMMENTED: QColor = QColor("#888888")
"""コメントアウトされたノードのテキスト色（グレー）。

is_commented = True の場合、ノードタイプ固有の色をこの色で上書きする。
"""

PREFIX_DYNAMIC: str = "[動的] "
"""動的参照ノードの表示名に付与するプレフィックス。"""

PREFIX_UNRESOLVED: str = "[未解決] "
"""未解決参照ノードの表示名に付与するプレフィックス。"""


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------


def populate_model(tree_node: TreeNode, model: QStandardItemModel) -> None:
    """TreeNode ツリーを QStandardItemModel に投入する。

    モデルをクリアしてから、tree_node をルートアイテムとして追加し、
    子ノードを再帰的に QStandardItem として追加する。

    Args:
        tree_node: ツリーのルートノード（NodeType.ROOT）。
            build_tree() の戻り値をそのまま渡す。
        model: 投入先の QStandardItemModel。
            既存のアイテムはクリアされる。

    Note:
        この関数はモデルの clear() を呼ぶため、既存のデータは失われる。
        QTreeView に setModel() 済みのモデルに対して呼んでも安全。
    """
    # モデルをクリア
    model.clear()

    # ルートアイテムを作成して追加
    root_item = _create_item(tree_node)
    model.appendRow(root_item)

    # 子ノードを再帰的に追加
    _populate_children(root_item, tree_node)


def _create_item(node: TreeNode) -> QStandardItem:
    """TreeNode から QStandardItem を作成する。

    NodeType に応じたテキスト色・フォント・プレフィックスを設定し、
    is_commented の場合はグレーアウト + 取り消し線を適用する。

    表示テキストのルール:
      - ROOT / REF / LITERAL / CIRCULAR / EMPTY: display_name をそのまま使用
      - DYNAMIC: PREFIX_DYNAMIC + display_name
      - UNRESOLVED: PREFIX_UNRESOLVED + display_name

    色のルール:
      - is_commented = True → COLOR_COMMENTED（他の色より優先）
      - ROOT / REF → COLOR_DEFAULT
      - LITERAL → COLOR_LITERAL
      - DYNAMIC → COLOR_DYNAMIC
      - UNRESOLVED → COLOR_UNRESOLVED
      - CIRCULAR / EMPTY → COLOR_COMMENTED

    フォントのルール:
      - ROOT → 太字 (bold)
      - LITERAL → イタリック (italic)
      - is_commented → 取り消し線 (strikethrough) を追加

    データ格納:
      - TREE_NODE_ROLE に TreeNode 参照を格納

    アイテムの状態:
      - 編集不可（setEditable(False)）

    Args:
        node: 変換元の TreeNode。

    Returns:
        設定済みの QStandardItem。
    """
    item = QStandardItem()

    # --- 表示テキストの設定 ---
    # DYNAMIC / UNRESOLVED はプレフィックスを付与、それ以外は display_name そのまま
    if node.node_type == NodeType.DYNAMIC:
        item.setText(PREFIX_DYNAMIC + node.display_name)
    elif node.node_type == NodeType.UNRESOLVED:
        item.setText(PREFIX_UNRESOLVED + node.display_name)
    else:
        item.setText(node.display_name)

    # --- is_commented の判定 ---
    is_commented = (
        node.value_entry is not None and node.value_entry.is_commented
    )

    # --- テキスト色の設定 ---
    if is_commented:
        # コメント色はノードタイプ固有の色を上書き
        item.setForeground(COLOR_COMMENTED)
    elif node.node_type in (NodeType.ROOT, NodeType.REF):
        item.setForeground(COLOR_DEFAULT)
    elif node.node_type == NodeType.LITERAL:
        item.setForeground(COLOR_LITERAL)
    elif node.node_type == NodeType.DYNAMIC:
        item.setForeground(COLOR_DYNAMIC)
    elif node.node_type == NodeType.UNRESOLVED:
        item.setForeground(COLOR_UNRESOLVED)
    elif node.node_type in (NodeType.CIRCULAR, NodeType.EMPTY):
        item.setForeground(COLOR_COMMENTED)
    else:
        item.setForeground(COLOR_DEFAULT)

    # --- フォントの設定 ---
    font = QFont()
    if node.node_type == NodeType.ROOT:
        font.setBold(True)
    if node.node_type == NodeType.LITERAL:
        font.setItalic(True)
    if is_commented:
        font.setStrikeOut(True)
    item.setFont(font)

    # --- データ格納 ---
    item.setData(node, TREE_NODE_ROLE)

    # --- 編集不可 ---
    item.setEditable(False)

    return item


def _populate_children(parent_item: QStandardItem, node: TreeNode) -> None:
    """子ノードを再帰的に QStandardItem として追加する。

    node.children の各子ノードに対して _create_item() で
    QStandardItem を作成し、parent_item に appendRow() で追加する。
    各子の子ノードも再帰的に処理する。

    Args:
        parent_item: 親の QStandardItem。
        node: 子ノードを展開する TreeNode。
    """
    for child_node in node.children:
        # 子の QStandardItem を作成
        child_item = _create_item(child_node)
        # 親に追加
        parent_item.appendRow(child_item)
        # 再帰的に孫ノードを追加
        _populate_children(child_item, child_node)
