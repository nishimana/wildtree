# S9: GUI テストハーネス + パフォーマンスログ

## タスク種別

混合（新規モジュール `gui/test_harness.py` + 既存コード変更 `gui/app.py` + 新規テスト `tests/test_smoke.py`）

## 機能の概要

実データ（271ファイル、43,000キー）でトップツリー「メイン」を選択しノードを展開するとアプリがフリーズ・クラッシュする問題が発生した。CLI から `build_tree` / `populate_model` を直接呼んで計測すると問題なし（各 0.03秒以下）。つまり Qt のシグナル伝播・ウィジェット描画・イベントループなど GUI 固有のコードパスにボトルネックがある。

この問題を再現可能かつ自動計測可能にするため、3つのコンポーネントを追加する:

1. **GUI テストハーネス** (`gui/test_harness.py`): `WildTreeWindow` を実際に生成し、プログラムから操作して所要時間・メモリを計測する API
2. **パフォーマンスログ** (`gui/app.py` の変更): パイプライン各ステップの所要時間をコンソール出力
3. **スモークテスト** (`tests/test_smoke.py`): テストハーネスを使った実データでの基本操作フロー自動検証

## 設計判断の理由（Why）

### 1. 実ウィジェットを使う理由（モックではなく）

ボトルネックは Qt のシグナル伝播・ウィジェット描画にある可能性が高い。モックでシグナルを差し替えると、まさに計測したいコードパスを回避してしまう。テストハーネスは `WildTreeWindow` の実インスタンスを使い、`QListWidget.setCurrentRow()` や `QTreeView.expand()` など、ユーザー操作と同じコードパスを通る。

**却下した代替案**:
- pytest-qt の `qtbot.mouseClick()`: ウィンドウの可視化とピクセル座標の指定が必要で、offscreen テストと相性が悪い
- `QTest.mouseClick()`: 同上。かつ PySide6 との互換性問題がある
- コア層の関数だけ計測: 既に実施済みで問題なし。GUI 層の計測が目的

### 2. テストハーネスをモジュールとして分離する理由（app.py に統合しない）

テストハーネスは計測・デバッグ用の API であり、通常のアプリケーションコードと責務が異なる。`app.py` に計測メソッドを追加すると:
- 通常コードとデバッグコードが混在して可読性が下がる
- テストハーネス固有の import（`time`, `tracemalloc`）が本番コードに入る
- テストハーネスの変更が `app.py` の diff に混ざる

`gui/test_harness.py` として分離し、`WildTreeWindow` をラップする `GUITestHarness` クラスを提供する。

### 3. パフォーマンスログを print ベースにする理由（logging モジュールではなく）

現在のコードベースは `logging` モジュールを一切使っておらず、`verify_v2.py` も `print` で計測結果を出力している。一貫性のために `print` を使う。

- プロジェクト全体で `logging` を導入するのは別のリファクタリングタスク
- `print` なら通常起動でも即座にコンソールに出力される
- 出力は `[perf]` プレフィックスで他の出力と区別する

**将来の拡張**: プロジェクト全体で `logging` を導入する際にまとめて移行する。

### 4. 計測結果を dataclass で返す理由（dict ではなく）

各操作の計測結果を `OperationResult` dataclass で返す。dict より以下の利点がある:
- 型ヒントによる IDE サポート
- 項目の追加・削除がコンパイル時エラーで検知できる
- プロジェクトの既存パターンに合致（`core/models.py` が dataclass ベース）

### 5. メモリ計測に tracemalloc を使う理由

`tracemalloc` は Python 標準ライブラリであり、追加の依存関係がない。`psutil` は外部ライブラリでありかつプロセス全体のメモリしか計測できない。`tracemalloc` はスナップショット間の差分を取れるため、特定操作のメモリ増加量を正確に計測できる。

ただし `tracemalloc` は Python オブジェクトのメモリのみを追跡し、Qt のネイティブメモリ（QStandardItem の内部バッファ等）は計測できない。この制約はドキュメントに明記する。

### 6. スモークテストで実データを使う理由（テストフィクスチャではなく）

既存のテストフィクスチャ（`simple_cards_dir` 等）は数個のファイル・数十キーしか含まない。パフォーマンス問題は 271ファイル・43,000キーの実データでのみ再現する。テストフィクスチャで問題が再現しないテストは意味がない。

実データが存在しない環境（CI 等）では `pytest.skip()` でスキップする。

### 7. expand_node で QTreeView.expand() を使う理由（expandAll ではなく）

`expandAll()` は全ノードを一括展開し、ユーザーの操作パターンとは異なる。ユーザーは特定のノードをクリックして1階層ずつ展開する。テストハーネスもこの操作を模倣すべきである。

ただし、問題の切り分けのために `expand_all()` も提供する。`expand()` と `expand_all()` の所要時間の差が Qt の描画コストの指標になる。

### 8. QApplication.processEvents() を挟む理由

Qt のシグナル/スロットは同じスレッドであれば直接呼び出しだが、ウィジェットの描画更新はイベントループで処理される。`processEvents()` を明示的に呼ぶことで:
- シグナル伝播 + 描画更新の両方を計測に含められる
- offscreen モードでもウィジェットの更新処理が実行される
- ユーザーが実際に体験する「操作→画面更新完了」のレイテンシに近い値が得られる

## スコープ（Scope）

### やること

- `gui/test_harness.py`: GUI テストハーネスモジュール
  - `GUITestHarness` クラス: `WildTreeWindow` をラップし、プログラムから操作する API
  - `OperationResult` dataclass: 各操作の計測結果（所要時間、メモリ増加量）
  - 操作 API: `load()`, `select_top_tree()`, `expand_node()`, `expand_all()`, `toggle_check()`, `select_node()`
- `gui/app.py` の変更: `_load_cards_dir()` と `_on_top_tree_selected()` にパフォーマンスログを追加
- `tests/test_smoke.py`: 実データでのスモークテスト

### やらないこと（意図的な対象外）

| 対象外 | 理由 |
|---|---|
| ボトルネックの修正 | このタスクは計測の仕組みを作る。修正は計測結果を見てから |
| Qt のネイティブメモリ計測 | tracemalloc の制約。必要なら psutil を追加で検討 |
| GUI の自動操作フレームワーク全般 | テストハーネスはパフォーマンス計測に特化。汎用 GUI テストは将来検討 |
| logging モジュールの導入 | プロジェクト全体のリファクタリングが必要。print で統一 |
| CI での実データテスト | 実データは開発環境にのみ存在。CI ではスキップ |
| パフォーマンスの閾値チェック | 環境依存のため自動テストでの閾値判定は行わない。計測値の出力のみ |
| ノード展開以外の GUI 操作のプロファイリング | まずは問題が報告されている操作（load → select_top_tree → expand）に集中 |

## 設計原則

### 1. 同じコードパスを通る

テストハーネスの各操作は、ユーザーが GUI で同じ操作をしたときと同じシグナル/スロット/描画パスを通ること。ショートカットを作らない。

### 2. 既存の振る舞いを変えない

パフォーマンスログの追加は `_load_cards_dir()` と `_on_top_tree_selected()` の既存の戻り値・シグナル発火タイミング・例外処理を一切変えない。追加するのは `print()` 呼び出しのみ。

### 3. 計測結果は構造化データとして返す

テストハーネスの各操作は `OperationResult` を返し、呼び出し元が計測値をプログラムで扱える。print 出力はテストハーネス内部で行い、呼び出し元は `OperationResult` のみを使う。

### 4. 実データが無くても壊れない

`tests/test_smoke.py` は実データディレクトリの存在をチェックし、無ければ `pytest.skip()` する。テストスイート全体の成否に影響しない。

## 既存コードとの関係（Context）

### gui/app.py との関係

テストハーネスは `WildTreeWindow` のパブリックメソッドと内部メソッドを呼ぶ:
- `__init__(cards_dir)`: コンストラクタでロードを実行
- `_list_top_trees.setCurrentRow(n)`: トップツリー選択のシグナルを発火
- `_tree_view.expand(index)`: ノード展開
- `_tree_model.item(row)` / `itemFromIndex()`: モデルのノード探索
- `_on_item_changed(item)`: チェックボックス変更のシグナルパス

テストハーネスは `WildTreeWindow` の内部属性（`_list_top_trees`, `_tree_view`, `_tree_model` 等）に直接アクセスする。これは設計上の妥協であり、`WildTreeWindow` のインターフェースが変わるとテストハーネスも追従が必要になる。ただし、テストハーネスはデバッグ・計測ツールであり、GUI の内部を触ること自体が目的なので、カプセル化の違反は許容する。

### verify_v2.py との関係

`verify_v2.py` はコア層の計測スクリプトであり、GUI は関与しない。テストハーネスは GUI 層の計測に特化しており、`verify_v2.py` を補完する関係にある。

### tests/conftest.py との関係

既存の `qapp` フィクスチャ（session スコープ、offscreen モード）をそのまま使用する。新規フィクスチャの追加は不要。

## 正常系・異常系の振る舞い

### GUITestHarness

| 操作 | 正常系 | 異常系 |
|---|---|---|
| `load(cards_dir)` | `WildTreeWindow` を生成し、`_load_cards_dir()` 経由でパイプラインを実行。`OperationResult` を返す | cards_dir が存在しない場合、`WildTreeWindow` の内部で `QMessageBox.warning()` が呼ばれるが、テストハーネスはそれを抑制しない。`OperationResult.success = False` を返す |
| `select_top_tree(name)` | 名前に一致する QListWidgetItem を探し `setCurrentRow()` で選択。`OperationResult` を返す | 名前が見つからない場合、`OperationResult.success = False`, `error = "トップツリーが見つかりません: {name}"` |
| `expand_node(path)` | パス（ルートからのノード名リスト）に一致するノードを探し `QTreeView.expand()` で展開。`OperationResult` を返す | パスが見つからない場合、`OperationResult.success = False` |
| `expand_all()` | `QTreeView.expandAll()` を呼ぶ。`OperationResult` を返す | 失敗しない（Qt API は例外を投げない） |
| `toggle_check(path)` | パスに一致するノードのチェック状態を反転。`OperationResult` を返す | パスが見つからない場合、`OperationResult.success = False` |
| `select_node(path)` | パスに一致するノードを選択。`OperationResult` を返す | パスが見つからない場合、`OperationResult.success = False` |
| `close()` | ウィンドウを閉じてリソースを解放 | 失敗しない |

### パフォーマンスログ

| 操作 | 出力例 |
|---|---|
| `_load_cards_dir()` | `[perf] scan: 0.05s, parse: 1.23s, index: 0.02s, top_trees: 0.01s, total: 1.31s` |
| `_on_top_tree_selected()` | `[perf] build_tree: 0.00s, populate_model: 0.03s, expand_root: 0.01s, total: 0.04s` |

### スモークテスト

| テスト | 正常系 | 異常系 |
|---|---|---|
| `test_load_real_data` | 実データをロードし、トップツリーリストにアイテムが表示される | 実データディレクトリが無ければ skip |
| `test_select_main_tree` | トップツリー「メイン」を選択し、ツリーモデルにノードが表示される | 「メイン」が無ければ skip |
| `test_expand_root` | ルートノードを展開し、子ノードが表示される | 展開に失敗したら fail |
| `test_expand_all` | 全ノードを展開し、所要時間を出力する | 展開に失敗したら fail |

## エッジケース

| ケース | 期待される扱い |
|---|---|
| `expand_node([])` — 空パス | `OperationResult.success = False`, エラーメッセージ |
| `select_top_tree("")` — 空文字列 | `OperationResult.success = False`, エラーメッセージ |
| `load()` を2回呼ぶ | 2回目は前の `WildTreeWindow` を `close()` してから新しいインスタンスを生成 |
| `select_top_tree()` を `load()` 前に呼ぶ | `OperationResult.success = False`, `error = "ウィンドウが初期化されていません"` |
| tracemalloc が既に起動している | `tracemalloc.is_tracing()` で確認し、起動済みなら再起動しない |
| ノードパスに同名の兄弟がある | 最初に見つかった方を使う（ユーザー操作と同じ） |
| 実データディレクトリのパスに日本語を含む | Path オブジェクトで扱い、UTF-8 で読み取る（既存コードと同じ） |

## 関数一覧

### `gui/test_harness.py`

| クラス/関数 | シグネチャ | 説明 |
|---|---|---|
| `OperationResult` | `@dataclass` | 操作の計測結果 |
| `OperationResult.success` | `bool` | 操作が成功したかどうか |
| `OperationResult.elapsed_sec` | `float` | 所要時間（秒） |
| `OperationResult.memory_delta_bytes` | `int` | メモリ増加量（バイト）。tracemalloc 計測。Qt ネイティブメモリは含まない |
| `OperationResult.error` | `str \| None` | エラーメッセージ。成功時は None |
| `GUITestHarness.__init__` | `(self) -> None` | テストハーネスの初期化。ウィンドウはまだ生成しない |
| `GUITestHarness.load` | `(self, cards_dir: Path) -> OperationResult` | cards ディレクトリをロード。WildTreeWindow を生成 |
| `GUITestHarness.select_top_tree` | `(self, name: str) -> OperationResult` | トップツリーを名前で選択 |
| `GUITestHarness.expand_node` | `(self, path: list[str]) -> OperationResult` | パスで指定したノードを展開 |
| `GUITestHarness.expand_all` | `(self) -> OperationResult` | 全ノードを展開 |
| `GUITestHarness.toggle_check` | `(self, path: list[str]) -> OperationResult` | パスで指定したノードのチェック状態を反転 |
| `GUITestHarness.select_node` | `(self, path: list[str]) -> OperationResult` | パスで指定したノードを選択（詳細ペイン更新を発火） |
| `GUITestHarness.close` | `(self) -> None` | ウィンドウを閉じてリソースを解放 |
| `GUITestHarness.window` | `@property -> WildTreeWindow \| None` | 現在のウィンドウインスタンスへのアクセス |
| `_find_node_index` | `(model: QStandardItemModel, path: list[str]) -> QModelIndex \| None` | パスに一致するノードの QModelIndex を探索する内部ヘルパー |
| `_measure` | `(func: Callable) -> OperationResult` | 関数を実行して時間とメモリを計測する内部ヘルパー |

### `gui/app.py` の変更

| 変更箇所 | 変更内容 |
|---|---|
| `_load_cards_dir()` | 各ステップ（scan, parse, index, top_trees）の前後に `time.perf_counter()` を挿入し、完了時に `print("[perf] ...")` で出力 |
| `_on_top_tree_selected()` | 各ステップ（build_tree, populate_model, expand_root）の前後に `time.perf_counter()` を挿入し、完了時に `print("[perf] ...")` で出力 |

### `tests/test_smoke.py`

| テスト関数 | 説明 |
|---|---|
| `test_load_real_data` | 実データをロードし、OperationResult.success が True であることを確認 |
| `test_select_main_tree` | トップツリー「メイン」を選択し、OperationResult.success が True であることを確認 |
| `test_expand_root` | ルートノードを展開し、OperationResult.success が True であることを確認 |
| `test_expand_all` | 全ノードを展開し、OperationResult を出力して確認 |

### 定数

#### `gui/test_harness.py`

| 定数 | 値 | 説明 |
|---|---|---|
| なし | — | 定数は不要。パスやタイムアウト値は呼び出し元が指定する |

#### `tests/test_smoke.py`

| 定数 | 値 | 説明 |
|---|---|---|
| `REAL_CARDS_DIR` | `Path(r"C:\Users\nishi\OneDrive\デスクトップ\git\webui_forge_cu121_torch231\webui\extensions\sd-dynamic-prompts\wildcards\cards")` | 実データの cards ディレクトリ |

## パフォーマンスログの出力フォーマット

### _load_cards_dir()

```
[perf] _load_cards_dir:
[perf]   scan:       0.050s (271 files)
[perf]   parse:      1.230s (43000 keys)
[perf]   index:      0.020s
[perf]   top_trees:  0.010s (16238 top trees)
[perf]   total:      1.310s
```

### _on_top_tree_selected()

```
[perf] _on_top_tree_selected("メイン"):
[perf]   build_tree:      0.003s (3476 nodes)
[perf]   populate_model:  0.030s
[perf]   expand_root:     0.010s
[perf]   total:           0.043s
```

## OperationResult の設計

```python
@dataclass
class OperationResult:
    """操作の計測結果。"""
    success: bool
    elapsed_sec: float
    memory_delta_bytes: int
    error: str | None = None
```

- `success`: 操作が正常に完了したかどうか
- `elapsed_sec`: `time.perf_counter()` で計測した経過時間（秒）
- `memory_delta_bytes`: `tracemalloc` で計測したメモリ増加量（バイト）。Qt のネイティブメモリは含まない
- `error`: エラー時のメッセージ。成功時は `None`

## GUITestHarness のライフサイクル

```
harness = GUITestHarness()
                    # window = None

result = harness.load(cards_dir)
                    # window = WildTreeWindow(cards_dir)
                    # _load_cards_dir() 実行済み

result = harness.select_top_tree("メイン")
                    # _list_top_trees.setCurrentRow(n)
                    # _on_top_tree_selected() が発火

result = harness.expand_node(["メイン"])
                    # _tree_view.expand(root_index)

result = harness.expand_all()
                    # _tree_view.expandAll()

result = harness.select_node(["メイン", "デフォルト"])
                    # selectionModel().setCurrentIndex(index, ...)
                    # _on_tree_node_selected() が発火

result = harness.toggle_check(["メイン", "デフォルト", "some_literal"])
                    # item.setCheckState(...)
                    # _on_item_changed() が発火

harness.close()
                    # window.close()
                    # window = None
```

## ノードパスの表現

ツリー内のノードを特定するために「パス」を使う。パスはルートからのノード名（`display_name`）のリスト。

例:
- `["メイン"]` → ルートノード
- `["メイン", "デフォルト"]` → ルート直下の「デフォルト」ノード
- `["メイン", "シーンまとめ", "朝田詩乃"]` → 3階層目のノード

この表現は `WildTreeWindow._save_selected_path()` / `_restore_selected_path()` で既に使われているパターンを踏襲する。

探索アルゴリズム:
1. モデルのルートアイテム（`model.item(0)`）の `display_name` が `path[0]` に一致するか確認
2. 一致する場合、子アイテムを走査して `path[1]` に一致するものを探す
3. 再帰的に繰り返す
4. パスの末端に到達したら、そのアイテムの `QModelIndex` を返す

## _measure ヘルパーの設計

```python
def _measure(func: Callable[[], None]) -> OperationResult:
    """関数を実行して時間とメモリを計測する。

    tracemalloc でメモリスナップショットを取得し、
    func 実行前後の差分を計測する。
    QApplication.processEvents() を func 後に呼んで
    Qt の描画更新を計測に含める。
    """
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    t0 = time.perf_counter()
    func()
    QApplication.processEvents()
    elapsed = time.perf_counter() - t0

    snapshot_after = tracemalloc.take_snapshot()
    # traced memory の差分
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # スナップショット間の差分からメモリ増加量を計算
    stats = snapshot_after.compare_to(snapshot_before, 'lineno')
    memory_delta = sum(stat.size_diff for stat in stats)

    return OperationResult(
        success=True,
        elapsed_sec=elapsed,
        memory_delta_bytes=memory_delta,
    )
```

注意: `tracemalloc` の start/stop を操作ごとに行うため、オーバーヘッドがある。計測結果は相対比較に使い、絶対値に過度に依存しないこと。

## テストパターン（tests/test_smoke.py）

```python
REAL_CARDS_DIR = Path(r"C:\Users\nishi\OneDrive\...")

# 実データが存在しない場合はモジュール全体をスキップ
pytestmark = pytest.mark.skipif(
    not REAL_CARDS_DIR.exists(),
    reason=f"実データディレクトリが見つかりません: {REAL_CARDS_DIR}",
)


class TestSmoke:
    """実データでのスモークテスト。"""

    @pytest.fixture(autouse=True)
    def setup_harness(self, qapp):
        """テストハーネスを初期化し、テスト後にクリーンアップする。"""
        self.harness = GUITestHarness()
        yield
        self.harness.close()

    def test_load_real_data(self):
        result = self.harness.load(REAL_CARDS_DIR)
        assert result.success
        print(f"load: {result.elapsed_sec:.3f}s, memory: {result.memory_delta_bytes:,} bytes")

    def test_select_main_tree(self):
        self.harness.load(REAL_CARDS_DIR)
        result = self.harness.select_top_tree("メイン")
        assert result.success
        print(f"select_top_tree: {result.elapsed_sec:.3f}s")

    def test_expand_root(self):
        self.harness.load(REAL_CARDS_DIR)
        self.harness.select_top_tree("メイン")
        result = self.harness.expand_node(["メイン"])
        assert result.success
        print(f"expand_root: {result.elapsed_sec:.3f}s")

    def test_expand_all(self):
        self.harness.load(REAL_CARDS_DIR)
        self.harness.select_top_tree("メイン")
        result = self.harness.expand_all()
        assert result.success
        print(f"expand_all: {result.elapsed_sec:.3f}s, memory: {result.memory_delta_bytes:,} bytes")
```

## エラー種別

| エラー | 発生条件 | 処理 |
|---|---|---|
| ウィンドウ未初期化 | load() 前に他の操作を呼んだ | `OperationResult(success=False, error="...")` |
| トップツリーが見つからない | select_top_tree() で名前が一致しない | `OperationResult(success=False, error="...")` |
| ノードパスが見つからない | expand_node() / select_node() / toggle_check() でパスが一致しない | `OperationResult(success=False, error="...")` |
| チェック不可ノード | toggle_check() で checkable でないノードを指定 | `OperationResult(success=False, error="...")` |
| 予期しない例外 | 操作中の想定外エラー | try-except で捕捉し `OperationResult(success=False, error=str(e))` |

テストハーネスは例外を投げない。全てのエラーを `OperationResult` で返す。
