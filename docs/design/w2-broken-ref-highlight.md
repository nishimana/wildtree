# W2: 壊れた参照のハイライト

## 機能の概要

ツリー表示で、解決できない参照（壊れた参照）を赤字で視覚的にハイライトする。現在はツリーに表示されていない未解決参照を、ノードとして表示し、壊れていることをひと目で分かるようにする。

## タスク種別

**混合**: 既存ファイル `core/wildcard_parser.py` と `gui/main_window.py` の両方を変更。新規モジュールなし。

## 設計判断の理由 (why)

### TreeNode に `is_unresolved` フラグを追加する

- 既存の `is_leaf` は「子ノードが0個」を意味し、`is_circular` は「循環参照で打ち切り」を意味する。壊れた参照はこれらとは異なる概念であり、専用のフラグが必要
- `is_leaf` を流用しない理由: `is_leaf=True` は「キー定義は存在するが、そのキーに参照がない（リテラル値のみ）」というケースを含む。壊れた参照（キー定義自体が存在しない）と意味が異なる
- 代替案として `is_unresolved` ではなく `is_broken` も検討したが、`resolve()` が `None` を返すことを直接反映する `is_unresolved` の方が core の語彙と一貫している

### `build_tree()` の変更（未解決参照をツリーに含める）

- 現在の `build_tree()` では `resolver.resolve(ref.name)` が `None` を返す子ノードを `continue` でスキップしている
- W2 ではこのスキップを廃止し、未解決参照も `TreeNode(is_unresolved=True)` としてツリーに含める
- これにより、GUI 側は `is_unresolved` フラグを見るだけで赤字表示を判定でき、GUI が名前解決ロジックを知る必要がない

### 赤字表示に `QTreeWidgetItem.setForeground()` を使用する

- Qt の QTreeWidgetItem で特定ノードの文字色を変えるには `setForeground(column, QBrush)` が標準的な方法
- アイコン付加やフォント変更など他の方法もあるが、赤字が最もシンプルで「壊れている」ことを直感的に伝える
- 色覚多様性を考慮し、将来的にツールチップや取り消し線を追加する余地を残すが、W2 のスコープでは赤字のみ

### 壊れた参照ノードの表示名

- `ref.name`（参照名）を表示名として使う。キー定義が存在しないため `key_def.name` は取得できない
- 参照名に `cards/` プレフィックスが付く場合は最後のスラッシュ以降をキー名として表示する（`cards/SAO/CH_asada/不明キー` -> `不明キー`）
- フルの ref_name は `setData(UserRole)` に格納し、右ペインの「(キー定義が見つかりません)」表示に使える

### 却下した代替案

- **壊れた参照ノードを表示せず、親ノードにマークを付ける案**: 壊れているのはどの参照かが分かりにくくなるため不採用
- **壊れた参照ノードに `(broken)` ラベルを追加する案**: 赤字だけで十分に識別可能。ラベル追加は冗長。ツールチップに情報を載せる方が邪魔にならない
- **GUI 側で `resolve()` を呼んで壊れた参照を判定する案**: ツリー構築時に既に判定済みの情報を GUI で再判定するのは無駄。`is_unresolved` フラグで core → GUI に情報を渡す方が関心の分離として正しい

## スコープ (scope)

### やること

- `TreeNode` に `is_unresolved: bool` フィールドを追加
- `build_tree()` の `_build_node()` で、未解決参照を `is_unresolved=True` でツリーに含める
- `_build_and_display_tree()` と `_populate_tree_item()` で `is_unresolved` ノードの文字色を赤に設定
- `UNRESOLVED_COLOR` 定数を `MainWindow` に追加
- 壊れた参照ノードの表示名に参照名から抽出したキー名を使用

### やらないこと（意図的な対象外）

| 対象外 | 理由 |
|---|---|
| 壊れた参照の自動修復 | 修復ロジックは複雑であり、W2 のスコープを超える |
| 壊れた参照の集計・レポート | 将来機能。W2 は視覚化のみ |
| 色のカスタマイズ設定 | QSettings による設定はスコープ外 |
| 色覚多様性対応（取り消し線、アイコン等） | 将来の改善。W2 では赤字のみ |
| 壊れた参照の右ペイン表示の変更 | 既に W1 で「(キー定義が見つかりません)」が実装済み。W2 では変更しない |
| 循環参照ノードの色変更 | 循環参照は別概念。W2 のスコープ外 |

## 設計原則

### 壊れた参照の表示名

implementer は以下のルールに従う:

1. `ref.name` にスラッシュが含まれる場合、最後のスラッシュ以降をキー名として表示する
   - 例: `cards/SAO/CH_asada/不明キー` -> `不明キー`
2. スラッシュが含まれない場合、`ref.name` をそのまま表示名にする
   - 例: `不明キー` -> `不明キー`
3. この表示名抽出ロジックは `_build_node()` 内で行う（core の責務）

### 赤字表示のタイミング

`_populate_tree_item()` でアイテム作成直後に設定する。既存の `is_circular` チェックと同じパターンに従う。

### is_unresolved ノードの子ノード

`is_unresolved=True` のノードには子ノードがない（キー定義が存在しないので参照も取得できない）。`children` は空リストのまま。

## 既存コードとの関係 (context)

### データの流れ

```
build_tree() の _build_node()
    |
    for ref in refs:
        child_key_def = resolver.resolve(ref.name)
        |
        [現在] child_key_def is None -> continue (スキップ)
        [W2後] child_key_def is None -> TreeNode(is_unresolved=True) を追加
    |
    v
TreeNode.is_unresolved = True
    |
    v
_populate_tree_item() / _build_and_display_tree()
    |
    if child.is_unresolved:
        child_item.setForeground(0, QBrush(UNRESOLVED_COLOR))
```

### 影響を受ける既存コード

#### `core/wildcard_parser.py`

| 箇所 | 変更内容 | 影響 |
|---|---|---|
| `TreeNode` dataclass (L57-75) | `is_unresolved: bool = False` フィールド追加 | 既存コードは `is_unresolved` を参照しないため影響なし。デフォルト値 `False` により既存の TreeNode 生成コードも変更不要 |
| `_build_node()` 内の子ノード構築ループ (L558-568) | `child_key_def is None` のとき `continue` ではなく `TreeNode(is_unresolved=True)` を追加 | **ロジック変更**。これまでスキップされていた未解決参照がツリーに出現するようになる |

#### `gui/main_window.py`

| 箇所 | 変更内容 | 影響 |
|---|---|---|
| `MainWindow` クラス定数 | `UNRESOLVED_COLOR` 定数追加 | 新規追加のみ |
| `_build_and_display_tree()` (L348-354) | ルートノードの `is_unresolved` チェック追加 | ルートが壊れた参照である場合は通常ないが、防御的にチェック |
| `_populate_tree_item()` (L379-387) | `is_unresolved` チェックと `setForeground()` の追加 | 既存の `is_circular` チェックと同じパターンで追加 |
| import 文 | `QBrush`, `QColor` の追加 | `PySide6.QtGui` からのインポート |

### 変更しないコード

- `_on_tree_item_selected()`: 壊れた参照ノードを選択した場合、`resolve()` が `None` を返すので既存の「(キー定義が見つかりません)」表示がそのまま動作する。変更不要
- `_format_key_definition()`: 壊れた参照では呼ばれないので変更不要
- `_load_cards_dir()`, `_on_browse()`, `_on_refresh()`, `_on_entry_changed()`: 変更不要
- `_connect_signals()`: 変更不要
- `_setup_ui()`: 変更不要

### 既存テストへの影響

`test_parser.py` の `test_ツリー構築_未解決参照はツリーに含まれない` (L676-695) は **W2 の変更により失敗する**。

このテストは「未解決参照がツリーに含まれない」ことをアサートしている:
```python
assert "non_existent_key" not in child_names
```

W2 後は未解決参照もツリーに含まれるようになるため、このアサーションは逆転する。**ただし、テストの変更は architect のスコープ外** であり、tester エージェントが W2 のテスト作成時に対応する。設計書でこの影響を明記しておく。

## 正常系の振る舞い

### 壊れた参照がツリーに赤字で表示される

1. YAML ファイルの値行に `__存在しないキー__` という参照がある
2. `build_tree()` が `resolver.resolve("存在しないキー")` を呼び、`None` が返る
3. `TreeNode(name="存在しないキー", ref_name="存在しないキー", is_unresolved=True)` が子ノードとして追加される
4. GUI の `_populate_tree_item()` で `is_unresolved=True` を検出し、`setForeground(0, QBrush(UNRESOLVED_COLOR))` を呼ぶ
5. ツリー上で「存在しないキー」が赤字で表示される

### フルパス参照が壊れている場合

1. YAML ファイルの値行に `__cards/SAO/CH_asada/存在しないキー__` という参照がある
2. `build_tree()` が `resolver.resolve("cards/SAO/CH_asada/存在しないキー")` を呼び、`None` が返る
3. `ref.name` = `"cards/SAO/CH_asada/存在しないキー"` → 最後のスラッシュ以降 = `"存在しないキー"` を表示名にする
4. `TreeNode(name="存在しないキー", ref_name="cards/SAO/CH_asada/存在しないキー", is_unresolved=True)` が追加される
5. ツリー上で「存在しないキー」が赤字で表示される

### 壊れた参照ノードを選択した場合

1. ユーザーが赤字の壊れた参照ノードをクリックする
2. `_on_tree_item_selected()` が呼ばれる
3. `current.data(0, UserRole)` から `ref_name` を取得
4. `resolver.resolve(ref_name)` が `None` を返す
5. 右ペインに「(キー定義が見つかりません)」が表示される（既存動作のまま）

## 異常系の振る舞い

| ケース | 処理 |
|---|---|
| 壊れた参照とリテラル値が混在する値行 | `extract_refs_from_line()` は `__name__` パターンのみ抽出。リテラル値はツリーに表示されない（既存動作のまま） |
| 全ての参照が壊れている | キーの全子ノードが赤字表示。親ノードは `is_unresolved=False` のまま（キー自体は存在する） |
| ルートノード自体が壊れた参照 | `_build_node()` がルート解決時に `is_leaf=True` を返す既存動作。`is_unresolved` は False（ルートはエントリポイントなので「参照」ではなく「キー名の直接指定」） |

## エッジケース

### 循環参照との違い

- **循環参照** (`is_circular=True`): キー定義は存在するが、再帰的な展開が無限ループになるため打ち切ったノード。表示テキストに `(circular ref)` が追加される
- **壊れた参照** (`is_unresolved=True`): キー定義自体が存在しない（`resolve()` が `None`）。赤字で表示される
- 同時に `is_circular=True` かつ `is_unresolved=True` になることはない。循環参照検出は `resolve()` より先に行われ、訪問済みキーの場合は `is_circular=True` で打ち切る。`is_unresolved=True` になるのは `resolve()` が `None` を返した場合のみ

### 複数の壊れた参照

1つのキーに複数の壊れた参照がある場合、それぞれ個別の赤字ノードとしてツリーに表示される。

```yaml
parent:
  - __broken_ref_1__
  - __valid_ref__
  - __broken_ref_2__
```

→ ツリー表示:
```
parent
  broken_ref_1  (赤字)
  valid_ref
  broken_ref_2  (赤字)
```

### 壊れた参照ノードの子ノード

壊れた参照ノードには子ノードがない。キー定義が存在しないため、そのキーの値行も存在せず、さらなる参照を辿ることができない。

### is_leaf との関係

`is_unresolved=True` のノードは `is_leaf=True` でもある。ただしこの2つは異なる意味を持つ:
- `is_leaf=True, is_unresolved=False`: キー定義は存在するが参照を持たない（正常なリーフ）
- `is_leaf=True, is_unresolved=True`: キー定義が存在しない（壊れた参照）

### 壊れた参照と is_leaf の整合性

`build_tree()` の既存ロジックで `is_leaf` は `len(children) == 0` で判定される。壊れた参照ノードは `children=[]` で生成するため、`is_leaf=True` になる。これは意図通り。

## implementer への変更指示

### 1. `TreeNode` にフィールド追加 (`core/wildcard_parser.py`)

`is_circular` の直後に追加:

```python
@dataclass
class TreeNode:
    name: str
    ref_name: str
    children: list[TreeNode] = field(default_factory=list)
    is_leaf: bool = False
    is_circular: bool = False
    is_unresolved: bool = False  # 追加
```

docstring の Attributes に以下を追加:
```
is_unresolved: True if this node's reference could not be resolved
    (resolve() returned None). These nodes have no children and
    are displayed with a red highlight in the GUI.
```

### 2. `_build_node()` の子ノード構築ロジック変更 (`core/wildcard_parser.py`)

**変更前** (L558-568):
```python
for ref in refs:
    child_key_def = resolver.resolve(ref.name)
    # 解決できない参照はツリーに含めない
    if child_key_def is None:
        continue
    child_node = _build_node(
        ref_name=ref.name,
        display_name=child_key_def.name,
        visited=visited_with_current,
    )
    children.append(child_node)
```

**変更後**:
```python
for ref in refs:
    child_key_def = resolver.resolve(ref.name)
    if child_key_def is None:
        # 壊れた参照: ツリーに含め、is_unresolved=True にする
        # 表示名は ref.name の最後のスラッシュ以降
        display_name = ref.name.rsplit("/", 1)[-1]
        children.append(TreeNode(
            name=display_name,
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
```

### 3. `MainWindow` に定数追加 (`gui/main_window.py`)

`CIRCULAR_REF_LABEL` の近くに追加:

```python
UNRESOLVED_COLOR: QColor = QColor("red")
```

### 4. import 文に `QBrush`, `QColor` を追加 (`gui/main_window.py`)

```python
from PySide6.QtGui import QBrush, QColor
```

### 5. `_build_and_display_tree()` にルートの赤字チェック追加

**追加箇所**: `root_item = QTreeWidgetItem([display_text])` の直後、`root_item.setData()` の前:

```python
if tree.is_unresolved:
    root_item.setForeground(0, QBrush(self.UNRESOLVED_COLOR))
```

### 6. `_populate_tree_item()` に赤字チェック追加

**追加箇所**: `child_item.setData(0, self.REF_NAME_ROLE, child.ref_name)` の直後:

```python
if child.is_unresolved:
    child_item.setForeground(0, QBrush(self.UNRESOLVED_COLOR))
```

## テストの指針

### 既存テストの影響

- `test_ツリー構築_未解決参照はツリーに含まれない` (test_parser.py L676-695): W2 の変更で失敗する。tester が更新または置換する必要がある

### テストパターン (core)

- 壊れた参照が TreeNode として含まれる (is_unresolved=True)
- 壊れた参照ノードの表示名が正しい（短縮形・フルパス形）
- 壊れた参照ノードの is_leaf=True
- 壊れた参照ノードの children が空
- 壊れた参照と正常な参照が混在するケース
- 全ての参照が壊れているケース
- 壊れた参照と循環参照が同時に存在するケース

### テストパターン (GUI)

- 壊れた参照ノードの文字色が赤い
- 正常なノードの文字色がデフォルト（赤ではない）
- 壊れた参照ノード選択で右ペインに「(キー定義が見つかりません)」が表示される
- UNRESOLVED_COLOR 定数の値チェック
- ツリー再構築後も壊れた参照が赤字のまま

### テストに必要なフィクスチャ

`conftest.py` に壊れた参照を含むフィクスチャを追加する:

```python
@pytest.fixture()
def broken_ref_cards_dir(tmp_path: Path) -> Path:
    """A cards directory containing broken (unresolved) references."""
    cards_dir = tmp_path / "cards"
    _write_yaml(
        cards_dir / "test.yaml",
        (
            "entry:\n"
            "  - __existing_key__\n"
            "  - __non_existent_key__\n"
            "\n"
            "existing_key:\n"
            "  - leaf value\n"
        ),
    )
    return cards_dir
```
