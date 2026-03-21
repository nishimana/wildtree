# 振り返り: Fix refresh_full_path_index / refresh_registry の Path.resolve() パフォーマンス改善

## 日付
2026-03-21

## サイクル概要

| フェーズ | 結果 |
|---------|------|
| 再現確認 | refresh_full_path_index + refresh_registry 合計 ~13.8秒のフリーズを確認 |
| 原因特定 | 両関数が `Path.resolve()` を全キー定義（44,675件）に対して呼んでいた。Windows + OneDrive 環境では 1回 0.15ms x 44,675回 = ~6.7秒/関数 |
| 修正設計 | `Path.resolve()` を `Path ==` 比較に変更 |
| テスト追加 | 既存テスト活用 |
| 修正実装 | 3ファイル変更（resolver.py, editor.py, app.py） |
| レビュー | OK |
| 修正 | レビュー指摘反映済み |
| 手戻り | なし |

### 成果物
- `core/resolver.py` -- `refresh_full_path_index()` の `Path.resolve()` を `Path ==` に変更（6,900ms -> 5ms）
- `core/editor.py` -- `refresh_registry()` の `Path.resolve()` を `Path ==` に変更（推定6,900ms -> 15ms）
- `gui/app.py` -- perf print の `UnicodeEncodeError` 対策

### テスト結果
- 全テスト: 770 passed
- パフォーマンス: ~13.8s -> ~20ms（690倍高速化）

## バグの根本原因

### 直接原因
前回の Fix（`a2f2303`）で `build_full_path_index` のフル再構築（8.7s）を差分更新 `refresh_full_path_index()` に置き換えたが、差分更新の実装で `Path.resolve()` を全キー定義に対して呼んでいた。

`refresh_registry()` にも同じパターンが最初から存在していたが、前回の Fix ではこれに気付かず、パフォーマンス測定も行わなかった。

### なぜ Path.resolve() が高コストだったか
Windows + OneDrive 環境では `Path.resolve()` がファイルシステム操作を伴い非常に高コスト:
- 1回あたり約 0.15ms
- 44,675回呼ぶと約 6.7秒
- `Path ==` 比較なら同等のことが 0.005秒で完了

### なぜこのバグが生まれたか

1. **実機テスト未実施**: 前回の Fix はテストハーネス（offscreen）での動作確認のみで、実データ・実環境での動作確認を行わなかった

2. **Path.resolve() のコスト認識不足**: Windows + OneDrive 環境での `Path.resolve()` の実コストを過小評価した。設計書に「`Path.resolve()` のコスト」をリスクとして記載していたにもかかわらず、実測しなかった

3. **レビューの不足（同一パターンの横展開漏れ）**: 前回のレビューで `refresh_full_path_index()` の `Path.resolve()` のみに注目し、`refresh_registry()` の同パターンに気付かなかった。同一コールチェーン内で同じパフォーマンスパターン（全件走査 + Path.resolve()）が複数箇所にあることを確認すべきだった

## 再発防止策

### 1. パフォーマンス修正は実データ・実環境で計測する
offscreen テストではパフォーマンス問題を再現できない。パフォーマンスに関わる修正は、必ず実データ（44,675キー）と実環境（Windows + OneDrive）で計測してから完了とする。

### 2. Windows でのパス操作のコストを意識する
`Path.resolve()`, `Path.absolute()`, `Path.relative_to()` 等のパス解決操作は、Windows（特に OneDrive パス）ではファイルシステムアクセスを伴い高コスト。ループ内での使用を避け、事前に解決済みのパスを使用する。

### 3. 修正対象だけでなく同一コールチェーン内の類似パターンを確認する
バグ修正やパフォーマンス改善では、修正対象の関数だけでなく、同じ呼び出しチェーン内で同じパターン（全件走査、Path 操作等）を使っている他の関数も確認する。

## プロセスの振り返り

### 良かった点
1. **前回の Fix で埋め込んだ perf ログが原因特定を加速した**: `[perf]` ログにより、`refresh_full_path_index` と `refresh_registry` の個別所要時間が即座に判明した
2. **修正が単純かつ効果的**: `Path.resolve()` -> `Path ==` の置換のみで 690倍の高速化を達成

### 改善すべき点
1. **前回の Fix で同パターンの横展開を見落とした**: `refresh_registry()` は前回の Fix の修正対象（`_on_item_changed` のコールチェーン）に含まれていたにもかかわらず、`Path.resolve()` パターンを見逃した
2. **前回の Fix で実環境テストを省略した**: offscreen テストの限界は既知（pyside6.md に記録済み）だったが、実行されなかった

## ナレッジ更新

| ファイル | 項目 | 変更内容 | 根拠 |
|---------|------|---------|------|
| principles.md | 同一概念の複数ハンドラには同じガードパターンを適用する | 9回->10回 | `refresh_registry()` の `Path.resolve()` パターンを `refresh_full_path_index()` 修正時に見落とした |
| principles.md | GUI イベントハンドラの処理パイプラインには計算量を見積もる | 1回->2回 | 差分更新で O(N x Path.resolve()) のコストを見積もらなかった |
| pyside6.md | offscreen テストではレンダリングパフォーマンス問題を再現できない | 2回->3回 | offscreen テストのみで実環境テストを省略し、13.8秒のフリーズを見逃した |
| windows.md | Path.resolve() は Windows + OneDrive で高コスト | 新規追加 | Path.resolve() が 1回 0.15ms、44K回で 6.7秒。Path == なら 0.005秒 |
