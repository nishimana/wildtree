# 実装ガイド: WildTree

## 1. 機能の概要

Dynamic Prompts 拡張のワイルドカード YAML ファイル群を解析し、`__参照__` の依存関係をツリー構造で可視化する PySide6 スタンドアロンビューア。

## 2. 設計判断の理由 (why)

### 2.1 行ベースパーサー（PyYAML を使わない）

Dynamic Prompts の YAML ファイルには、プロンプト文字列がそのまま値に書かれている。これらの文字列には `()`、`:`、`{}` 等の YAML 特殊文字が含まれるため、厳密な YAML パーサーでは解析に失敗するケースがある。

`dynamic_linter` (TypeScript) でも同じ理由で行ベースパーサーを採用しており、WildTree でもこれを踏襲する。

### 2.2 core と gui の分離

`core/wildcard_parser.py` は PySide6 に一切依存しない純粋な Python モジュールにする。これにより:

- テストが QApplication なしで実行可能
- 将来的に CLI ツールとしても利用可能
- 関心の分離が明確

### 2.3 WildcardResolver をクラスにした理由

Stage 4（名前解決）は状態を持つ（キーレジストリと cards_dir）。関数にすると毎回レジストリを引き回す必要があるため、クラスにまとめた。また `get_all_key_names()` や `get_refs_for_key()` といったユーティリティメソッドの置き場としても自然。

### 2.4 TreeNode の設計

`TreeNode.ref_name` を `name`（表示名）と分離した理由: 同名キーが別ディレクトリに存在する場合、表示名は同じでも参照先は異なる。循環参照の検出には `ref_name` を使う必要がある。

### 2.5 却下した代替案

- **PyYAML + エラーハンドリング**: YAML パースエラーを個別にキャッチして回避する案。エラーパターンが多様すぎて安定しない。行ベースの方がシンプルかつ堅牢
- **グラフデータ構造 (networkx 等)**: ツリー表示だけなら再帰的な TreeNode で十分。外部依存を増やすメリットがない
- **非同期スキャン**: ファイル数が数百程度の規模なので同期実行で問題ない（設計書 Section 6 参照）

## 3. スコープ (scope)

### 3.1 初期リリースに含むもの

- YAML ファイルの再帰スキャン
- トップレベルキーと値行の抽出（コメント行スキップ）
- `__name__` 参照の抽出（ネスト対応）
- フルパス / 短縮形の名前解決
- 循環参照検出付きのツリー構築
- QTreeWidget によるツリー表示
- エントリポイント選択（QComboBox）
- cards ディレクトリの選択（QFileDialog / コマンドライン引数）
- 更新ボタン（再スキャン + ツリー再構築）

### 3.2 意図的な対象外

| 対象外の機能 | 理由 |
|---|---|
| ノード選択 → 右ペインにキー定義を表示 | 初期リリースでは可視化に集中。将来の拡張ポイント |
| キー定義のインライン編集 | 編集は YAML ファイルを直接編集する運用で十分 |
| 壊れた参照のハイライト | 未解決参照は非表示にする。将来対応予定 |
| 検索機能 | ツリーの規模的に目視で十分。将来対応予定 |
| `.txt` ベースのワイルドカード | YAML ファイルのみを対象とする。`.txt` ファイルは構造が異なる |
| リテラル値（プロンプトタグ）の表示 | `__name__` 参照のみをツリーに表示 |
| 未解決参照のツリー表示 | 解決できない参照はツリーに含めない |

## 4. dynamic_linter からの移植ポイント

### 4.1 `wildcard-validator.ts` → `core/wildcard_parser.py`

| TypeScript 関数 | Python 関数 | 差異 |
|---|---|---|
| `scanYAML()` | `scan_yaml_files()` | TS はクラスメソッド、Python はモジュール関数。TS は複数ディレクトリ対応だが Python は単一ディレクトリ |
| `extractKeysFromText()` | `extract_keys_from_file()` | **TS はキー名のみ返す。Python は値行も取得する**（参照抽出のため）。Python では `KeyDefinition` データクラスを返す |
| `extractKeysFromFile()` | `extract_keys_from_file()` | TS はファイル読み込み + テキスト解析が別関数。Python は1関数に統合（テスト用にテキスト解析を分ける必要があれば後で分離） |

### 4.2 `wildcard-utils.ts` → `core/wildcard_parser.py`

| TypeScript 関数 | Python 関数 | 差異 |
|---|---|---|
| `parseWildcardSpansOnLine()` | `extract_refs_from_line()` | TS は `{start, end, name}` を返す（エディタ用に位置情報が必要）。Python は `WildcardRef(name, raw)` を返す（位置情報は不要） |
| `scanLineWildcard()` | `_scan_closing_underscores()` | ほぼ同じロジック。ブレース深度追跡、インナーワイルドカード深度追跡を忠実に移植する |
| `getWildcardNameAtPosition()` | (移植しない) | エディタ専用機能。ツリービューアでは不要 |
| `getWildcardRangeAtPosition()` | (移植しない) | エディタ専用機能 |
| `findKeyLineInText()` | (移植しない) | エディタ専用機能。将来「ノードクリック → ファイルを開く」機能を追加する場合に移植 |

### 4.3 TypeScript → Python 移植時の注意

- **文字列インデックスアクセス**: TS の `text[i]` は Python でも同じだが、範囲チェックの方法が異なる。Python は `IndexError` を出すので事前にチェックする
- **`prevChar` の初期化**: TS 版では `bodyStart > 0 ? text[bodyStart - 1] : ''` としている。Python では同じ条件分岐で初期化する
- **`continue` の使い方**: TS と Python で同じ
- **正規表現**: キー抽出の `^([^:]+):` パターンはそのまま使える

## 5. 正常系の振る舞い

### 5.1 起動フロー

```
1. main.py: sys.argv から cards_dir を取得（省略可）
2. QApplication + MainWindow を生成
3. cards_dir が指定されていれば _load_cards_dir() を呼ぶ
4. _load_cards_dir():
   a. scan_yaml_files(cards_dir) → YAML ファイル一覧
   b. build_key_registry(yaml_files) → キーレジストリ
   c. WildcardResolver(registry, cards_dir) を生成
   d. resolver.get_all_key_names() → QComboBox に設定
   e. デフォルトエントリ（存在すれば "メイン"）を選択
5. _on_entry_changed() → _build_and_display_tree()
6. build_tree(entry_key, resolver) → TreeNode
7. QTreeWidget に TreeNode を再帰的に表示
```

### 5.2 更新フロー

```
1. ユーザーが [Refresh] をクリック
2. _on_refresh() → _load_cards_dir()
3. YAML ファイルを再スキャン、キーレジストリを再構築
4. QComboBox を更新（現在の選択をできるだけ維持）
5. ツリーを再構築
```

## 6. 異常系の振る舞い

### 6.1 エラーケース一覧

| エラーケース | 発生箇所 | 処理 |
|---|---|---|
| cards_dir が存在しない | `scan_yaml_files()` | `FileNotFoundError` を raise。GUI 側でキャッチしてユーザーに通知 |
| cards_dir がディレクトリでない | `scan_yaml_files()` | `NotADirectoryError` を raise。GUI 側でキャッチしてユーザーに通知 |
| YAML ファイルが読めない（権限等） | `extract_keys_from_file()` | 空リストを返す（スキップ）。例外は raise しない |
| YAML ファイルが UTF-8 でない | `extract_keys_from_file()` | 空リストを返す（スキップ） |
| YAML ファイルが空 | `extract_keys_from_file()` | 空リストを返す |
| エントリキーが見つからない | `build_tree()` | `is_leaf=True` の TreeNode を返す |
| 参照先が見つからない | `WildcardResolver.resolve()` | `None` を返す。ツリーに含めない |
| 循環参照 | `build_tree()` | `is_circular=True` の TreeNode を生成して打ち切る |

### 6.2 GUI のエラー表示

- `scan_yaml_files()` で例外が発生した場合: ステータスバーまたはメッセージボックスでエラーを表示
- YAML ファイルが0個の場合: ツリーは空、QComboBox は空

## 7. エッジケース

### 7.1 循環参照

キー A が キー B を参照し、キー B が キー A を参照するパターン。`build_tree()` の再帰で訪問済みセット（パススコープ）を保持し、同じキーに再度遭遇したら `is_circular=True` として打ち切る。

訪問済みの判定は `ref_name`（表示名ではなく参照名）で行う。これにより同名キーが別ファイルに定義されている場合でも正しく区別できる。

訪問済みセットはパススコープ（現在のルートからの経路上のみ）であり、グローバルではない。これにより、同じキーがツリーの異なるブランチに複数回出現することを許容する（循環でない限り）。

### 7.2 同名キーの後勝ち

複数の YAML ファイルで同じキー名が定義されている場合、短縮形参照（`__keyname__`）では `key_registry[name]` の最後の要素が使われる。スキャン順はファイルパスのソート順で決定論的にする。

### 7.3 コメント行のスキップ

値行のうち、先頭空白を除去した後に `#` で始まるものはスキップする。

```yaml
scenes:
  # - __cards/blue_archive/...__    <- skipped
  - __cards/sao/...__               <- processed
```

これにより、コメントアウトされたキャラクターがツリーに含まれない。

### 7.4 ネスト参照 (`__{__inner__}outer__`)

Dynamic Prompts のブレース `{}` 構文内に参照がネストされるパターン。

```
__{__season__}_{__character__}__
```

ツリービューアでの扱い:
- 外側の参照: 動的参照（実行時に決まる）としてノード表示
- 内側の `__season__`、`__character__`: それぞれ独立した参照として子ノードに展開

`_scan_closing_underscores()` がブレース深度を追跡することで、内側の `__` を閉じ区切りと誤認しない。

### 7.5 値行の `- ` プレフィックス

YAML リスト形式の値行は `  - value` の形をしている。`- ` プレフィックスを除去してから参照抽出を行う。ただし参照パターン `__name__` の検出は行全体に対して行うため、プレフィックスの除去は `raw_values` の格納時に行い、参照抽出は格納後の値に対して実行する。

### 7.6 フルパス参照の解決

`__cards/SAO/CH_asada/asada_body__` の解決手順:
1. `cards/` を除去 → `SAO/CH_asada/asada_body`
2. `/` で分割 → `["SAO", "CH_asada", "asada_body"]`
3. 最後の要素 `asada_body` がキー名
4. 先行要素 `SAO/CH_asada` がディレクトリパス
5. `key_registry["asada_body"]` の中から、`file_path` の相対パス（cards_dir からの）にディレクトリパスが含まれるものを選択

### 7.7 空の cards ディレクトリ

YAML ファイルが1つも見つからない場合、`build_key_registry()` は空辞書を返す。GUI の QComboBox は空になり、ツリーも空のまま。エラーではない。

### 7.8 Windows パス区切り

`Path` オブジェクトを使うことでパス区切り文字の違いを吸収する。参照名（`cards/dir/key`）はスラッシュ区切りで統一されているため、`PurePosixPath` で分割するか、単純に `str.split("/")` で分割する。

## 8. 設計原則

### 8.1 ファイル I/O は UTF-8 を明示する

`Path.read_text()` は Windows ではデフォルトで cp932 を使う。必ず `encoding="utf-8"` を指定すること。

### 8.2 エラーハンドリングの方針

- **`scan_yaml_files()`**: ディレクトリの問題は早期に検出すべきなので例外を raise する
- **`extract_keys_from_file()`**: 個別ファイルの問題でスキャン全体を止めない。空リストを返す
- **`WildcardResolver.resolve()`**: 未解決参照は `None` を返す。例外ではない
- **`build_tree()`**: 常に TreeNode を返す。エントリキーが見つからない場合は leaf ノード

### 8.3 テスト容易性

core モジュールの全関数は PySide6 に依存しない。テストは `QApplication` なしで実行可能。GUI のテストは tester エージェントが担当する。
