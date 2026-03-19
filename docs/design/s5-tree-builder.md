# S5: ツリー構築 (`core/tree_builder.py`)

## タスク種別

新規モジュール → コード成果物あり（`core/tree_builder.py` にスタブを配置）

## 機能の概要

KeyRegistry と FullPathIndex を使い、指定されたエントリポイント（トップツリー等）から参照を再帰的に辿って TreeNode ツリーを構築する。S1-S4 の全成果物を統合し、GUI が表示可能なツリー構造を生成する。

## 設計判断の理由（Why）

### 1. visited セットのスコープ: パスごと（per-path）を採用する理由

循環参照の検出には「現在の探索パス上に同じキーがあるか」で判定する（パスごとのスコープ）。

**グローバル visited（一度訪問したキーを再訪問しない）を却下する理由**:
- ダイヤモンド参照パターンが実データに存在する。実データの `メイン` から全展開すると 3,476 ノードになり、同一キーが異なるブランチから参照される
- グローバル visited では、最初に到達したブランチでしかノードが展開されず、他のブランチでは空になる
- これはユーザーの期待に反する。`branch_a → shared` と `branch_b → shared` のどちらのブランチでも `shared` の子が展開されるべき

**パフォーマンス上の考慮**:
- パスごとの visited は各再帰呼び出しでコピーが必要だが、最大深度が 9 であるため集合のサイズは最大 10 要素。コピーコストは無視できる
- `メイン` の全展開で 3,476 ノードが生成される程度なので、パス単位の visited でもパフォーマンス問題は生じない

### 2. 再帰の深さ制限を 50 に設定する理由

実データの最大深度は 9。安全マージンを十分に取って 50 を上限とする。

- 正常なデータでは深度 9 が最大であり、50 に達することはありえない
- 50 に達した場合は循環参照の検出漏れまたはデータの異常を意味する
- Python のデフォルト再帰制限（1000）に対して十分な余裕がある
- この制限は `MAX_DEPTH` 定数として定義し、テストで差し替え可能にする

### 3. 全展開（eager expansion）を初期実装とする理由

遅延展開（lazy expansion、ノード展開時に子を構築）ではなく、全展開を採用する。

- 実データで最大のツリー（`メイン`）が 3,476 ノード。これはメモリ上もパフォーマンス上も問題にならないサイズ
- 全展開のほうが実装が単純で、ツリー全体の整合性検証が容易
- GUI 側の検索機能（W3 で実装済み）は全ノードの走査を前提としている
- パフォーマンス問題が発生した場合は S6 で遅延展開に切り替える（v2-tree-editor.md §6 に記載済み）

### 4. 1つの ValueEntry から複数の TreeNode を生成する理由

1つの値行には参照とリテラルが混在しうる。例:

```
- dynamic_angle,__cards/シネマシャドウ__,literal_tag
```

この値行から以下の TreeNode が生成される:
- REF ノード: シネマシャドウ（参照先を再帰展開）
- LITERAL ノード: dynamic_angle
- LITERAL ノード: literal_tag

**値行とノードの対応関係**: `TreeNode.value_entry` で元の値行を辿れる。チェックボックスの ON/OFF 切り替え（S8）で使用する。同じ値行から生成された複数のノードは、同一の `value_entry` を参照する。

### 5. ルートノードに NodeType.ROOT を使う理由

v2-tree-editor.md では ROOT は明記されていなかったが、S1 の models.py で NodeType.ROOT が定義済み。

- トップツリーのエントリポイントは「他のどこかから参照された」ノードではなく、ツリーの起点
- GUI でルートノードを特別に描画する必要がある（太字、アイコン等）
- REF ノードとは意味論が異なる（REF は「ある値行の参照先」、ROOT は「トップツリーの起点」）

### 6. コメントノードの扱い: 展開するが is_commented 情報を保持する

コメントアウトされた値行（`is_commented=True`）の参照も展開する。

- コメントアウトされた参照先の子ツリーを見たいというユースケースがある（「無効化した参照の内容を確認する」）
- `TreeNode.value_entry.is_commented` で GUI がチェックボックスの状態を判定できる
- 展開しない場合、コメントを有効化したときにツリーの再構築が必要になり、UX が悪化する

### 7. build_tree の入力を KeyDefinition にする理由

`find_top_trees()` の結果（TopTreeInfo）は内部に KeyDefinition を持つ。`build_tree()` の入力を KeyDefinition にすることで:
- 任意のキー定義からツリーを構築できる（トップツリー以外のキーからも構築可能）
- TopTreeInfo に依存しない。top_tree モジュールとの結合度を下げる
- テスト時に KeyDefinition を直接渡せる

### 却下した代替案

| 案 | 却下理由 |
|---|---|
| グローバル visited | ダイヤモンド参照で一方のブランチが展開されない |
| 遅延展開 | 実データ 3,476 ノードで不要。実装複雑度が増す |
| 値行ごとに1ノード | 参照とリテラルの混在を表現できない |
| build_tree に TopTreeInfo を渡す | 不要な依存。KeyDefinition で十分 |
| コメント行を展開しない | コメント解除時にツリー再構築が必要になる |
| 深さ制限なし | 循環参照検出漏れ時に StackOverflow のリスク |

## スコープ（Scope）

### やること

- `build_tree()`: 指定された KeyDefinition からツリーを再帰展開して TreeNode ツリーを構築する
- `build_forest()`: 複数のトップツリーから一括でツリーを構築する（`build_tree` のバッチ版）
- 循環参照の検出（パスごとの visited セット）
- 深さ制限による安全停止
- 全 NodeType の判定と TreeNode 構築:
  - ROOT: ルートノード
  - REF: 解決済み通常参照
  - LITERAL: リテラル値
  - DYNAMIC: 動的参照
  - UNRESOLVED: 未解決参照
  - CIRCULAR: 循環参照検出
  - EMPTY: 空定義 `"{}"`

### やらないこと（意図的な対象外）

| 対象外 | 理由 |
|---|---|
| 遅延展開 | 実データ規模で不要。パフォーマンス問題が出たら S6 で対応 |
| 動的参照の完全展開（変数代入→最終参照名の組み立て） | S9 の責務 |
| GUI への結果表示 | S6 の責務 |
| YAML の書き換え | S7（editor）の責務 |
| トップツリーの検出 | S4（top_tree）の責務 |
| 名前解決ロジック | S3（resolver）の責務。resolver.resolve() を呼ぶだけ |
| トップツリーの優先度付け | GUI 層の責務 |
| ツリーの差分更新（編集後の部分再構築） | S8 で必要になったら検討。初期は全再構築 |

## 既存コードとの関係（Context）

### v1 プロトタイプとの対応

v1 の `wildcard_parser.py` に相当する `_build_tree_recursive()` 相当のロジックを新規実装する。v1 の問題点:
- クロスファイル参照が解決できなかった（v2 は resolver で解決済み）
- リテラルノードが表示されなかった（v2 は LITERAL ノードを生成）
- コメント行が無視されていた（v2 は is_commented を保持して展開）

### S1-S4 成果物の統合

S5 は S1-S4 の全成果物を統合する。具体的な依存関係:

```
core/models.py (S1)
├── KeyDefinition  — build_tree の入力
├── KeyRegistry    — resolve の引数
├── FullPathIndex  — resolve の引数
├── TreeNode       — build_tree の出力
├── NodeType       — TreeNode.node_type の値
├── ValueEntry     — TreeNode.value_entry に保持
├── WildcardRef    — TreeNode.ref に保持、resolve の引数
└── RefType        — 動的参照の判定

core/resolver.py (S3)
├── resolve()      — 参照の名前解決
├── ResolveResult  — resolve の戻り値（key_def を取り出す）
└── resolve_dynamic_inner_refs() — 動的参照の内部参照解決

core/top_tree.py (S4)
└── TopTreeInfo    — build_forest の入力（key_def を取り出す）
```

### データフロー

```
[TopTreeInfo]  ← find_top_trees() の出力
    |
    v
build_forest(top_trees, registry, full_path_index)
    |
    ├── build_tree(top_trees[0].key_def, registry, full_path_index)
    │       |
    │       v
    │   _expand_key_def(key_def, registry, full_path_index, visited, depth)
    │       |
    │       ├── 各 ValueEntry を処理:
    │       │   ├── 参照あり → resolve() → _expand_key_def() 再帰
    │       │   ├── リテラルあり → LITERAL ノード生成
    │       │   └── 空定義 → EMPTY ノード生成
    │       │
    │       ├── 循環検出 → CIRCULAR ノード
    │       ├── 未解決 → UNRESOLVED ノード
    │       └── 動的参照 → DYNAMIC ノード + inner_refs の展開
    │
    ├── build_tree(top_trees[1].key_def, ...)
    │       ...
    v
[list[TreeNode]]  ← 各 TreeNode は ROOT タイプのルートノード
```

### ノード生成の判定フロー

ValueEntry の各要素に対して以下の順序で判定:

```
ValueEntry
├── refs (WildcardRef のリスト)
│   ├── RefType.NORMAL
│   │   ├── resolve() 成功
│   │   │   ├── 循環検出（visited に key_def.name あり） → CIRCULAR ノード
│   │   │   ├── 深さ制限超過 → CIRCULAR ノード（安全停止）
│   │   │   └── 正常 → REF ノード → 再帰展開
│   │   └── resolve() 失敗 → UNRESOLVED ノード
│   │
│   └── RefType.DYNAMIC
│       └── DYNAMIC ノード + inner_refs の各参照を子ノードとして展開
│
├── literals (str のリスト)
│   ├── '"{}"' → EMPTY ノード
│   └── それ以外 → LITERAL ノード
│
└── refs も literals も空 → (ノード生成なし)
```

## 設計原則（implementer 向け）

### 1. ルートノードの構築ルール

`build_tree(key_def, registry, full_path_index)` は以下のルールでルートノードを構築する:

1. `TreeNode(display_name=key_def.name, node_type=NodeType.ROOT)` を作成
2. `key_def` を `TreeNode.key_def` に設定
3. `value_entry` は None（ルートはどの値行にも属さない）
4. `ref` は None（ルートは参照ではなく起点）
5. 子ノード: key_def の各 ValueEntry を処理して子ノードを生成

### 2. 参照ノード（REF）の構築ルール

ValueEntry 内の `RefType.NORMAL` の WildcardRef に対して:

1. `resolve(ref.full_path, full_path_index, registry)` を呼ぶ
2. 解決成功（`ResolveResult` が返る）:
   a. `result.key_def.name` が visited セットに含まれる → CIRCULAR ノード
   b. depth が MAX_DEPTH 以上 → CIRCULAR ノード（安全停止として同じ扱い）
   c. 正常: `TreeNode(display_name=result.key_def.name, node_type=NodeType.REF)` を作成
      - `key_def = result.key_def`
      - `value_entry = 現在の ValueEntry`
      - `ref = 現在の WildcardRef`
      - 子ノード: `result.key_def` の各 ValueEntry を再帰展開
3. 解決失敗（None が返る）:
   - `TreeNode(display_name=ref.name, node_type=NodeType.UNRESOLVED)` を作成
   - `value_entry = 現在の ValueEntry`
   - `ref = 現在の WildcardRef`
   - 子ノードなし

### 3. リテラルノード（LITERAL）の構築ルール

ValueEntry 内の各リテラル文字列に対して:

1. `'"{}"'` にマッチするか判定 → EMPTY ノード
2. それ以外: `TreeNode(display_name=literal, node_type=NodeType.LITERAL)` を作成
   - `key_def = None`
   - `value_entry = 現在の ValueEntry`
   - `ref = None`
   - 子ノードなし

### 4. 空定義ノード（EMPTY）の構築ルール

リテラル文字列が `'"{}"'` の場合:

- `TreeNode(display_name="(空)", node_type=NodeType.EMPTY)` を作成
- `value_entry = 現在の ValueEntry`
- 子ノードなし

### 5. 動的参照ノード（DYNAMIC）の構築ルール

ValueEntry 内の `RefType.DYNAMIC` の WildcardRef に対して:

1. `TreeNode(display_name=ref.raw, node_type=NodeType.DYNAMIC)` を作成
   - `value_entry = 現在の ValueEntry`
   - `ref = 現在の WildcardRef`
2. 子ノード: `ref.inner_refs` の各内部参照を展開
   - 各内部参照に対して `resolve()` を呼ぶ
   - 解決成功 → REF ノードとして再帰展開
   - 解決失敗 → UNRESOLVED ノード

### 6. 循環参照ノード（CIRCULAR）の構築ルール

パスごとの visited セットでキー名の重複を検出した場合:

- `TreeNode(display_name=key_name + " (循環)", node_type=NodeType.CIRCULAR)` を作成
- `value_entry = 現在の ValueEntry`
- `ref = 現在の WildcardRef`
- `key_def = None`（循環先の KeyDefinition は設定しない — 展開しないため）
- 子ノードなし

### 7. visited セットの管理ルール

- visited セットにはキー名（`key_def.name`）を格納する
- visited セットは**パスごとのスコープ**。再帰呼び出し時にコピーして渡す
- ルートノードのキー名を最初に visited に追加する
- REF ノードの展開前に参照先のキー名を visited に追加する
- ダイヤモンド参照パターン: 異なるブランチからの再訪問は循環ではないため、パスごとの visited で正しく判定される

### 8. build_forest の構築ルール

`build_forest(top_trees, registry, full_path_index)`:

1. 各 TopTreeInfo に対して `build_tree(top.key_def, registry, full_path_index)` を呼ぶ
2. 結果を `list[TreeNode]` として返す
3. 入力の順序を保持する（`find_top_trees()` がソート済みで返すため）

### 9. エラーハンドリング方針

- `build_tree()` は例外を投げない。全ての入力に対して TreeNode を返す
- `build_forest()` は例外を投げない。空リストが渡された場合は空リストを返す
- `resolve()` の戻り値が None の場合は UNRESOLVED ノードを生成する
- 深さ制限超過は CIRCULAR ノードとして処理する（エラーではなく正常なフロー）

## 正常系・異常系の振る舞い

### build_tree

| 状況 | 振る舞い |
|---|---|
| 値行がリテラルのみのキー | ROOT ノード + LITERAL 子ノード群 |
| 値行が参照のみのキー | ROOT ノード + REF 子ノード群（再帰展開） |
| 値行にリテラルと参照が混在 | ROOT ノード + REF / LITERAL 混在の子ノード群 |
| 参照が解決できない | UNRESOLVED ノード（子なし） |
| 循環参照がある | CIRCULAR ノード（子なし） |
| 動的参照がある | DYNAMIC ノード + inner_refs の子ノード |
| 空定義 `"{}"` がある | EMPTY ノード |
| コメント行がある | 通常と同じノードを生成。value_entry.is_commented が True |
| 値行がゼロ個のキー | ROOT ノード（子なし） |
| 深さ制限に到達 | CIRCULAR ノード（安全停止） |

### build_forest

| 状況 | 振る舞い |
|---|---|
| 正常なトップツリーリスト | 各トップツリーの ROOT ノードのリスト |
| 空リスト | 空リスト |
| トップツリーが1つ | 1要素のリスト |

## エッジケース

| ケース | 期待される扱い |
|---|---|
| 自己参照（A → A） | CIRCULAR ノード。visited にルートの A が入っているため、A への参照で循環検出 |
| 相互参照（A → B → A） | B の展開中に A が visited にあるため、A は CIRCULAR ノードになる |
| ダイヤモンド参照（A → B → D, A → C → D） | D は B と C の両方のブランチで正常に展開される。パスごとの visited なので再訪問にならない |
| 深度 50 の直線チェーン | 深度 50 で CIRCULAR ノードとして安全停止。実データではありえない（最大 9）|
| 空定義のみの値行 `'"{}"'` | EMPTY ノード。display_name は "(空)" |
| 1つの値行に参照3つ + リテラル2つ | 5つの子ノードが生成される（REF × 3 + LITERAL × 2） |
| コメントアウトされた参照 | REF/UNRESOLVED ノードとして生成される。value_entry.is_commented = True |
| 同名キーが複数ファイルに存在 | resolve() が後勝ちで1つの KeyDefinition を返すため、そちらが展開される |
| 動的参照の inner_ref が未解決 | DYNAMIC ノードの子に UNRESOLVED ノード |
| 動的参照の inner_ref が循環 | DYNAMIC ノードの子に CIRCULAR ノード |
| 値行のリテラルが空文字列 | extract_literals が空文字列を除外するため、ノード生成されない |
| 実データ: `メイン` の全展開 | 約 3,476 ノード。パフォーマンス問題なし |
| 実データ: 142 キーの循環参照 | 各循環は CIRCULAR ノードで打ち切られ、無限ループにならない |

## パフォーマンス考慮

### 実データでの規模

- 全キー数: 42,957
- トップツリー数: 16,238（大半は動的参照の展開先。参照を持つもの 15,554）
- 最大深度: 9
- 最大ツリーノード数: `メイン` で約 3,476 ノード
- 循環参照を含むキー: 142

### パフォーマンス見積もり

1. **単一ツリーの構築**: `メイン` の 3,476 ノードは数十ミリ秒以内で構築可能。各ノードの構築は resolve() の O(1) + TreeNode 生成
2. **全トップツリーの構築**: 16,238 ツリーの一括構築は不要（GUI でユーザーが選択したツリーだけ構築する）
3. **visited セットのコピー**: 最大深度 9 → 最大 10 要素の set コピー。無視できるコスト
4. **メモリ**: TreeNode 1つあたり約 200 バイト。3,476 ノード × 200B ≈ 700KB。問題なし

### ボトルネックの予測

- ボトルネックは存在しない見込み
- 万が一の場合に備え、`build_forest()` は呼び出し元が必要なツリーだけ構築する設計にする（全トップツリーを一括で構築しない選択も可能）

## 関数一覧

### `core/tree_builder.py`

| 関数 | シグネチャ | 説明 |
|---|---|---|
| `build_tree` | `(key_def: KeyDefinition, registry: KeyRegistry, full_path_index: FullPathIndex) -> TreeNode` | 指定された KeyDefinition をルートとしてツリーを構築する |
| `build_forest` | `(top_trees: list[TopTreeInfo], registry: KeyRegistry, full_path_index: FullPathIndex) -> list[TreeNode]` | 複数のトップツリーから一括でツリーを構築する |
| `_expand_key_def` | `(key_def: KeyDefinition, registry: KeyRegistry, full_path_index: FullPathIndex, visited: set[str], depth: int) -> list[TreeNode]` | キー定義の値行群を子ノードに展開する（内部関数） |
| `_process_value_entry` | `(value_entry: ValueEntry, registry: KeyRegistry, full_path_index: FullPathIndex, visited: set[str], depth: int) -> list[TreeNode]` | 1つの値行から TreeNode 群を生成する（内部関数） |

### 定数

| 定数 | 値 | 説明 |
|---|---|---|
| `MAX_DEPTH` | `50` | 再帰の最大深さ。超過時は CIRCULAR ノードとして安全停止 |
| `EMPTY_DISPLAY_NAME` | `"(空)"` | 空定義ノードの表示名 |
| `CIRCULAR_SUFFIX` | `" (循環)"` | 循環参照ノードの表示名サフィックス |

## エラー種別

| エラー | 発生条件 | 例外型 | 発生関数 |
|---|---|---|---|
| なし | — | — | — |

tree_builder は例外を投げない設計。全ての入力に対して正常な TreeNode を返す。resolve() が None を返す場合は UNRESOLVED ノード、深さ制限超過は CIRCULAR ノードとして処理する。

## conftest.py フィクスチャ設計

### 既存フィクスチャの活用

- `simple_cards_dir`: 基本テスト。`greeting` → `farewell` の1段参照 + リテラル
- `multi_file_cards_dir`: 複数ファイル・クロスファイル参照。`メイン` → `シーンまとめ` → `朝田詩乃` の多段参照
- `circular_ref_cards_dir`: 循環参照。`alpha` ⇔ `beta`
- `diamond_ref_cards_dir`: ダイヤモンド参照。`root` → `branch_a` → `shared`, `root` → `branch_b` → `shared`
- `commented_ref_cards_dir`: コメントアウト参照。`シーンまとめ` → `朝田詩乃`（有効）/ `シロコ`（コメント）
- `nested_ref_cards_dir`: 動的参照。`scene` → `__{__season__}_{__character__}__`
- `broken_ref_cards_dir`: 未解決参照。`entry` → `existing_key`（解決可）/ `non_existent_key`（未解決）
- `broken_and_circular_cards_dir`: 未解決 + 循環の混在

### 新規フィクスチャの要否

既存フィクスチャで主要なテストパターンをカバーできる。以下のケースが不足する場合、テスターの判断で追加:

- 空定義 `"{}"` を含むキーからのツリー構築（`empty_def_yaml` は単一ファイル向け。cards ディレクトリ形式が必要な場合）
- 深さ制限テスト用の深い参照チェーン（テスト内で `MAX_DEPTH` を小さくモンキーパッチして代用可能）
- 1つの値行に参照とリテラルが混在するケース
- 値行がゼロ個のキー定義

これらはテスト内で KeyDefinition と KeyRegistry を直接構築して対応可能。
