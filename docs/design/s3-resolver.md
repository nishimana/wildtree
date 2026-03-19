# S3: 名前解決 (`core/resolver.py`)

## タスク種別

新規モジュール → コード成果物あり（`core/resolver.py` にスタブを配置）

## 機能の概要

パーサーが構築した KeyRegistry を使い、ワイルドカード参照（WildcardRef の full_path）を対応する KeyDefinition にマッピングする。v2 パーサーパイプラインの Stage 4 に該当する。

## 設計判断の理由（Why）

### 1. クラスではなく関数ベースにする理由

v1 は `WildcardResolver` クラスで `_key_registry` と `_cards_dir` をインスタンス変数として保持していた。v2 では以下の理由で関数ベースに変更する:

- **`cards_dir` への依存を排除**: v1 ではフルパス参照の解決に `cards_dir` を使ってファイルの相対パスを計算していた。v2 では KeyRegistry に **フルパスインデックス**（`full_path → KeyDefinition` のマッピング）を事前構築することで、解決時にファイルシステムパスを参照する必要がなくなる
- **テスト容易性**: 関数ベースにすることで、テスト時にクラスのインスタンス化が不要。レジストリと参照を渡すだけでテスト可能
- **責務の明確化**: v1 の `get_refs_for_key()` は「キー定義から参照を抽出する」処理であり、パーサーの責務。v2 ではパーサーが ValueEntry.refs に事前格納済みのため不要

### 2. フルパスインデックスを事前構築する理由

v1 ではフルパス参照の解決時に、`cards_dir` からの相対パスを動的に計算していた。v2 では:

- `build_full_path_index()` でレジストリから全 KeyDefinition を走査し、`cards_dir` 相対パスから `full_path`（`"dir/subdir/keyname"` 形式）を計算して辞書に格納する
- 解決時は辞書引き O(1) で完了。42,957 キーでの線形探索を避ける
- このインデックスは `KeyRegistry` とは別のデータ構造として管理する（KeyRegistry のキーは「キー名」、フルパスインデックスのキーは「full_path」）

### 3. フルパスインデックス構築を resolver に配置する理由

- フルパスインデックスは「名前解決のための索引」であり、resolver の責務
- パーサーはファイル単位で動作し、cards_dir 全体の構造を知らない
- scanner が cards_dir を知っているが、scanner はファイルシステム操作のみを担当する方針

### 4. 短縮形参照の「後勝ち」ルールを維持する理由

- v1 と同じ振る舞い。実データの重複キー4件は全て同一内容なので、後勝ちで問題ない
- 将来的に重複キーが増えた場合はあいまい警告を出す。ただし S3 の初期実装では警告は GUI 層の責務とし、resolver は「最後の定義を返す」に徹する
- 「最後」の定義は `build_registry()` のファイル処理順序で決まる（ソート済みのファイルリスト → 後のファイルの定義が後に来る）

### 5. 循環参照検出を resolver に含めない理由

- 循環参照は「ツリー構築時の再帰的な参照辿り」で発生する。resolver は「1つの参照名 → 1つの KeyDefinition」の単発マッピングであり、再帰構造を持たない
- v1 でも循環参照は `build_tree()` 内の visited セットで検出していた
- resolver に循環検出を含めると、resolver がツリー構築の文脈（どの経路から到達したか）を知る必要が生じ、責務が混ざる

### 6. 動的参照の扱い

動的参照（`__{__cards/a__}suffix__`）は、その full_path に `{__...}__` を含むため、直接的な辞書引きでは解決できない。

**S3 での対応範囲**:
- `resolve()` は動的参照に対して `None` を返す（フルパスインデックスにマッチしないため）
- `resolve_dynamic_inner_refs()` で動的参照の内部参照（`inner_refs`）を個別に解決する。これにより、ツリー構築時に動的参照の内部構造を展開できる
- 動的参照の完全な展開（変数値の代入 → 最終参照名の組み立て → 解決）は S9 の責務

### 7. ResolveResult の導入理由

`resolve()` の戻り値を `KeyDefinition | None` ではなく `ResolveResult` データクラスにした理由:

- 解決成功時に「どのような方法で解決されたか」（フルパス / 短縮形）を記録する
- 重複キーの存在を呼び出し元に伝達する（`is_ambiguous` フラグ）
- 将来的に「解決時の追加情報」（候補の一覧等）を拡張しやすい

### 却下した代替案

| 案 | 却下理由 |
|---|---|
| v1 同様のクラスベース設計 | `cards_dir` 依存が残り、テスト時に実際のディレクトリ構造が必要。フルパスインデックスを事前構築すれば不要 |
| 短縮形参照で「先勝ち」 | v1 との互換性を壊す。実データで問題がない現状で変更する理由がない |
| resolver に循環参照検出を含める | 責務の混在。解決と構築を分離する設計方針に反する |
| `resolve()` で動的参照を完全展開 | 変数値の解決にはツリー構築時の文脈（どの値行が有効か）が必要。S3 単独では不可能 |
| フルパスインデックスを KeyRegistry に統合 | KeyRegistry は「キー名 → 定義リスト」の素直なマッピング。別の索引形式を混ぜると KeyRegistry の意味が曖昧になる |

## スコープ（Scope）

### やること

- `build_full_path_index()`: KeyRegistry と cards_dir からフルパスインデックスを構築する
- `resolve()`: 参照の full_path を使って KeyDefinition を解決する（フルパス参照 → 短縮形参照の2段フォールバック）
- `resolve_dynamic_inner_refs()`: 動的参照の inner_refs を個別に解決する
- `find_unresolved_refs()`: レジストリ全体をスキャンし、解決できない参照を収集する
- `find_duplicate_keys()`: 同名キーが複数ファイルに存在するケースを検出する
- `ResolveResult` データクラスの定義

### やらないこと（意図的な対象外）

| 対象外 | 理由 |
|---|---|
| 循環参照の検出 | tree_builder (S5) の責務。resolver は単発の名前解決のみ |
| 動的参照の完全展開（変数値の代入 → 最終参照名の組み立て） | S9 の責務。S3 では内部参照の個別解決まで |
| ツリー構築 | tree_builder (S5) の責務 |
| トップツリー検出 | top_tree (S4) の責務 |
| GUI への結果表示 | GUI 層 (S6) の責務 |
| 重複キーの警告 UI | GUI 層の責務。resolver は検出のみ |
| コメント行の解決スキップ | `is_commented` の判定は tree_builder が行う。resolver は渡された参照を解決するだけ |

## 既存コードとの関係（Context）

### v1 プロトタイプとの対応

| v1 (`wildcard_parser.py`) | v2 (`resolver.py`) | 変更点 |
|---|---|---|
| `WildcardResolver.__init__(keys, cards_dir)` | `build_full_path_index(registry, cards_dir)` | クラス → 関数。cards_dir はインデックス構築時のみ使用 |
| `WildcardResolver.resolve(ref_name)` | `resolve(full_path, full_path_index, registry)` | 純粋関数化。インデックスとレジストリを引数で受け取る |
| `WildcardResolver.get_all_key_names()` | なし | `sorted(registry.keys())` で代替可能。専用関数不要 |
| `WildcardResolver.get_refs_for_key()` | なし | v2 ではパーサーが ValueEntry.refs に格納済み。resolver の責務外 |
| なし | `resolve_dynamic_inner_refs()` | 新規。動的参照の内部参照を解決 |
| なし | `find_unresolved_refs()` | 新規。未解決参照の一括検出 |
| なし | `find_duplicate_keys()` | 新規。v2-tree-editor.md に定義済みだが配置先が未定だった |
| なし | `ResolveResult` | 新規。解決結果の構造化 |

### データフロー

```
[KeyRegistry]  -- parser.build_registry() の出力
    ↓
build_full_path_index(registry, cards_dir)
    ↓
[FullPathIndex]  -- full_path → KeyDefinition の辞書
    ↓
resolve(full_path, full_path_index, registry)
    ↓
[ResolveResult]  -- 解決結果（KeyDefinition + メタ情報）
    ↓ (S5: tree_builder.py が使用)
[TreeNode ツリー]
```

### 依存関係

- `core/resolver.py` は `core/models.py` に依存（KeyDefinition, KeyRegistry, WildcardRef, RefType）
- `core/resolver.py` は `core/parser.py` に依存しない（レジストリは引数で受け取る）
- `core/resolver.py` は `core/scanner.py` に依存しない（cards_dir は引数で受け取る）

### データモデルとの関係

resolver が使用する既存の型:
- `KeyDefinition`: 解決結果として返却
- `KeyRegistry` (`dict[str, list[KeyDefinition]]`): 短縮形参照の解決に使用
- `WildcardRef`: `full_path`, `ref_type`, `inner_refs` を参照
- `RefType`: 動的参照の判定に使用

resolver が新規追加する型:
- `ResolveResult`: 解決結果の構造化データ
- `FullPathIndex` (型エイリアス): フルパスインデックスの型

## 設計原則（implementer 向け）

### 1. フルパスインデックスの構築ルール

`build_full_path_index(registry, cards_dir)` は以下のルールでインデックスを構築する:

1. レジストリの全 KeyDefinition を走査する
2. 各 KeyDefinition の `file_path` から `cards_dir` の相対パスを計算する
3. 相対パスの親ディレクトリ + キー名を `/` で結合して full_path を組み立てる
4. Windows パスの `\` は `/` に正規化する
5. 相対パスの親が `.`（直下のファイル）の場合、full_path はキー名のみ

**例**:
```
cards_dir: C:/cards
file_path: C:/cards/SAO/CH_asada/asada.yaml
key_name: "朝田詩乃"
→ relative: SAO/CH_asada/asada.yaml
→ parent: SAO/CH_asada
→ full_path: "SAO/CH_asada/朝田詩乃"
```

```
cards_dir: C:/cards
file_path: C:/cards/main.yaml
key_name: "メイン"
→ relative: main.yaml
→ parent: .
→ full_path: "メイン"
```

**重複 full_path の扱い**: 同じ full_path を持つ KeyDefinition が複数ある場合（同一ディレクトリ・同一キー名）、後のエントリで上書き（後勝ち）する。これは KeyRegistry の「後のファイルが後に来る」順序と整合する。

### 2. 参照解決のアルゴリズム

`resolve(full_path, full_path_index, registry)` は以下の順序で解決を試みる:

**ステップ 1: フルパスインデックスで直接引き**
- `full_path` が `"cards/"` で始まる場合、`"cards/"` を除去した文字列でフルパスインデックスを検索する
- `full_path` が `"cards/"` で始まらない場合もそのまま検索する（直下ファイルのキー等）
- ヒットした場合、解決成功（`ResolveResult(key_def=..., method="full_path")`）

**ステップ 2: 短縮形参照として解決**
- `full_path` の最後の `/` 以降をキー名として KeyRegistry を検索する
- `/` が含まれない場合は `full_path` 全体がキー名
- ヒットした場合、リストの最後の KeyDefinition を返す（後勝ち）
- 同名キーが2つ以上ある場合は `is_ambiguous=True` を設定する

**ステップ 3: 解決失敗**
- どちらでもヒットしない場合は `None` を返す

**`"cards/"` プレフィックスの扱い**:
実データの参照は `__cards/SAO/CH_asada/朝田詩乃__` のように `cards/` プレフィックスを含む。これは cards ディレクトリの名前であり、ファイルシステム上のパス構造に由来する。フルパスインデックスのキーは `cards/` を含まない形式（`"SAO/CH_asada/朝田詩乃"`）で格納するため、resolve 時に除去する。

### 3. 動的参照の内部参照解決

`resolve_dynamic_inner_refs(ref, full_path_index, registry)`:

- `ref.ref_type == RefType.DYNAMIC` の場合のみ処理する
- `ref.inner_refs` の各内部参照に対して `resolve()` を呼ぶ
- 結果を `dict[WildcardRef, ResolveResult | None]` として返す
- 内部参照が全て解決できた場合でも、動的参照自体は「未展開」のまま（展開は S9）

### 4. 未解決参照の収集

`find_unresolved_refs(registry, full_path_index)`:

- レジストリの全 KeyDefinition の全 ValueEntry の全 WildcardRef を走査する
- 各参照に対して `resolve()` を実行し、解決できない参照を収集する
- 動的参照は `ref_type == RefType.DYNAMIC` なので、以下のルールで判定する:
  - 動的参照自体は「未解決」ではない（展開前なので判定不能）
  - 動的参照の `inner_refs` 内の参照が解決できない場合は「未解決」として記録する
- 結果を `list[UnresolvedRef]` として返す（参照元のキー名・ファイル・行番号を含む）

### 5. 重複キーの検出

`find_duplicate_keys(registry)`:

- KeyRegistry の各エントリで `len(defs) > 1` のものを抽出する
- v2-tree-editor.md の §5 に定義済みのアルゴリズムと同等

### 6. エラーハンドリング方針

- `build_full_path_index()`: `file_path` が `cards_dir` の外にある場合（`relative_to()` で `ValueError`）、その KeyDefinition はインデックスに含めない。エラーは無視する
- `resolve()`: 解決できない場合は `None` を返す。例外は投げない
- `resolve_dynamic_inner_refs()`: 通常参照が渡された場合は空辞書を返す。例外は投げない
- `find_unresolved_refs()`: 全参照を走査するため時間がかかる可能性があるが、42,957 キーの規模では問題にならない見込み

## 正常系・異常系の振る舞い

### build_full_path_index

| 状況 | 振る舞い |
|---|---|
| 正常なレジストリと cards_dir | FullPathIndex を返す |
| 空のレジストリ | 空の FullPathIndex を返す |
| file_path が cards_dir 外のキー定義がある | その定義はインデックスに含めない（スキップ） |
| 同一 full_path を持つ複数の KeyDefinition | 後勝ち（後のエントリで上書き） |
| cards_dir 直下のファイルのキー | full_path はキー名のみ（ディレクトリ部分なし） |

### resolve

| 状況 | 振る舞い |
|---|---|
| フルパス参照 `cards/SAO/CH_asada/朝田詩乃` → インデックスにある | `ResolveResult(key_def=..., method="full_path")` |
| フルパス参照 → インデックスにない → 短縮形で見つかる | `ResolveResult(key_def=..., method="short")` |
| 短縮形参照 `朝田詩乃` → レジストリにある（1件） | `ResolveResult(key_def=..., method="short", is_ambiguous=False)` |
| 短縮形参照 → レジストリにある（複数件） | `ResolveResult(key_def=last, method="short", is_ambiguous=True)` |
| 参照がどこにもない | `None` |
| 空文字列の full_path | `None` |
| 動的参照の full_path（`{__...}__` を含む） | フルパスインデックスにマッチしない → 短縮形でもマッチしない → `None` |

### resolve_dynamic_inner_refs

| 状況 | 振る舞い |
|---|---|
| 動的参照で inner_refs が全て解決可能 | 全ての内部参照に ResolveResult が設定された辞書 |
| 動的参照で inner_refs の一部が未解決 | 未解決の内部参照は `None` |
| 動的参照で inner_refs が空 | 空辞書 |
| 通常参照が渡された場合 | 空辞書（動的参照でないため処理しない） |

### find_unresolved_refs

| 状況 | 振る舞い |
|---|---|
| 全参照が解決可能 | 空リスト |
| 一部の参照が未解決 | 未解決参照のリスト（参照元情報付き） |
| 動的参照の inner_refs が未解決 | 内部参照が未解決として記録される |
| レジストリが空 | 空リスト |

### find_duplicate_keys

| 状況 | 振る舞い |
|---|---|
| 重複なし | 空辞書 |
| 重複あり | `{キー名: list[KeyDefinition]}` の辞書（len >= 2 のもの） |
| レジストリが空 | 空辞書 |

## エッジケース

| ケース | 期待される扱い |
|---|---|
| `cards/` プレフィックスなしのフルパス参照 | 直接フルパスインデックスを検索。見つからなければ短縮形として解決 |
| 短縮形参照でキー名がユニーク | `is_ambiguous=False` で解決 |
| 短縮形参照でキー名が複数ファイルに存在（重複キー4件） | 後勝ちで最後の定義を返し、`is_ambiguous=True` |
| 動的参照の full_path（`{__cards/姦キー__}{__cards/鬼キー__}`） | resolve で `None`。resolve_dynamic_inner_refs で内部参照を個別解決 |
| cards_dir 直下のファイルに定義されたキー | full_path にディレクトリ部分がない。短縮形と同じパスになる |
| Windows パスの `\` | フルパスインデックス構築時に `/` に正規化 |
| file_path が cards_dir 外にある KeyDefinition | フルパスインデックスに含めない（スキップ）。短縮形では解決可能 |
| 空文字列の full_path | `None` を返す |
| 同名キーが同一ファイル内に複数 | パーサーが別の KeyDefinition として抽出し、レジストリに追加される。後勝ちで解決 |
| 42,957 キーでのフルパスインデックス構築 | 辞書構築は O(n) で問題なし |
| 112,105 参照の一括未解決チェック | 各参照の解決が O(1) なので、全体で O(n) |

## パフォーマンス考慮

### 規模

- 42,957 ユニークキー（42,961 キー定義、重複 4 件）
- 112,105 参照（通常参照）
- 18,953 動的参照

### 設計上の配慮

1. **フルパスインデックスは辞書**: `dict[str, KeyDefinition]` による O(1) ルックアップ。42,957 エントリの辞書構築は数ミリ秒
2. **短縮形参照は KeyRegistry の辞書引き**: O(1) ルックアップ
3. **`find_unresolved_refs()` の全スキャン**: 112,105 + 18,953 = 131,058 参照 × O(1) 解決 = 数百ミリ秒以内
4. **メモリ**: フルパスインデックスは 42,957 エントリの辞書。数 MB 程度

### ボトルネックの予測

- `build_full_path_index()` の `relative_to()` 呼び出しが 42,961 回。Path 操作は軽量なので問題なし
- `find_unresolved_refs()` は起動時に1回だけ実行。実行時間が問題になる場合は遅延実行（ツリー構築時に個別判定）に切り替え可能

## 関数一覧

### `core/resolver.py`

| 関数 | シグネチャ | 説明 |
|---|---|---|
| `build_full_path_index` | `(registry: KeyRegistry, cards_dir: Path) -> FullPathIndex` | フルパスインデックスを構築する |
| `resolve` | `(full_path: str, full_path_index: FullPathIndex, registry: KeyRegistry) -> ResolveResult \| None` | 参照を解決する（フルパス → 短縮形の2段フォールバック） |
| `resolve_dynamic_inner_refs` | `(ref: WildcardRef, full_path_index: FullPathIndex, registry: KeyRegistry) -> dict[WildcardRef, ResolveResult \| None]` | 動的参照の内部参照を個別に解決する |
| `find_unresolved_refs` | `(registry: KeyRegistry, full_path_index: FullPathIndex) -> list[UnresolvedRef]` | 全参照をスキャンし、解決できない参照を収集する |
| `find_duplicate_keys` | `(registry: KeyRegistry) -> dict[str, list[KeyDefinition]]` | 同名キーが複数ファイルに存在するケースを検出する |

### `core/models.py` に追加する型

| 型 | 定義 | 説明 |
|---|---|---|
| `FullPathIndex` | `dict[str, KeyDefinition]` (型エイリアス) | フルパス → KeyDefinition のマッピング |

### `core/resolver.py` 内の型

| 型 | 定義 | 説明 |
|---|---|---|
| `ResolveResult` | `@dataclass` | 解決結果（key_def, method, is_ambiguous） |
| `UnresolvedRef` | `@dataclass` | 未解決参照情報（ref, key_name, file_path, line_number） |

## エラー種別

| エラー | 発生条件 | 例外型 | 発生関数 |
|---|---|---|---|
| 解決失敗 | 参照先が見つからない | 例外なし（`None` を返す） | `resolve` |
| 相対パス計算失敗 | file_path が cards_dir 外 | 例外なし（スキップ） | `build_full_path_index` |

resolver は例外を投げない設計。全てのエラーを戻り値で表現する。

## conftest.py フィクスチャ設計

S3 のテストでは以下のフィクスチャが必要になる:

### 既存フィクスチャの活用

- `yaml_factory`: YAML ファイルの作成。フルパスインデックスのテストで使用
- `multi_file_cards_dir` 等: build_registry → build_full_path_index → resolve の結合テスト

### 新規フィクスチャ

- `sample_registry`: 複数キー定義を含む KeyRegistry。resolve のユニットテストで使用
- `sample_full_path_index`: 事前構築済みのフルパスインデックス。resolve のユニットテストで使用
- `duplicate_key_registry`: 重複キーを含む KeyRegistry。find_duplicate_keys のテスト用

これらは目的が明確に異なるため、別フィクスチャとして分離する（ナレッジ: 共有フィクスチャに複数の目的を兼ねさせない）。
