# S6: GUI -- ツリー表示（読み取り専用）

## タスク種別

新規モジュール → コード成果物あり（`gui/` 以下にスタブを配置）

## 機能の概要

S1-S5 で構築したコア層（パーサーパイプライン + ツリー構築）の成果を PySide6 GUI で表示する。v2 の最初の視覚的成果物。TreeNode ツリーを QTreeView + QStandardItemModel にマッピングし、3ペイン構成のウィンドウで表示する。

読み取り専用。編集機能は S7（YAML エディタ）、S8（GUI 編集機能）で追加する。

## 設計判断の理由（Why）

### 1. QTreeView + QStandardItemModel を採用する理由（v1 の QTreeWidget からの変更）

v1 プロトタイプでは QTreeWidget を使用していた。v2 では QTreeView + QStandardItemModel に変更する。

**理由**:
- QStandardItemModel は Model/View アーキテクチャに基づき、データと表示の分離が明確。S8（編集機能）でモデルデータを変更すると自動的にビューに反映される
- QStandardItem にカスタムデータ（TreeNode 参照）を `setData(role)` で格納でき、v1 の `setData(0, UserRole, ref_name)` より柔軟
- ソート・フィルタリング（QSortFilterProxyModel）を将来的に追加しやすい
- デリゲート（QStyledItemDelegate）によるカスタム描画が容易で、NodeType ごとのアイコン・色分け・グレーアウトが実装しやすい

**却下した代替案**:
- QTreeWidget を引き続き使用: 小規模ツリーには十分だが、Model/View 分離がなく、S8 の編集機能追加時にデータとビューの同期が複雑になる

### 2. 3ペイン構成を採用する理由

v1 は2ペイン（ツリー + 詳細）だったが、v2 では3ペイン（トップツリーリスト + ツリー + 詳細）にする。

**理由**:
- v1 ではエントリポイントをコンボボックスで選択していたが、43,000キーのうち 16,238 がトップツリーであり、コンボボックスでは操作不能
- トップツリーリストペインを左端に配置し、選択するとツリーペインが更新される構成にすることで、ナビゲーションが直感的になる
- 3ペインは設計書 v2-tree-editor.md の GUI 設計に記載されている構成

**却下した代替案**:
- コンボボックスでのトップツリー選択: v1 と同じ問題が再発する
- タブ切り替え: トップツリーが 16,238 個あるためタブは現実的でない
- 検索のみ: ブラウジングのユースケースに対応できない

### 3. トップツリーリストに QListView + QStringListModel ではなく QListWidget を採用する理由

トップツリーリストは単純なキー名のリスト（文字列のリスト）であり、Model/View の複雑さは不要。QListWidget で十分であり、実装がシンプル。

**理由**:
- find_top_trees() の戻り値は `list[TopTreeInfo]`。表示名とデータ（TopTreeInfo）のマッピングが必要だが、QListWidgetItem の `setData(UserRole)` で対応可能
- フィルタリング・ソートは現時点では不要（find_top_trees() がソート済みで返す）
- 将来的に検索フィルタが必要になった場合は QListView + QSortFilterProxyModel への移行を検討する

### 4. TreeNode → QStandardItem のマッピング方針: 全展開（eager）を維持する理由

S5 の tree_builder は全展開（eager expansion）でツリーを構築する。GUI 層でも全ノードを一括でモデルに追加する方針を取る。

**理由**:
- S5 の build_tree() が返す TreeNode ツリーは最大 3,476 ノード（メイン）。QStandardItemModel への全投入はパフォーマンス上問題ない
- 遅延展開（QAbstractItemModel の canFetchMore/fetchMore）は実装が複雑で、3,476 ノードに対してはオーバーエンジニアリング
- 検索機能（W3 のリファイン）で全ノードの走査が必要なため、全展開が前提

**パフォーマンス見積もり**:
- QStandardItem 1つあたりの追加: 数マイクロ秒
- 3,476 QStandardItem の一括追加: 約 10-50ms
- ユーザー体感: 即座（100ms 以下で完了）

### 5. NodeType ごとの表示仕様をデリゲートではなく QStandardItem のプロパティで実現する理由

S6（読み取り専用）ではカスタムデリゲートを使わず、QStandardItem の setForeground / setIcon / setFont で表示差分を実現する。

**理由**:
- S6 の表示要件（テキスト色、アイコン、グレーアウト）は QStandardItem の標準プロパティで全て対応可能
- カスタムデリゲートは S8（チェックボックスの表示・操作）で初めて必要になる可能性がある
- 読み取り専用の段階ではシンプルな実装を優先し、必要になったら拡張する

### 6. 詳細ペインに QTextEdit ではなく QTextBrowser を採用する理由

v1 は QTextEdit(readOnly=True) を使用していた。v2 では QTextBrowser に変更する。

**理由**:
- QTextBrowser は元々読み取り専用であり、setReadOnly(True) が不要
- ファイルパスをクリック可能なリンクとして表示する拡張が容易
- HTML/リッチテキストのレンダリングが標準機能として組み込まれている（参照のハイライト等）
- 読み取り専用の S6 に適切。S8 で編集機能を追加する際は詳細ペインの再設計を行う

### 7. モジュール分割の方針

v1 は `gui/main_window.py` の1ファイルに全機能を集約していた。v2 では以下に分離する:

- `gui/main_window.py` — v1 のプロトタイプ。変更しない
- `gui/app.py` — v2 メインウィンドウ（3ペイン構成、シグナル接続、初期化フロー）
- `gui/tree_model.py` — TreeNode → QStandardItemModel 変換ロジック
- `gui/detail_pane.py` — 詳細ペイン（ノード選択時のキー定義表示）

**理由**:
- コア層と同じく責務ごとにモジュールを分離する
- `tree_model.py` は TreeNode → QStandardItem のマッピングロジックに集中し、Qt のウィジェット構成からは独立。テスト可能
- `detail_pane.py` はキー定義の表示フォーマットに集中。これもテスト可能
- `app.py` は3つのペインの統合・シグナル接続・初期化フローに集中

### 8. 初期化フロー: cards ディレクトリの読み込みパイプライン

cards ディレクトリのロード時に S1-S5 のパイプラインを順に実行する。

```
cards_dir
  → scan_yaml_files()           [S2: scanner]
  → build_registry()            [S2: parser]
  → build_full_path_index()     [S3: resolver]
  → find_top_trees()            [S4: top_tree]
  → (トップツリーリスト更新)     [GUI]
  → (ユーザーがトップツリーを選択)
  → build_tree()                [S5: tree_builder]
  → populate_model()            [S6: tree_model]
  → (ツリービュー更新)           [GUI]
```

このパイプラインは `_load_cards_dir()` メソッドで実装する。全スキャンは初回ロード・Refresh時のみ実行する。

### 9. 検索機能は S6 のスコープ外とする理由

v1（W3）で実装した検索機能は、v2 のツリー構造に合わせてリファインが必要。S6 は読み取り専用の基本表示に集中し、検索は後のスプリントで対応する。

**理由**:
- v1 の検索は QTreeWidget.findItems() に依存しているが、v2 では QTreeView + QStandardItemModel に変更されるため、検索ロジックの再実装が必要
- S6 のスコープを絞ることで、設計・テスト・実装の品質を維持する
- 検索は独立した機能として、S6 完了後に追加可能

### 却下した代替案まとめ

| 案 | 却下理由 |
|---|---|
| QTreeWidget を継続使用 | Model/View 分離がなく、S8 での編集機能追加時にデータ同期が複雑になる |
| 2ペイン構成 | 16,238 トップツリーのナビゲーションに対応できない |
| 遅延展開 (fetchMore) | 3,476 ノードに対してオーバーエンジニアリング |
| カスタムデリゲート | S6 の表示要件は QStandardItem のプロパティで対応可能 |
| 検索機能を S6 に含める | スコープが広がりすぎる。QTreeView への移行で再実装が必要 |
| QTextEdit を詳細ペインに使用 | QTextBrowser の方が読み取り専用のユースケースに適切 |

## スコープ（Scope）

### やること

- `gui/app.py`: v2 メインウィンドウ（3ペイン構成）
  - 上段: cards パス表示 + Browse ボタン + Refresh ボタン
  - 左ペイン: トップツリーリスト（QListWidget）
  - 中央ペイン: ツリービュー（QTreeView + QStandardItemModel）
  - 右ペイン: 詳細表示（QTextBrowser）
  - シグナル接続（トップツリー選択 → ツリー更新、ノード選択 → 詳細更新）
- `gui/tree_model.py`: TreeNode → QStandardItemModel 変換
  - NodeType ごとの表示仕様（色・アイコン・グレーアウト）
  - QStandardItem へのカスタムデータ格納（TreeNode 参照）
- `gui/detail_pane.py`: ノード選択時の詳細表示
  - キー名、ファイルパス、行番号、値行一覧の表示
  - is_commented の視覚的区別

### やらないこと（意図的な対象外）

| 対象外 | 理由 |
|---|---|
| 検索機能 | v2 ツリー構造に合わせたリファインが必要。S6 後に独立スプリントで対応 |
| チェックボックスによるコメント切り替え | S8 の責務 |
| YAML の書き換え | S7（editor）の責務 |
| プログレスバー | 初期実装では省略。パフォーマンス問題が出たら追加 |
| QSettings による状態保存・復元 | 将来の改善 |
| キーボードショートカット | 将来の改善 |
| ステータスバー | 将来の改善。情報表示は詳細ペインに集約 |
| 動的参照の完全展開表示 | S9 の責務 |
| トップツリーリストのフィルタリング | 将来の改善 |

## 設計原則

### 1. コア層と GUI 層の分離

- GUI 層はコア層のデータモデル（TreeNode, KeyDefinition, ValueEntry, TopTreeInfo）を読み取り専用で使用する
- GUI 層からコア層の関数を直接呼ぶ（scan_yaml_files, build_registry, build_full_path_index, find_top_trees, build_tree）
- コア層は GUI 層の存在を知らない（逆方向の依存なし）

### 2. tree_model.py のテスト可能性

- `populate_model()` は TreeNode を受け取り QStandardItemModel を返す。Qt のモデル API でテスト可能
- ビジュアル要素（色・フォント）は定数として定義し、テストで検証可能にする

### 3. 例外を投げない原則の継続

- コア層と同じく、GUI 層も可能な限り例外を投げない
- ファイル読み込みエラーは QMessageBox で通知する（v1 と同じ）
- ノード選択で情報が取得できない場合は詳細ペインにメッセージを表示する

## 既存コードとの関係（Context）

### v1 プロトタイプ（gui/main_window.py）との対応

| v1 要素 | v2 の対応 | 変更点 |
|---|---|---|
| QTreeWidget | QTreeView + QStandardItemModel | Model/View 分離 |
| QComboBox (エントリポイント選択) | QListWidget (トップツリーリスト) | 16,238 エントリ対応 |
| QTextEdit (詳細ペイン) | QTextBrowser (詳細ペイン) | 読み取り専用に最適化 |
| core.wildcard_parser の全 API | core/scanner + parser + resolver + top_tree + tree_builder | モジュール分離済み |
| 2ペイン (ツリー + 詳細) | 3ペイン (リスト + ツリー + 詳細) | トップツリーリスト追加 |
| `_build_and_display_tree()` | `_on_top_tree_selected()` + tree_model.populate_model() | 責務分離 |

### S1-S5 のデータフロー

```
gui/app.py
  ├── core/scanner.py
  │     └── scan_yaml_files(cards_dir) → list[Path]
  ├── core/parser.py
  │     └── build_registry(yaml_files) → KeyRegistry
  ├── core/resolver.py
  │     └── build_full_path_index(registry, cards_dir) → FullPathIndex
  ├── core/top_tree.py
  │     └── find_top_trees(registry) → list[TopTreeInfo]
  └── core/tree_builder.py
        └── build_tree(key_def, registry, full_path_index) → TreeNode

gui/tree_model.py
  └── populate_model(tree_node) → QStandardItemModel

gui/detail_pane.py
  └── format_node_detail(tree_node) → str
```

### 保持するデータ（MainWindow の状態）

| 属性 | 型 | 用途 |
|---|---|---|
| `_cards_dir` | `Path \| None` | 現在の cards ディレクトリパス |
| `_registry` | `KeyRegistry \| None` | パーサーが構築したキーレジストリ |
| `_full_path_index` | `FullPathIndex \| None` | フルパスインデックス |
| `_top_trees` | `list[TopTreeInfo]` | トップツリー情報リスト |
| `_current_tree` | `TreeNode \| None` | 現在表示中のツリーのルートノード |

## 正常系・異常系の振る舞い

### 初期化

| 状況 | 振る舞い |
|---|---|
| cards_dir 引数なしで起動 | 3ペインが空状態で表示。Browse ボタンで選択可能 |
| cards_dir 引数付きで起動 | 自動でスキャン→パース→トップツリーリスト表示 |
| cards_dir が存在しない | QMessageBox.warning() でエラー表示 |

### トップツリー選択

| 状況 | 振る舞い |
|---|---|
| トップツリーをクリック | ツリービューに TreeNode ツリーが表示される |
| 別のトップツリーをクリック | ツリービューが新しいツリーに更新される。詳細ペインはクリア |
| トップツリーが0件 | リストが空。ツリービューも空 |

### ノード選択

| 状況 | 振る舞い |
|---|---|
| REF / ROOT ノードを選択 | 詳細ペインにキー名、ファイルパス、行番号、値行一覧を表示 |
| LITERAL ノードを選択 | 詳細ペインにリテラル値を表示 |
| UNRESOLVED ノードを選択 | 詳細ペインに「未解決参照」のメッセージと参照テキストを表示 |
| CIRCULAR ノードを選択 | 詳細ペインに「循環参照」のメッセージを表示 |
| DYNAMIC ノードを選択 | 詳細ペインに動的参照の情報を表示 |
| EMPTY ノードを選択 | 詳細ペインに「空定義」のメッセージを表示 |
| コメントアウトされたノードを選択 | 詳細ペインに表示。コメント状態がわかるように区別する |
| 選択が解除された | 詳細ペインにプレースホルダテキストを表示 |

### Refresh

| 状況 | 振る舞い |
|---|---|
| Refresh ボタン押下 | cards_dir を再スキャンし、トップツリーリスト・ツリービュー・詳細ペインを全更新 |
| cards_dir 未選択で Refresh | 何もしない |

## エッジケース

| ケース | 期待される扱い |
|---|---|
| トップツリーが 16,238 件 | QListWidget で全件表示。スクロール可能 |
| メインの全展開（3,476 ノード） | QStandardItemModel に全投入。パフォーマンス問題なし |
| is_commented=True のノード | グレーアウト（フォントカラーをグレーに） |
| UNRESOLVED ノード | 赤字で表示 |
| CIRCULAR ノード | 表示名に "(循環)" サフィックス。アイコンで区別 |
| DYNAMIC ノード | 動的参照のアイコンで区別。子ノードに inner_refs の展開結果 |
| EMPTY ノード | "(空)" と表示 |
| 同一キーが複数ブランチで展開 | ダイヤモンド参照。各ブランチで正常に表示される（S5 の設計通り） |
| 値行がゼロ個のキー | ツリーノードは表示されるが子ノードなし。詳細ペインにキー名のみ |
| Browse で無効なディレクトリを選択 | QMessageBox.warning() でエラー表示 |

## TreeNode → QStandardItemModel へのマッピング方針

### マッピングの基本ルール

1. TreeNode 1つ → QStandardItem 1つ
2. TreeNode.children → QStandardItem の子 QStandardItem（appendRow）
3. 再帰的にマッピング（全展開）

### QStandardItem へのデータ格納

| カスタムロール | 格納するデータ | 用途 |
|---|---|---|
| `Qt.ItemDataRole.UserRole` | TreeNode 参照 | ノード選択時に TreeNode の全情報にアクセスする |

TreeNode 参照を直接格納することで、v1 の ref_name 格納 → resolve() のルックアップが不要になる。TreeNode が保持する key_def, value_entry, ref に直接アクセスできる。

### テキスト表示

| NodeType | 表示テキスト | ソース |
|---|---|---|
| ROOT | `TreeNode.display_name` | キー名 |
| REF | `TreeNode.display_name` | キー名 |
| LITERAL | `TreeNode.display_name` | プロンプトタグ値 |
| DYNAMIC | `TreeNode.display_name` | 参照の raw テキスト |
| UNRESOLVED | `TreeNode.display_name` | 参照名 |
| CIRCULAR | `TreeNode.display_name` | "キー名 (循環)" |
| EMPTY | `TreeNode.display_name` | "(空)" |

全 NodeType で `TreeNode.display_name` をそのまま `QStandardItem.setText()` に設定する。

## NodeType ごとの表示仕様

### 色分け

| NodeType | テキスト色 | 背景色 | 条件 |
|---|---|---|---|
| ROOT | デフォルト（黒） | なし | — |
| REF | デフォルト（黒） | なし | is_commented でない場合 |
| REF (コメント) | グレー (#888888) | なし | value_entry.is_commented = True |
| LITERAL | ダークグリーン (#006400) | なし | — |
| LITERAL (コメント) | グレー (#888888) | なし | value_entry.is_commented = True |
| DYNAMIC | ダークオレンジ (#FF8C00) | なし | — |
| UNRESOLVED | 赤 (#FF0000) | なし | — |
| CIRCULAR | グレー (#888888) | なし | — |
| EMPTY | グレー (#888888) | なし | — |

### フォント

| NodeType | フォントスタイル | 条件 |
|---|---|---|
| ROOT | 太字 | — |
| REF | 通常 | — |
| LITERAL | イタリック | — |
| is_commented の全ノード | 取り消し線（strikethrough） | value_entry.is_commented = True |

### アイコン（将来の拡張用。S6 初期実装ではテキストプレフィックスで代替）

S6 初期実装ではアイコンファイルを用意せず、テキストプレフィックスでノードタイプを視覚的に区別する：

| NodeType | プレフィックス | 意味 |
|---|---|---|
| ROOT | なし | ルートノード |
| REF | なし | 参照ノード（最も一般的なので装飾なし） |
| LITERAL | なし | リテラル（イタリック + 色で区別） |
| DYNAMIC | `[動的]` | 動的参照 |
| UNRESOLVED | `[未解決]` | 未解決参照 |
| CIRCULAR | なし | 循環（display_name に "(循環)" 含む） |
| EMPTY | なし | 空定義（display_name が "(空)"） |

### コメントアウトされたノード（is_commented）のグレーアウト

`TreeNode.value_entry` が存在し、`value_entry.is_commented == True` の場合:
- テキスト色をグレー (#888888) に変更
- フォントに取り消し線を追加
- ノードタイプ固有の色はグレーで上書きされる

## パフォーマンス考慮

### 初期化パイプライン

| フェーズ | 処理 | 推定時間 |
|---|---|---|
| scan_yaml_files | 271 ファイルの検出 | < 100ms |
| build_registry | 271 ファイルのパース | < 2s |
| build_full_path_index | インデックス構築 | < 50ms |
| find_top_trees | トップツリー検出 | < 50ms |
| **合計** | | **< 3s** |

※ verify_v2.py の実データ実行結果に基づく。

### トップツリー選択時

| フェーズ | 処理 | 推定時間 |
|---|---|---|
| build_tree | TreeNode ツリー構築 | < 50ms |
| populate_model | QStandardItemModel への投入 | < 50ms |
| QTreeView の表示更新 | ビューの再描画 | < 50ms |
| **合計** | | **< 150ms** |

3,476 ノード（メイン）の場合でも 150ms 以下でツリーが表示される見込み。ユーザーが体感する遅延は許容範囲。

### メモリ

- TreeNode: 3,476 ノード x 約200B ≒ 700KB
- QStandardItem: 3,476 アイテム x 約500B ≒ 1.7MB
- 合計: 約 2.4MB — デスクトップアプリとしては無視できるサイズ

## ウィンドウレイアウト

```
+-------------------------------------------------------------------+
| WildTree v2                                                 [_][X] |
+-------------------------------------------------------------------+
| cards: [/path/to/cards]                      [Browse...] [Refresh] |
+-------------------------------------------------------------------+
| Top Trees    | Tree View               | Detail                    |
| +---------+  | +--------------------+  | +----------------------+  |
| | メイン    |  | | メイン              |  | | キー名: メイン       |  |
| | メインNP  |  | | ├── デフォルト     |  | | ファイル: main.yaml  |  |
| | ...      |  | | │   ├── シネマ...  |  | | 行番号: 1            |  |
| |          |  | | │   └── バック...  |  | |                      |  |
| |          |  | | ├── アングル      |  | | 値:                   |  |
| |          |  | | └── シーンまとめ   |  | |   - __cards/xxx__    |  |
| |          |  | |     ├── 朝田...   |  | |   - # __cards/yyy__  |  |
| |          |  | |     └── 白洲...   |  | |   - literal_value    |  |
| +---------+  | +--------------------+  | +----------------------+  |
+-------------------------------------------------------------------+
```

### ペイン比率

QSplitter で3ペインを水平方向に配置する。初期比率:

| ペイン | 比率 | ピクセル（1200px ウィンドウの場合） |
|---|---|---|
| トップツリーリスト | 1 | 200px |
| ツリービュー | 3 | 600px |
| 詳細ペイン | 2 | 400px |

### ウィンドウサイズ

- デフォルト幅: 1200px（v1 の 1000px から拡大。3ペインに合わせて）
- デフォルト高さ: 800px（v1 と同じ）

## 詳細ペインの表示フォーマット

### ROOT / REF ノード選択時

```
キー名: メイン
ファイル: C:/path/to/cards/main.yaml
行番号: 1

値:
  - __cards/デフォルト__
  # - __cards/無効化された参照__
  - literal_value
```

- キー名、ファイルパス（絶対パス）、行番号をヘッダとして表示
- 値行は YAML の元の形式に近い表示
- コメント行は `# ` プレフィックス付きで表示（is_commented = True の場合）

### LITERAL ノード選択時

```
リテラル値: (cinematic_shadow:1.1)
```

LITERAL ノードの TreeNode には key_def が設定されておらず（None）、
value_entry 経由では直接キー名を取得できないため、所属キー情報は表示しない。

### UNRESOLVED ノード選択時

```
[未解決参照]
参照: __cards/存在しないキー__

この参照は解決できませんでした。
参照先のキーが存在しないか、パスが正しくない可能性があります。
```

### CIRCULAR ノード選択時

```
[循環参照]
参照: __cards/キー名__

このノードは循環参照により展開が打ち切られました。
```

### DYNAMIC ノード選択時

```
[動的参照]
参照: __{__cards/キャラキー__}NP__

変数参照を含む動的参照です。
内部参照は子ノードとして展開されています。
```

### EMPTY ノード選択時

```
[空定義]
値: "{}"

このエントリは空定義です。
```

## 関数一覧

### `gui/app.py`

| 関数/メソッド | シグネチャ | 説明 |
|---|---|---|
| `WildTreeWindow.__init__` | `(self, cards_dir: Path \| None = None, parent: QWidget \| None = None) -> None` | ウィンドウ初期化。UI 構築、シグナル接続、初期ロード |
| `_setup_ui` | `(self) -> None` | 3ペインの UI を構築 |
| `_connect_signals` | `(self) -> None` | シグナルとスロットを接続 |
| `_on_browse` | `(self) -> None` | Browse ボタン: ディレクトリ選択ダイアログ |
| `_on_refresh` | `(self) -> None` | Refresh ボタン: 再スキャン |
| `_load_cards_dir` | `(self) -> None` | cards ディレクトリのロードパイプライン |
| `_on_top_tree_selected` | `(self) -> None` | トップツリーリスト選択: ツリー構築と表示 |
| `_on_tree_node_selected` | `(self, current: QModelIndex, previous: QModelIndex) -> None` | ツリーノード選択: 詳細ペイン更新 |

### `gui/tree_model.py`

| 関数 | シグネチャ | 説明 |
|---|---|---|
| `populate_model` | `(tree_node: TreeNode, model: QStandardItemModel) -> None` | TreeNode ツリーを QStandardItemModel に投入 |
| `_create_item` | `(node: TreeNode) -> QStandardItem` | TreeNode から QStandardItem を作成（色・フォント・データ設定） |
| `_populate_children` | `(parent_item: QStandardItem, node: TreeNode) -> None` | 子ノードを再帰的に QStandardItem として追加 |

### `gui/detail_pane.py`

| 関数 | シグネチャ | 説明 |
|---|---|---|
| `format_node_detail` | `(node: TreeNode) -> str` | TreeNode の情報を詳細表示用の文字列にフォーマット |
| `_format_ref_detail` | `(node: TreeNode) -> str` | REF / ROOT ノードの詳細フォーマット |
| `_format_literal_detail` | `(node: TreeNode) -> str` | LITERAL ノードの詳細フォーマット |
| `_format_unresolved_detail` | `(node: TreeNode) -> str` | UNRESOLVED ノードの詳細フォーマット |
| `_format_circular_detail` | `(node: TreeNode) -> str` | CIRCULAR ノードの詳細フォーマット |
| `_format_dynamic_detail` | `(node: TreeNode) -> str` | DYNAMIC ノードの詳細フォーマット |
| `_format_empty_detail` | `(node: TreeNode) -> str` | EMPTY ノードの詳細フォーマット |

### 定数

#### `gui/app.py`

| 定数 | 値 | 説明 |
|---|---|---|
| `WINDOW_TITLE` | `"WildTree v2"` | ウィンドウタイトル |
| `DEFAULT_WIDTH` | `1200` | ウィンドウのデフォルト幅 |
| `DEFAULT_HEIGHT` | `800` | ウィンドウのデフォルト高さ |
| `SPLITTER_SIZES` | `[200, 600, 400]` | 3ペインの初期サイズ比 |
| `DETAIL_PLACEHOLDER` | `"(ノードを選択するとキー定義を表示します)"` | 詳細ペインの初期テキスト |

#### `gui/tree_model.py`

| 定数 | 値 | 説明 |
|---|---|---|
| `TREE_NODE_ROLE` | `Qt.ItemDataRole.UserRole` | QStandardItem に TreeNode を格納するロール |
| `COLOR_DEFAULT` | `QColor("#000000")` | デフォルトテキスト色 |
| `COLOR_LITERAL` | `QColor("#006400")` | リテラルノードのテキスト色 |
| `COLOR_DYNAMIC` | `QColor("#FF8C00")` | 動的参照ノードのテキスト色 |
| `COLOR_UNRESOLVED` | `QColor("#FF0000")` | 未解決参照ノードのテキスト色 |
| `COLOR_COMMENTED` | `QColor("#888888")` | コメントアウトノードのテキスト色 |
| `PREFIX_DYNAMIC` | `"[動的] "` | 動的参照ノードの表示プレフィックス |
| `PREFIX_UNRESOLVED` | `"[未解決] "` | 未解決参照ノードの表示プレフィックス |

## エラー種別

| エラー | 発生条件 | 処理 |
|---|---|---|
| FileNotFoundError | cards_dir が存在しない | QMessageBox.warning() で通知 |
| NotADirectoryError | cards_dir がディレクトリでない | QMessageBox.warning() で通知 |
| 予期しない例外 | スキャン/パース中の想定外エラー | QMessageBox.warning() で通知。アプリは続行 |

GUI 層のメソッドは例外を投げない。全てのエラーを UI 上で通知する。

## conftest.py フィクスチャ設計

### 既存フィクスチャの活用

S6 のテストでは既存のフィクスチャを活用し、TreeNode を構築してから GUI コンポーネントに渡す:

- `simple_cards_dir`: 基本テスト。少数ノードのツリー表示
- `multi_file_cards_dir`: クロスファイル参照を含むツリー表示
- `commented_ref_cards_dir`: コメントアウトノードのグレーアウト表示テスト

### 新規フィクスチャの要否

- QApplication フィクスチャ: テスト全体で1つの QApplication インスタンスを共有する `qapp` フィクスチャが必要
- TreeNode フィクスチャ: 各 NodeType のノードを含むテスト用 TreeNode を構築するヘルパーフィクスチャ

### テストパターン

**tree_model.py**:
- populate_model で TreeNode が QStandardItemModel に正しく変換される
- NodeType ごとのテキスト色が正しい
- is_commented のノードがグレー + 取り消し線
- UserRole に TreeNode が格納される
- 子ノードの再帰的追加

**detail_pane.py**:
- format_node_detail が各 NodeType に対して正しいフォーマットを返す
- REF ノードでキー名・ファイルパス・行番号・値行が含まれる
- UNRESOLVED / CIRCULAR / DYNAMIC / EMPTY の固有メッセージ

**app.py**:
- QApplication が必要なテストは最小限に抑える
- _load_cards_dir のパイプラインが正しく動作する（統合テスト）
- トップツリー選択 → ツリー表示の連携
- ノード選択 → 詳細ペイン更新の連携
