# Fix: チェックボックストグル操作のパフォーマンス改善

## バグ概要

チェックボックスのトグル操作に 12.3 秒かかる。内訳のうち約 8.7 秒が `build_full_path_index()` のフル再構築に消費されている。

## 1. 原因特定

### 発生箇所

- **ファイル**: `gui/app.py`
- **メソッド**: `_rebuild_tree()` (560-608行目)
- **問題の行**: 587-589行目

```python
# フルパスインデックスを再構築
self._full_path_index = build_full_path_index(
    self._registry, self._cards_dir
)
```

### 呼び出しチェーン

```
_on_item_changed()
  → toggle_comment(file_path, value_entry, enable)  # ファイル書き換え
  → refresh_registry(file_path, registry)            # 1ファイル分の再パース
  → _rebuild_tree()                                  # ★ここが遅い
      → build_full_path_index(registry, cards_dir)   # ~8.7s ← 不要
      → build_tree(key_def, registry, full_path_index)
      → populate_model(tree_node, tree_model)
```

### 根本原因

`_rebuild_tree()` が無条件で `build_full_path_index()` を呼んでいる。これはレジストリ全体（約 43,000 キー定義）を走査してフルパスインデックスを構築する処理であり、約 8.7 秒かかる。

`build_full_path_index()` が構築するインデックスは `KeyDefinition.file_path` と `KeyDefinition.name` の組み合わせから決まる。コメント切替では値行（`ValueEntry`）のコメント状態が変わるだけであり、**キー名もファイルパスも変化しない**。したがって、コメント切替後のフルパスインデックスのフル再構築は論理的に不要。

### なぜ `_rebuild_tree()` で呼んでいるのか

`_rebuild_tree()` は S8（GUI 編集機能）の一部として実装された。当初の設計意図は「レジストリが変更された場合に安全にツリーを再構築する」ことであり、**将来的にキー名の変更やファイル追加/削除を伴う編集操作にも対応できるよう**、保守的にフルパスインデックスを再構築していた。

しかし現在の唯一の呼び出し元は `_on_item_changed()` のコメント切替であり、この操作ではキー名・ファイルパスは不変。

### `refresh_registry` 後のオブジェクト参照の問題

`refresh_registry()` は対象ファイルを再パースし、レジストリ内の `KeyDefinition` オブジェクトを新しいものに差し替える。このとき:

1. **`_full_path_index` 内の古い `KeyDefinition` 参照が stale になる**: インデックスが古い `KeyDefinition` を指したままになる。ただし、コメント切替では `KeyDefinition.name` と `KeyDefinition.file_path` は不変なので、参照解決（`resolve()`）の**キーマッピング自体は正しい**。問題は `resolve()` が返す `ResolveResult.key_def` が古い `KeyDefinition`（コメント切替前の `ValueEntry` を持つ）を返す点。

2. **`build_tree()` は `resolve()` が返した `KeyDefinition` を使って子ノードを展開する**: stale な `KeyDefinition` はコメント切替前の `ValueEntry`（古い `is_commented` フラグ）を持つため、**ツリーのチェックボックス状態が正しく反映されない**。

→ これが `build_full_path_index` を再構築している真の理由。stale な `KeyDefinition` 参照を新しいものに更新する必要がある。

### コメント切替後に `_full_path_index` が変わりうるケース

`build_full_path_index` の出力は以下にのみ依存する:

- `KeyDefinition.name` — コメント切替では不変
- `KeyDefinition.file_path` — コメント切替では不変
- `cards_dir` — 定数

**コメント切替では `_full_path_index` のキー（フルパス文字列）は絶対に変わらない。**

変わるのは値（`KeyDefinition` オブジェクト参照）のみ。`refresh_registry` が該当ファイルの `KeyDefinition` を新しいオブジェクトに差し替えるため、`_full_path_index` 内の参照が古いままになる。

## 2. 修正設計

### 修正方針

フルパスインデックスのフル再構築（~8.7s）を、**差分更新**（該当ファイルの `KeyDefinition` のみ更新）に置き換える。

コメント切替で変わるのは 1 ファイル分の `KeyDefinition` オブジェクト参照のみなので、そのファイルに由来するインデックスエントリだけを更新すればよい。

### 差分更新アルゴリズム

```
refresh_full_path_index(file_path, registry, full_path_index, cards_dir):
  1. full_path_index 内の全エントリを走査
  2. 値の KeyDefinition.file_path が file_path と一致するエントリを特定
  3. registry から同じキー名の新しい KeyDefinition を取得
  4. full_path_index の該当エントリを新しい KeyDefinition で上書き
```

### 変更箇所

| ファイル | 関数/メソッド | 変更内容 |
|---|---|---|
| `core/resolver.py` | `refresh_full_path_index()` (新規) | 差分更新関数を追加 |
| `gui/app.py` | `_on_item_changed()` | `refresh_registry` の後に `refresh_full_path_index` を呼ぶ |
| `gui/app.py` | `_rebuild_tree()` | `build_full_path_index` の呼び出しを削除 |

### 詳細設計

#### 2.1 `core/resolver.py` に `refresh_full_path_index()` を追加

```python
def refresh_full_path_index(
    file_path: Path,
    registry: KeyRegistry,
    full_path_index: FullPathIndex,
    cards_dir: Path,
) -> None:
    """変更されたファイルの KeyDefinition 参照をフルパスインデックス内で更新する。

    refresh_registry() でレジストリが更新された後に呼ぶ。
    full_path_index 内の該当ファイルに由来するエントリを
    新しい KeyDefinition オブジェクトに差し替える。

    コメント切替ではキー名・ファイルパスは不変なので、
    インデックスのキー（フルパス文字列）は変わらない。
    値（KeyDefinition オブジェクト）のみが更新される。

    Args:
        file_path: 変更されたファイルのパス。
        registry: 更新済みのキーレジストリ。
        full_path_index: 更新対象のフルパスインデックス（in-place で変更）。
        cards_dir: cards ディレクトリのルートパス。
    """
    target_path = file_path.resolve()

    # registry から file_path に属する新しい KeyDefinition を収集
    # キー名 → KeyDefinition のマッピングを構築
    new_key_defs: dict[str, KeyDefinition] = {}
    for key_defs in registry.values():
        for kd in key_defs:
            if kd.file_path.resolve() == target_path:
                new_key_defs[kd.name] = kd

    # full_path_index 内の該当エントリを更新
    for full_path, old_kd in full_path_index.items():
        if old_kd.file_path.resolve() == target_path:
            if old_kd.name in new_key_defs:
                full_path_index[full_path] = new_key_defs[old_kd.name]
```

計算量: `O(R + I)` ここで R = registry 内の該当ファイルのキー数、I = full_path_index のエントリ数。
実データでは I ≒ 43,000、R ≒ 数十。フル再構築と同じ O(N) だが、`Path.relative_to()` の呼び出しが不要な分高速。

ただし、さらに効率的な実装として:

```python
def refresh_full_path_index(
    file_path: Path,
    registry: KeyRegistry,
    full_path_index: FullPathIndex,
    cards_dir: Path,
) -> None:
    target_path = file_path.resolve()

    # file_path から cards_dir の相対パスを計算（1回だけ）
    try:
        relative = file_path.relative_to(cards_dir)
    except ValueError:
        return

    parent = relative.parent

    # registry から該当ファイルの新しい KeyDefinition を取得し、
    # フルパスを計算してインデックスを上書き
    for key_defs in registry.values():
        for kd in key_defs:
            if kd.file_path.resolve() == target_path:
                if parent == Path("."):
                    fp = kd.name
                else:
                    fp = parent.as_posix() + "/" + kd.name
                full_path_index[fp] = kd
```

計算量: `O(R)` ここで R = registry 内の該当ファイルのキー数（通常 1〜数十）。フル再構築の `O(N)` に対し大幅に高速。

#### 2.2 `gui/app.py` の `_on_item_changed()` を修正

`refresh_registry` の直後に `refresh_full_path_index` を呼び出す。

```python
# 変更されたファイルのレジストリを更新
from core.editor import refresh_registry
if self._registry is not None:
    refresh_registry(file_path, self._registry)

# フルパスインデックスを差分更新
from core.resolver import refresh_full_path_index
if self._full_path_index is not None and self._cards_dir is not None:
    refresh_full_path_index(
        file_path, self._registry, self._full_path_index, self._cards_dir
    )
```

#### 2.3 `gui/app.py` の `_rebuild_tree()` から `build_full_path_index` を削除

```python
def _rebuild_tree(self) -> None:
    """ツリーを再構築する。

    build_tree → populate_model のパイプラインを実行する。
    refresh_registry と refresh_full_path_index は呼び出し元が事前に呼ぶ。
    """
    from core.tree_builder import build_tree
    from gui.tree_model import populate_model

    # レジストリ / カードディレクトリが未構築の場合は何もしない
    if self._registry is None or self._cards_dir is None:
        return
    if self._full_path_index is None:
        return

    # 現在のトップツリー情報を取得
    current_item = self._list_top_trees.currentItem()
    if current_item is None:
        return

    top_info: TopTreeInfo = current_item.data(TOP_TREE_DATA_ROLE)
    if top_info is None:
        return

    # ★ build_full_path_index の呼び出しを削除

    # ツリーを再構築
    tree_node = build_tree(
        top_info.key_def, self._registry, self._full_path_index
    )

    # モデルに投入（_is_populating ガードで itemChanged を無視）
    self._is_populating = True
    try:
        populate_model(tree_node, self._tree_model)
    finally:
        self._is_populating = False

    # ルートノードを展開
    root_index = self._tree_model.index(0, 0)
    self._tree_view.expand(root_index)

    # 状態を更新
    self._current_tree = tree_node
```

### `top_info.key_def` の stale 問題

`_rebuild_tree()` は `top_info.key_def` を `build_tree` の起点として渡している。この `key_def` は `_load_cards_dir()` 時に `find_top_trees()` から取得されたもの。

コメント切替で `refresh_registry()` が呼ばれると、レジストリ内の `KeyDefinition` は新しいオブジェクトに差し替えられるが、`top_info.key_def` は古いオブジェクトを指したまま。

**影響**: `build_tree()` はルートノードの `key_def.values` を使って子ノードを展開する。ルートの `key_def` が stale だと、ルート直下の子ノードのチェックボックス状態が正しく反映されない。

**対策**: `_rebuild_tree()` 内でレジストリから最新の `KeyDefinition` を取得する。

```python
# レジストリから最新の key_def を取得
key_name = top_info.key_def.name
if key_name in self._registry:
    current_key_def = self._registry[key_name][-1]  # 後勝ち
else:
    return

# ツリーを再構築
tree_node = build_tree(
    current_key_def, self._registry, self._full_path_index
)
```

### 期待される効果

| 処理 | 修正前 | 修正後 |
|---|---|---|
| `build_full_path_index` (フル再構築) | ~8.7s | 削除 |
| `refresh_full_path_index` (差分更新) | — | ~0.001s (該当ファイルのキー数に依存) |
| `build_tree` | ~0.5s | ~0.5s (変化なし) |
| `populate_model` | ~1.5s | ~1.5s (変化なし) |
| **合計** | **~12.3s** | **~3.5s** |

フル再構築の ~8.7s を差分更新の ~0.001s に置き換えることで、約 70% の高速化が見込める。

### リスクと回避策

| リスク | 回避策 |
|---|---|
| 差分更新の漏れ: `refresh_full_path_index` の呼び忘れでインデックスが stale になる | `_on_item_changed` 内で `refresh_registry` と `refresh_full_path_index` をセットで呼ぶ。将来的に他の編集操作が追加された場合も同様のパターンを踏襲する |
| `top_info.key_def` の stale 問題 | `_rebuild_tree` 内でレジストリから最新の `key_def` を取得する |
| 将来のキー名変更・ファイル追加/削除を伴う編集操作 | そのような操作が追加された場合は `_rebuild_tree` 内でフル再構築に戻す、または差分更新ロジックを拡張する。現時点では YAGNI |
| `refresh_full_path_index` 内での `Path.resolve()` のコスト | Windows では `Path.resolve()` が遅い場合がある。必要に応じて `os.path.normcase` で正規化する方式に切り替える |

### テスト方針

1. `refresh_full_path_index` の単体テスト: 差分更新後のインデックスがフル再構築と同じ結果になることを検証
2. `_on_item_changed` のパフォーマンステスト: 実データでトグル操作の所要時間を計測（目標: 4秒以下）
3. 回帰テスト: 既存の `test_editor.py`, `test_tree_builder.py` が全てパスすることを確認
