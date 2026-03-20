# S8: GUI 編集機能 -- チェックボックス + リアルタイムツリー更新

## タスク種別

既存コード変更（`gui/app.py`, `gui/tree_model.py`）→ コード成果物（スタブ）不要

## 機能の概要

S6（ツリー表示）の QTreeView にチェックボックスを追加し、ユーザーのチェック操作で S7（editor.py）の `toggle_comment` を呼び出す。YAML ファイルの書き換え後、レジストリを更新してツリーを再構築し、選択位置を復元する。

v2 の核心機能「その場で編集」の実現。

## 設計判断の理由（Why）

### 1. QStandardItem.setCheckable + itemChanged シグナルを採用する理由

チェックボックスの実現方式として、QStandardItem の組み込みチェック機能（`setCheckable(True)` + `setCheckState()`）を使い、QStandardItemModel の `itemChanged` シグナルでチェック操作を検知する。

**理由**:
- QStandardItem のチェック機能は Qt 組み込みであり、カスタムデリゲートやカスタムウィジェットが不要。最小限のコード変更で実現できる
- `itemChanged` シグナルはチェック状態変更時に自動的に発火する。手動でのイベントフィルタリングが不要
- S6 設計時に「S8 でカスタムデリゲートが必要になる可能性がある」と検討したが、QStandardItem のチェック機能で十分と判断した

**却下した代替案**:
- QStyledItemDelegate でチェックボックスを描画: QStandardItem の組み込み機能で同じことが実現でき、不要な複雑さを持ち込む
- QTreeView のクリックイベントを自前で処理: チェックボックスのヒットテスト・状態管理を手動で行う必要があり、バグの温床になる

### 2. チェックボックスを value_entry を持つノードのみに付ける理由

全ノードにチェックボックスを付けるのではなく、`TreeNode.value_entry` が存在するノードのみ `setCheckable(True)` とする。

**理由**:
- チェックボックスの意味は「この値行を有効/無効にする」。値行に紐づかないノード（ROOT ノード）にチェックボックスがあると混乱する
- ROOT ノードは value_entry=None であり、toggle_comment の対象外。チェックボックスを付けても操作対象がない
- ツリーのルートにチェックボックスがあると「全有効/全無効の一括操作」と誤解される可能性がある

**チェックボックス対象の判定ルール**:
- `node.value_entry is not None` → `setCheckable(True)`
- `node.value_entry is None` → `setCheckable(False)`（デフォルト）
- チェック状態: `value_entry.is_commented == False` → `Qt.CheckState.Checked`、`True` → `Qt.CheckState.Unchecked`

### 3. 全ツリー再構築方式を採用する理由

チェック操作後のツリー更新方式として、「変更されたノードだけ差分更新」ではなく「ツリー全体の再構築」を採用する。

**理由**:
- コメント切り替えは参照先のキー定義の有効/無効を変える。コメント解除すると新たな参照が有効になり、その先にサブツリーが展開される可能性がある。差分更新ではこのサブツリー展開を正しく計算するのが困難
- `toggle_comment` → `refresh_registry` → `build_full_path_index` → `build_tree` → `populate_model` のパイプラインは既に検証済み。新しいロジックを書く必要がない
- パフォーマンス: `build_tree`（< 50ms）+ `populate_model`（< 50ms）= 100ms 以下。ユーザーのチェック操作に対して十分高速
- S7 設計時に「全再構築方式」を採用済み。同じ方針を GUI 層でも踏襲する

**却下した代替案**:
- 差分更新（変更ノードだけ再描画）: コメント解除で新たな参照が有効になるケース（サブツリー展開）の正確な差分計算が困難。バグのリスクが高い
- TreeNode のインプレース変更 + モデルの部分更新: TreeNode は dataclass であり、build_tree が新しいツリーを返す設計。既存の TreeNode を変更する設計に合わない

### 4. 選択位置復元を「ノードパス」ベースで行う理由

ツリー再構築後に以前選択していたノードの位置を復元する。復元の手がかりとして、ルートからのノード名のパス（例: `["メイン", "シーンまとめ", "朝田詩乃"]`）を使用する。

**理由**:
- QModelIndex はモデル再構築で無効になるため、インデックスベースの復元は使えない
- TreeNode のオブジェクト参照も再構築で新しいオブジェクトに置き換わるため使えない
- ノード名のパスはモデル非依存で、ツリー構造が大きく変わらない限り一意にノードを特定できる
- コメント切り替えではツリー構造の大枠は変わらない（切り替えたノードの子が展開/折りたたまれるだけ）ため、パスベースの復元は高い成功率が期待できる

**復元失敗時の挙動**: パスが一致するノードが見つからない場合、ルートノードを選択する。エラーにしない。

### 5. itemChanged シグナルのガードが必要な理由

`populate_model` 内で QStandardItem のチェック状態を設定すると、`itemChanged` シグナルが発火する。このシグナルがチェックボックス操作ハンドラを呼ぶと、ツリー再構築中に再帰的な再構築が始まる無限ループが発生する。

**対策**: フラグ（`_is_populating: bool`）を設け、`populate_model` 中は `itemChanged` ハンドラを無視する。

**理由**:
- `blockSignals(True)` でモデル全体のシグナルを止める方法もあるが、他のシグナル（例: `rowsInserted` 等）も止まり、QTreeView の内部状態が不整合になる可能性がある
- フラグベースのガードは明示的で副作用が少ない。実装も簡単

### 6. 詳細ペインの表示を S6 のまま維持する理由

S6 設計時に「S8 で詳細ペインの再設計を行う」と言及されていたが、S8 では詳細ペインの変更を行わない。

**理由**:
- 現在の詳細ペイン（QTextBrowser + format_node_detail）はノードの情報を十分に表示しており、チェックボックス操作と連携するために再設計する必然性がない
- チェック操作後のツリー再構築で、選択復元が成功すれば `_on_tree_node_selected` が呼ばれて詳細ペインも更新される。追加ロジックは不要
- 将来的に詳細ペインから直接値行の有効/無効を切り替える UI が必要になったら、独立した改善タスクとして扱う

### 却下した代替案まとめ

| 案 | 却下理由 |
|---|---|
| カスタムデリゲートでチェックボックス描画 | QStandardItem の組み込み機能で十分 |
| 全ノードにチェックボックス | ROOT ノードには操作対象（value_entry）がなく混乱する |
| 差分ツリー更新 | コメント解除によるサブツリー展開の正確な差分計算が困難 |
| QModelIndex ベースの選択復元 | モデル再構築でインデックスが無効化される |
| blockSignals(True) でシグナル抑制 | 他のシグナルも止まり QTreeView の内部状態が不整合になるリスク |
| 詳細ペインの再設計 | 現状で十分。変更の必然性がない |

## スコープ（Scope）

### やること

- `gui/tree_model.py` の `_create_item` 変更: value_entry を持つノードにチェックボックスを追加
  - `setCheckable(True)` / `setCheckState()` の設定
- `gui/app.py` の変更:
  - `_on_item_changed` ハンドラ: チェック操作 → toggle_comment → 再構築パイプライン
  - `_rebuild_tree` メソッド: refresh_registry → build_full_path_index → build_tree → populate_model
  - `_save_selected_path` / `_restore_selected_path`: ツリー再構築前後の選択位置復元
  - `_is_populating` フラグ: populate_model 中の itemChanged シグナル無視
  - `_connect_signals` への itemChanged シグナル接続追加
  - EditResult エラー時の QMessageBox 表示

### やらないこと（意図的な対象外）

| 対象外 | 理由 |
|---|---|
| 詳細ペインからの編集操作 | 独立した改善タスク。S8 はツリービューのチェックボックスに集中 |
| Undo/Redo | v2 フェーズ1 では対象外（v2-tree-editor.md 未決定事項） |
| 値行の追加/削除 | S7 スコープ外。editor.py が対応していない |
| 展開状態の保存・復元 | 選択位置の復元のみ。展開状態は将来の改善 |
| プログレスバー | 再構築は 100ms 以下。不要 |
| 複数ノードの一括チェック操作 | 1ノードずつの操作で十分。将来の改善 |
| detail_pane.py の変更 | 表示フォーマットの変更は不要 |

## 設計原則

### 1. 既存パイプラインの再利用

チェック操作後の再構築は、既存の関数をそのまま呼ぶ。新しいロジックを書かない。

```
toggle_comment(file_path, value_entry, enable)
  → refresh_registry(file_path, registry)
  → build_full_path_index(registry, cards_dir)
  → build_tree(key_def, registry, full_path_index)
  → populate_model(tree_node, model)
```

S7 設計書 (s7-yaml-editor.md) の「S8 GUI 層からの呼び出しパターン」がそのまま適用される。

### 2. コア層は変更しない

S8 では `core/` 配下のモジュールを一切変更しない。全ての変更は `gui/` 配下に限定される。

- `core/editor.py`: toggle_comment, refresh_registry をそのまま使用
- `core/models.py`: データモデルの変更なし
- `core/tree_builder.py`: build_tree をそのまま使用
- `core/resolver.py`: build_full_path_index をそのまま使用

### 3. 例外を投げない原則の継続

- toggle_comment の EditResult.success が False の場合、QMessageBox.warning で通知してツリーを変更しない
- 選択復元に失敗した場合はルートノードを選択する。エラーにしない
- itemChanged ハンドラ内の全処理を try-except で保護し、予期しない例外も QMessageBox で通知する

### 4. チェックボックスの意味の一貫性

- Checked = 値行が有効（is_commented=False）
- Unchecked = 値行が無効（is_commented=True、YAML 上でコメントアウト）
- この対応はツリー表示のグレーアウト表示（S6）と一致する

## 既存コードとの関係（Context）

### 変更対象ファイルと既存の責務

| ファイル | 現在の責務 | S8 での追加責務 |
|---|---|---|
| `gui/tree_model.py` | TreeNode → QStandardItem 変換（色・フォント・データ格納） | チェックボックスの設定（setCheckable + setCheckState） |
| `gui/app.py` | 3ペイン構成、パイプライン統合、シグナル接続 | チェック操作ハンドラ、再構築パイプライン、選択位置復元 |

### 変更しないファイル

| ファイル | 理由 |
|---|---|
| `gui/detail_pane.py` | 表示フォーマットの変更は不要 |
| `core/editor.py` | S7 で完成済み。そのまま使用 |
| `core/models.py` | データモデルの変更は不要 |
| `core/tree_builder.py` | そのまま使用 |
| `core/resolver.py` | そのまま使用 |
| `core/parser.py` | そのまま使用 |

### tree_model.py の _create_item への変更

現在の `_create_item` は表示プロパティ（テキスト・色・フォント）と TREE_NODE_ROLE を設定している。S8 では以下を追加する:

- `node.value_entry is not None` の場合に `setCheckable(True)` を呼ぶ
- チェック状態を `value_entry.is_commented` に基づいて設定する

この変更は `_create_item` 関数の末尾に追加する形で実現でき、既存の表示ロジックには影響しない。

### app.py のシグナル接続への追加

現在の `_connect_signals`:
- `_btn_browse.clicked` → `_on_browse`
- `_btn_refresh.clicked` → `_on_refresh`
- `_list_top_trees.currentItemChanged` → `_on_top_tree_selected`
- `_tree_view.selectionModel().currentChanged` → `_on_tree_node_selected`

S8 で追加:
- `_tree_model.itemChanged` → `_on_item_changed`

### app.py の内部状態への追加

| 属性 | 型 | 用途 |
|---|---|---|
| `_is_populating` | `bool` | populate_model 実行中かどうか。True の間は itemChanged ハンドラを無視 |

既存の状態（`_cards_dir`, `_registry`, `_full_path_index`, `_top_trees`, `_current_tree`）はそのまま。

### データフロー: チェック操作時

```
ユーザーがチェックボックスをクリック
  │
  ▼
_tree_model.itemChanged シグナル発火
  │
  ▼
_on_item_changed(item: QStandardItem)
  │
  ├── _is_populating == True → return（ガード）
  │
  ├── item.data(TREE_NODE_ROLE) → TreeNode を取得
  │
  ├── TreeNode.value_entry を確認
  │   └── value_entry が None → return（チェック対象外）
  │
  ├── 親ノードの key_def.file_path を取得（→ file_path）
  │   └── 親の key_def が None → return（異常状態）
  │
  ├── チェック状態の判定
  │   └── item.checkState() == Qt.CheckState.Checked → enable=True
  │
  ├── toggle_comment(file_path, value_entry, enable)
  │   └── EditResult.success == False → QMessageBox.warning + return
  │
  ├── _rebuild_tree()
  │   ├── refresh_registry(file_path, registry)
  │   ├── build_full_path_index(registry, cards_dir)
  │   ├── build_tree(current_top_tree.key_def, registry, full_path_index)
  │   └── populate_model(tree_node, model)  ※ _is_populating=True の間
  │
  └── _restore_selected_path(saved_path)
```

### file_path の取得: 親ノードの key_def を使う

toggle_comment に渡す `file_path` は **value_entry が書かれているファイル** のパスでなければならない。

TreeNode の構造上、ノード自身の `key_def` は**参照先**のキー定義であり、`value_entry` は**参照元**（親キー定義）の値行を指す。この2つのファイルパスは異なる。

```
例: シーンまとめ（scenes.yaml） の子ノード「朝田詩乃」
  - node.key_def.file_path = asada.yaml    ← 参照先（朝田詩乃の定義ファイル）
  - node.value_entry.line_number = 2       ← scenes.yaml 内の行番号
  - 親ノード.key_def.file_path = scenes.yaml  ← value_entry が書かれたファイル ★これが正解
```

**ルール**: QStandardItem の `parent()` から親アイテムを取得し、親アイテムの TreeNode の `key_def.file_path` を toggle_comment に渡す。

| 親のタイプ | file_path の取得元 |
|---|---|
| ROOT ノード | ROOT.key_def.file_path |
| REF ノード | REF.key_def.file_path |
| 親なし（ルート自身） | value_entry が None なのでチェック不可（ガード済み） |

**注意**: QStandardItem.parent() はルート直下の子の場合 `None` を返す（Qt の仕様）。この場合は `model.invisibleRootItem()` の子ではなく、ルートアイテム（ツリーの ROOT ノードに対応する QStandardItem）の子なので、`item.parent()` が None になる。ルート直下の子に対しては `model.item(0)` でルートの QStandardItem を取得し、そこから TreeNode の key_def.file_path を得る。

## 正常系・異常系の振る舞い

### チェック操作

| 状況 | 振る舞い |
|---|---|
| チェック ON（コメント解除） | toggle_comment(enable=True) → YAML の `# ` 除去 → ツリー再構築。解除されたノードが有効になり、子ノードが展開される |
| チェック OFF（コメント化） | toggle_comment(enable=False) → YAML に `# ` 付与 → ツリー再構築。コメント化されたノードがグレーアウト + 取り消し線 |
| 冪等操作（状態変化なし） | toggle_comment が何もせず EditResult(success=True) を返す。ツリー再構築は実行する（参照の有効/無効は変わっていないため構造は同じ） |
| populate_model 中のチェック | _is_populating ガードにより無視される |

### 再構築パイプライン

| 状況 | 振る舞い |
|---|---|
| 再構築成功 | ツリーが更新され、以前の選択位置に復元される |
| 選択復元成功 | 詳細ペインが更新される（_on_tree_node_selected が発火） |
| 選択復元失敗 | ルートノードが選択される |
| _registry が None（未ロード状態でのチェック操作） | 発生しない。ツリーが表示されている時点で registry は構築済み |

### エラーハンドリング

| 状況 | 振る舞い |
|---|---|
| toggle_comment が EditResult(success=False) | QMessageBox.warning でエラーメッセージを表示。ツリーを変更しない |
| 予期しない例外 | try-except で捕捉し、QMessageBox.warning で通知。ツリーを変更しない |
| key_def が None のノードでチェック操作 | ガードで無視（操作対象なし）。通常は発生しない |

## エッジケース

| ケース | 期待される扱い |
|---|---|
| コメント解除で新たな参照が有効 → サブツリー展開 | 全ツリー再構築で正しく展開される |
| コメント化で参照が無効 → サブツリー消滅 | 全ツリー再構築で正しく反映。コメント化されたノードはグレーアウトで残る |
| LITERAL ノードのチェック操作 | value_entry があるので操作可能。リテラルのコメント化/解除 |
| UNRESOLVED ノードのチェック操作 | value_entry があるので操作可能。ただし解決できない参照のコメント化のみ意味がある |
| CIRCULAR ノードのチェック操作 | value_entry があるので操作可能。循環参照のコメント化 |
| DYNAMIC ノードのチェック操作 | value_entry があるので操作可能 |
| EMPTY ノードのチェック操作 | value_entry があるので操作可能。空定義のコメント化 |
| 高速連打（短時間に複数回チェック操作） | 各操作は同期的（toggle_comment + rebuild が完了してから次の itemChanged が処理される）。Qt のイベントキューにより自然に直列化される |
| ツリーが巨大（3,476 ノード）でのチェック操作 | 再構築 100ms 以下。ユーザー体感に問題なし |
| 別のトップツリーへの切り替え後のチェック操作 | `_current_tree` と `_on_top_tree_selected` で取得した TopTreeInfo を使って再構築。問題なし |
| 選択復元時にノード名が重複（ダイヤモンド参照） | パスベースの復元は最初にマッチしたノードを選択する。完全な一致は保証しないが、ユーザー体験として十分 |

## 冪等操作時の再構築について

toggle_comment は冪等（既にチェック済み → enable=True で何もしない）だが、itemChanged シグナルは populate_model 時にチェック状態を設定する際にも発火しうる。_is_populating ガードでこのケースを防ぐ。

ユーザーが意図的にチェック状態を変更した場合で冪等操作になるケースは、populate_model でチェック状態を復元した直後に同じ操作をするケース（理論上は起きにくい）。この場合も toggle_comment が何もせず、rebuild_tree がツリーを再構築する（構造は変わらない）ため、無駄な処理ではあるが害はない。

## テストパターン（テスター向けのガイド）

### tree_model.py

**チェックボックスの設定:**
- value_entry ありのノード（REF, LITERAL, DYNAMIC, UNRESOLVED, CIRCULAR, EMPTY）に setCheckable(True) が設定される
- value_entry なしのノード（ROOT）に setCheckable(False)（または setCheckable が呼ばれない）
- is_commented=False → Qt.CheckState.Checked
- is_commented=True → Qt.CheckState.Unchecked
- populate_model 後のモデルで上記が正しく反映される

### app.py

**チェック操作 → YAML 書き換え:**
- チェック ON で YAML ファイルのコメントが除去される（commented_ref_cards_dir を使用）
- チェック OFF で YAML ファイルにコメントが付与される
- 操作後にツリーが再構築される（model.rowCount() > 0）

**選択位置復元:**
- チェック操作後に選択していたノードが復元される
- 復元失敗時にルートノードが選択される

**エラーハンドリング:**
- toggle_comment 失敗時にツリーが変更されない
- EditResult.error のメッセージが QMessageBox に表示される

**ガード:**
- _is_populating=True の間は _on_item_changed が何もしない

### conftest.py フィクスチャ

既存のフィクスチャで十分:
- `commented_ref_cards_dir`: コメント行を含む。チェック操作のテストに最適
- `simple_cards_dir`: 基本テスト
- `multi_file_cards_dir`: クロスファイル参照を含むツリーでのチェック操作テスト
- `qapp`: QApplication インスタンス

新規フィクスチャは不要と判断。
