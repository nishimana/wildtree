"""スモークテスト — 実データでの基本操作フロー自動検証。

S9 — GUI テストハーネスを使って実データ（271ファイル、43,000キー）で
基本操作フローが正常に動作するかを検証する。

実データディレクトリが存在しない場合はモジュール全体をスキップする。
パフォーマンスの閾値チェックは行わず、計測値の出力のみ行う。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gui.test_harness import GUITestHarness

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

REAL_CARDS_DIR = Path(
    r"C:\Users\nishi\OneDrive\デスクトップ\git\webui_forge_cu121_torch231"
    r"\webui\extensions\sd-dynamic-prompts\wildcards\cards"
)
"""実データの cards ディレクトリ。"""

# 実データが存在しない場合はモジュール全体をスキップ
pytestmark = pytest.mark.skipif(
    not REAL_CARDS_DIR.exists(),
    reason=f"実データディレクトリが見つかりません: {REAL_CARDS_DIR}",
)


# ---------------------------------------------------------------------------
# テストクラス
# ---------------------------------------------------------------------------


class TestSmoke:
    """実データでのスモークテスト。

    テストハーネスを使って実データで基本操作を実行し、
    各操作が成功することと計測値を確認する。
    """

    @pytest.fixture(autouse=True)
    def setup_harness(self, qapp):
        """テストハーネスを初期化し、テスト後にクリーンアップする。"""
        self.harness = GUITestHarness()
        yield
        self.harness.close()

    def test_load_real_data(self):
        """実データをロードし、トップツリーリストにアイテムが表示される。"""
        result = self.harness.load(REAL_CARDS_DIR)
        assert result.success, f"ロードに失敗: {result.error}"
        print(
            f"\n[smoke] load: {result.elapsed_sec:.3f}s, "
            f"memory: {result.memory_delta_bytes:,} bytes"
        )

        # トップツリーリストにアイテムがあることを確認
        assert self.harness.window is not None
        count = self.harness.window._list_top_trees.count()
        print(f"[smoke] top_trees count: {count}")
        assert count > 0

    def test_select_main_tree(self):
        """トップツリー「メイン」を選択し、ツリーモデルにノードが表示される。"""
        load_result = self.harness.load(REAL_CARDS_DIR)
        assert load_result.success, f"ロードに失敗: {load_result.error}"

        result = self.harness.select_top_tree("メイン")
        if not result.success and "見つかりません" in (result.error or ""):
            pytest.skip("トップツリー「メイン」が実データに存在しません")

        assert result.success, f"トップツリー選択に失敗: {result.error}"
        print(
            f"\n[smoke] select_top_tree('メイン'): {result.elapsed_sec:.3f}s, "
            f"memory: {result.memory_delta_bytes:,} bytes"
        )

        # ツリーモデルにノードがあることを確認
        assert self.harness.window is not None
        row_count = self.harness.window._tree_model.rowCount()
        print(f"[smoke] tree_model row count: {row_count}")
        assert row_count > 0

    def test_expand_root(self):
        """ルートノードを展開し、子ノードが表示される。"""
        load_result = self.harness.load(REAL_CARDS_DIR)
        assert load_result.success, f"ロードに失敗: {load_result.error}"

        select_result = self.harness.select_top_tree("メイン")
        if not select_result.success and "見つかりません" in (select_result.error or ""):
            pytest.skip("トップツリー「メイン」が実データに存在しません")
        assert select_result.success, f"トップツリー選択に失敗: {select_result.error}"

        result = self.harness.expand_node(["メイン"])
        assert result.success, f"ルートノード展開に失敗: {result.error}"
        print(
            f"\n[smoke] expand_node(['メイン']): {result.elapsed_sec:.3f}s, "
            f"memory: {result.memory_delta_bytes:,} bytes"
        )

    def test_expand_all(self):
        """全ノードを展開し、所要時間を出力する。"""
        load_result = self.harness.load(REAL_CARDS_DIR)
        assert load_result.success, f"ロードに失敗: {load_result.error}"

        select_result = self.harness.select_top_tree("メイン")
        if not select_result.success and "見つかりません" in (select_result.error or ""):
            pytest.skip("トップツリー「メイン」が実データに存在しません")
        assert select_result.success, f"トップツリー選択に失敗: {select_result.error}"

        result = self.harness.expand_all()
        assert result.success, f"全ノード展開に失敗: {result.error}"
        print(
            f"\n[smoke] expand_all: {result.elapsed_sec:.3f}s, "
            f"memory: {result.memory_delta_bytes:,} bytes"
        )

    def test_select_node_and_detail(self):
        """ノードを選択し、詳細ペインが更新される。"""
        load_result = self.harness.load(REAL_CARDS_DIR)
        assert load_result.success, f"ロードに失敗: {load_result.error}"

        select_result = self.harness.select_top_tree("メイン")
        if not select_result.success and "見つかりません" in (select_result.error or ""):
            pytest.skip("トップツリー「メイン」が実データに存在しません")
        assert select_result.success, f"トップツリー選択に失敗: {select_result.error}"

        # ルートノードを選択して詳細ペインの更新を確認
        result = self.harness.select_node(["メイン"])
        assert result.success, f"ノード選択に失敗: {result.error}"
        print(
            f"\n[smoke] select_node(['メイン']): {result.elapsed_sec:.3f}s"
        )

        # 詳細ペインが更新されていることを確認
        from gui.app import DETAIL_PLACEHOLDER
        assert self.harness.window is not None
        detail_text = self.harness.window._detail_browser.toPlainText()
        assert detail_text != DETAIL_PLACEHOLDER
        assert "キー名:" in detail_text
