"""名前解決 — ワイルドカード参照を KeyDefinition にマッピングする。

S3 — Stage 4 of the v2 パーサーパイプライン。
パーサーが構築した KeyRegistry を使い、WildcardRef の full_path を
対応する KeyDefinition に解決する。

責務:
  - フルパスインデックス（full_path → KeyDefinition）の構築
  - 参照の名前解決（フルパス → 短縮形の2段フォールバック）
  - 動的参照の内部参照の個別解決
  - 未解決参照の一括検出
  - 重複キーの検出

設計方針:
  - クラスではなく関数ベース。状態を持たず、引数で全情報を受け取る
  - 例外を投げない。全てのエラーを戻り値で表現する
  - 循環参照の検出は含まない（tree_builder の責務）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from core.models import (
    FullPathIndex,
    KeyDefinition,
    KeyRegistry,
    RefType,
    WildcardRef,
)


# ---------------------------------------------------------------------------
# 解決結果データ
# ---------------------------------------------------------------------------


@dataclass
class ResolveResult:
    """参照の解決結果。

    resolve() が返す構造化データ。解決先の KeyDefinition に加えて、
    解決方法やあいまいさの有無を記録する。

    Attributes:
        key_def: 解決先の KeyDefinition。
        method: 解決方法。
            "full_path" — フルパスインデックスで直接解決された
            "short" — 短縮形（キー名のみ）で解決された
        is_ambiguous: 短縮形解決で同名キーが複数存在する場合 True。
            フルパス解決の場合は常に False。
    """

    key_def: KeyDefinition
    method: Literal["full_path", "short"]
    is_ambiguous: bool = False


@dataclass
class UnresolvedRef:
    """未解決参照の情報。

    find_unresolved_refs() が返す構造化データ。
    参照自体と、その参照が出現する文脈情報を含む。

    Attributes:
        ref: 解決できなかったワイルドカード参照。
        key_name: この参照を含むキー定義の名前。
        file_path: この参照を含むファイルのパス。
        line_number: この参照を含む値行の行番号。
    """

    ref: WildcardRef
    key_name: str
    file_path: Path
    line_number: int


# ---------------------------------------------------------------------------
# フルパスインデックスの構築
# ---------------------------------------------------------------------------


def build_full_path_index(
    registry: KeyRegistry,
    cards_dir: Path,
) -> FullPathIndex:
    """KeyRegistry からフルパスインデックスを構築する。

    各 KeyDefinition の file_path から cards_dir の相対パスを計算し、
    親ディレクトリ + キー名 を "/" で結合してフルパスとする。
    Windows パスの "\\" は "/" に正規化する。

    構築ルール:
      - file_path が cards_dir の外にある場合はスキップ（ValueError を無視）
      - cards_dir 直下のファイルの場合、full_path はキー名のみ
      - 同一 full_path が複数ある場合は後勝ち（レジストリの順序に準拠）

    Args:
        registry: パーサーが構築したキーレジストリ。
        cards_dir: cards ディレクトリのルートパス。

    Returns:
        フルパスインデックス。full_path → KeyDefinition のマッピング。
        空のレジストリの場合は空辞書。

    Note:
        この関数は例外を投げない。file_path が cards_dir 外の場合は
        その KeyDefinition をスキップする。
    """
    index: FullPathIndex = {}

    for key_defs in registry.values():
        for key_def in key_defs:
            # file_path が cards_dir 外の場合はスキップ
            try:
                relative = key_def.file_path.relative_to(cards_dir)
            except ValueError:
                continue

            # 親ディレクトリを POSIX 形式で取得
            parent = relative.parent
            if parent == Path("."):
                # cards_dir 直下のファイル: full_path はキー名のみ
                full_path = key_def.name
            else:
                # サブディレクトリ: 親ディレクトリ + キー名を "/" で結合
                full_path = parent.as_posix() + "/" + key_def.name

            # 同一 full_path は後勝ち（上書き）
            index[full_path] = key_def

    return index


# ---------------------------------------------------------------------------
# 参照の名前解決
# ---------------------------------------------------------------------------


def resolve(
    full_path: str,
    full_path_index: FullPathIndex,
    registry: KeyRegistry,
) -> ResolveResult | None:
    """ワイルドカード参照の full_path を KeyDefinition に解決する。

    2段フォールバックで解決を試みる:
      1. フルパスインデックスで直接引き
         - full_path が "cards/" で始まる場合、"cards/" を除去して検索
         - それ以外はそのまま検索
      2. 短縮形参照として KeyRegistry を検索
         - full_path の最後の "/" 以降をキー名として検索
         - "/" が含まれない場合は full_path 全体がキー名
         - 同名キーが複数ある場合は後勝ち（リストの最後）

    Args:
        full_path: 参照の full_path（WildcardRef.full_path）。
            例: "cards/SAO/CH_asada/朝田詩乃", "メイン", "朝田詩乃"
        full_path_index: build_full_path_index() が構築したインデックス。
        registry: パーサーが構築したキーレジストリ。

    Returns:
        解決結果の ResolveResult。解決できない場合は None。
        フルパス解決の場合 method="full_path"、
        短縮形解決の場合 method="short"。
        短縮形で同名キーが複数ある場合 is_ambiguous=True。

    Note:
        動的参照の full_path（"{__...}__" を含む）はフルパスインデックスにも
        KeyRegistry にもマッチしないため None が返る。
        動的参照の解決には resolve_dynamic_inner_refs() を使用する。
    """
    # 空文字列はすぐに None を返す
    if not full_path:
        return None

    # ステップ 1: フルパスインデックスで直接引き
    lookup_path = full_path
    if lookup_path.startswith("cards/"):
        # "cards/" プレフィックスを除去して検索
        lookup_path = lookup_path[len("cards/"):]

    # プレフィックス除去後が空文字列なら解決不能
    if not lookup_path:
        return None

    if lookup_path in full_path_index:
        return ResolveResult(
            key_def=full_path_index[lookup_path],
            method="full_path",
        )

    # ステップ 2: 短縮形参照として KeyRegistry を検索
    # full_path の最後の "/" 以降をキー名として使う
    if "/" in full_path:
        key_name = full_path.rsplit("/", 1)[-1]
    else:
        key_name = full_path

    if not key_name:
        return None

    if key_name in registry:
        defs = registry[key_name]
        # 後勝ち: リストの最後の KeyDefinition を返す
        key_def = defs[-1]
        is_ambiguous = len(defs) > 1
        return ResolveResult(
            key_def=key_def,
            method="short",
            is_ambiguous=is_ambiguous,
        )

    # ステップ 3: 解決失敗
    return None


# ---------------------------------------------------------------------------
# 動的参照の内部参照解決
# ---------------------------------------------------------------------------


def resolve_dynamic_inner_refs(
    ref: WildcardRef,
    full_path_index: FullPathIndex,
    registry: KeyRegistry,
) -> dict[WildcardRef, ResolveResult | None]:
    """動的参照の内部参照（inner_refs）を個別に解決する。

    動的参照（RefType.DYNAMIC）に含まれる内部参照の各 WildcardRef に
    対して resolve() を呼び、結果を辞書で返す。

    通常参照（RefType.NORMAL）が渡された場合は空辞書を返す。

    Args:
        ref: 解決対象のワイルドカード参照。
            RefType.DYNAMIC の場合のみ inner_refs を処理する。
        full_path_index: build_full_path_index() が構築したインデックス。
        registry: パーサーが構築したキーレジストリ。

    Returns:
        内部参照 → 解決結果のマッピング。
        解決できない内部参照には None が設定される。
        通常参照や inner_refs が空の場合は空辞書。

    Note:
        この関数は動的参照の「完全な展開」（変数値の代入 → 最終参照名の
        組み立て）は行わない。それは S9 の責務。
        ここでは内部参照を個別に解決し、ツリー構築時に内部参照の
        子ノード表示を可能にする。
    """
    # 通常参照が渡された場合は空辞書を返す
    if ref.ref_type != RefType.DYNAMIC:
        return {}

    # 各 inner_ref に対して resolve() を呼ぶ
    results: dict[WildcardRef, ResolveResult | None] = {}
    for inner_ref in ref.inner_refs:
        results[inner_ref] = resolve(
            inner_ref.full_path, full_path_index, registry
        )

    return results


# ---------------------------------------------------------------------------
# 未解決参照の検出
# ---------------------------------------------------------------------------


def find_unresolved_refs(
    registry: KeyRegistry,
    full_path_index: FullPathIndex,
) -> list[UnresolvedRef]:
    """レジストリ全体をスキャンし、解決できない参照を収集する。

    全 KeyDefinition の全 ValueEntry の全 WildcardRef を走査し、
    各参照に対して resolve() を実行する。解決できない参照を
    UnresolvedRef として収集する。

    動的参照の扱い:
      - 動的参照自体（RefType.DYNAMIC）は「未解決」としない
        （展開前なので判定不能）
      - 動的参照の inner_refs 内の参照が解決できない場合は
        「未解決」として記録する

    Args:
        registry: パーサーが構築したキーレジストリ。
        full_path_index: build_full_path_index() が構築したインデックス。

    Returns:
        未解決参照の情報リスト。全参照が解決可能な場合は空リスト。
        各 UnresolvedRef は参照元のキー名・ファイル・行番号を含む。

    Note:
        112,105 通常参照 + 18,953 動的参照の規模でも、
        各解決が O(1) のため全体で数百ミリ秒以内に完了する見込み。
    """
    unresolved: list[UnresolvedRef] = []

    for key_defs in registry.values():
        for key_def in key_defs:
            for value_entry in key_def.values:
                for ref in value_entry.refs:
                    if ref.ref_type == RefType.DYNAMIC:
                        # 動的参照自体は未解決として記録しない
                        # 内部参照のみチェックする
                        for inner_ref in ref.inner_refs:
                            result = resolve(
                                inner_ref.full_path,
                                full_path_index,
                                registry,
                            )
                            if result is None:
                                unresolved.append(
                                    UnresolvedRef(
                                        ref=inner_ref,
                                        key_name=key_def.name,
                                        file_path=key_def.file_path,
                                        line_number=value_entry.line_number,
                                    )
                                )
                    else:
                        # 通常参照: resolve() で解決を試みる
                        result = resolve(
                            ref.full_path, full_path_index, registry
                        )
                        if result is None:
                            unresolved.append(
                                UnresolvedRef(
                                    ref=ref,
                                    key_name=key_def.name,
                                    file_path=key_def.file_path,
                                    line_number=value_entry.line_number,
                                )
                            )

    return unresolved


# ---------------------------------------------------------------------------
# 重複キーの検出
# ---------------------------------------------------------------------------


def find_duplicate_keys(
    registry: KeyRegistry,
) -> dict[str, list[KeyDefinition]]:
    """同名キーが複数ファイルに存在するケースを検出する。

    KeyRegistry の各エントリで、KeyDefinition のリストが2つ以上の
    ものを抽出する。

    Args:
        registry: パーサーが構築したキーレジストリ。

    Returns:
        重複キー名 → KeyDefinition リストのマッピング。
        重複がない場合は空辞書。
        各リストには2つ以上の KeyDefinition が含まれる。

    Note:
        実データでは重複キーは4件。42,957 ユニークキーのうちごく少数。
        v2-tree-editor.md §5 に定義済みのアルゴリズムと同等。
    """
    return {
        key_name: defs
        for key_name, defs in registry.items()
        if len(defs) > 1
    }
