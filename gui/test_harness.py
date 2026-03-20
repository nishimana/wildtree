"""GUI テストハーネス — WildTreeWindow をプログラムから操作して計測する。

S9 — パフォーマンス計測とスモークテストのためのテストハーネス。

WildTreeWindow を実際に生成し、ユーザー操作と同じコードパス
（シグナル/スロット、ウィジェット描画）を通る操作 API を提供する。
各操作の所要時間・メモリ使用量を OperationResult として返す。

設計方針:
  - WildTreeWindow の実インスタンスを使い、モックを使わない
  - QApplication.processEvents() で描画更新を計測に含める
  - tracemalloc で Python オブジェクトのメモリ増加量を計測
    （Qt のネイティブメモリは含まない）
  - 例外を投げない。全てのエラーを OperationResult で返す
"""

from __future__ import annotations

import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------


@dataclass
class OperationResult:
    """操作の計測結果。

    Attributes:
        success: 操作が正常に完了したかどうか。
        elapsed_sec: 所要時間（秒）。time.perf_counter() で計測。
        memory_delta_bytes: メモリ増加量（バイト）。tracemalloc で計測。
            Qt のネイティブメモリ（QStandardItem の内部バッファ等）は含まない。
        error: エラーメッセージ。成功時は None。
    """

    success: bool
    elapsed_sec: float
    memory_delta_bytes: int
    error: str | None = None


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _measure(func: Callable[[], None]) -> OperationResult:
    """関数を実行して時間とメモリを計測する。

    tracemalloc でメモリスナップショットを取得し、
    func 実行前後の差分を計測する。
    QApplication.processEvents() を func 後に呼んで
    Qt の描画更新を計測に含める。

    Args:
        func: 計測対象の関数。引数なし、戻り値なし。

    Returns:
        計測結果の OperationResult。success=True で返す。
    """
    # tracemalloc が既に起動中なら再起動しない
    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()

    snapshot_before = tracemalloc.take_snapshot()

    t0 = time.perf_counter()
    func()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    elapsed = time.perf_counter() - t0

    snapshot_after = tracemalloc.take_snapshot()

    if not was_tracing:
        tracemalloc.stop()

    # スナップショット間の差分からメモリ増加量を計算
    stats = snapshot_after.compare_to(snapshot_before, "lineno")
    memory_delta = sum(stat.size_diff for stat in stats)

    return OperationResult(
        success=True,
        elapsed_sec=elapsed,
        memory_delta_bytes=memory_delta,
    )


def _find_node_index(
    model: QStandardItemModel,
    path: list[str],
) -> QModelIndex | None:
    """パスに一致するノードの QModelIndex を探索する。

    パスはルートからのノード名（display_name）のリスト。
    モデルの最初のルートアイテムから再帰的に子を辿る。

    Args:
        model: 探索対象の QStandardItemModel。
        path: ルートからのノード名リスト。
            例: ["メイン", "デフォルト", "シネマシャドウ"]

    Returns:
        一致するノードの QModelIndex。見つからない場合は None。
    """
    from gui.tree_model import TREE_NODE_ROLE

    if not path:
        return None

    # ルートアイテムの確認
    if model.rowCount() == 0:
        return None

    root_item = model.item(0)
    if root_item is None:
        return None

    root_node = root_item.data(TREE_NODE_ROLE)
    if root_node is None or root_node.display_name != path[0]:
        return None

    if len(path) == 1:
        return root_item.index()

    # パスの残りを辿る
    current_item = root_item
    for i in range(1, len(path)):
        target_name = path[i]
        found = False
        for row in range(current_item.rowCount()):
            child_item = current_item.child(row)
            if child_item is None:
                continue
            child_node = child_item.data(TREE_NODE_ROLE)
            if child_node is not None and child_node.display_name == target_name:
                current_item = child_item
                found = True
                break
        if not found:
            return None

    return current_item.index()


# ---------------------------------------------------------------------------
# テストハーネス
# ---------------------------------------------------------------------------


class GUITestHarness:
    """WildTreeWindow をプログラムから操作して計測するテストハーネス。

    ユーザー操作と同じコードパスを通る API を提供し、
    各操作の所要時間・メモリ使用量を OperationResult として返す。

    使い方:
        harness = GUITestHarness()
        result = harness.load(cards_dir)
        result = harness.select_top_tree("メイン")
        result = harness.expand_node(["メイン"])
        result = harness.expand_all()
        harness.close()

    Note:
        QApplication が事前に作成されていること。
        offscreen モード（QT_QPA_PLATFORM=offscreen）でも動作する。
    """

    def __init__(self) -> None:
        """テストハーネスを初期化する。ウィンドウはまだ生成しない。"""
        self._window = None

    @property
    def window(self):
        """現在のウィンドウインスタンスへのアクセス。

        Returns:
            WildTreeWindow インスタンス。load() 前は None。
        """
        return self._window

    def load(self, cards_dir: Path) -> OperationResult:
        """cards ディレクトリをロードする。

        WildTreeWindow を生成し、コンストラクタ内で
        _load_cards_dir() パイプラインを実行する。
        Browse ボタンと同じコードパスを通る。

        既にウィンドウが存在する場合は close() してから再生成する。

        Args:
            cards_dir: cards ディレクトリのパス。

        Returns:
            操作の計測結果。
        """
        # 既存ウィンドウがあれば閉じる
        if self._window is not None:
            self._window.close()
            self._window = None

        try:
            def _do_load():
                from gui.app import WildTreeWindow
                self._window = WildTreeWindow(cards_dir=cards_dir)

            result = _measure(_do_load)

            # ロード成功の判定: トップツリーリストにアイテムがあるか
            if self._window is not None and self._window._list_top_trees.count() > 0:
                return result
            else:
                return OperationResult(
                    success=False,
                    elapsed_sec=result.elapsed_sec,
                    memory_delta_bytes=result.memory_delta_bytes,
                    error="トップツリーリストが空です。ロードに失敗した可能性があります。",
                )
        except Exception as e:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=str(e),
            )

    def select_top_tree(self, name: str) -> OperationResult:
        """トップツリーを名前で選択する。

        QListWidget から名前に一致するアイテムを探し、
        setCurrentRow() で選択する。
        _on_top_tree_selected() がシグナル経由で発火する。

        Args:
            name: トップツリー名（例: "メイン"）。

        Returns:
            操作の計測結果。
        """
        if self._window is None:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error="ウィンドウが初期化されていません。先に load() を呼んでください。",
            )

        # 名前に一致するアイテムのインデックスを探す
        target_row = -1
        list_widget = self._window._list_top_trees
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item is not None and item.text() == name:
                target_row = row
                break

        if target_row < 0:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=f"トップツリーが見つかりません: {name}",
            )

        try:
            def _do_select():
                list_widget.setCurrentRow(target_row)

            return _measure(_do_select)
        except Exception as e:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=str(e),
            )

    def expand_node(self, path: list[str]) -> OperationResult:
        """パスで指定したノードを展開する。

        QTreeView.expand() を呼び、ユーザーのツリーノード展開と
        同じコードパスを通る。

        Args:
            path: ルートからのノード名リスト。
                例: ["メイン", "デフォルト"]

        Returns:
            操作の計測結果。
        """
        if self._window is None:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error="ウィンドウが初期化されていません。先に load() を呼んでください。",
            )

        if not path:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error="パスが空です。",
            )

        index = _find_node_index(self._window._tree_model, path)
        if index is None:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=f"ノードが見つかりません: {' > '.join(path)}",
            )

        try:
            def _do_expand():
                self._window._tree_view.expand(index)

            return _measure(_do_expand)
        except Exception as e:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=str(e),
            )

    def expand_all(self) -> OperationResult:
        """全ノードを展開する。

        QTreeView.expandAll() を呼ぶ。
        ユーザー操作では通常行わないが、パフォーマンスの上限計測に使う。

        Returns:
            操作の計測結果。
        """
        if self._window is None:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error="ウィンドウが初期化されていません。先に load() を呼んでください。",
            )

        try:
            def _do_expand_all():
                self._window._tree_view.expandAll()

            return _measure(_do_expand_all)
        except Exception as e:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=str(e),
            )

    def select_node(self, path: list[str]) -> OperationResult:
        """パスで指定したノードを選択する。

        selectionModel().setCurrentIndex() を呼び、
        _on_tree_node_selected() がシグナル経由で発火する。
        詳細ペインの更新が行われる。

        Args:
            path: ルートからのノード名リスト。

        Returns:
            操作の計測結果。
        """
        if self._window is None:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error="ウィンドウが初期化されていません。先に load() を呼んでください。",
            )

        if not path:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error="パスが空です。",
            )

        index = _find_node_index(self._window._tree_model, path)
        if index is None:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=f"ノードが見つかりません: {' > '.join(path)}",
            )

        try:
            def _do_select():
                self._window._tree_view.selectionModel().setCurrentIndex(
                    index,
                    self._window._tree_view.selectionModel().SelectionFlag.ClearAndSelect,
                )

            return _measure(_do_select)
        except Exception as e:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=str(e),
            )

    def toggle_check(self, path: list[str]) -> OperationResult:
        """パスで指定したノードのチェック状態を反転する。

        QStandardItem.setCheckState() を呼び、
        itemChanged シグナル → _on_item_changed() のコードパスを通る。

        Args:
            path: ルートからのノード名リスト。

        Returns:
            操作の計測結果。
        """
        if self._window is None:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error="ウィンドウが初期化されていません。先に load() を呼んでください。",
            )

        if not path:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error="パスが空です。",
            )

        index = _find_node_index(self._window._tree_model, path)
        if index is None:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=f"ノードが見つかりません: {' > '.join(path)}",
            )

        item = self._window._tree_model.itemFromIndex(index)
        if item is None:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=f"アイテムが取得できません: {' > '.join(path)}",
            )

        if not item.isCheckable():
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=f"チェック不可のノードです: {' > '.join(path)}",
            )

        try:
            def _do_toggle():
                # 現在のチェック状態を反転
                current_state = item.checkState()
                if current_state == Qt.CheckState.Checked:
                    item.setCheckState(Qt.CheckState.Unchecked)
                else:
                    item.setCheckState(Qt.CheckState.Checked)

            return _measure(_do_toggle)
        except Exception as e:
            return OperationResult(
                success=False,
                elapsed_sec=0.0,
                memory_delta_bytes=0,
                error=str(e),
            )

    def close(self) -> None:
        """ウィンドウを閉じてリソースを解放する。"""
        if self._window is not None:
            self._window.close()
            self._window = None
