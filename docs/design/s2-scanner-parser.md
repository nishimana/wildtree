# S2: スキャナ + パーサー (`core/scanner.py`, `core/parser.py`)

## タスク種別

新規モジュール → コード成果物あり（`core/scanner.py`, `core/parser.py` にスタブを配置）

## 機能の概要

cards ディレクトリから YAML ファイルを再帰スキャンし（スキャナ）、各ファイルから KeyDefinition を行ベースで抽出する（パーサー）。v1 の `wildcard_parser.py` が1ファイルに担っていた Stage 1〜3 の責務を2つのモジュールに分離する。

## 設計判断の理由（Why）

### 1. スキャナとパーサーを分離した理由

v1 では `scan_yaml_files`, `extract_keys_from_file`, `extract_refs_from_line` が全て `wildcard_parser.py` に同居していた。v2 では以下の理由で分離する:

- **責務の明確化**: スキャナは「ファイルシステムとの対話」、パーサーは「テキストの構造解析」。テスト方針が異なる（スキャナは tmp_path でのファイルシステムテスト、パーサーは純粋な文字列変換テスト）
- **v2 全体設計書 (v2-tree-editor.md) のアーキテクチャ§4.1 に準拠**: `scanner.py` と `parser.py` を別モジュールとして定義済み
- **テスト容易性**: パーサーは入力文字列から出力データクラスへの純粋関数として設計でき、ファイルI/Oなしでテスト可能

### 2. 行ベースパーサーを継続採用する理由

- Dynamic Prompts の YAML は `(`, `:`, `{}`, `<>` 等の特殊文字をプロンプト文字列としてそのまま値に持つ
- PyYAML ではこれらの特殊文字でパースエラーが発生する（v1 プロトタイプで確認済み）
- 実データの YAML 構造は単純（トップレベルキー + インデントされた値行リスト）なので、行ベースパーサーで十分

### 3. `build_key_registry` をパーサーモジュールに配置する理由

- レジストリ構築は「パース済みの KeyDefinition をキー名で索引化する」処理
- scanner でも resolver でもない中間的な責務だが、パーサーの出力を直接消費する点で parser.py が最も自然
- v1 でも `build_key_registry` は `wildcard_parser.py` 内に存在していた

### 4. 参照抽出をパーサーモジュールに含める理由

- 参照抽出（`__name__` パターンの検出）はテキスト解析の一部であり、パーサーの責務
- v1 の `extract_refs_from_line` + `_scan_closing_underscores` の2関数構成を踏襲
- ただし v2 では抽出結果を `WildcardRef` オブジェクト（v2 モデル）として返し、`RefType` の判定と `inner_refs` の構造化も同時に行う

### 5. v1 からの主な変更点

| v1 の振る舞い | v2 での変更 | 理由 |
|---|---|---|
| コメント行をスキップ | コメント行を `ValueEntry(is_commented=True)` として保持 | コメント切替機能に必要 |
| 行番号を追跡しない | `KeyDefinition.line_number` と `ValueEntry.line_number` を記録 | 編集時の書き換え位置特定 |
| リテラルを無視 | `ValueEntry.literals` にリテラル部分を抽出 | ツリー上のリテラル表示 |
| `WildcardRef(name, raw)` | `WildcardRef(raw, full_path, ref_type, inner_refs)` | 動的参照の構造解析 |
| インナー参照をフラットリストに追加 | 動的参照の `inner_refs` タプルに構造化 | ツリー構築時の情報保持 |

### 却下した代替案

| 案 | 却下理由 |
|---|---|
| PyYAML でパースし、失敗時に行ベースにフォールバック | 実データの大半が PyYAML で失敗する。フォールバックが常態化するなら最初から行ベースでよい |
| 値行のコメント判定をパーサー外（editor 等）で行う | コメント判定はパース時の文脈（インデント内の `#` か、キーレベルの `#` か）に依存するため、パーサーに集約すべき |
| `extract_refs_from_line` を `ValueEntry` のメソッドにする | モデルにロジックを持たせない方針（S1 設計書）に反する。パーサーが外部から `refs` と `literals` を設定する |
| 全ファイルを1回で読み込み、巨大な文字列として処理 | ファイル単位の処理の方がメモリ効率が良く、エラー分離もしやすい |

## スコープ（Scope）

### やること

- `core/scanner.py`: ディレクトリ再帰スキャン、YAML ファイルリストの返却
- `core/parser.py`:
  - キー定義の抽出（行ベース、コメント行も保持、行番号追跡）
  - 参照パターンの抽出（通常参照、動的参照の判定、inner_refs 構造化）
  - リテラル部分の抽出（カンマ区切りで参照でない部分）
  - レジストリ構築（キー名 → KeyDefinition リストの辞書）

### やらないこと（意図的な対象外）

| 対象外 | 理由 |
|---|---|
| 名前解決（`resolve()`） | S3 の責務。パーサーは `WildcardRef.full_path` を記録するだけで、解決先の `KeyDefinition` は知らない |
| ツリー構築 | S5 の責務 |
| トップツリー検出 | S4 の責務 |
| 動的参照の展開（変数値の解決） | S9 の責務。パーサーは動的参照を検出し構造化するのみ |
| YAML ファイルの書き換え | S7 (editor) の責務 |
| GUI との連携 | S6 以降の責務 |
| Dynamic Prompts 構文の完全解析（`{0-2$$...}`, `{...|...}` 等） | ワイルドカード参照（`__name__`）の抽出のみを行う。DP 構文自体はリテラルとして扱う |
| 値行内のインラインコメント解析 | `# まあほどほどに使える` のようなキー定義行末のコメントは、キー名抽出時にコロン以降として除外される。値行内のインラインコメントは実データに存在しないため対応しない |

## 既存コードとの関係（Context）

### v1 プロトタイプとの対応

| v1 (`wildcard_parser.py`) | v2 | 変更点 |
|---|---|---|
| `scan_yaml_files()` | `scanner.scan_yaml_files()` | ロジックは同等。別モジュールに移動 |
| `extract_keys_from_file()` | `parser.parse_yaml_file()` | コメント行の保持、行番号追跡、ValueEntry への構造化を追加 |
| `extract_refs_from_line()` | `parser.extract_refs()` | v2 の `WildcardRef`（RefType, inner_refs）を返す |
| `_scan_closing_underscores()` | `parser._scan_closing_delimiters()` | v2 向けにリネーム。ロジックは v1 を参考にする |
| `build_key_registry()` | `parser.build_registry()` | v2 の `KeyRegistry` 型を使用 |
| なし | `parser.extract_literals()` | 新規。値行テキストから参照でない部分を抽出 |
| なし | `parser._parse_value_line()` | 新規。値行テキストから ValueEntry を構築する統合関数 |

### データモデルとの関係

パーサーの出力型は全て `core/models.py` で定義済み:

```
parser.parse_yaml_file(file_path)
  → list[KeyDefinition]
       ↓
  各 KeyDefinition.values: list[ValueEntry]
       ↓
  各 ValueEntry.refs: list[WildcardRef]
  各 ValueEntry.literals: list[str]

parser.build_registry(yaml_files)
  → KeyRegistry (= dict[str, list[KeyDefinition]])
```

### データフロー

```
[cards ディレクトリ]
    ↓ scanner.scan_yaml_files()
[list[Path]]  -- YAML ファイルパスの一覧
    ↓ parser.parse_yaml_file() × N回
[list[KeyDefinition]]  -- 各ファイルのキー定義
    ↓ parser.build_registry()
[KeyRegistry]  -- 名前解決用の索引
    ↓ (S3: resolver.py)
    ↓ (S4: top_tree.py)
    ↓ (S5: tree_builder.py)
```

## 設計原則（implementer 向け）

### スキャナ

1. **ファイルシステム操作のみを担当する**: パースロジックは一切含まない。Path のリストを返すだけ
2. **存在しないディレクトリは例外で報告**: `FileNotFoundError` / `NotADirectoryError`。v1 と同じ振る舞い
3. **ソート順を保証する**: `sorted()` で安定した処理順序を確保。重複キーの「後勝ち」動作が予測可能になる
4. **拡張子は `.yaml` と `.yml` の両方を対象**: v1 踏襲

### パーサー

1. **行ベースパーサーの基本構造**: ファイルの各行を順にスキャンし、インデントの有無でキー行と値行を判別する
2. **コメント行の判定ルール**:
   - **キーレベルのコメント** (`# SSNN0001: ...`, `####...`, `# ---- 区切り ----`): スキップ（ValueEntry を生成しない）
   - **値行のコメント** (`  # - __ref__`): `ValueEntry(is_commented=True)` として保持
   - 判定基準: インデントされた行で、strip 後に `#` で始まる行が値行コメント。ただし、**`- ` プレフィックスを含む行のみ** を値行コメントとして扱う（`# - value` または `# value` の形式で、実際に有効な値行をコメントアウトしたもの）
   - **セクション区切り** (`  # ---- 白球少女 ----`): `- ` プレフィックスを含まないため値行コメントではない。スキップする
3. **行番号は 1 始まり**: ファイルの最初の行が 1
4. **UTF-8 エンコーディングを明示**: `file_path.read_text(encoding="utf-8")`
5. **CRLF 対応**: `content.splitlines()` を使う（`split("\n")` ではない）
6. **I/O エラー時は空リスト**: 読めないファイルは空の `list[KeyDefinition]` を返す。個別ファイルのエラーで全体スキャンを止めない
7. **`raw_text` の正規化**: `"  - "` プレフィックスを除去。コメント行は `"# - "` の `"# "` も除去した中身（`"- "` まで除去した残りの値テキスト）
8. **キー定義行末のコメント処理**: `動き構図: # まあほどほどに使える` → キー名は `動き構図`。`:` 以降をコメント（または値）として解釈するが、Dynamic Prompts の YAML では `:` 以降に値を持つキーはないため、`:` で split してキー名を取得すれば十分
9. **参照抽出は ValueEntry 構築時に同時に行う**: パース済みの `raw_text` から参照とリテラルを抽出し、`ValueEntry.refs` と `ValueEntry.literals` に設定する
10. **空行はスキップ**: strip 後に空文字列になる行は ValueEntry を生成しない

### 参照抽出

1. **`__name__` パターンの検出**: v1 の `_scan_closing_underscores` のアルゴリズムを参考にする。ブレース深度とインナーワイルドカード深度を追跡して正しく閉じ `__` を見つける
2. **RefType の判定**: ボディ部分に `{__` を含む場合は `RefType.DYNAMIC`、それ以外は `RefType.NORMAL`
3. **inner_refs の構造化**: 動的参照の場合、ボディ部分を再帰的にパースして内部の `__name__` を抽出し、`WildcardRef.inner_refs` に `tuple[WildcardRef, ...]` として格納する。v1 はフラットリストに追加していたが、v2 では親子関係を保持する
4. **full_path の構成**: 開き `__` と閉じ `__` の間のテキストがそのまま `full_path` になる。動的参照の場合は `{__inner__}` を含むテキスト全体が `full_path`

### リテラル抽出

1. **カンマ区切りの値行**を分割し、各セグメントが参照（`__name__`）でない場合にリテラルとして扱う
2. **空文字列のセグメントは除外**: `,,` のような連続カンマがあっても空リテラルは生成しない
3. **リテラルの trim**: 前後の空白を strip する
4. **DP 構文 (`{...|...}`, `{0-2$$...}`) はリテラルとして保持**: パーサーはワイルドカード参照のみ解析し、DP 構文は「そのまま」リテラルテキストとして残す
5. **リテラルと参照の混在**: `dynamic_angle,dynamic_pose,__cards/シネマシャドウ__` → literals = `["dynamic_angle", "dynamic_pose"]`, refs = `[WildcardRef(full_path="cards/シネマシャドウ", ...)]`

### コメント行の `raw_text` 正規化詳細

実データの値行コメントパターン:

```
  # - __cards/xxx/yyy__,__cards/xxx/zzz__     ← 典型的なコメントアウト
  # - __朝田詩乃シーンまとめ__                   ← 短縮形
```

正規化手順:
1. 行全体を strip → `# - __cards/xxx/yyy__,...`
2. 先頭の `#` を除去し strip → `- __cards/xxx/yyy__,...`
3. `- ` プレフィックスを除去 → `__cards/xxx/yyy__,...`
4. これが `raw_text` になる

非コメント行:
1. 行全体を strip → `- __cards/xxx/yyy__,...`
2. `- ` プレフィックスを除去 → `__cards/xxx/yyy__,...`
3. これが `raw_text` になる

**結果**: コメント行と非コメント行で `raw_text` のフォーマットが統一される。参照抽出・リテラル抽出のロジックを共通化できる。

### conftest.py フィクスチャ設計

S1 振り返りで「conftest.py のフィクスチャ設計を早期に検討すべき」と記録されている。S2 のテストでは以下のフィクスチャが必要になる:

- **スキャナテスト用**: `yaml_factory` フィクスチャ（既存）で十分。ファイルシステム操作のテスト
- **パーサーテスト用**: YAML 文字列を直接渡すヘルパー不要（`parse_yaml_file` はファイルパスを受け取る設計のため、`yaml_factory` でファイルを作成してからパース）
- **参照抽出テスト用**: 純粋関数のテストなので文字列を直接渡す。フィクスチャ不要
- **レジストリ構築テスト用**: 既存の `multi_file_cards_dir` 等を活用可能

新規フィクスチャの追加が必要な場合:
- `commented_values_yaml`: コメント行を含む YAML（値行コメントとセクション区切りの混在テスト用）
- `empty_def_yaml`: `"{}"` を含む YAML
- `dynamic_ref_yaml`: 動的参照を含む YAML

これらは目的が明確に異なるため、別フィクスチャとして分離する（ナレッジ: 共有フィクスチャに複数の目的を兼ねさせない）。

## 正常系・異常系の振る舞い

### スキャナ

| 状況 | 振る舞い |
|---|---|
| cards ディレクトリが存在し YAML ファイルがある | ソート済みの `list[Path]` を返す |
| cards ディレクトリが存在するが YAML ファイルがない | 空の `list[Path]` を返す |
| cards ディレクトリが存在しない | `FileNotFoundError` を raise |
| パスがディレクトリでない（ファイル等） | `NotADirectoryError` を raise |
| `.yaml` と `.yml` が混在 | 両方を収集する |
| サブディレクトリが深くネストされている | 再帰的に全階層を探索する |
| 日本語ファイル名・日本語ディレクトリ名 | 正常に処理する（Path の Unicode 対応） |

### パーサー — ファイルパース

| 状況 | 振る舞い |
|---|---|
| 正常な YAML ファイル | `list[KeyDefinition]` を返す（各キー定義に values が含まれる） |
| ファイルが読めない (OSError) | 空の `list[KeyDefinition]` を返す |
| ファイルが UTF-8 でない (UnicodeDecodeError) | 空の `list[KeyDefinition]` を返す |
| ファイルが空 | 空の `list[KeyDefinition]` を返す |
| キー定義に値行がゼロ個 | `KeyDefinition(values=[])` を返す（有効） |
| 全ての値行がコメント | 全 ValueEntry が `is_commented=True` で保持される |

### パーサー — 参照抽出

| 状況 | 振る舞い |
|---|---|
| 通常参照 `__cards/path/key__` | `WildcardRef(ref_type=NORMAL, full_path="cards/path/key")` |
| 短縮形参照 `__key__` | `WildcardRef(ref_type=NORMAL, full_path="key")` |
| 動的参照 `__{__cards/a__}{__cards/b__}__` | `WildcardRef(ref_type=DYNAMIC, inner_refs=(ref_a, ref_b))` |
| 参照なしのリテラル行 | 空の `refs` リスト、リテラル全体が `literals` に |
| 閉じ `__` が見つからない | その `__` は参照として認識されない。リテラルの一部として扱う |
| 1行に参照とリテラルが混在 | `refs` に参照、`literals` にリテラル部分が分離して格納 |

### パーサー — レジストリ構築

| 状況 | 振る舞い |
|---|---|
| 正常な YAML ファイルリスト | `KeyRegistry` を返す |
| 空のファイルリスト | 空の `KeyRegistry ({})` を返す |
| 同名キーが複数ファイルに存在 | 同名キーに対して `list[KeyDefinition]` に複数のエントリが格納される |
| 個別ファイルのパースが失敗 | そのファイルの KeyDefinition が 0 個になるだけ。他のファイルは正常に処理 |

## エッジケース

### 実データから発見したパターン

| パターン | 実例 | 期待する処理 |
|---|---|---|
| カンマ区切りで参照とリテラルが混在 | `dynamic_angle,dynamic_pose,__cards/シネマシャドウ__,__cards/バックライト__,` | refs: 2件、literals: 2件。末尾カンマ後の空セグメントは無視 |
| 行末のカンマ | `__cards/デフォルト__,__cards/アングル__,__cards/options/ライティングxmdl__,__cards/シーンまとめ__` | 参照のみ、リテラルなし |
| 空定義 `"{}"` | `- "{}"` | `ValueEntry(raw_text='"{}"', refs=[], literals=['"{}"'])` |
| DP 構文を含むリテラル | `scenery{,(wide_shot:1.3)\|(very_wide_shot:1.3)\|}` | リテラルとして保持（DP 構文は解析しない） |
| lora タグ | `<lora:SwordArtOnline_Sinon_IlluXL:0.8>,AsadaShino` | リテラルとして保持 |
| 動的参照 — 単一内部参照 | `__{__cards/options/貧乳キャラ__}__` | `RefType.DYNAMIC`, inner_refs に1つ |
| 動的参照 — 複数内部参照 | `__{__cards/姦キー__}{__cards/鬼キー__}__` | `RefType.DYNAMIC`, inner_refs に2つ |
| 動的参照 — サフィックス付き | `__{__cards/キャラキー__}NP__` | `RefType.DYNAMIC`, full_path は `{__cards/キャラキー__}NP` |
| 動的参照 — プレフィックス付き | `__cards/ソードアート・オンライン/CH朝田詩乃/朝田詩乃ステージSSNN0001_{__cards/姦キー__}{__cards/鬼キー__}__` | `RefType.DYNAMIC`, full_path は `cards/ソードアート・オンライン/CH朝田詩乃/朝田詩乃ステージSSNN0001_{__cards/姦キー__}{__cards/鬼キー__}` |
| セクション区切りコメント | `  # ---- 白球少女 ----` | スキップ（ValueEntry を生成しない） |
| セパレータ行 | `############################################################################################` | キーレベルのコメントとしてスキップ |
| 値行コメント内にカンマ区切り参照 | `  # - __ref1__,__ref2__,__ref3__` | `ValueEntry(is_commented=True, raw_text="__ref1__,__ref2__,__ref3__", refs=[3件])` |
| キー定義行末のコメント | `動き構図: # まあほどほどに使える` | キー名: `動き構図`。`#` 以降は無視 |
| クォート付き値 | `- "00"`, `- "01"` | `raw_text` は `"00"` (クォート含む)。リテラルとして `'"00"'` |
| 性格表現（DP 構文の複雑な例） | `"{{,(expressionless:0.7)}|}{{,(slight_smile:0.7)|}|}"` | リテラルとして保持 |
| DP 量指定子付き参照 | `{0-2$$__cards/options/ライティング__}` | `__cards/options/ライティング__` は参照として抽出。`{0-2$$...}` はリテラルの一部 |
| DP 選択構文と参照の混在 | `{,__cards/options/アングル_from系2__\|}` | `__cards/options/アングル_from系2__` は参照として抽出 |
| DP 選択構文と参照（末尾パイプ） | `{,__cards/options/男序盤251007__\|}` | `__cards/options/男序盤251007__` は参照として抽出 |
| 短縮形参照（パスなし） | `__朝田詩乃SinonGGOFight脱00__` | `WildcardRef(full_path="朝田詩乃SinonGGOFight脱00", ref_type=NORMAL)` |
| 動的参照 — シーケンス行動 | `__cards/シーケンス{__cards/ソードアート・オンライン/CH朝田詩乃/シーン/朝田詩乃シーケンス行動種別キー__}行動00__` | `RefType.DYNAMIC` |
| `#シーン／シーケンス定義` (インデントなし) | ファイル先頭のコメント | キーレベルコメント。スキップ |
| `####################` | セパレータ | キーレベルコメント。スキップ |
| キー定義全体のコメントアウト | `# 朝田詩乃SSNN000400:` + `#   - 1girl,...` | 両方ともインデントなし（column 0）でキーレベルコメント。スキップ |
| 空行のみの値ブロック | キー定義の後に空行のみ | `KeyDefinition(values=[])` |

### コメント行の判定ルール（詳細）

実データのインデントされたコメント行には2種類がある:

1. **値行のコメントアウト** — 元は有効な値行だった:
   ```
     # - __cards/ブルーアーカイブ/CH白洲アズサ/シーン/白洲アズサシーンまとめ__,...
   ```
   - 特徴: strip 後に `# - ` で始まる、または `#` を除去して strip すると `- ` で始まる
   - → `ValueEntry(is_commented=True)` として保持

2. **セクション区切り・メモ** — 値行ではない:
   ```
     # ---- 白球少女 ----
     # ---- 湯煙の宿 花菱 ----
   ```
   - 特徴: strip 後に `#` で始まるが、`- ` で始まるリスト項目パターンを含まない
   - → スキップ（ValueEntry を生成しない）

**判定ロジック**:
```
stripped = line.strip()
if stripped.startswith("#"):
    after_hash = stripped.lstrip("#").strip()
    if after_hash.startswith("- "):
        # 値行のコメントアウト → ValueEntry(is_commented=True)
        raw_text = after_hash[2:]  # "- " を除去
    else:
        # セクション区切りまたはメモ → スキップ
```

ただし、`# value_without_dash` のような `- ` なしのコメントアウトも考慮する必要がある。実データでは確認されていないが、安全側に倒して以下のルールとする:

**確定ルール**: strip 後に `#` で始まるインデント行のうち:
- `# - ` で始まるもの → 値行コメント（`- ` 以降が `raw_text`）
- 上記以外（`# ---- ...`, `# 自由コメント`） → スキップ

この方針は実データの全パターンと整合する。将来的に `# value` 形式のコメントアウトが必要になった場合は、判定ロジックを拡張する。

## パフォーマンス考慮

### 規模

- 271 ファイル、43,000 キー定義
- 1ファイルあたり平均 160 キー定義
- 全ファイルの読み込み + パースが起動時に一括実行される

### 設計上の配慮

1. **ファイル読み込みは1回のみ**: `file_path.read_text()` でファイル全体を1回で読み、`splitlines()` で行リストに変換。行ごとに `readline()` しない
2. **正規表現のコンパイル**: キーパターンの正規表現 (`re.compile(r"^([^:]+):")`) はモジュールレベルで1度だけコンパイルする
3. **参照抽出は値行単位**: 行全体に `__` が含まれない場合は参照抽出をスキップ（早期リターン）
4. **レジストリ構築は defaultdict**: `defaultdict(list)` で追加のオーバーヘッドを最小化。最終的に通常の `dict` に変換して返す
5. **メモリ**: 43,000 × KeyDefinition + ValueEntry + WildcardRef は数十 MB 程度。問題なし

### ボトルネックの予測

- **ファイル I/O**: 271 ファイルの読み込み。SSD 環境では数百ミリ秒程度
- **参照抽出**: `_scan_closing_delimiters` の文字単位スキャンが最も計算コストが高い。ただし行あたりの文字数は通常数百文字以下

### 計測ポイント

実装後に以下を計測し、ボトルネックがあれば対処:
- `scan_yaml_files()` の実行時間
- `parse_yaml_file()` の1ファイルあたりの実行時間
- `build_registry()` の全体実行時間
- 全体（スキャン + パース + レジストリ構築）の合計時間

目標: 実データ（271 ファイル、43,000 キー）で合計 3 秒以内。

## 関数一覧

### `core/scanner.py`

| 関数 | シグネチャ | 説明 |
|---|---|---|
| `scan_yaml_files` | `(cards_dir: Path) -> list[Path]` | YAML ファイルを再帰的にスキャンし、ソート済みリストを返す |

### `core/parser.py`

| 関数 | シグネチャ | 説明 |
|---|---|---|
| `parse_yaml_file` | `(file_path: Path) -> list[KeyDefinition]` | YAML ファイルからキー定義を抽出する |
| `extract_refs` | `(text: str) -> list[WildcardRef]` | テキストからワイルドカード参照を抽出する |
| `extract_literals` | `(text: str, refs: list[WildcardRef]) -> list[str]` | テキストから参照部分を除いたリテラルを抽出する |
| `build_registry` | `(yaml_files: list[Path]) -> KeyRegistry` | YAML ファイルリストからキーレジストリを構築する |
| `_scan_closing_delimiters` | `(text: str, body_start: int) -> int` | 閉じ `__` の位置を検出する（内部関数） |
| `_parse_value_line` | `(raw_text: str) -> tuple[list[WildcardRef], list[str]]` | 値行テキストから参照とリテラルを抽出する（内部関数） |

## エラー種別

| エラー | 発生条件 | 例外型 | 発生モジュール |
|---|---|---|---|
| ディレクトリが存在しない | `cards_dir` が存在しない | `FileNotFoundError` | scanner |
| パスがディレクトリでない | `cards_dir` がファイル等 | `NotADirectoryError` | scanner |
| ファイル読み込みエラー | I/O エラー、パーミッション等 | 例外なし（空リストを返す） | parser |
| エンコーディングエラー | UTF-8 でないファイル | 例外なし（空リストを返す） | parser |
