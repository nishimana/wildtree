"""GUITestHarness のユニットテスト。

gui/test_harness.py の GUITestHarness クラスと内部ヘルパーのテスト。
テストフィクスチャ（数個のファイル・数十キー）を使ったユニットテスト。

テスト対象:
  - OperationResult: dataclass のフィールドとデフォルト値
  - GUITestHarness.load(): cards_dir のロード
  - GUITestHarness.select_top_tree(): トップツリーの選択
  - GUITestHarness.expand_node(): ノードの展開
  - GUITestHarness.expand_all(): 全ノードの展開
  - GUITestHarness.select_node(): ノードの選択と詳細ペイン更新
  - GUITestHarness.toggle_check(): チェック状態の反転
  - GUITestHarness.close(): ウィンドウのクローズ
  - GUITestHarness.window プロパティ: ウィンドウインスタンスへのアクセス
  - _find_node_index(): パス探索ヘルパー
  - _measure(): 計測ヘルパー

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conftest import _write_yaml


# =========================================================================
# テストフィクスチャ
# =========================================================================


@pytest.fixture()
def harness_cards_dir(tmp_path: Path) -> Path:
    """GUITestHarness テスト用の cards ディレクトリ。

    Structure::

        cards/
          main.yaml
            メイン:
              - __シーンまとめ__
              - __デフォルト__

          scenes.yaml
            シーンまとめ:
              - __キャラA__
              - literal_tag

            デフォルト:
              - default lighting
              # - __無効化された参照__

          characters.yaml
            キャラA:
              - slender body
              - __キャラA体格__

            キャラA体格:
              - athletic build
    """
    cards_dir = tmp_path / "cards"

    _write_yaml(
        cards_dir / "main.yaml",
        (
            "メイン:\n"
            "  - __シーンまとめ__\n"
            "  - __デフォルト__\n"
        ),
    )

    _write_yaml(
        cards_dir / "scenes.yaml",
        (
            "シーンまとめ:\n"
            "  - __キャラA__\n"
            "  - literal_tag\n"
            "\n"
            "デフォルト:\n"
            "  - default lighting\n"
            "  # - __無効化された参照__\n"
        ),
    )

    _write_yaml(
        cards_dir / "characters.yaml",
        (
            "キャラA:\n"
            "  - slender body\n"
            "  - __キャラA体格__\n"
            "\n"
            "キャラA体格:\n"
            "  - athletic build\n"
        ),
    )

    return cards_dir


@pytest.fixture()
def harness(qapp):
    """GUITestHarness インスタンスを生成し、テスト後にクリーンアップする。"""
    from gui.test_harness import GUITestHarness

    h = GUITestHarness()
    yield h
    h.close()


@pytest.fixture()
def loaded_harness(qapp, harness_cards_dir: Path):
    """ロード済みの GUITestHarness インスタンス。"""
    from gui.test_harness import GUITestHarness

    h = GUITestHarness()
    result = h.load(harness_cards_dir)
    assert result.success, f"ロードに失敗: {result.error}"
    yield h
    h.close()


# =========================================================================
# OperationResult: dataclass のフィールドとデフォルト値
# =========================================================================


class TestOperationResult:
    """OperationResult dataclass のテスト。"""

    def test_必須フィールドが設定される(self):
        """success, elapsed_sec, memory_delta_bytes が設定される。"""
        from gui.test_harness import OperationResult

        result = OperationResult(
            success=True,
            elapsed_sec=1.5,
            memory_delta_bytes=1024,
        )
        assert result.success is True
        assert result.elapsed_sec == 1.5
        assert result.memory_delta_bytes == 1024

    def test_errorのデフォルトはNone(self):
        """error フィールドのデフォルト値は None。"""
        from gui.test_harness import OperationResult

        result = OperationResult(
            success=True,
            elapsed_sec=0.0,
            memory_delta_bytes=0,
        )
        assert result.error is None

    def test_error指定時の値(self):
        """error フィールドに値を設定できる。"""
        from gui.test_harness import OperationResult

        result = OperationResult(
            success=False,
            elapsed_sec=0.0,
            memory_delta_bytes=0,
            error="テストエラー",
        )
        assert result.error == "テストエラー"

    def test_失敗時のフィールド組み合わせ(self):
        """success=False, error あり、elapsed_sec=0.0 の組み合わせ。"""
        from gui.test_harness import OperationResult

        result = OperationResult(
            success=False,
            elapsed_sec=0.0,
            memory_delta_bytes=0,
            error="ウィンドウが初期化されていません",
        )
        assert result.success is False
        assert result.elapsed_sec == 0.0
        assert result.memory_delta_bytes == 0
        assert result.error is not None


# =========================================================================
# GUITestHarness.window プロパティ
# =========================================================================


class TestWindowProperty:
    """GUITestHarness.window プロパティのテスト。"""

    def test_load前はNone(self, harness):
        """load() 前の window プロパティは None。"""
        assert harness.window is None

    def test_load後はWildTreeWindow(self, loaded_harness):
        """load() 後の window プロパティは WildTreeWindow インスタンス。"""
        from gui.app import WildTreeWindow

        assert loaded_harness.window is not None
        assert isinstance(loaded_harness.window, WildTreeWindow)


# =========================================================================
# GUITestHarness.load()
# =========================================================================


class TestLoad:
    """GUITestHarness.load() のテスト。"""

    def test_正常系_successがTrue(self, harness, harness_cards_dir: Path):
        """正常な cards_dir でロードし、success=True を返す。"""
        result = harness.load(harness_cards_dir)

        assert result.success is True
        assert result.error is None

    def test_正常系_elapsed_secが正の値(self, harness, harness_cards_dir: Path):
        """ロード時の elapsed_sec が 0 より大きい。"""
        result = harness.load(harness_cards_dir)

        assert result.elapsed_sec > 0

    def test_正常系_ウィンドウが生成される(self, harness, harness_cards_dir: Path):
        """ロード後に window プロパティが設定される。"""
        harness.load(harness_cards_dir)

        assert harness.window is not None

    def test_正常系_トップツリーリストにアイテムがある(
        self, harness, harness_cards_dir: Path
    ):
        """ロード後にトップツリーリストにアイテムがある。"""
        harness.load(harness_cards_dir)

        assert harness.window._list_top_trees.count() > 0

    def test_存在しないディレクトリ_successがFalse(self, harness, tmp_path: Path):
        """存在しない cards_dir の場合、success=False を返す。"""
        nonexistent = tmp_path / "nonexistent_dir"

        # QMessageBox.warning をモックしてモーダルダイアログを抑制
        with patch("gui.app.QMessageBox"):
            result = harness.load(nonexistent)

        assert result.success is False

    def test_2回呼ぶと前のウィンドウが閉じられる(
        self, harness, harness_cards_dir: Path
    ):
        """load() を2回呼ぶと、1回目のウィンドウが閉じられて新しいインスタンスが生成される。"""
        harness.load(harness_cards_dir)
        first_window = harness.window

        harness.load(harness_cards_dir)
        second_window = harness.window

        assert second_window is not None
        assert first_window is not second_window

    def test_空ディレクトリ_successがFalse(self, harness, tmp_path: Path):
        """空のディレクトリ（YAML なし）の場合、success=False を返す。"""
        empty_dir = tmp_path / "empty_cards"
        empty_dir.mkdir()

        result = harness.load(empty_dir)

        # YAML ファイルがないのでトップツリーが空 → success=False
        assert result.success is False


# =========================================================================
# GUITestHarness.select_top_tree()
# =========================================================================


class TestSelectTopTree:
    """GUITestHarness.select_top_tree() のテスト。"""

    def test_正常系_存在するトップツリー名で_successがTrue(self, loaded_harness):
        """存在するトップツリー名で select_top_tree を呼ぶと success=True。"""
        # トップツリーリストの最初のアイテム名を取得
        window = loaded_harness.window
        first_name = window._list_top_trees.item(0).text()

        result = loaded_harness.select_top_tree(first_name)

        assert result.success is True
        assert result.error is None
        assert result.elapsed_sec > 0

    def test_名前が見つからない場合_successがFalse(self, loaded_harness):
        """存在しないトップツリー名で success=False を返す。"""
        result = loaded_harness.select_top_tree("存在しないツリー名")

        assert result.success is False
        assert result.error is not None
        assert "見つかりません" in result.error

    def test_load前に呼ぶと_successがFalse(self, harness):
        """load() 前に select_top_tree を呼ぶと success=False。"""
        result = harness.select_top_tree("メイン")

        assert result.success is False
        assert result.error is not None
        assert "初期化されていません" in result.error

    def test_正常系_ツリーモデルにデータが投入される(self, loaded_harness):
        """select_top_tree 後にツリーモデルにデータが投入される。"""
        window = loaded_harness.window
        first_name = window._list_top_trees.item(0).text()

        loaded_harness.select_top_tree(first_name)

        assert window._tree_model.rowCount() > 0


# =========================================================================
# GUITestHarness.expand_node()
# =========================================================================


class TestExpandNode:
    """GUITestHarness.expand_node() のテスト。"""

    def _get_root_name(self, loaded_harness) -> str:
        """選択可能なトップツリーの最初の名前を取得し、トップツリーを選択する。"""
        window = loaded_harness.window
        first_name = window._list_top_trees.item(0).text()
        loaded_harness.select_top_tree(first_name)
        return first_name

    def test_正常系_有効なパスで_successがTrue(self, loaded_harness):
        """有効なパスで expand_node を呼ぶと success=True。"""
        root_name = self._get_root_name(loaded_harness)

        result = loaded_harness.expand_node([root_name])

        assert result.success is True
        assert result.error is None

    def test_パスが空の場合_successがFalse(self, loaded_harness):
        """空のパスで expand_node を呼ぶと success=False。"""
        self._get_root_name(loaded_harness)

        result = loaded_harness.expand_node([])

        assert result.success is False
        assert result.error is not None
        assert "パスが空" in result.error

    def test_パスが見つからない場合_successがFalse(self, loaded_harness):
        """存在しないパスで expand_node を呼ぶと success=False。"""
        self._get_root_name(loaded_harness)

        result = loaded_harness.expand_node(["存在しないノード"])

        assert result.success is False
        assert result.error is not None
        assert "見つかりません" in result.error

    def test_load前に呼ぶと_successがFalse(self, harness):
        """load() 前に expand_node を呼ぶと success=False。"""
        result = harness.expand_node(["メイン"])

        assert result.success is False
        assert result.error is not None
        assert "初期化されていません" in result.error

    def test_正常系_elapsed_secが0以上(self, loaded_harness):
        """expand_node の elapsed_sec が 0 以上。"""
        root_name = self._get_root_name(loaded_harness)

        result = loaded_harness.expand_node([root_name])

        assert result.elapsed_sec >= 0


# =========================================================================
# GUITestHarness.expand_all()
# =========================================================================


class TestExpandAll:
    """GUITestHarness.expand_all() のテスト。"""

    def test_正常系_successがTrue(self, loaded_harness):
        """expand_all を呼ぶと success=True。"""
        # トップツリーを選択
        window = loaded_harness.window
        first_name = window._list_top_trees.item(0).text()
        loaded_harness.select_top_tree(first_name)

        result = loaded_harness.expand_all()

        assert result.success is True
        assert result.error is None

    def test_正常系_elapsed_secが0以上(self, loaded_harness):
        """expand_all の elapsed_sec が 0 以上。"""
        window = loaded_harness.window
        first_name = window._list_top_trees.item(0).text()
        loaded_harness.select_top_tree(first_name)

        result = loaded_harness.expand_all()

        assert result.elapsed_sec >= 0

    def test_load前に呼ぶと_successがFalse(self, harness):
        """load() 前に expand_all を呼ぶと success=False。"""
        result = harness.expand_all()

        assert result.success is False
        assert result.error is not None
        assert "初期化されていません" in result.error


# =========================================================================
# GUITestHarness.select_node()
# =========================================================================


class TestSelectNode:
    """GUITestHarness.select_node() のテスト。"""

    def _setup_tree(self, loaded_harness) -> str:
        """トップツリーを選択してルート名を返す。"""
        window = loaded_harness.window
        first_name = window._list_top_trees.item(0).text()
        loaded_harness.select_top_tree(first_name)
        return first_name

    def test_正常系_有効なパスで_successがTrue(self, loaded_harness):
        """有効なパスで select_node を呼ぶと success=True。"""
        root_name = self._setup_tree(loaded_harness)

        result = loaded_harness.select_node([root_name])

        assert result.success is True
        assert result.error is None

    def test_正常系_詳細ペインが更新される(self, loaded_harness):
        """select_node 後に詳細ペインの内容が更新される。"""
        from gui.app import DETAIL_PLACEHOLDER

        root_name = self._setup_tree(loaded_harness)

        loaded_harness.select_node([root_name])

        # 詳細ペインがプレースホルダから変更されている
        detail_text = loaded_harness.window._detail_browser.toPlainText()
        assert detail_text != DETAIL_PLACEHOLDER

    def test_パスが見つからない場合_successがFalse(self, loaded_harness):
        """存在しないパスで select_node を呼ぶと success=False。"""
        self._setup_tree(loaded_harness)

        result = loaded_harness.select_node(["存在しないノード"])

        assert result.success is False
        assert result.error is not None
        assert "見つかりません" in result.error

    def test_パスが空の場合_successがFalse(self, loaded_harness):
        """空のパスで select_node を呼ぶと success=False。"""
        self._setup_tree(loaded_harness)

        result = loaded_harness.select_node([])

        assert result.success is False
        assert result.error is not None
        assert "パスが空" in result.error

    def test_load前に呼ぶと_successがFalse(self, harness):
        """load() 前に select_node を呼ぶと success=False。"""
        result = harness.select_node(["メイン"])

        assert result.success is False
        assert "初期化されていません" in result.error

    def test_子ノードのパスで_詳細ペインが子の情報を表示(self, loaded_harness):
        """子ノードのパスで select_node を呼ぶと、詳細ペインに子の情報が表示される。"""
        root_name = self._setup_tree(loaded_harness)

        # ルート直下の子ノードの名前を取得
        from gui.tree_model import TREE_NODE_ROLE

        window = loaded_harness.window
        root_item = window._tree_model.item(0)
        if root_item.rowCount() > 0:
            child_item = root_item.child(0)
            child_node = child_item.data(TREE_NODE_ROLE)
            child_name = child_node.display_name

            result = loaded_harness.select_node([root_name, child_name])

            assert result.success is True
            detail_text = window._detail_browser.toPlainText()
            assert len(detail_text) > 0


# =========================================================================
# GUITestHarness.toggle_check()
# =========================================================================


class TestToggleCheck:
    """GUITestHarness.toggle_check() のテスト。"""

    def _setup_tree(self, loaded_harness) -> str:
        """トップツリーを選択してルート名を返す。"""
        window = loaded_harness.window
        first_name = window._list_top_trees.item(0).text()
        loaded_harness.select_top_tree(first_name)
        return first_name

    def _find_checkable_path(self, loaded_harness) -> list[str] | None:
        """チェック可能なノードのパスを探して返す。なければ None。"""
        from gui.tree_model import TREE_NODE_ROLE

        window = loaded_harness.window
        root_item = window._tree_model.item(0)
        if root_item is None:
            return None

        root_node = root_item.data(TREE_NODE_ROLE)
        root_name = root_node.display_name

        for i in range(root_item.rowCount()):
            child_item = root_item.child(i)
            if child_item is not None and child_item.isCheckable():
                child_node = child_item.data(TREE_NODE_ROLE)
                return [root_name, child_node.display_name]

        return None

    def test_正常系_checkableノードで_successがTrue(self, loaded_harness):
        """checkable なノードで toggle_check を呼ぶと success=True。"""
        self._setup_tree(loaded_harness)
        path = self._find_checkable_path(loaded_harness)
        if path is None:
            pytest.skip("チェック可能なノードが見つからない")

        result = loaded_harness.toggle_check(path)

        assert result.success is True
        assert result.error is None

    def test_チェック不可ノードの場合_successがFalse(self, loaded_harness):
        """checkable でないノード（ROOT）で toggle_check を呼ぶと success=False。"""
        root_name = self._setup_tree(loaded_harness)

        # ROOT ノードはチェック不可
        result = loaded_harness.toggle_check([root_name])

        assert result.success is False
        assert result.error is not None
        assert "チェック不可" in result.error

    def test_パスが見つからない場合_successがFalse(self, loaded_harness):
        """存在しないパスで toggle_check を呼ぶと success=False。"""
        self._setup_tree(loaded_harness)

        result = loaded_harness.toggle_check(["存在しないノード"])

        assert result.success is False
        assert result.error is not None
        assert "見つかりません" in result.error

    def test_パスが空の場合_successがFalse(self, loaded_harness):
        """空のパスで toggle_check を呼ぶと success=False。"""
        self._setup_tree(loaded_harness)

        result = loaded_harness.toggle_check([])

        assert result.success is False
        assert result.error is not None
        assert "パスが空" in result.error

    def test_load前に呼ぶと_successがFalse(self, harness):
        """load() 前に toggle_check を呼ぶと success=False。"""
        result = harness.toggle_check(["メイン", "子ノード"])

        assert result.success is False
        assert "初期化されていません" in result.error


# =========================================================================
# GUITestHarness.close()
# =========================================================================


class TestClose:
    """GUITestHarness.close() のテスト。"""

    def test_ウィンドウが閉じられてwindowがNoneになる(self, loaded_harness):
        """close() 後に window プロパティが None になる。"""
        assert loaded_harness.window is not None

        loaded_harness.close()

        assert loaded_harness.window is None

    def test_windowがNone時にcloseを呼んでもエラーにならない(self, harness):
        """window が None の状態で close() を呼んでも例外が発生しない。"""
        assert harness.window is None

        # 例外が発生しないことを確認
        harness.close()

        assert harness.window is None

    def test_2回closeを呼んでもエラーにならない(self, loaded_harness):
        """close() を2回呼んでも例外が発生しない。"""
        loaded_harness.close()
        loaded_harness.close()  # 2回目でも例外なし

        assert loaded_harness.window is None


# =========================================================================
# _find_node_index(): パス探索ヘルパー
# =========================================================================


class TestFindNodeIndex:
    """_find_node_index() 内部ヘルパーのテスト。"""

    def _build_model(self, qapp):
        """テスト用のモデルを構築する。"""
        from PySide6.QtGui import QStandardItemModel

        from core.models import KeyDefinition, NodeType, TreeNode, ValueEntry, WildcardRef
        from gui.tree_model import populate_model

        # ツリー構造を構築
        kd_root = KeyDefinition(
            name="ルート", file_path=Path("C:/cards/test.yaml"), line_number=1
        )
        ve_child = ValueEntry(raw_text="__子ノード__", line_number=2)
        ve_grandchild = ValueEntry(raw_text="リーフ", line_number=3)

        grandchild = TreeNode(
            display_name="リーフ",
            node_type=NodeType.LITERAL,
            value_entry=ve_grandchild,
        )
        child = TreeNode(
            display_name="子ノード",
            node_type=NodeType.REF,
            children=[grandchild],
            key_def=KeyDefinition(
                name="子ノード", file_path=Path("C:/cards/test.yaml"), line_number=5
            ),
            value_entry=ve_child,
            ref=WildcardRef(raw="__子ノード__", full_path="子ノード"),
        )
        root = TreeNode(
            display_name="ルート",
            node_type=NodeType.ROOT,
            children=[child],
            key_def=kd_root,
        )

        model = QStandardItemModel()
        populate_model(root, model)
        return model

    def test_ルートパスで一致(self, qapp):
        """パス ["ルート"] でルートアイテムの QModelIndex を返す。"""
        from gui.test_harness import _find_node_index

        model = self._build_model(qapp)

        index = _find_node_index(model, ["ルート"])

        assert index is not None
        assert index.isValid()

    def test_子パスで一致(self, qapp):
        """パス ["ルート", "子ノード"] で子アイテムの QModelIndex を返す。"""
        from gui.test_harness import _find_node_index

        model = self._build_model(qapp)

        index = _find_node_index(model, ["ルート", "子ノード"])

        assert index is not None
        assert index.isValid()

    def test_孫パスで一致(self, qapp):
        """パス ["ルート", "子ノード", "リーフ"] で孫アイテムの QModelIndex を返す。"""
        from gui.test_harness import _find_node_index

        model = self._build_model(qapp)

        index = _find_node_index(model, ["ルート", "子ノード", "リーフ"])

        assert index is not None
        assert index.isValid()

    def test_空パスでNone(self, qapp):
        """空のパスで None を返す。"""
        from gui.test_harness import _find_node_index

        model = self._build_model(qapp)

        index = _find_node_index(model, [])

        assert index is None

    def test_ルート名不一致でNone(self, qapp):
        """ルート名が一致しないパスで None を返す。"""
        from gui.test_harness import _find_node_index

        model = self._build_model(qapp)

        index = _find_node_index(model, ["不一致のルート名"])

        assert index is None

    def test_子ノード名不一致でNone(self, qapp):
        """子ノード名が一致しないパスで None を返す。"""
        from gui.test_harness import _find_node_index

        model = self._build_model(qapp)

        index = _find_node_index(model, ["ルート", "存在しない子"])

        assert index is None

    def test_空モデルでNone(self, qapp):
        """空のモデルで None を返す。"""
        from PySide6.QtGui import QStandardItemModel

        from gui.test_harness import _find_node_index

        model = QStandardItemModel()

        index = _find_node_index(model, ["何か"])

        assert index is None


# =========================================================================
# _measure(): 計測ヘルパー
# =========================================================================


class TestMeasure:
    """_measure() 計測ヘルパーのテスト。"""

    def test_正常系_successがTrue(self, qapp):
        """正常な関数を渡すと success=True を返す。"""
        from gui.test_harness import _measure

        def noop():
            pass

        result = _measure(noop)

        assert result.success is True
        assert result.error is None

    def test_正常系_elapsed_secが0以上(self, qapp):
        """計測した elapsed_sec が 0 以上。"""
        from gui.test_harness import _measure

        def noop():
            pass

        result = _measure(noop)

        assert result.elapsed_sec >= 0

    def test_正常系_memory_delta_bytesが数値(self, qapp):
        """memory_delta_bytes が int 型の値を返す。"""
        from gui.test_harness import _measure

        def noop():
            pass

        result = _measure(noop)

        assert isinstance(result.memory_delta_bytes, int)

    def test_メモリ確保時にmemory_delta_bytesが増加する可能性(self, qapp):
        """メモリを確保する関数で memory_delta_bytes が 0 でない可能性がある。

        tracemalloc のオーバーヘッドにより正確な値は保証できないが、
        大きなリストを確保した場合は正の値が返る可能性が高い。
        """
        from gui.test_harness import _measure

        data = []

        def allocate():
            # 大きなリストを作成
            for i in range(10000):
                data.append(f"item_{i}")

        result = _measure(allocate)

        # 確保後は何かしらのメモリ差分が出る（ただし環境依存のため厳密な判定は行わない）
        assert isinstance(result.memory_delta_bytes, int)

    def test_tracemalloc起動済みでも正常動作(self, qapp):
        """tracemalloc が既に起動中でも _measure が正常に動作する。"""
        import tracemalloc

        from gui.test_harness import _measure

        # 事前に起動
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()

        try:
            def noop():
                pass

            result = _measure(noop)

            assert result.success is True
            # tracemalloc は停止されていない（既に起動済みだったため）
            assert tracemalloc.is_tracing()
        finally:
            if not was_tracing:
                tracemalloc.stop()


# =========================================================================
# 統合テスト: 一連の操作フロー
# =========================================================================


class TestIntegrationFlow:
    """一連の操作フローの統合テスト。"""

    def test_load_select_expand_close(self, qapp, harness_cards_dir: Path):
        """load → select_top_tree → expand_node → close の一連のフロー。"""
        from gui.test_harness import GUITestHarness

        harness = GUITestHarness()
        try:
            # ロード
            load_result = harness.load(harness_cards_dir)
            assert load_result.success is True

            # トップツリー選択
            first_name = harness.window._list_top_trees.item(0).text()
            select_result = harness.select_top_tree(first_name)
            assert select_result.success is True

            # ルートノード展開
            expand_result = harness.expand_node([first_name])
            assert expand_result.success is True

            # 全展開
            expand_all_result = harness.expand_all()
            assert expand_all_result.success is True

            # ノード選択
            select_node_result = harness.select_node([first_name])
            assert select_node_result.success is True
        finally:
            harness.close()
            assert harness.window is None

    def test_load_select_toggle_check(self, qapp, harness_cards_dir: Path):
        """load → select_top_tree → toggle_check の一連のフロー。"""
        from gui.tree_model import TREE_NODE_ROLE

        from gui.test_harness import GUITestHarness

        harness = GUITestHarness()
        try:
            # ロード
            harness.load(harness_cards_dir)

            # トップツリー選択
            first_name = harness.window._list_top_trees.item(0).text()
            harness.select_top_tree(first_name)

            # チェック可能な子ノードを探す
            root_item = harness.window._tree_model.item(0)
            root_node = root_item.data(TREE_NODE_ROLE)
            root_name = root_node.display_name

            checkable_path = None
            for i in range(root_item.rowCount()):
                child_item = root_item.child(i)
                if child_item is not None and child_item.isCheckable():
                    child_node = child_item.data(TREE_NODE_ROLE)
                    checkable_path = [root_name, child_node.display_name]
                    break

            if checkable_path is not None:
                toggle_result = harness.toggle_check(checkable_path)
                assert toggle_result.success is True
        finally:
            harness.close()
