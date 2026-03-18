# 振り返り: WildTree 初回実装サイクル

日付: 2026-03-18

## サイクル概要

- **プロジェクト**: WildTree -- Dynamic Prompts ワイルドカード YAML のツリービューア
- **技術スタック**: Python 3.12 + PySide6
- **スコープ**: core パーサー（5ステージパイプライン）+ GUI + テスト
- **成果**: 59テスト全パス、レビュー OK 判定

## 開発の流れ

1. **設計**: 既存設計書 (`wildcard-tree-viewer.md`) から実装ガイド (`implementation-guide.md`) を作成。TypeScript 参考実装 (`dynamic_linter`) を分析し、Python へのスタブ移植ポイントを整理
2. **テスト**: 設計書とスタブから 52 テストを conftest.py のファクトリフィクスチャ付きで作成
3. **実装**: スタブを実装。TypeScript からブレース深度追跡ロジック (`_scan_closing_underscores`) を移植。59 テスト全パス（tester が書いた 52 + implementer が追加した 7）
4. **レビュー**: OK 判定。重要指摘なし。推奨 3 件を修正

## うまくいったこと

### 設計の明確さが実装をスムーズにした

- 設計書で 5 ステージパイプラインを明確に分離し、各ステージの入出力を確定させていた
- TypeScript からの移植ポイントを関数単位で対応表にまとめていたため、implementer が迷わず移植できた
- エラーハンドリング方針（scan_yaml_files は raise、extract_keys_from_file は空リスト返却）を設計段階で確定していたため、テストとの整合性が最初から取れていた

### core と GUI の分離が効果的だった

- core モジュールが PySide6 に一切依存しない設計にしたため、59 テスト中大半が QApplication なしで実行可能
- テストの実行速度が速く、フィードバックサイクルが短かった

### ファクトリフィクスチャの設計

- `yaml_factory` + ドメイン固有フィクスチャ（`multi_file_cards_dir`, `circular_ref_cards_dir` 等）の 2 層構成が機能した
- テストデータの生成が conftest.py に集約され、test_parser.py は純粋にテストロジックに集中できた

## 設計と実装のギャップ

### ギャップ 1: `content.split("\n")` vs `splitlines()`

設計書では行分割方法について明示的な指定をしていなかった。implementer が `split("\n")` を使ったが、Windows 環境では CRLF (`\r\n`) のファイルで `\r` が行末に残る問題がある。レビューで `splitlines()` への変更が推奨された。

**教訓**: Windows 対応が必要なプロジェクトでは、設計段階で行分割方法を `splitlines()` と明示すべき。

### ギャップ 2: GUI エラー表示方法

設計書の実装ガイドでは「ステータスバーまたはメッセージボックスでエラーを表示」と曖昧に書いていた。implementer が `statusBar().showMessage()` を使ったが、レビューで `QMessageBox.warning()` への変更が推奨された。エラーの見落とし防止の観点から、ユーザーの注意を確実に引くモーダルダイアログの方が適切。

**教訓**: 設計書の UI 指示で「AまたはB」と書くと implementer の判断任せになる。明確に一方を選択すべき。

### ギャップ 3: QApplication 引数

設計書では `QApplication(sys.argv)` の代わりに `QApplication([sys.argv[0]])` とすべきことに言及していなかった。`sys.argv` をそのまま渡すと、アプリ固有のコマンドライン引数が Qt に誤認される可能性がある。

**教訓**: PySide6 アプリでコマンドライン引数を自前解析する場合、`QApplication` に渡す引数を制限する必要がある。

## レビュー結果

### 修正済み（推奨）

| 指摘 | 修正内容 | カテゴリ |
|------|---------|---------|
| statusBar → QMessageBox | `QMessageBox.warning()` に変更 | UI/UX |
| split("\n") → splitlines() | CRLF 対応のため `splitlines()` に変更 | Windows 互換 |
| QApplication(sys.argv) → QApplication([sys.argv[0]]) | 引数誤認防止 | PySide6 |

### スキップ（推奨・提案）

| 指摘 | スキップ理由 |
|------|-------------|
| 変数名 `after_uu` | コスメ的変更 |
| キー名にコロンを含む問題 | 設計準拠、実データにそのケースなし |
| ルートノードの表示名 | ComboBox 経由のため不要 |
| rglob パターン | コスメ的変更 |
| テスト追加（連結パターン） | テスト変更は不可ルール |

## 次回以降に活かすべき改善点

1. **Windows 環境での文字列行分割**: `splitlines()` を設計段階のデフォルトとして明記する。`split("\n")` を使う場合は意図的な理由をコメントで残す
2. **GUI のエラー通知方法**: 設計書で「ステータスバー or ダイアログ」ではなく、エラーの深刻度に応じた通知手段を明確に指定する（致命的エラー → QMessageBox、軽微な通知 → ステータスバー）
3. **QApplication への引数**: PySide6 プロジェクトの設計書テンプレートに「QApplication には `[sys.argv[0]]` を渡す」を標準パターンとして記載する

## テンプレート改善メモ

なし。今回のサイクルではテンプレート構造に起因する問題は発生しなかった。
