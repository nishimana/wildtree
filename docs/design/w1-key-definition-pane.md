# W1: ノード選択 → 右ペインにキー定義表示

## 機能の概要

ツリーウィジェットでノードを選択すると、右ペインにそのキーの定義（YAML 上の値リスト）を表示する。メインエリアを QSplitter で左右に分割し、左にツリー、右に読み取り専用の QTextEdit を配置する。

## タスク種別

**混合**: 既存ファイル `gui/main_window.py` の変更 + 新規モジュールなし

core モジュールの変更は不要。キー定義の取得に必要な機能は `WildcardResolver.resolve()` と `KeyDefinition.raw_values` で既に提供されている。

## 設計判断の理由 (why)

### QSplitter による左右分割

- QSplitter を使うことで、ユーザーが左右ペインの幅比率をドラッグで調整できる
- QHBoxLayout + 固定幅では柔軟性が低く、画面サイズの異なる環境で使いにくい
- QSplitter は Qt 標準のウィジェットで、追加の依存なく使える

### QTextEdit (読み取り専用)

- QLabel ではなく QTextEdit を使う理由: 値リストが長い場合のスクロール対応、テキスト選択・コピー対応
- `setReadOnly(True)` で編集不可にする。編集機能は W1 のスコープ外
- QPlainTextEdit も候補だが、QTextEdit の方が将来的にリッチテキスト（参照のハイライト等）に対応しやすい

### QTreeWidgetItem.setData() による ref_name の紐付け

- 表示テキスト (`text(0)`) には表示名が入るが、これだけでは名前解決できない（同名キーが存在する場合）
- `QTreeWidgetItem.setData(0, Qt.ItemDataRole.UserRole, ref_name)` で TreeNode.ref_name を格納し、選択時に取得して `WildcardResolver.resolve()` に渡す
- 代替案: `dict[QTreeWidgetItem, TreeNode]` のマッピングを保持する方法。こちらは GC 管理が複雑になるため不採用

### _format_key_definition() の分離

- 表示フォーマットのロジックをスロットから分離することで、テストが書きやすくなる
- 将来、フォーマットの変更（シンタックスハイライト等）が必要になった場合の変更箇所が明確

### DEFAULT_WIDTH の変更 (600 → 1000)

- 右ペインを追加するため、ウィンドウ幅が 600px では狭すぎる
- 1000px にして左:右 = 400:600 のデフォルト比率にする

### 却下した代替案

- **右ペインに QListWidget**: 値行をリストアイテムとして表示する案。個々の値行を選択する必要がなく、テキストコピーの利便性から QTextEdit の方が適切
- **右ペインにタブ付きウィジェット**: ファイルパス表示、参照一覧等の追加情報も表示する案。W1 のスコープを超えるため不採用。将来の拡張ポイントとして記録
- **core モジュールに format 関数を追加**: 表示フォーマットは GUI の関心事であり、core に含めるべきではない

## スコープ (scope)

### やること

- `_setup_ui()` のメインエリアを QSplitter に変更（左: QTreeWidget、右: QTextEdit）
- `_connect_signals()` に `_tree_widget.currentItemChanged` → `_on_tree_item_selected` の接続を追加
- `_build_and_display_tree()` と `_populate_tree_item()` で各 QTreeWidgetItem に `setData(0, UserRole, ref_name)` を追加
- `_on_tree_item_selected()` の実装: ref_name の取得 → 名前解決 → 右ペインへの表示
- `_format_key_definition()` の実装: キー名 + 値行リストの整形
- ツリー再構築時に右ペインをクリア（プレースホルダに戻す）

### やらないこと（意図的な対象外）

| 対象外 | 理由 |
|---|---|
| 右ペインでの YAML 編集 | 設計書で明確に対象外としている。YAML は外部エディタで編集する運用 |
| 参照リンクのハイライト/クリック | 将来の拡張。W1 はプレーンテキスト表示のみ |
| ファイルパスの表示 | 将来タブ化する際に対応。W1 では値行のみ |
| QSplitter の状態保存・復元 | QSettings による永続化は W1 のスコープ外 |
| 未解決参照ノードの右ペイン表示 | 未解決参照はツリーに表示されないため対象外 |

## 設計原則

### エラー通知方針（振り返りの教訓）

- 致命的エラー（ディレクトリ読み込み失敗等）: `QMessageBox.warning()` を使う（既存実装を踏襲）
- 軽微な表示問題（ノード選択で解決できない等）: 右ペインにメッセージを表示。ダイアログは出さない

### QTreeWidgetItem のデータ格納

- `setData(column=0, role=Qt.ItemDataRole.UserRole, value=ref_name)` で格納
- `data(column=0, role=Qt.ItemDataRole.UserRole)` で取得
- ルートノードの ref_name はエントリキー名と同じ

## 既存コードとの関係 (context)

### データの流れ

```
[ユーザーがツリーノードをクリック]
    ↓
QTreeWidget.currentItemChanged シグナル
    ↓
_on_tree_item_selected(current, previous)
    ↓
current.data(0, UserRole) → ref_name: str
    ↓
self._resolver.resolve(ref_name) → KeyDefinition | None
    ↓
KeyDefinition.raw_values → list[str]
    ↓
_format_key_definition(key_name, raw_values) → str
    ↓
self._text_detail.setPlainText(formatted_text)
```

### 影響を受ける既存メソッド

| メソッド | 変更内容 | 影響 |
|---|---|---|
| `_setup_ui()` | メインエリアを QSplitter に変更、QTextEdit 追加 | レイアウト構造が変わる。ただし外部からは `_tree_widget` の参照方法が変わらないため、他メソッドへの影響は限定的 |
| `_connect_signals()` | `currentItemChanged` シグナルの接続を追加 | 既存の接続に1行追加するのみ |
| `_build_and_display_tree()` | ルートアイテムに `setData()` を追加、右ペインをクリア | 既存のルートアイテム作成の直後に1行追加 |
| `_populate_tree_item()` | 子アイテムに `setData()` を追加 | 既存の子アイテム作成の直後に1行追加 |

### 変更しないメソッド

- `__init__()`: 既存のフローをそのまま使う（`_setup_ui()` と `_connect_signals()` の呼び出し順序は変わらない）
- `_on_browse()`, `_on_refresh()`, `_on_entry_changed()`: 変更不要
- `_load_cards_dir()`: 変更不要（`_build_and_display_tree()` の呼び出しは同じ）

### core モジュールとの関係

core モジュール (`core/wildcard_parser.py`) の変更は一切不要。既存の公開 API のみを使用する:

- `WildcardResolver.resolve(ref_name: str) -> KeyDefinition | None`
- `KeyDefinition.name: str`
- `KeyDefinition.raw_values: list[str]`
- `KeyDefinition.file_path: Path`（W1 では未使用だが、将来のファイルパス表示で使用可能）
- `TreeNode.ref_name: str`

## 正常系の振る舞い

### ノード選択時

1. ユーザーがツリーノードをクリックする
2. `currentItemChanged` シグナルが発火し、`_on_tree_item_selected()` が呼ばれる
3. `current.data(0, UserRole)` から `ref_name` を取得する
4. `self._resolver.resolve(ref_name)` でキー定義を取得する
5. `_format_key_definition()` で表示テキストを生成する
6. `self._text_detail.setPlainText()` で右ペインに表示する

### 表示フォーマット

```
朝田詩乃体格:
  - slender body
  - __cards/SAO/options/エイジスライダー__
```

ヘッダ行にキー名 + コロン、値行は `  - ` プレフィックス付きで1行ずつ表示する。YAML の元の形式に近い表示にすることで、ユーザーが YAML ファイルとの対応を理解しやすくする。

### ツリー再構築時

1. エントリポイント変更または Refresh ボタン押下
2. `_build_and_display_tree()` が呼ばれる
3. ツリーがクリアされ、右ペインはプレースホルダテキスト `DETAIL_PLACEHOLDER` に戻る

### 初期状態

- アプリ起動直後、ノードが未選択の状態では右ペインにプレースホルダテキストを表示する

## 異常系の振る舞い

| ケース | 発生タイミング | 処理 |
|---|---|---|
| current が None | ツリーがクリアされた時 | 右ペインにプレースホルダテキストを表示 |
| ref_name が None | setData() 未設定の場合（通常は発生しない） | 右ペインにプレースホルダテキストを表示 |
| resolve() が None を返す | 循環参照ノードの選択、または参照先が消失 | 右ペインに「(キー定義が見つかりません)」を表示 |
| _resolver が None | cards_dir 未設定の状態 | 右ペインにプレースホルダテキストを表示 |
| raw_values が空リスト | コメント行のみのキー | ヘッダ行のみ表示（値行なし） |

いずれのケースもダイアログは出さない。右ペインのテキスト更新のみで対応する。

## エッジケース

### 循環参照ノードの選択

循環参照としてマークされたノード（`is_circular=True`）は、テキスト末尾に `(circular ref)` が付いている。このノードを選択した場合:
- `data(0, UserRole)` で ref_name は取得できる
- `resolve()` はキー定義を返す可能性がある（キー自体は存在するため）
- したがって、循環参照ノードであっても正常にキー定義を表示する

### 同名キーが複数ファイルに存在する場合

`ref_name` をそのまま `resolve()` に渡すため、フルパス参照の場合は正しいファイルのキー定義が表示される。短縮形参照の場合は後勝ちのキー定義が表示される。これは既存の名前解決ロジックと一貫している。

### ルートノードの選択

ルートノードも他のノードと同じ扱い。`ref_name` にはエントリキー名が入っており、`resolve()` でキー定義を取得できる。

### 右ペインへの高速連続選択

ユーザーがキーボードの上下矢印キーでノードを高速に切り替えた場合、`currentItemChanged` が連続発火する。各呼び出しで `setPlainText()` を呼ぶだけなので、パフォーマンス問題は発生しない（`resolve()` はインメモリの辞書ルックアップ、`setPlainText()` は Qt のネイティブ処理）。

### 値行が非常に多いキー

プロンプト文字列が多数含まれるキーでは、値行リストが数十行以上になる可能性がある。QTextEdit はスクロール可能なので表示上の問題はない。

## implementer への変更指示

### 1. `_setup_ui()` の変更

メインエリアのツリーウィジェット直接追加を、QSplitter ベースに変更する。

**変更前** (L126-130):
```python
# --- メインエリア: ツリーウィジェット ---
self._tree_widget = QTreeWidget()
self._tree_widget.setHeaderHidden(True)
self._tree_widget.setColumnCount(1)
main_layout.addWidget(self._tree_widget)
```

**変更後**:
```python
# --- メインエリア: QSplitter (左: ツリー, 右: キー定義) ---
self._splitter = QSplitter(Qt.Orientation.Horizontal)

self._tree_widget = QTreeWidget()
self._tree_widget.setHeaderHidden(True)
self._tree_widget.setColumnCount(1)
self._splitter.addWidget(self._tree_widget)

self._text_detail = QTextEdit()
self._text_detail.setReadOnly(True)
self._text_detail.setPlainText(self.DETAIL_PLACEHOLDER)
self._splitter.addWidget(self._text_detail)

self._splitter.setSizes([self.SPLITTER_LEFT_RATIO, self.SPLITTER_RIGHT_RATIO])
main_layout.addWidget(self._splitter)
```

`_setup_ui()` の docstring も更新する:
```
- Main area: QSplitter with QTreeWidget (left) and QTextEdit (right)
```

### 2. `_connect_signals()` の変更

既存の接続の後に1行追加:
```python
self._tree_widget.currentItemChanged.connect(self._on_tree_item_selected)
```

docstring にも追加:
```
- _tree_widget.currentItemChanged -> _on_tree_item_selected
```

### 3. `_build_and_display_tree()` の変更

ルートアイテム作成直後に `setData()` を追加し、ツリークリア時に右ペインをリセットする。

**追加箇所 1**: `self._tree_widget.clear()` の直後に:
```python
self._text_detail.setPlainText(self.DETAIL_PLACEHOLDER)
```

**追加箇所 2**: `root_item = QTreeWidgetItem([display_text])` の直後に:
```python
root_item.setData(0, self.REF_NAME_ROLE, tree.ref_name)
```

### 4. `_populate_tree_item()` の変更

子アイテム作成直後に `setData()` を追加:

```python
child_item = QTreeWidgetItem(parent, [display_text])
child_item.setData(0, self.REF_NAME_ROLE, child.ref_name)
```

### 5. `_on_tree_item_selected()` の実装

スタブの `raise NotImplementedError` を実装に置き換える。

### 6. `_format_key_definition()` の実装

スタブの `raise NotImplementedError` を実装に置き換える。

## テストの指針

### テスト可能な範囲（QApplication なしで可能）

- `_format_key_definition()`: 入力と出力が文字列のため、純粋なロジックテスト

### テストに QApplication が必要な範囲

- `_on_tree_item_selected()`: QTreeWidgetItem を操作するため QApplication が必要
- QSplitter の構成確認
- currentItemChanged シグナルの接続確認

### テストパターン

- ノード選択でキー定義が表示される（正常系）
- 未解決ノード選択でメッセージが表示される
- ツリー再構築で右ペインがクリアされる
- current が None のときプレースホルダが表示される
- raw_values が空のときヘッダのみ表示される
- 循環参照ノードを選択してもクラッシュしない
