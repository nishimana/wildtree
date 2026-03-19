"""トップツリー検出 — 参照されていないキー（エントリポイント）を特定する。

S4 — Stage 5 of the v2 パーサーパイプライン。
レジストリ全体をスキャンし、他のどのキー定義からも参照されていない
キーをトップツリーとして検出する。これらは S5（ツリー構築）のルートノードとなる。

責務:
  - 参照されているキー名の収集（通常参照 + 動的参照の inner_refs）
  - トップツリー（参照されていないキー）の特定

設計方針:
  - 関数ベース。状態を持たず、引数で全情報を受け取る
  - 例外を投げない。空レジストリを含む全入力に対して正常な戻り値を返す
  - FullPathIndex は不要。WildcardRef.name で全参照のキー名が取得可能
  - コメント行内の参照も「参照されている」としてカウントする
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.models import (
    KeyDefinition,
    KeyRegistry,
    RefType,
)


# ---------------------------------------------------------------------------
# トップツリー情報データ
# ---------------------------------------------------------------------------


@dataclass
class TopTreeInfo:
    """トップツリーの情報。

    find_top_trees() が返す構造化データ。
    キー名と対応する KeyDefinition、ファイルパスを含む。

    Attributes:
        name: トップツリーのキー名。
        key_def: 対応する KeyDefinition。
            同名キーが複数ファイルに存在する場合は最後のもの（後勝ち）。
        file_path: key_def.file_path と同じ（アクセスの利便性のため）。
    """

    name: str
    key_def: KeyDefinition
    file_path: Path


# ---------------------------------------------------------------------------
# 参照されているキー名の収集
# ---------------------------------------------------------------------------


def collect_referenced_key_names(registry: KeyRegistry) -> set[str]:
    """レジストリ全体をスキャンし、参照されているキー名の集合を返す。

    全 KeyDefinition の全 ValueEntry の全 WildcardRef を走査し、
    参照先のキー名を集合として収集する。

    収集ルール:
      - 通常参照 (RefType.NORMAL): ref.name を追加
      - 動的参照 (RefType.DYNAMIC): 動的参照自体の name は追加しない
        （テンプレートでありキー名ではない）。
        inner_refs 内の各内部参照の name を追加
      - コメント行 (is_commented=True) 内の参照も同じルールで収集

    Args:
        registry: パーサーが構築したキーレジストリ。

    Returns:
        参照されているキー名の集合。
        空のレジストリの場合は空集合。

    Note:
        コメント行内の参照もカウントする理由:
        コメントアウトは一時的な無効化であり、構造的には参照が存在する。
        コメントアウトした参照先がトップツリーに浮上するとユーザーを混乱させる。
    """
    referenced: set[str] = set()

    for key_defs in registry.values():
        for key_def in key_defs:
            for value_entry in key_def.values:
                for ref in value_entry.refs:
                    if ref.ref_type == RefType.DYNAMIC:
                        # 動的参照自体の name は追加しない。内部参照のみ収集する
                        for inner_ref in ref.inner_refs:
                            referenced.add(inner_ref.name)
                    else:
                        # 通常参照: ref.name を追加
                        referenced.add(ref.name)

    return referenced


# ---------------------------------------------------------------------------
# トップツリーの検出
# ---------------------------------------------------------------------------


def find_top_trees(registry: KeyRegistry) -> list[TopTreeInfo]:
    """参照されていないキーをトップツリーとして特定する。

    全キー名の集合から参照されているキー名の集合を差し引き、
    残ったキーをトップツリーとして返す。

    アルゴリズム:
      1. set(registry.keys()) で全キー名の集合を取得
      2. collect_referenced_key_names(registry) で参照されているキー名を取得
      3. 差分（全キー − 参照されているキー）がトップツリー候補
      4. 各候補に対して TopTreeInfo を構築
      5. name のソート順で返す

    Args:
        registry: パーサーが構築したキーレジストリ。

    Returns:
        トップツリーの情報リスト（名前順ソート済み）。
        空のレジストリの場合は空リスト。
        全キーが参照されている場合も空リスト。

    Note:
        同名キーが複数ファイルに存在する場合、TopTreeInfo.key_def は
        リストの最後の KeyDefinition を使用する（後勝ち、resolver と同じ方針）。
    """
    if not registry:
        return []

    # 全キー名から参照されているキー名を差し引く
    all_key_names = set(registry.keys())
    referenced = collect_referenced_key_names(registry)
    top_tree_names = all_key_names - referenced

    # 各候補に TopTreeInfo を構築（同名キーは後勝ち = リストの最後）
    result: list[TopTreeInfo] = []
    for name in sorted(top_tree_names):
        key_def = registry[name][-1]  # 後勝ち
        result.append(TopTreeInfo(
            name=name,
            key_def=key_def,
            file_path=key_def.file_path,
        ))

    return result
