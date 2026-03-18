"""WildTree v2 データモデル定義。

ワイルドカード YAML のパース結果とツリー構造を表現するデータクラス群。
このモジュールは純粋なデータ定義のみを含み、ロジックは持たない。

データフロー:
  YAML ファイル
    → scanner.py: ファイルパスのリスト
    → parser.py: KeyDefinition（ValueEntry, WildcardRef を含む）
    → resolver.py: キー名からの KeyDefinition 解決
    → tree_builder.py: TreeNode ツリー
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# ---------------------------------------------------------------------------
# 参照の種別
# ---------------------------------------------------------------------------


class RefType(Enum):
    """ワイルドカード参照の種別。

    参照パターンの分類に使う。パーサーが値行テキストを解析して判定する。
    """

    NORMAL = "normal"
    """通常参照: __cards/パス/キー名__ または __キー名__"""

    DYNAMIC = "dynamic"
    """動的参照: __{__変数__}サフィックス__ のように変数展開を含む"""


# ---------------------------------------------------------------------------
# ツリーノードの種別
# ---------------------------------------------------------------------------


class NodeType(Enum):
    """ツリーノードの種別。

    ツリー表示時の描画方法とノードの意味を決定する。
    """

    ROOT = "root"
    """ルートノード: トップツリーのエントリポイント"""

    REF = "ref"
    """参照ノード: 解決済みの通常参照（子ノードを持つ）"""

    LITERAL = "literal"
    """リテラルノード: プロンプトタグ等の値（リーフノード）"""

    DYNAMIC = "dynamic"
    """動的参照ノード: 変数展開を含む参照"""

    UNRESOLVED = "unresolved"
    """未解決参照ノード: 参照先が見つからない（赤字表示）"""

    CIRCULAR = "circular"
    """循環参照ノード: 循環検出で打ち切られたノード"""

    EMPTY = "empty"
    """空定義ノード: "{}" — 未使用スロット"""


# ---------------------------------------------------------------------------
# 参照データ
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WildcardRef:
    """値行テキスト内のワイルドカード参照（__name__ パターン）。

    パーサーが値行テキストからこのオブジェクトを抽出する。
    frozen=True により、レジストリのキーやセットの要素として使用可能。

    Attributes:
        raw: 元テキスト（デリミタ含む）。例: "__cards/SAO/キー名__"
        full_path: 参照フルパス（デリミタ除去後）。例: "cards/SAO/キー名"
        ref_type: 参照の種別（通常 or 動的）
        inner_refs: 動的参照内の変数参照タプル。
            通常参照の場合は空タプル。
            例: __{__cards/姦キー__}{__cards/鬼キー__}__ の場合、
            内部の __cards/姦キー__ と __cards/鬼キー__ がここに入る。

    プロパティ:
        name: 参照キー名（フルパスの最後のスラッシュ以降）。
            例: "cards/SAO/キー名" → "キー名"
    """

    raw: str
    full_path: str
    ref_type: RefType = RefType.NORMAL
    inner_refs: tuple[WildcardRef, ...] = ()

    @property
    def name(self) -> str:
        """参照キー名（フルパスの最後の要素）。

        例:
            "cards/SAO/CH_asada_shino/キー名" → "キー名"
            "キー名" → "キー名"
        """
        # full_path の最後の "/" 以降を返す。"/" がなければ全体を返す
        return self.full_path.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# 値行データ
# ---------------------------------------------------------------------------


@dataclass
class ValueEntry:
    """キー定義内の1つの値行。

    YAML の `  - value` 行に対応する。コメント行（`  # - value`）も保持する。
    行番号を持つことで、エディタがこの行を直接書き換えられる。

    Attributes:
        raw_text: 元の値テキスト（"  - " プレフィックス除去後）。
            コメント行の場合は "# " プレフィックスも除去した中身。
            例: "__cards/xxx__,literal_tag"
        line_number: ファイル内の行番号（1始まり）。編集時の書き換え位置特定に使用。
        is_commented: コメント行（# でコメントアウトされた値行）かどうか。
            True の場合、UI でチェックボックスが OFF で表示される。
        refs: この値行内に含まれる参照のリスト。
            パーサーが raw_text から抽出する。
        literals: この値行内に含まれるリテラル部分のリスト。
            参照でもカンマでもない部分。
            例: "dynamic_angle,dynamic_pose,__cards/シネマシャドウ__"
            → literals = ["dynamic_angle", "dynamic_pose"]

    Note:
        refs と literals はパーサー (parser.py) が設定する。
        パーサー未処理の状態ではどちらも空リスト。
    """

    raw_text: str
    line_number: int
    is_commented: bool = False
    refs: list[WildcardRef] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# キー定義データ
# ---------------------------------------------------------------------------


@dataclass
class KeyDefinition:
    """YAML ファイルのトップレベルキーとその値行群。

    1つの YAML ファイルに複数の KeyDefinition が存在しうる。
    同名の KeyDefinition が異なるファイルに存在する場合、
    レジストリ上では list[KeyDefinition] として管理される。

    Attributes:
        name: キー名。例: "メイン", "シーンまとめ", "朝田詩乃SSNN0001脱00"
        file_path: 定義元の YAML ファイルパス。
        line_number: キー名が記述されている行番号（1始まり）。
            ファイル内での位置特定とエディタでのジャンプに使用。
        values: このキーに属する値行のリスト。
            コメント行も含む（is_commented=True で区別）。

    Note:
        v1 の KeyDefinition はコメント行を除外し raw_values: list[str] のみを
        持っていた。v2 では ValueEntry に構造化し、コメント行も保持する。
    """

    name: str
    file_path: Path
    line_number: int
    values: list[ValueEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# キーレジストリの型エイリアス
# ---------------------------------------------------------------------------

KeyRegistry = dict[str, list[KeyDefinition]]
"""キーレジストリの型。

キー名をキーとし、同名の KeyDefinition のリストを値とする。
同名キーが複数ファイルに存在するケース（重複キー）に対応する。

用途:
  - resolver.py: 名前解決時にキー名で KeyDefinition を検索
  - top_tree.py: トップツリー検出時に全キーと全参照の比較
  - editor.py: 編集後のレジストリ差分更新
"""


# ---------------------------------------------------------------------------
# ツリーノードデータ
# ---------------------------------------------------------------------------


@dataclass
class TreeNode:
    """ツリー表示用のノード。

    tree_builder.py がエントリポイントから再帰的に構築する。
    GUI のツリーウィジェットに直接マッピングされる。

    Attributes:
        display_name: ツリー上の表示名。
            参照ノード: キー名（例: "シネマシャドウ"）
            リテラルノード: プロンプトタグ値（例: "(cinematic_shadow:1.1)"）
            循環参照ノード: キー名 + "(循環)"
            未解決参照ノード: 参照名（赤字表示用）
            空定義ノード: "(空)"
        node_type: ノードの種別
        children: 子ノードのリスト。リーフノードでは空リスト。
        key_def: 対応するキー定義。
            参照ノード・ルートノード: 解決先の KeyDefinition
            リテラル・循環・未解決・空: None
        value_entry: 対応する値行。
            チェックボックスの ON/OFF 切り替えに使用。
            ルートノード: None
            参照ノード・リテラルノード: この値行から展開されたことを示す
        ref: 元の参照情報。
            ルートノード: None
            参照ノード・動的参照ノード・未解決参照ノード: 元の WildcardRef

    Note:
        is_leaf / is_circular / is_unresolved のブールフラグを使っていた v1 と異なり、
        v2 では node_type (NodeType Enum) で種別を統一的に判定する。
    """

    display_name: str
    node_type: NodeType
    children: list[TreeNode] = field(default_factory=list)
    key_def: KeyDefinition | None = None
    value_entry: ValueEntry | None = None
    ref: WildcardRef | None = None
