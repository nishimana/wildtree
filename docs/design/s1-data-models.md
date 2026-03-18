# S1: データモデル定義 (`core/models.py`)

## タスク種別

新規モジュール → コード成果物あり（`core/models.py` にスタブを配置）

## 機能の概要

WildTree v2 のデータモデル層。YAML パース結果とツリー構造を表現するデータクラス群を定義する。S2 以降の全モジュール（scanner, parser, resolver, tree_builder, editor, GUI）がこのモデルに依存する。

## 設計判断の理由（Why）

### 1. v1 との構造的な違い

v1 の `KeyDefinition` は `raw_values: list[str]` を持ち、コメント行を除外、行番号も持たなかった。v2 では以下の要求に対応するため構造を変更した:

- **コメント切り替え機能**: コメント行も保持し、行番号で YAML ファイルの書き換え位置を特定する必要がある
- **リテラル表示**: 値行内の参照とリテラルを分離して保持する必要がある
- **ツリーノードの種別統一**: v1 の `is_leaf` / `is_circular` / `is_unresolved` ブールフラグは排他的関係が暗黙的だった。NodeType Enum で明示化する

### 2. WildcardRef を frozen にした理由

- 参照データはパース後に変更されない（イミュータブル）
- セットやディクショナリのキーとして使用される場面がある（参照の重複検出、循環検出のパス追跡）
- `inner_refs` を `tuple` にしたのも frozen 対応（list は hashable でない）

### 3. WildcardRef.name をプロパティにした理由

- `full_path` から導出可能な値を冗長に保持しない
- 「最後のスラッシュ以降」というルールが1か所に集約される
- ただし、v1 では `name` フィールドとして持っていた。パフォーマンス上の懸念があれば `cached_property` に変更してよい

### 4. RefType と NodeType を分離した理由

- `RefType` は「パーサーが判定する参照パターンの種別」（パース時の関心事）
- `NodeType` は「ツリー表示時のノードの描画方法」（GUI の関心事）
- 同じ Enum に混ぜると、パーサーが GUI の関心事を知る必要が生じる
- 例: `CIRCULAR` や `EMPTY` はパース段階では存在しない（ツリー構築時に生まれる）

### 5. NodeType に ROOT を追加した理由

- v1 ではルートノードは通常の参照ノードと同じ構造だった
- トップツリーのルートノードは意味的に特別（エントリポイント、展開の起点）
- GUI で異なるアイコンや太字表示を適用するために型レベルで区別する

### 6. KeyRegistry 型エイリアスの導入理由

- `dict[str, list[KeyDefinition]]` が複数モジュール（resolver, top_tree, editor）で繰り返し登場する
- 型エイリアスで命名することで、ドメインの語彙として定着させる
- 将来的にラッパークラスに昇格させる余地を残す

### 7. ValueEntry.raw_text の正規化レベル

- `"  - "` プレフィックスは除去（パーサーの責務）
- コメント行の場合は `"# "` プレフィックスも除去した中身を保持
- 元の行全体は `line_number` + ファイル読み直しで復元可能
- この方針により、`raw_text` は参照抽出・リテラル抽出の入力として直接使える

### 却下した代替案

| 案 | 却下理由 |
|----|---------|
| v1 の `raw_values: list[str]` を維持し、コメント情報を別に持つ | 値行と行番号の対応関係が壊れやすい。ValueEntry に統合する方が自然 |
| TreeNode に `is_checked: bool` を持つ | チェック状態は `value_entry.is_commented` の反転で表現可能。冗長なフラグは同期コストを増やす |
| WildcardRef に解決結果 (`resolved_key_def`) を持つ | パーサーの責務（テキスト解析）と resolver の責務（名前解決）が混ざる。レイヤー分離に反する |
| NodeType を str 定数で定義 | Enum の方が typo を防ぎ、IDE の補完・型チェックが効く |
| TreeNode を frozen にする | ツリー構築時に children を段階的に追加するため、ミュータブルの方が自然 |

## スコープ（Scope）

### やること
- 全データクラスの定義（フィールド、型、docstring）
- Enum の定義
- 型エイリアスの定義
- `WildcardRef.name` プロパティのスタブ

### やらないこと（意図的な対象外）
- ロジック（パース、名前解決、ツリー構築、編集操作）は S2 以降で実装
- `WildcardRef.name` プロパティの実装（implementer が実装する唯一のロジック）
- シリアライズ / デシリアライズ（to_dict / from_dict）は現時点で不要
- バリデーションメソッド（is_valid 等）は現時点で不要。パーサーが正しいデータを構築する責務を持つ
- GUI 固有の表示ロジック（アイコン選択、色決定）は GUI 層で行う

## 既存コードとの関係（Context）

### プロトタイプ (`core/wildcard_parser.py`) との対応

| v1 | v2 | 変更点 |
|----|-----|--------|
| `KeyDefinition(name, file_path, raw_values)` | `KeyDefinition(name, file_path, line_number, values)` | `raw_values: list[str]` → `values: list[ValueEntry]`、`line_number` 追加 |
| `WildcardRef(name, raw)` | `WildcardRef(raw, full_path, ref_type, inner_refs)` | `name` をプロパティに、`full_path` を追加、`ref_type` と `inner_refs` を追加、`frozen=True` |
| `TreeNode(name, ref_name, children, is_leaf, is_circular, is_unresolved)` | `TreeNode(display_name, node_type, children, key_def, value_entry, ref)` | ブールフラグ → NodeType Enum、表示に必要な情報を直接保持 |
| なし | `ValueEntry(raw_text, line_number, is_commented, refs, literals)` | 新規。値行の構造化表現 |
| なし | `RefType`, `NodeType` | 新規。Enum で種別を型レベルで管理 |
| なし | `KeyRegistry` | 新規。型エイリアス |

### データフロー

```
scanner.py  →  list[Path]
                  ↓
parser.py   →  list[KeyDefinition]  ← 各 KeyDefinition は ValueEntry を含む
                  ↓                    各 ValueEntry は WildcardRef を含む
           KeyRegistry (dict[str, list[KeyDefinition]])
                  ↓
resolver.py →  キー名 → KeyDefinition の解決
                  ↓
tree_builder.py → TreeNode ツリー
                  ↓
GUI         →  ツリー表示・編集操作
                  ↓
editor.py   →  YAML ファイルの書き換え（ValueEntry.line_number を使用）
```

### 依存関係

- `core/models.py` は標準ライブラリのみに依存（`dataclasses`, `enum`, `pathlib`）
- 他のモジュールは全て `core/models.py` に依存する
- `core/models.py` は他の `core/` モジュールに依存しない（循環依存なし）

## 設計原則（implementer 向け）

### WildcardRef.name プロパティの実装

- `full_path` の最後の `/` 以降を返す
- `/` が含まれない場合は `full_path` 全体を返す
- 空文字列の場合は空文字列を返す

### フィールドの初期値

- `list` 型フィールドには `field(default_factory=list)` を使用（ミュータブルデフォルトの罠を防ぐ）
- `WildcardRef.inner_refs` は `tuple` を使用（frozen=True 対応）

### 命名規則

- フィールド名は英語スネークケース
- docstring とコメントは日本語
- `display_name` は GUI に表示する名前（`name` だと v1 の意味と混同しやすいため変更）

## 正常系・異常系の振る舞い

### 正常系

- パーサーが YAML ファイルを解析し、KeyDefinition と ValueEntry を構築する
- 値行内の参照はパーサーが WildcardRef として抽出する
- tree_builder がエントリポイントから再帰的に TreeNode ツリーを構築する

### 異常系

データモデル自体は例外を投げない（純粋なデータ構造）。異常系は各モジュールで処理する:

| 状況 | 担当モジュール | データモデル上の表現 |
|------|---------------|---------------------|
| YAML ファイルが読めない | parser.py | 空の list[KeyDefinition] を返す（v1 踏襲） |
| 参照先が見つからない | resolver.py / tree_builder.py | TreeNode(node_type=UNRESOLVED) |
| 循環参照を検出 | tree_builder.py | TreeNode(node_type=CIRCULAR) |
| 空定義 `"{}"` | parser.py / tree_builder.py | TreeNode(node_type=EMPTY) |
| 動的参照を含む | parser.py | WildcardRef(ref_type=DYNAMIC, inner_refs=(...)) |
| 重複キー名 | resolver.py | KeyRegistry で同名キーに複数の KeyDefinition |
| 値行が空テキスト | parser.py | スキップ（ValueEntry を生成しない） |

## エッジケース

| ケース | 期待される扱い |
|--------|---------------|
| 空定義 `"{}"` | `ValueEntry(raw_text="{}", ...)` として保持。tree_builder が `NodeType.EMPTY` ノードに変換 |
| 動的参照 `__{__変数__}サフィックス__` | `WildcardRef(ref_type=DYNAMIC, inner_refs=(...))` として保持。初期実装では内部参照を子ノードとして表示 |
| 循環参照 | tree_builder が検出し `TreeNode(node_type=CIRCULAR)` として表示を打ち切る。データモデル自体は循環を検出しない |
| 1行に参照とリテラルが混在 | パーサーが `ValueEntry.refs` と `ValueEntry.literals` に分離して格納 |
| コメントアウトされた値行 | `ValueEntry(is_commented=True)` として保持。GUI でチェックボックス OFF |
| キー定義に値行がゼロ個 | `KeyDefinition(values=[])` — 有効（ただし実データでは稀） |
| 同名キーが複数ファイルに存在 | `KeyRegistry[name]` に複数の `KeyDefinition` が格納される |
| 値行内にカンマ区切りで複数参照 | 1つの `ValueEntry` に複数の `WildcardRef` が `refs` リストとして格納される |
| ファイルレベルのコメント行（`# コメント`） | パーサーがスキップ。ValueEntry は生成されない（v1 踏襲） |
| 値行コメントの中のセクション区切り（`# ---- 区切り ----`） | パーサーがスキップ。ValueEntry は生成されない |
| `line_number` が 0 | 許容しない。行番号は 1 始まり |

## パフォーマンス考慮

- 43,000 キー定義、271 ファイルの規模で全 KeyDefinition をメモリに保持する
- `WildcardRef` を `frozen=True` にすることで、同一参照のハッシュベース比較が O(1)
- `TreeNode` はミュータブル（構築時の段階的な子ノード追加に対応）
- `WildcardRef.name` プロパティの計算コストは `rsplit("/", 1)` の O(n) だが、参照名の長さは通常 50 文字以下なので問題にならない。ホットパスで頻繁に呼ばれる場合は `@cached_property` に変更してよい（ただし frozen dataclass との組み合わせに注意）
