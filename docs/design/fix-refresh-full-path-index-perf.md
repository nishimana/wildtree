# Fix: refresh_full_path_index パフォーマンス問題

## バグ概要

コミット `a2f2303` で追加した `refresh_full_path_index()` が、チェックボックストグル操作時に **6.9秒** のGUIフリーズを引き起こす。ユーザーには「アプリが落ちた」ように見える。

## 原因分析

### 発生箇所

- **ファイル**: `core/resolver.py`
- **関数**: `refresh_full_path_index()`
- **問題の行**: `if kd.file_path.resolve() == target_path:` — 全 44,675 件のキー定義に対して `Path.resolve()` を呼んでいる

### 根本原因

`refresh_full_path_index()` は設計上 O(R)（R = 変更ファイルのキー数）だが、実装では全レジストリ（44,675エントリ）を走査し、各エントリで `Path.resolve()` を呼んでいる。Windows + OneDrive環境では `Path.resolve()` はファイルシステム操作を伴い、1回あたり約 0.15ms かかる。44,675回 × 0.15ms ≒ 6.7秒。

### パフォーマンス比較

| 比較方法 | 所要時間 | 倍率 |
|---|---|---|
| `kd.file_path.resolve() == target` （現在） | 3.7s | 1x |
| `str(kd.file_path) == str(target)` | 0.012s | 300x |
| `kd.file_path == file_path` （Path.__eq__） | 0.012s | 300x |
| `kd.file_path is file_path` | 0.005s | 750x |

### なぜ Path == で安全か

`parse_yaml_file(file_path)` は入力の `file_path` オブジェクトをそのまま `KeyDefinition.file_path` に格納する。`refresh_registry` 経由で再パースされた KeyDefinition も同じ `file_path` オブジェクトを使う。Windows の `Path.__eq__` はケース非依存比較を行うため、同一ファイルの異なる表現でも正しく一致する。

### 付随バグ: perf print のエンコーディング

`_on_top_tree_selected` の perf log で `top_info.name` を `print()` する際、cp932（Windows デフォルト）でエンコードできない文字（♥ `\u2665` 等）を含むと `UnicodeEncodeError` が発生する。このエラーは try-except で捕捉されないため、処理が中断する（ただし PySide6 がスロット内例外をキャッチするのでアプリ自体は落ちない）。

実データには ♥ を含むキー名が 30 件存在するが、いずれもトップツリーではないため、ツリー選択時のクラッシュは起きない。しかし将来的にトップツリーに ♥ が含まれる可能性があるので修正する。

## 修正設計

### 変更1: `refresh_full_path_index` のパス比較を修正

- **ファイル**: `core/resolver.py`
- **変更**: `kd.file_path.resolve() == target_path` を `kd.file_path == file_path` に変更
- **効果**: 6.9秒 → 0.012秒

```python
def refresh_full_path_index(
    file_path: Path,
    registry: KeyRegistry,
    full_path_index: FullPathIndex,
    cards_dir: Path,
) -> None:
    try:
        relative = file_path.relative_to(cards_dir)
    except ValueError:
        return

    parent = relative.parent

    # Path.__eq__ による安価な比較（Path.resolve() は Windows で高コスト）
    for key_defs in registry.values():
        for kd in key_defs:
            if kd.file_path == file_path:
                if parent == Path("."):
                    fp = kd.name
                else:
                    fp = parent.as_posix() + "/" + kd.name
                full_path_index[fp] = kd
```

### 変更2: perf print のエンコーディング安全化

- **ファイル**: `gui/app.py`
- **変更**: `_on_top_tree_selected` と `_load_cards_dir` の print 文で例外を捕捉
- **方法**: perf print 全体を try-except で囲み、UnicodeEncodeError を無視する

```python
try:
    print(f'[perf] _on_top_tree_selected("{top_info.name}"):')
    ...
except (UnicodeEncodeError, OSError):
    pass  # コンソールが対応していない文字の場合はログ出力をスキップ
```

## 期待される効果

| 処理 | 修正前 | 修正後 |
|---|---|---|
| `refresh_full_path_index` | ~6.9s | ~0.012s |
| チェック操作全体 | ~9.0s | ~2.1s |

## 影響範囲

- `refresh_full_path_index` は `_on_item_changed` からのみ呼ばれる
- `build_full_path_index`（初回ロード時の関数）は変更なし
- perf print の修正は表示のみの変更、ロジックに影響なし

## リスク

| リスク | 回避策 |
|---|---|
| Path == 比較の不一致（同一ファイルが異なるパス表現で登録されるケース） | scan_yaml_files → parse_yaml_file のパイプラインでは全て同じ Path オブジェクトが使われるため、不一致は起きない。万一不一致があっても、build_full_path_index（初回ロード時）で正しいインデックスが構築されており、差分更新で漏れたエントリは stale な KeyDefinition を指すだけで、キーマッピング自体は正しい |
