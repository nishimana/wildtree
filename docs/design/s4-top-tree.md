# S4: トップツリー検出 (`core/top_tree.py`)

## タスク種別

新規モジュール → コード成果物あり（`core/top_tree.py` にスタブを配置）

## 機能の概要

KeyRegistry 全体をスキャンし、他のどのキー定義からも参照されていないキー（トップツリー）を特定する。これらは S5（ツリー構築）のルートノードとなり、GUI でユーザーが展開するエントリポイントになる。

## 設計判断の理由（Why）

### 1. 集合差分アルゴリズムを採用する理由

トップツリー検出の本質は「全キー名の集合 − 参照されているキー名の集合」の差分計算。これは O(n) の線形スキャンで実現でき、43,000 キー + 131,000 参照の規模でも数十ミリ秒で完了する。グラフ構築やトポロジカルソートは不要。

### 2. 関数ベースにする理由

S3（resolver）と同じ設計方針。状態を持たず、引数で全情報を受け取る純粋関数として設計する。テスト時にクラスのインスタンス化が不要で、レジストリとインデックスを直接渡すだけでテスト可能。

### 3. 参照収集の対象範囲

「参照されている」と判定する条件:

- 通常参照（RefType.NORMAL）の WildcardRef.name → そのキー名は参照されている
- 動的参照（RefType.DYNAMIC）の inner_refs 内の各 WildcardRef.name → そのキー名も参照されている
- コメントアウトされた値行（is_commented=True）内の参照も「参照されている」としてカウントする

**コメント行の参照もカウントする理由**: コメントアウトされた参照は「一時的に無効化されたが、構造としては存在する」もの。トップツリー検出はツリーの「構造」を見つける処理であり、一時的な有効/無効の状態には依存しない。コメントアウトした参照先がトップツリーに浮上すると、ユーザーを混乱させる。

### 4. FullPathIndex からではなく KeyRegistry + FullPathIndex の両方を使う理由

- `referenced_key_names` の収集には KeyRegistry の走査で十分（全キー定義の値行の参照を辿る）
- ただし、フルパス参照（`__cards/SAO/CH_asada/朝田詩乃__`）のキー名解決には FullPathIndex が必要
- 短縮形参照（`__朝田詩乃__`）は WildcardRef.name で直接キー名が取れる
- フルパス参照は full_path からキー名を取る必要があるが、WildcardRef.name プロパティが full_path の最後のスラッシュ以降を返すので、同じく直接キー名が取れる

**結論**: WildcardRef.name を使えば、フルパス参照も短縮形参照も同じように扱える。FullPathIndex は S4 では不要。KeyRegistry のみで実現可能。

### 5. 動的参照自体の full_path を「参照されているキー名」に含めない理由

動的参照の full_path は `{__cards/姦キー__}{__cards/鬼キー__}NP` のようなテンプレートであり、キー名ではない。解決先は変数展開後に初めて確定する。よって動的参照自体の full_path.name はキー名として扱わない。内部参照（inner_refs）のキー名のみをカウントする。

### 6. TopTreeResult を導入する理由

`find_top_trees()` が単なる `list[str]` を返すと、呼び出し元に以下の情報が伝わらない:
- 各トップツリーがどの KeyDefinition に対応するか
- 各トップツリーがどのファイルに定義されているか

GUI がトップツリーの一覧を表示するとき、ファイルパスや値行数の情報も必要になる。`TopTreeInfo` データクラスで構造化することで、GUI 層が追加のルックアップを不要にする。

### 却下した代替案

| 案 | 却下理由 |
|---|---|
| グラフ構築 + 入次数 0 のノード検出 | 集合差分で十分。グラフ構築のメモリと計算コストが無駄 |
| resolve() を使って参照の解決状況を考慮 | トップツリー検出は「構造的に参照されているか」だけが関心事。解決成功/失敗は S5 の責務 |
| コメント行の参照を除外してカウント | コメントアウトしたキーがトップツリーに浮上すると混乱する |
| FullPathIndex を使ったキー名解決 | WildcardRef.name プロパティで十分。不要な依存を増やさない |
| `list[str]` を返す簡易設計 | GUI が追加のルックアップを必要とし、呼び出し側のコードが冗長になる |

## スコープ（Scope）

### やること

- `collect_referenced_key_names()`: レジストリ全体をスキャンし、参照されているキー名の集合を構築する
- `find_top_trees()`: 全キー名から参照されているキー名を差し引き、トップツリーを特定する
- `TopTreeInfo` データクラスの定義

### やらないこと（意図的な対象外）

| 対象外 | 理由 |
|---|---|
| ツリー構築 | S5（tree_builder）の責務 |
| 循環参照の検出 | S5（tree_builder）の責務 |
| 名前解決（resolve） | S3（resolver）の責務。S4 は参照の「名前」だけを見る |
| 動的参照の完全展開 | S9 の責務。内部参照（inner_refs）のキー名のみ収集する |
| GUI への結果表示 | S6 の責務 |
| トップツリーの優先度付け（「メイン」を先頭にする等） | S4 はアルファベット順（ソート済み）で返す。優先度付けは GUI 層の責務 |
| FullPathIndex の使用 | WildcardRef.name で十分なため不要 |

## 既存コードとの関係（Context）

### v1 プロトタイプとの対応

v1 にはトップツリー検出機能がなかった。全キーを QComboBox に列挙してユーザーに選ばせていた。S4 は完全に新規の機能。

### v2 全体設計書との対応

`v2-tree-editor.md` §4.4 にプロトタイプのアルゴリズムが記載されている:

```python
def find_top_trees(registry: dict[str, list[KeyDefinition]]) -> list[str]:
    """他のどのキー定義からも参照されていないキー名を返す"""
    all_keys = set(registry.keys())
    referenced_keys = set()
    for key_defs in registry.values():
        for key_def in key_defs:
            for value in key_def.values:
                for ref in value.refs:
                    referenced_keys.add(ref.name)
    return sorted(all_keys - referenced_keys)
```

S4 の設計はこのプロトタイプを拡張する:
1. **動的参照の inner_refs も対象に含める** — プロトタイプでは `ref.name` だけ見ていた
2. **TopTreeInfo を返す** — キー名だけでなく KeyDefinition も含める
3. **参照収集を独立関数に分離** — テスト容易性と再利用性のため

### データフロー

```
[KeyRegistry]  -- parser.build_registry() の出力
    |
    v
collect_referenced_key_names(registry)
    |
    v
[set[str]]  -- 参照されているキー名の集合
    |
    v
find_top_trees(registry)
    |
    v
[list[TopTreeInfo]]  -- トップツリーの一覧（名前順ソート済み）
    |
    v (S5: tree_builder.py が使用)
[TreeNode ツリー]  -- 各 TopTreeInfo がルートノードになる
```

### 依存関係

- `core/top_tree.py` は `core/models.py` に依存（KeyDefinition, KeyRegistry, WildcardRef, RefType）
- `core/top_tree.py` は `core/resolver.py` に依存しない（resolve() は使わない）
- `core/top_tree.py` は `core/parser.py` に依存しない（レジストリは引数で受け取る）

### データモデルとの関係

top_tree が使用する既存の型:
- `KeyDefinition`: トップツリーの定義情報として TopTreeInfo に含める
- `KeyRegistry` (`dict[str, list[KeyDefinition]]`): 全キーと全参照の走査に使用
- `WildcardRef`: `name` プロパティと `ref_type`, `inner_refs` を参照
- `RefType`: 動的参照の判定に使用

top_tree が新規追加する型:
- `TopTreeInfo`: トップツリーの情報を構造化するデータクラス

## 設計原則（implementer 向け）

### 1. 参照されているキー名の収集ルール

`collect_referenced_key_names(registry)` は以下のルールで「参照されているキー名」を収集する:

1. レジストリの全 KeyDefinition の全 ValueEntry の全 WildcardRef を走査する
2. **通常参照** (`RefType.NORMAL`): `ref.name` を集合に追加する
3. **動的参照** (`RefType.DYNAMIC`):
   - 動的参照自体の `ref.name` は追加**しない**（テンプレートであり、キー名ではない）
   - `ref.inner_refs` 内の各内部参照の `name` を集合に追加する
4. **コメント行** (`is_commented=True`): コメント行内の参照も上記と同じルールで収集する
5. 結果は `set[str]` として返す

### 2. トップツリーの特定ルール

`find_top_trees(registry)` は以下のルールでトップツリーを特定する:

1. `set(registry.keys())` で全キー名の集合を取得する
2. `collect_referenced_key_names(registry)` で参照されているキー名の集合を取得する
3. 差分（全キー − 参照されているキー）がトップツリー候補
4. 各候補に対して KeyRegistry からキー定義を取得し、`TopTreeInfo` を構築する
5. 結果を `name` のソート順で返す（安定した出力順序の保証）

### 3. TopTreeInfo の構築ルール

- `name`: キー名（レジストリのキー）
- `key_def`: 対応する KeyDefinition。同名キーが複数ある場合は最後のもの（後勝ち、resolver と同じ方針）
- `file_path`: `key_def.file_path` と同じ（アクセスの利便性のため重複保持）

### 4. エラーハンドリング方針

- `collect_referenced_key_names()`: 例外を投げない。空レジストリなら空集合を返す
- `find_top_trees()`: 例外を投げない。空レジストリなら空リストを返す

## 正常系・異常系の振る舞い

### collect_referenced_key_names

| 状況 | 振る舞い |
|---|---|
| 通常のレジストリ | 参照されているキー名の集合を返す |
| 空のレジストリ | 空の集合を返す |
| 通常参照のみ | 各 ref.name を集合に追加 |
| 動的参照あり | inner_refs 内の各参照の name を集合に追加。動的参照自体の name は追加しない |
| コメント行のみで構成されたキー定義 | コメント行内の参照もカウントする |
| 値行に参照がない（リテラルのみ） | その値行からは何も追加されない |

### find_top_trees

| 状況 | 振る舞い |
|---|---|
| 正常なレジストリ | 参照されていないキーの TopTreeInfo リストを名前順で返す |
| 空のレジストリ | 空リスト |
| 全キーが何かから参照されている | 空リスト（トップツリーなし） |
| 全キーがどこからも参照されていない | 全キーがトップツリーとして返る |
| 自己参照のみのキー（A → A） | A は自分自身から参照されているので、トップツリーにはならない |
| 相互参照（A → B, B → A）で他からの参照なし | A, B ともにトップツリーにはならない（互いに参照し合っているため）。ただし外部からの参照がなければ到達不能になるが、これは S4 の関心事ではない |
| 同名キーが複数ファイルに存在し、いずれも参照されていない | 1つの TopTreeInfo として返す（後勝ちの KeyDefinition を使用） |

## エッジケース

| ケース | 期待される扱い |
|---|---|
| 空レジストリ | `find_top_trees()` → 空リスト、`collect_referenced_key_names()` → 空集合 |
| キー定義が1つだけ、参照なし | そのキーがトップツリーとして返る |
| キー定義が1つだけ、自己参照あり | そのキーは参照されているため、トップツリーにはならない → 空リスト |
| 全キーが相互参照のみ（クリーク構造） | 互いに参照し合っているため、全キーが「参照されている」 → 空リスト |
| 動的参照のみを持つキー | 動的参照の inner_refs のキー名がカウントされる。動的参照自体の解決先は不明なのでカウントしない |
| コメントアウトされた参照だけを持つキー | コメント行内の参照も「参照されている」としてカウント |
| 値行がゼロ個のキー定義 | 参照を出していないので、他のキーを「参照している」とはカウントしない。このキー自体が他から参照されていなければトップツリーになる |
| 実データでの想定結果 | `メイン`, `メインNP` など少数のキーがトップツリーとして検出されるはず |
| 参照先キー名がレジストリに存在しない（未解決参照） | 参照先キー名は `referenced_key_names` 集合に追加されるが、レジストリの `keys()` には含まれないため、差分計算に影響しない。未解決参照の存在はトップツリー検出に影響しない |
| 同名キーが複数ファイルに存在し、参照されている場合 | キー名ベースでカウントするので、1回参照されていれば十分。複数の定義が全て「参照されている」扱いになる |

## パフォーマンス考慮

### 規模

- 42,957 ユニークキー
- 112,105 通常参照 + 18,953 動的参照 = 131,058 参照
- 動的参照の inner_refs 数は未計測だが、1動的参照あたり 1〜3 個程度

### 設計上の配慮

1. **集合演算**: `set` の差分計算（`all_keys - referenced_keys`）は O(min(m, n))。42,957 キーでは数ミリ秒
2. **参照収集**: 全 ValueEntry の全 WildcardRef を走査する 4 重ループだが、各操作（`set.add()`）は O(1)。131,058 参照の走査は数十ミリ秒以内
3. **ソート**: 結果のトップツリー数は少数（想定 2〜5 件）のため、ソートコストは無視できる
4. **メモリ**: `referenced_key_names` の集合は最大 42,957 エントリ。数 MB 以下

### ボトルネックの予測

- ボトルネックは存在しない見込み。全処理が O(参照総数) で完了し、参照総数は 131,058 + α（inner_refs）
- `find_unresolved_refs()` と同じ走査パターンだが、resolve() を呼ばない分さらに軽量

## 関数一覧

### `core/top_tree.py`

| 関数 | シグネチャ | 説明 |
|---|---|---|
| `collect_referenced_key_names` | `(registry: KeyRegistry) -> set[str]` | レジストリ全体をスキャンし、参照されているキー名の集合を返す |
| `find_top_trees` | `(registry: KeyRegistry) -> list[TopTreeInfo]` | 参照されていないキーをトップツリーとして返す（名前順ソート済み） |

### `core/top_tree.py` 内の型

| 型 | 定義 | 説明 |
|---|---|---|
| `TopTreeInfo` | `@dataclass` | トップツリーの情報（name, key_def, file_path） |

## エラー種別

| エラー | 発生条件 | 例外型 | 発生関数 |
|---|---|---|---|
| なし | — | — | — |

top_tree は例外を投げない設計。空レジストリを含む全ての入力に対して正常な戻り値を返す。

## conftest.py フィクスチャ設計

S4 のテストでは以下の既存フィクスチャが活用可能:

### 既存フィクスチャの活用

- `simple_cards_dir`: 基本テスト。`greeting` がトップツリー（`farewell` は `greeting` から参照されている）
- `multi_file_cards_dir`: 複数ファイルテスト。`メイン` がトップツリー
- `circular_ref_cards_dir`: 相互参照テスト。`alpha` と `beta` は互いに参照 → トップツリーなし
- `commented_ref_cards_dir`: コメントアウト参照テスト。`シーンまとめ` がトップツリー（`朝田詩乃` は非コメント行で参照、`シロコ` はコメント行で参照）
- `sample_registry`: ユニットテスト用。in-memory のレジストリ

### 新規フィクスチャの要否

既存フィクスチャで主要なテストパターンをカバーできる。以下のケースが不足する場合、テスターの判断で追加:

- 全キーが参照されているケース（トップツリーなし）
- 自己参照のみのケース
- 動的参照の inner_refs がトップツリー判定に影響するケース
- 値行がゼロ個のキー定義

これらは `sample_registry` の変形（テスト内で直接構築）で対応可能なため、新規フィクスチャの追加は必須ではない。
