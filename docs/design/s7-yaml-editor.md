# S7: YAML エディタ (`core/editor.py`)

## タスク種別

新規モジュール → コード成果物あり（`core/editor.py` にスタブを配置）

## 機能の概要

YAML ファイルの行ベース書き換えを行うコアモジュール。S8（GUI 編集機能）のバックエンドとして、コメント切り替え（`# ` プレフィックスの付与/除去）を行番号ベースで実行する。

S2 パーサーと同じ方針で、PyYAML を使わず行単位で操作する。ファイルの改行コードを保持し、最小限の行書き換えでフォーマットを崩さない。

## 設計判断の理由（Why）

### 1. 行単位書き換え（行全体の置換）を採用する理由

YAML ファイルの編集方式として「行単位の全体書き換え」を採用する。つまり、ファイルを行リストとして読み込み、対象行を置換し、全体を書き戻す。

**理由**:
- S2 パーサーが行番号（1始まり）を ValueEntry.line_number に記録しており、行番号による直接アクセスが可能
- 行単位の操作であれば、コメント切り替えは正規表現によるプレフィックスの付与/除去で実現でき、行内の構造理解が不要
- 部分書き換え（seek + write）はファイルサイズ変更時にトランケーションが必要で、Windows 環境での CRLF を考慮すると複雑になる
- 実データの YAML ファイルは最大でも数百行程度。全体書き換えのコストは無視できる

**却下した代替案**:
- バイト位置ベースの部分書き換え: CRLF/LF 混在時のバイト数計算が複雑。行挿入/削除でオフセットがずれる。利点（パフォーマンス）に対してリスクが大きい
- PyYAML による読み書き: Dynamic Prompts の YAML は特殊文字を含み、PyYAML でパース失敗するケースがある（S2 の設計方針と同じ理由）。また、PyYAML はコメントを破棄する

### 2. ファイル全体書き戻し方式を採用する理由

行を置換した後、ファイル全体を書き戻す。

**理由**:
- 行の挿入/削除（将来の拡張: 値行の追加/削除）に自然に対応可能
- ファイル書き込みは atomic write（tmpfile + rename）ではなく、直接 write_text() で行う。理由: ユーザーが手動でも YAML を編集しうるため、OS レベルのファイルロックは不要。また、271 ファイル中の1ファイルの書き込みで数ミリ秒であり、クラッシュ時のデータ損失リスクは許容可能
- S2 パーサーの read_text() と対になる write_text() で I/O の一貫性を保つ

### 3. 改行コード保持方式を採用する理由

ファイル読み込み時に改行コードを検出し、書き戻し時に同じ改行コードを使用する。

**理由**:
- Windows 環境ではエディタによって CRLF/LF が混在する可能性がある
- Git の autocrlf 設定や .gitattributes によるファイル単位の改行コード制御があるユーザー環境を壊さない
- `splitlines()` で分割すると改行コード情報が失われるため、最初に `\r\n` の有無を確認して保持する

**実装方針**:
- ファイル先頭部分で `\r\n` を検出 → CRLF。なければ LF
- `splitlines()` で分割し、処理後に検出した改行コードで `join()` して書き戻す
- ファイル末尾の改行有無も保持する

### 4. 全再構築方式（書き換え後のレジストリ再構築）を採用する理由

ファイル書き換え後、変更されたファイルを再パースしてレジストリを更新する。「差分更新」ではなく「該当ファイルの再パース + レジストリマージ」方式を採用する。

**理由**:
- コメント切り替えは ValueEntry.is_commented の変更だが、パーサーが raw_text から refs/literals を再構築するため、KeyDefinition 全体の再生成が必要
- 差分更新（ValueEntry の is_commented フラグだけ変更）は一見効率的だが、パーサーの出力と内部状態の整合性を手動で維持する必要があり、バグの温床になる
- 実測で1ファイルの再パースは1ms以下。ファイル全体の再パース + レジストリ更新は数ミリ秒でユーザー体感に影響しない
- FullPathIndex の再構築も cards_dir 全体ではなく、変更されたファイルのキー定義のみ差し替えれば O(n)（n = 変更ファイル内のキー数）で完了

**却下した代替案**:
- ValueEntry のフラグだけ変更: 一見高速だが、refs/literals の再抽出を省略するとパーサーの出力と不整合になる。コメント解除時に参照が追加される場合（`# - __ref__` → `- __ref__`）、refs リストの更新が必要
- 全ファイル再スキャン + 全レジストリ再構築: 271 ファイル × 数ミリ秒 = 数百ミリ秒。不必要に遅い

### 5. コメント切り替え関数のインターフェースに ValueEntry を使用する理由

`toggle_comment()` の引数として `ValueEntry` を直接受け取る。

**理由**:
- GUI（S8）のチェックボックス操作時、TreeNode.value_entry から直接 ValueEntry を取得できる。行番号やファイルパスを別途組み立てる必要がない
- ValueEntry は file_path を持たないため、file_path は `KeyDefinition` 経由（または引数）で渡す。これは caller（S8 の GUI 層）がツリーノードから key_def.file_path を取得できるため問題ない
- ValueEntry.line_number で書き換え位置を特定でき、is_commented で現在の状態を参照できる

### 6. レジストリ更新関数を editor.py に含める理由

`refresh_registry()` を editor.py に配置し、ファイル書き換え → 再パース → レジストリ更新の一連の流れを1つのモジュール内で完結させる。

**理由**:
- 書き換えとレジストリ更新は常にセットで呼ばれる。分離すると caller が更新を忘れるリスクがある
- ただし、refresh_registry は parser.parse_yaml_file を呼ぶだけであり、ロジックの重複はない
- GUI 層（S8）は editor の関数を1回呼ぶだけで「書き換え + レジストリ同期」が完了する

### 却下した代替案まとめ

| 案 | 却下理由 |
|---|---|
| バイト位置ベースの部分書き換え | CRLF/LF 混在時のバイト数計算が複雑。行挿入/削除でオフセットがずれる |
| PyYAML による読み書き | 特殊文字でパース失敗。コメント破棄 |
| atomic write (tmpfile + rename) | 単一ファイルの数ms書き込みに対してオーバーエンジニアリング |
| ValueEntry のフラグだけ更新（差分更新） | refs/literals の再抽出をスキップすると整合性が崩れる |
| 全ファイル再スキャン + 全レジストリ再構築 | 271 ファイルの再パースは不要に遅い |
| toggle 関数に file_path + line_number を直接渡す | ValueEntry を渡す方が caller のコードがシンプル |

## スコープ（Scope）

### やること

- `core/editor.py`: YAML ファイルの行ベース編集モジュール
  - `toggle_comment()`: 値行のコメント状態を切り替える（有効化/無効化）
  - `detect_line_ending()`: ファイルの改行コードを検出する
  - `read_lines()`: ファイルを行リストとして読み込む（改行コード情報付き）
  - `write_lines()`: 行リストをファイルに書き戻す（改行コード保持）
  - `refresh_registry()`: 変更されたファイルを再パースしてレジストリを更新する

### やらないこと（意図的な対象外）

| 対象外 | 理由 |
|---|---|
| 値行の追加/削除 | S7 のスコープはコメント切り替えのみ。値行の追加/削除は将来の拡張 |
| キー定義の追加/削除/リネーム | 将来の拡張。S7 は既存行の書き換えのみ |
| Undo/Redo | v2 フェーズ1 では対象外。v2-tree-editor.md §8 の未決定事項 |
| ファイルロック | 単一プロセスのデスクトップアプリ。外部からの同時編集は考慮しない |
| GUI への通知（シグナル） | S8 の責務。editor.py はコア層であり、GUI を知らない |
| FullPathIndex の再構築 | 呼び出し側（S8 の GUI 層）が registry 更新後に `build_full_path_index()` を呼ぶ |
| ツリーの再構築 | 呼び出し側が `build_tree()` を呼ぶ |

## 設計原則

### 1. コア層の独立性

- editor.py はコア層のモジュール。GUI の存在を知らない
- 入力はデータモデル（ValueEntry, KeyDefinition）と Path。出力は bool（成否）とレジストリの更新
- GUI 層（S8）は editor の関数を呼び、戻り値に基づいて UI を更新する

### 2. 最小限の変更原則

- コメント切り替えは対象行のみを書き換える。他の行は一切触らない
- インデントを保持する。元の行のインデント（スペース数）をそのまま維持する
- 改行コードを保持する。ファイルの改行コード（CRLF/LF）を変更しない

### 3. 例外を投げない原則の継続

- S1-S6 と同じく、editor.py も例外を投げない
- I/O エラー（ファイルが読めない/書けない）は戻り値の `EditResult` で報告する
- caller（S8）が EditResult を見て UI 上のエラー表示を行う

### 4. パーサーとの整合性

- ファイル書き換え後の再パースには `parser.parse_yaml_file()` をそのまま使用する
- コメント行のフォーマット（`  # - value`）はパーサーが認識する形式に合わせる
- パーサーが認識する値行コメントパターン: `strip() → "#" 開始 → lstrip("#").strip() → "- " 開始`

## 既存コードとの関係（Context）

### データフロー

```
S8 (GUI 編集機能)
  │
  │ チェックボックス操作
  │   → TreeNode.value_entry (ValueEntry)
  │   → TreeNode.key_def.file_path (Path)
  │
  ▼
core/editor.py
  │
  │ toggle_comment(file_path, value_entry, enable)
  │   → read_lines(file_path)
  │   → 対象行の書き換え
  │   → write_lines(file_path, lines, line_ending)
  │   → EditResult (成功/失敗)
  │
  │ refresh_registry(file_path, registry)
  │   → parser.parse_yaml_file(file_path)
  │   → registry の差し替え
  │
  ▼
core/parser.py (既存)
  │ parse_yaml_file(file_path) → list[KeyDefinition]
  │
  ▼
core/models.py (既存)
  ValueEntry, KeyDefinition, KeyRegistry
```

### S2 パーサーとの関係

editor.py はパーサーの逆操作を行う。パーサーが YAML → データモデルの変換を行うのに対し、editor はデータモデルの変更指示 → YAML の行書き換えを行う。

| パーサーの処理 | editor の逆操作 |
|---|---|
| `  - __ref__` → `ValueEntry(is_commented=False)` | `ValueEntry(is_commented=False)` → `  # - __ref__` |
| `  # - __ref__` → `ValueEntry(is_commented=True)` | `ValueEntry(is_commented=True)` → `  - __ref__` |

### S8 GUI 層からの呼び出しパターン

```python
# S8 でのチェックボックス操作時の想定コード（参考）
def _on_checkbox_toggled(self, tree_node: TreeNode, checked: bool):
    ve = tree_node.value_entry
    kd = tree_node.key_def  # or 親ノードの key_def

    # 1. YAML ファイルを書き換え
    result = toggle_comment(kd.file_path, ve, enable=checked)
    if not result.success:
        # エラー表示
        return

    # 2. レジストリを更新
    refresh_registry(kd.file_path, self._registry)

    # 3. FullPathIndex を再構築
    self._full_path_index = build_full_path_index(
        self._registry, self._cards_dir
    )

    # 4. ツリーを再構築して表示を更新
    ...
```

## 正常系・異常系の振る舞い

### toggle_comment

| 状況 | 振る舞い |
|---|---|
| コメント解除（enable=True、現在 is_commented=True） | `  # - __ref__` → `  - __ref__`。EditResult(success=True) |
| コメント化（enable=False、現在 is_commented=False） | `  - __ref__` → `  # - __ref__`。EditResult(success=True) |
| 既にコメント解除済みで enable=True | 何もしない。EditResult(success=True)。冪等操作 |
| 既にコメント化済みで enable=False | 何もしない。EditResult(success=True)。冪等操作 |
| ファイルが存在しない | EditResult(success=False, error="ファイルが見つかりません: ...") |
| ファイルの読み込みエラー | EditResult(success=False, error="ファイルの読み込みに失敗しました: ...") |
| ファイルの書き込みエラー | EditResult(success=False, error="ファイルの書き込みに失敗しました: ...") |
| line_number がファイルの範囲外 | EditResult(success=False, error="行番号が範囲外です: ...") |

### refresh_registry

| 状況 | 振る舞い |
|---|---|
| 正常 | ファイルを再パースし、レジストリ内の該当ファイルの KeyDefinition を差し替え |
| ファイルが読めない | parse_yaml_file() が空リストを返す → レジストリから該当ファイルのキーが除去される |
| ファイルが削除された | 同上 |

### read_lines

| 状況 | 振る舞い |
|---|---|
| 正常 | (行リスト, 改行コード) のタプルを返す |
| ファイルが存在しない | FileNotFoundError を送出（toggle_comment が catch） |
| エンコーディングエラー | UnicodeDecodeError を送出（toggle_comment が catch） |

### write_lines

| 状況 | 振る舞い |
|---|---|
| 正常 | ファイルに書き戻す |
| 書き込みエラー | OSError を送出（toggle_comment が catch） |

## エッジケース

| ケース | 期待される扱い |
|---|---|
| ダブルハッシュコメント `  ## - __ref__` のコメント解除 | `  - __ref__` に変換。パーサーが lstrip("#") で複数 "#" を処理するため、editor も同様にすべての "#" を除去する |
| インデントがタブの場合 | タブを保持する。行頭のホワイトスペースをそのまま維持 |
| インデントがスペース2個ではない場合（4個等） | スペース数をそのまま維持。行頭のホワイトスペースを変更しない |
| CRLF ファイルでのコメント切り替え | 改行コードを CRLF のまま保持 |
| LF ファイルでのコメント切り替え | 改行コードを LF のまま保持 |
| 空ファイル | toggle_comment: 行番号が範囲外でエラー |
| ファイル末尾に改行がない場合 | 改行なしのまま書き戻す |
| ファイル末尾に改行がある場合 | 改行ありのまま書き戻す |
| 値行ではない行（キー定義行等）の line_number が渡された場合 | 行の内容を検証し、値行パターンに一致しない場合は EditResult(success=False) |
| 同じ ValueEntry に対して連続で toggle を呼ぶ | 冪等操作。同じ enable 値なら2回目は何もしない |
| `  - ` プレフィックスなしの値行（`  value` 形式） | パーサーが `- ` 除去後の raw_text を扱うのと同様、editor も `- ` 有無を判定して処理 |

## コメント切り替えの行変換ルール

### コメント化（enable=False）

```
入力行:    "  - __ref__"
出力行:    "  # - __ref__"

入力行:    "    - literal_value"
出力行:    "    # - literal_value"

入力行:    "\t- __ref__"
出力行:    "\t# - __ref__"
```

変換ルール:
1. 行頭のホワイトスペース（インデント）を保持する
2. インデント直後に `# ` を挿入する
3. 残りの部分（`- value` 等）はそのまま

正規表現パターン: `^(\s*)(- .*)$` → `\1# \2`

### コメント解除（enable=True）

```
入力行:    "  # - __ref__"
出力行:    "  - __ref__"

入力行:    "  ## - __ref__"
出力行:    "  - __ref__"

入力行:    "    # - literal_value"
出力行:    "    - literal_value"
```

変換ルール:
1. 行頭のホワイトスペース（インデント）を保持する
2. `# ` プレフィックス（複数の `#` を含む）を除去する
3. 残りの部分（`- value` 等）を保持する

正規表現パターン: `^(\s*)#+\s*(- .*)$` → `\1\2`

### 冪等性

- 既にコメント化されている行に対して enable=False → 何もしない
- 既にコメント解除されている行に対して enable=True → 何もしない

判定方法: 行の strip() が `#` で始まるかどうか（パーサーと同じ判定ロジック）

## 関数一覧

### `core/editor.py`

| 関数 | シグネチャ | 説明 |
|---|---|---|
| `toggle_comment` | `(file_path: Path, value_entry: ValueEntry, enable: bool) -> EditResult` | 値行のコメント状態を切り替える |
| `refresh_registry` | `(file_path: Path, registry: KeyRegistry) -> None` | ファイルを再パースしてレジストリを更新する |
| `detect_line_ending` | `(content: str) -> str` | ファイル内容から改行コードを検出する |
| `read_lines` | `(file_path: Path) -> tuple[list[str], str]` | ファイルを行リストと改行コードのタプルとして返す |
| `write_lines` | `(file_path: Path, lines: list[str], line_ending: str) -> None` | 行リストをファイルに書き戻す |
| `_comment_line` | `(line: str) -> str` | 値行をコメント化する（`# ` プレフィックスの付与） |
| `_uncomment_line` | `(line: str) -> str` | 値行のコメントを解除する（`# ` プレフィックスの除去） |
| `_is_commented_line` | `(line: str) -> bool` | 行がコメント行かどうかを判定する |

### データクラス

| クラス | フィールド | 説明 |
|---|---|---|
| `EditResult` | `success: bool`, `error: str \| None = None` | 編集操作の結果。success=False の場合、error にエラーメッセージ |

### 定数

| 定数 | 値 | 説明 |
|---|---|---|
| `LINE_ENDING_CRLF` | `"\r\n"` | Windows 改行コード |
| `LINE_ENDING_LF` | `"\n"` | Unix 改行コード |
| `DEFAULT_LINE_ENDING` | `"\n"` | 改行コードが検出できない場合のデフォルト |

## パフォーマンス考慮

| 操作 | 処理 | 推定時間 |
|---|---|---|
| read_lines | 1ファイルの読み込み | < 1ms |
| 行の書き換え | 文字列置換 | < 0.1ms |
| write_lines | 1ファイルの書き戻し | < 1ms |
| parse_yaml_file（再パース） | 1ファイルのパース | < 1ms |
| レジストリ更新 | dict 操作 | < 0.1ms |
| **toggle_comment 全体** | | **< 5ms** |

ユーザーのチェックボックス操作に対して即座にレスポンスする（5ms 以下）。

## エラー種別

| エラー | 発生条件 | EditResult の error メッセージ |
|---|---|---|
| FileNotFoundError | ファイルが存在しない | "ファイルが見つかりません: {file_path}" |
| UnicodeDecodeError | UTF-8 で読めない | "ファイルの読み込みに失敗しました: {file_path}" |
| OSError | 書き込み権限なし等 | "ファイルの書き込みに失敗しました: {file_path}" |
| IndexError 相当 | line_number が範囲外 | "行番号が範囲外です: {line_number} (ファイル行数: {total})" |
| 行が値行パターンに一致しない | 想定外の行内容 | "対象行が値行ではありません: {line_number}" |

## テストパターン（テスター向けのガイド）

### toggle_comment

**正常系:**
- コメント解除: `# - __ref__` → `- __ref__`（is_commented=True, enable=True）
- コメント化: `- __ref__` → `# - __ref__`（is_commented=False, enable=False）
- ダブルハッシュのコメント解除: `## - __ref__` → `- __ref__`
- リテラル値のコメント化: `- literal_value` → `# - literal_value`
- 冪等: 既にコメント化済み + enable=False → 変更なし
- 冪等: 既にコメント解除済み + enable=True → 変更なし
- インデント保持: スペース4個のインデント → スペース4個のまま
- タブインデント: タブ → タブのまま

**改行コード保持:**
- CRLF ファイル → CRLF のまま
- LF ファイル → LF のまま
- ファイル末尾の改行有無を保持

**異常系:**
- ファイル不存在 → EditResult(success=False)
- 行番号が範囲外 → EditResult(success=False)
- 非値行（キー定義行等）→ EditResult(success=False)

### refresh_registry

- 変更後のファイルを再パースし、レジストリのキー定義が更新されること
- コメント切り替え後に is_commented フラグが正しく更新されること
- 他のファイルのキー定義に影響しないこと

### detect_line_ending / read_lines / write_lines

- CRLF の検出と保持
- LF の検出と保持
- 空ファイル → DEFAULT_LINE_ENDING
- 改行を含まない1行ファイル → DEFAULT_LINE_ENDING

## conftest.py フィクスチャ設計

### 既存フィクスチャの活用

- `commented_ref_cards_dir`: コメント行を含むファイル。toggle_comment のテストで使用
- `yaml_factory`: 任意の YAML コンテンツでファイルを作成

### 新規フィクスチャ候補

- `crlf_yaml(tmp_path)`: CRLF 改行コードの YAML ファイル
- `commented_value_yaml(tmp_path)`: コメント/非コメントの値行を含む YAML ファイル
- `multi_key_yaml(tmp_path)`: 複数キー定義を持つ YAML ファイル（refresh_registry テスト用）
