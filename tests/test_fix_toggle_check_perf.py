"""Fix: チェックボックストグル操作のパフォーマンス改善 — テスト。

修正設計 (docs/design/fix-toggle-check-perf.md) に基づいて、
差分更新関数とコメント切替後のツリー正当性を検証する。

テスト対象:
  - refresh_full_path_index(file_path, registry, full_path_index, cards_dir) -> None
  - コメント切替後のツリー再構築の正当性（回帰テスト）

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models import (
    FullPathIndex,
    KeyDefinition,
    KeyRegistry,
    NodeType,
    ValueEntry,
    WildcardRef,
)
from core.resolver import (
    build_full_path_index,
    refresh_full_path_index,
)


# =========================================================================
# ヘルパー
# =========================================================================


def _make_key_def(
    name: str,
    file_path: Path,
    line_number: int = 1,
    values: list[ValueEntry] | None = None,
) -> KeyDefinition:
    """テスト用 KeyDefinition を生成するヘルパー。"""
    return KeyDefinition(
        name=name,
        file_path=file_path,
        line_number=line_number,
        values=values if values is not None else [],
    )


def _make_registry(*entries: tuple[str, KeyDefinition]) -> KeyRegistry:
    """テスト用 KeyRegistry を生成するヘルパー。

    同名キーは同じリストに追加される。
    """
    registry: KeyRegistry = {}
    for key_name, key_def in entries:
        registry.setdefault(key_name, []).append(key_def)
    return registry


def _make_value_entry(
    raw_text: str,
    line_number: int = 2,
    is_commented: bool = False,
    refs: list[WildcardRef] | None = None,
    literals: list[str] | None = None,
) -> ValueEntry:
    """テスト用 ValueEntry を生成するヘルパー。"""
    return ValueEntry(
        raw_text=raw_text,
        line_number=line_number,
        is_commented=is_commented,
        refs=refs if refs is not None else [],
        literals=literals if literals is not None else [],
    )


def _write_yaml(path: Path, content: str) -> Path:
    """テスト用 YAML ファイルを作成するヘルパー。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# =========================================================================
# refresh_full_path_index — 正常系
# =========================================================================


class TestRefreshFullPathIndex正常系:
    """refresh_full_path_index の正常系テスト。"""

    def test_refresh_full_path_index_差分更新後にフル再構築と同じ結果になる(
        self, tmp_path: Path
    ):
        """レジストリ更新後に差分更新を行い、
        フル再構築と同じインデックスが得られることを検証する。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        # 初期ファイルを作成
        file_a = _write_yaml(
            cards_dir / "SAO" / "asada.yaml",
            "朝田詩乃:\n"
            "  - slender body\n"
            "  - __朝田詩乃体格__\n",
        )
        _write_yaml(
            cards_dir / "BA" / "shiroko.yaml",
            "シロコ:\n"
            "  - athletic body\n",
        )

        # 初期レジストリとインデックスを構築
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)

        full_path_index = build_full_path_index(registry, cards_dir)

        # ファイルを書き換え（コメント切替をシミュレート）
        _write_yaml(
            file_a,
            "朝田詩乃:\n"
            "  # - slender body\n"
            "  - __朝田詩乃体格__\n",
        )

        # レジストリを更新
        from core.editor import refresh_registry
        refresh_registry(file_a, registry)

        # 差分更新
        refresh_full_path_index(file_a, registry, full_path_index, cards_dir)

        # フル再構築で得られるインデックスと比較
        expected_index = build_full_path_index(registry, cards_dir)

        # キーが同じ
        assert set(full_path_index.keys()) == set(expected_index.keys())
        # 各キーの値（KeyDefinition オブジェクト）が同一
        for fp in expected_index:
            assert full_path_index[fp] is expected_index[fp], (
                f"フルパス '{fp}' の KeyDefinition が一致しない"
            )

    def test_refresh_full_path_index_更新対象ファイルのKeyDefinitionが新しいオブジェクトに差し替わる(
        self, tmp_path: Path
    ):
        """差分更新で対象ファイルの KeyDefinition が新しいオブジェクトに更新される。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        file_a = _write_yaml(
            cards_dir / "test.yaml",
            "keyA:\n"
            "  - value1\n",
        )

        # 初期レジストリとインデックスを構築
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)

        full_path_index = build_full_path_index(registry, cards_dir)

        # 元の KeyDefinition を記録
        old_kd = full_path_index["keyA"]

        # ファイルを書き換え
        _write_yaml(
            file_a,
            "keyA:\n"
            "  # - value1\n",
        )

        # レジストリを更新（新しい KeyDefinition オブジェクトが生成される）
        from core.editor import refresh_registry
        refresh_registry(file_a, registry)

        new_kd = registry["keyA"][-1]
        assert old_kd is not new_kd  # 異なるオブジェクト

        # 差分更新
        refresh_full_path_index(file_a, registry, full_path_index, cards_dir)

        # インデックスの KeyDefinition が新しいオブジェクトに差し替わっている
        assert full_path_index["keyA"] is new_kd
        assert full_path_index["keyA"] is not old_kd

    def test_refresh_full_path_index_他のファイルのエントリは変更されない(
        self, tmp_path: Path
    ):
        """差分更新で対象ファイル以外のエントリは変更されない。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        file_a = _write_yaml(
            cards_dir / "a.yaml",
            "keyA:\n"
            "  - valueA\n",
        )
        _write_yaml(
            cards_dir / "b.yaml",
            "keyB:\n"
            "  - valueB\n",
        )

        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)

        full_path_index = build_full_path_index(registry, cards_dir)

        # keyB の KeyDefinition を記録
        kd_b_before = full_path_index["keyB"]

        # file_a のみ書き換え
        _write_yaml(
            file_a,
            "keyA:\n"
            "  # - valueA\n",
        )

        from core.editor import refresh_registry
        refresh_registry(file_a, registry)
        refresh_full_path_index(file_a, registry, full_path_index, cards_dir)

        # keyB の KeyDefinition は変更されていない（同一オブジェクト）
        assert full_path_index["keyB"] is kd_b_before

    def test_refresh_full_path_index_インプレースで変更される(self):
        """full_path_index が in-place で変更されること（新しい辞書を返さない）。"""
        cards_dir = Path("C:/cards")
        kd_old = _make_key_def("keyA", cards_dir / "test.yaml", values=[
            _make_value_entry("old_value"),
        ])
        kd_new = _make_key_def("keyA", cards_dir / "test.yaml", values=[
            _make_value_entry("new_value"),
        ])

        registry: KeyRegistry = {"keyA": [kd_new]}
        full_path_index: FullPathIndex = {"keyA": kd_old}

        original_dict_id = id(full_path_index)

        refresh_full_path_index(
            cards_dir / "test.yaml", registry, full_path_index, cards_dir
        )

        # 同じ辞書オブジェクトが更新されている
        assert id(full_path_index) == original_dict_id
        assert full_path_index["keyA"] is kd_new


# =========================================================================
# refresh_full_path_index — エッジケース
# =========================================================================


class TestRefreshFullPathIndexエッジケース:
    """refresh_full_path_index のエッジケーステスト。"""

    def test_refresh_full_path_index_空のレジストリ_例外なし(self):
        """空のレジストリに対して差分更新しても例外が発生しない。"""
        cards_dir = Path("C:/cards")
        registry: KeyRegistry = {}
        full_path_index: FullPathIndex = {}

        # 例外なし
        refresh_full_path_index(
            cards_dir / "test.yaml", registry, full_path_index, cards_dir
        )

        assert len(full_path_index) == 0

    def test_refresh_full_path_index_空のインデックス_例外なし(self):
        """空のインデックスに対して差分更新しても例外が発生しない。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("keyA", cards_dir / "test.yaml")
        registry: KeyRegistry = {"keyA": [kd]}
        full_path_index: FullPathIndex = {}

        # 例外なし（空インデックスに対しても安全に動作）
        refresh_full_path_index(
            cards_dir / "test.yaml", registry, full_path_index, cards_dir
        )

        # 設計上、差分更新はインデックス内の既存エントリを更新するのみ
        # ただし効率的な実装ではレジストリからフルパスを計算して上書きする
        # いずれの実装でもインデックスは一貫した状態になる

    def test_refresh_full_path_index_該当ファイルがレジストリに存在しない_例外なし(self):
        """指定ファイルのキーがレジストリに存在しない場合、例外が発生しない。"""
        cards_dir = Path("C:/cards")
        kd_other = _make_key_def("keyB", cards_dir / "other.yaml")
        registry: KeyRegistry = {"keyB": [kd_other]}
        full_path_index: FullPathIndex = {"keyB": kd_other}

        # test.yaml に由来するキーは存在しない
        refresh_full_path_index(
            cards_dir / "test.yaml", registry, full_path_index, cards_dir
        )

        # keyB は変更されない
        assert full_path_index["keyB"] is kd_other

    def test_refresh_full_path_index_cards_dir外のファイル_例外なし(self):
        """cards_dir 外のファイルパスを指定しても例外が発生しない。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("keyA", cards_dir / "test.yaml")
        registry: KeyRegistry = {"keyA": [kd]}
        full_path_index: FullPathIndex = {"keyA": kd}

        # cards_dir 外のパスを指定
        refresh_full_path_index(
            Path("D:/other/test.yaml"), registry, full_path_index, cards_dir
        )

        # インデックスは変更されない
        assert full_path_index["keyA"] is kd


# =========================================================================
# refresh_full_path_index — 複数キー
# =========================================================================


class TestRefreshFullPathIndex複数キー:
    """1ファイルに複数キーがある場合の差分更新テスト。"""

    def test_refresh_full_path_index_1ファイルに複数キーの差分更新(
        self, tmp_path: Path
    ):
        """1つのファイルに複数のキー定義がある場合、
        差分更新で全キーの KeyDefinition が更新される。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        file_a = _write_yaml(
            cards_dir / "SAO" / "asada.yaml",
            "朝田詩乃:\n"
            "  - slender body\n"
            "\n"
            "朝田詩乃体格:\n"
            "  - slim\n",
        )
        _write_yaml(
            cards_dir / "other.yaml",
            "other_key:\n"
            "  - other_value\n",
        )

        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)

        full_path_index = build_full_path_index(registry, cards_dir)

        # 元のオブジェクトを記録
        old_kd_asada = full_path_index["SAO/朝田詩乃"]
        old_kd_taikaku = full_path_index["SAO/朝田詩乃体格"]
        old_kd_other = full_path_index["other_key"]

        # ファイルを書き換え（コメント切替シミュレーション）
        _write_yaml(
            file_a,
            "朝田詩乃:\n"
            "  # - slender body\n"
            "\n"
            "朝田詩乃体格:\n"
            "  - slim\n",
        )

        from core.editor import refresh_registry
        refresh_registry(file_a, registry)
        refresh_full_path_index(file_a, registry, full_path_index, cards_dir)

        # 両方のキーが新しい KeyDefinition に差し替わっている
        assert full_path_index["SAO/朝田詩乃"] is not old_kd_asada
        assert full_path_index["SAO/朝田詩乃体格"] is not old_kd_taikaku

        # 新しい KeyDefinition はレジストリ内のものと同一
        assert full_path_index["SAO/朝田詩乃"] is registry["朝田詩乃"][-1]
        assert full_path_index["SAO/朝田詩乃体格"] is registry["朝田詩乃体格"][-1]

        # 他のファイルのエントリは変更されない
        assert full_path_index["other_key"] is old_kd_other

    def test_refresh_full_path_index_直下ファイルの複数キー(
        self, tmp_path: Path
    ):
        """cards_dir 直下のファイルに複数キーがある場合の差分更新。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        file_main = _write_yaml(
            cards_dir / "main.yaml",
            "メイン:\n"
            "  - __シーン__\n"
            "\n"
            "シーン:\n"
            "  - scene_value\n",
        )

        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)

        full_path_index = build_full_path_index(registry, cards_dir)

        old_kd_main = full_path_index["メイン"]
        old_kd_scene = full_path_index["シーン"]

        # コメント切替シミュレーション
        _write_yaml(
            file_main,
            "メイン:\n"
            "  # - __シーン__\n"
            "\n"
            "シーン:\n"
            "  - scene_value\n",
        )

        from core.editor import refresh_registry
        refresh_registry(file_main, registry)
        refresh_full_path_index(file_main, registry, full_path_index, cards_dir)

        # 両方とも新しいオブジェクトに更新
        assert full_path_index["メイン"] is not old_kd_main
        assert full_path_index["シーン"] is not old_kd_scene

        # レジストリと同一オブジェクト
        assert full_path_index["メイン"] is registry["メイン"][-1]
        assert full_path_index["シーン"] is registry["シーン"][-1]


# =========================================================================
# 回帰テスト — コメント切替後のツリー正当性
# =========================================================================


class Testコメント切替後のツリー正当性:
    """コメント切替後にツリーを再構築し、
    チェックボックス状態が正しく反映されることを検証する回帰テスト。"""

    def _build_pipeline(
        self, cards_dir: Path
    ) -> tuple[KeyRegistry, FullPathIndex]:
        """cards_dir からスキャン・パース・インデックス構築を行うヘルパー。"""
        from core.scanner import scan_yaml_files
        from core.parser import parse_yaml_file

        yaml_files = scan_yaml_files(cards_dir)
        registry: KeyRegistry = {}
        for yf in yaml_files:
            key_defs = parse_yaml_file(yf)
            for kd in key_defs:
                registry.setdefault(kd.name, []).append(kd)
        index = build_full_path_index(registry, cards_dir)
        return registry, index

    def test_コメント化後のツリーでis_commentedがTrueに反映される(
        self, tmp_path: Path
    ):
        """値行をコメント化 → refresh_registry → refresh_full_path_index →
        build_tree の結果で、コメント化した値行の is_commented が True になる。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        file_path = _write_yaml(
            cards_dir / "scenes.yaml",
            "シーンまとめ:\n"
            "  - __朝田詩乃__\n"
            "  - __シロコ__\n"
            "\n"
            "朝田詩乃:\n"
            "  - slender body\n"
            "\n"
            "シロコ:\n"
            "  - athletic body\n",
        )

        registry, full_path_index = self._build_pipeline(cards_dir)

        from core.tree_builder import build_tree

        # 初期ツリー: 両方 is_commented=False
        kd_scene = registry["シーンまとめ"][-1]
        root = build_tree(kd_scene, registry, full_path_index)

        assert len(root.children) == 2
        for child in root.children:
            assert child.value_entry is not None
            assert child.value_entry.is_commented is False

        # シロコへの参照をコメント化
        from core.editor import toggle_comment, refresh_registry

        ve_shiroko = registry["シーンまとめ"][-1].values[1]
        result = toggle_comment(file_path, ve_shiroko, enable=False)
        assert result.success is True

        # レジストリとインデックスを更新
        refresh_registry(file_path, registry)
        refresh_full_path_index(file_path, registry, full_path_index, cards_dir)

        # 最新の key_def を取得してツリーを再構築
        kd_scene_new = registry["シーンまとめ"][-1]
        root_after = build_tree(kd_scene_new, registry, full_path_index)

        # 朝田詩乃は有効のまま
        assert root_after.children[0].value_entry is not None
        assert root_after.children[0].value_entry.is_commented is False
        # シロコはコメント化
        assert root_after.children[1].value_entry is not None
        assert root_after.children[1].value_entry.is_commented is True

    def test_コメント解除後のツリーでis_commentedがFalseに反映される(
        self, tmp_path: Path
    ):
        """コメント化された値行を解除 → refresh_registry → refresh_full_path_index →
        build_tree の結果で、コメント解除した値行の is_commented が False になる。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        file_path = _write_yaml(
            cards_dir / "scenes.yaml",
            "シーンまとめ:\n"
            "  - __朝田詩乃__\n"
            "  # - __シロコ__\n"
            "\n"
            "朝田詩乃:\n"
            "  - slender body\n"
            "\n"
            "シロコ:\n"
            "  - athletic body\n",
        )

        registry, full_path_index = self._build_pipeline(cards_dir)

        # 初期状態: シロコはコメント化
        kd_scene = registry["シーンまとめ"][-1]
        assert kd_scene.values[1].is_commented is True

        # シロコのコメント解除
        from core.editor import toggle_comment, refresh_registry
        from core.tree_builder import build_tree

        ve_shiroko = kd_scene.values[1]
        result = toggle_comment(file_path, ve_shiroko, enable=True)
        assert result.success is True

        # レジストリとインデックスを更新
        refresh_registry(file_path, registry)
        refresh_full_path_index(file_path, registry, full_path_index, cards_dir)

        # 最新の key_def を取得してツリーを再構築
        kd_scene_new = registry["シーンまとめ"][-1]
        root_after = build_tree(kd_scene_new, registry, full_path_index)

        # 両方とも有効
        for child in root_after.children:
            assert child.value_entry is not None
            assert child.value_entry.is_commented is False

    def test_差分更新後のツリーでstaleなKeyDefinitionが使われない(
        self, tmp_path: Path
    ):
        """差分更新を行った場合、ツリー内の参照先ノードが
        新しい（stale でない）KeyDefinition を参照していることを検証する。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        file_target = _write_yaml(
            cards_dir / "target.yaml",
            "target_key:\n"
            "  - value1\n"
            "  - value2\n",
        )
        _write_yaml(
            cards_dir / "entry.yaml",
            "entry:\n"
            "  - __target_key__\n",
        )

        registry, full_path_index = self._build_pipeline(cards_dir)

        # 元の KeyDefinition を記録
        old_target_kd = registry["target_key"][-1]

        # target_key の値行をコメント化
        from core.editor import toggle_comment, refresh_registry
        from core.tree_builder import build_tree

        ve = old_target_kd.values[0]
        result = toggle_comment(file_target, ve, enable=False)
        assert result.success is True

        # レジストリとインデックスを更新
        refresh_registry(file_target, registry)
        refresh_full_path_index(
            file_target, registry, full_path_index, cards_dir
        )

        new_target_kd = registry["target_key"][-1]
        assert old_target_kd is not new_target_kd  # 新しいオブジェクト

        # entry からツリーを構築
        kd_entry = registry["entry"][-1]
        root = build_tree(kd_entry, registry, full_path_index)

        # entry → target_key の REF ノード
        assert len(root.children) >= 1
        ref_node = root.children[0]
        assert ref_node.node_type == NodeType.REF
        assert ref_node.display_name == "target_key"

        # REF ノードの key_def が新しい KeyDefinition を参照している
        assert ref_node.key_def is new_target_kd
        assert ref_node.key_def is not old_target_kd

        # 新しい KeyDefinition の値行の is_commented 状態が反映されている
        assert new_target_kd.values[0].is_commented is True

    def test_差分更新後のツリーで子ノードのis_commentedが正しい(
        self, tmp_path: Path
    ):
        """参照先キーの値行をコメント化した後、
        ツリーの子ノード（参照先の展開結果）の is_commented が正しいことを検証する。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        file_child = _write_yaml(
            cards_dir / "child.yaml",
            "child_key:\n"
            "  - leaf_a\n"
            "  - leaf_b\n",
        )
        _write_yaml(
            cards_dir / "parent.yaml",
            "parent_key:\n"
            "  - __child_key__\n",
        )

        registry, full_path_index = self._build_pipeline(cards_dir)

        from core.editor import toggle_comment, refresh_registry
        from core.tree_builder import build_tree

        # child_key の leaf_a をコメント化
        kd_child = registry["child_key"][-1]
        ve_leaf_a = kd_child.values[0]
        result = toggle_comment(file_child, ve_leaf_a, enable=False)
        assert result.success is True

        refresh_registry(file_child, registry)
        refresh_full_path_index(
            file_child, registry, full_path_index, cards_dir
        )

        # parent_key からツリーを構築
        kd_parent = registry["parent_key"][-1]
        root = build_tree(kd_parent, registry, full_path_index)

        # parent_key → child_key (REF) → [leaf_a (LITERAL), leaf_b (LITERAL)]
        ref_node = root.children[0]
        assert ref_node.node_type == NodeType.REF
        assert ref_node.display_name == "child_key"
        assert len(ref_node.children) == 2

        # leaf_a はコメント化されている
        leaf_a = ref_node.children[0]
        assert leaf_a.node_type == NodeType.LITERAL
        assert leaf_a.value_entry is not None
        assert leaf_a.value_entry.is_commented is True

        # leaf_b は有効のまま
        leaf_b = ref_node.children[1]
        assert leaf_b.node_type == NodeType.LITERAL
        assert leaf_b.value_entry is not None
        assert leaf_b.value_entry.is_commented is False

    def test_コメント切替の往復でツリーが元に戻る(self, tmp_path: Path):
        """コメント化 → コメント解除 の往復後、
        ツリーの is_commented 状態が元の状態に戻ることを検証する。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        file_path = _write_yaml(
            cards_dir / "test.yaml",
            "key1:\n"
            "  - __key2__\n"
            "\n"
            "key2:\n"
            "  - leaf\n",
        )

        registry, full_path_index = self._build_pipeline(cards_dir)

        from core.editor import toggle_comment, refresh_registry
        from core.tree_builder import build_tree

        # 初期ツリー
        kd1 = registry["key1"][-1]
        root_before = build_tree(kd1, registry, full_path_index)
        assert root_before.children[0].value_entry.is_commented is False

        # コメント化
        ve = registry["key1"][-1].values[0]
        toggle_comment(file_path, ve, enable=False)
        refresh_registry(file_path, registry)
        refresh_full_path_index(file_path, registry, full_path_index, cards_dir)

        kd1_after_comment = registry["key1"][-1]
        root_commented = build_tree(
            kd1_after_comment, registry, full_path_index
        )
        assert root_commented.children[0].value_entry.is_commented is True

        # コメント解除
        ve_commented = registry["key1"][-1].values[0]
        toggle_comment(file_path, ve_commented, enable=True)
        refresh_registry(file_path, registry)
        refresh_full_path_index(file_path, registry, full_path_index, cards_dir)

        kd1_after_uncomment = registry["key1"][-1]
        root_uncommented = build_tree(
            kd1_after_uncomment, registry, full_path_index
        )
        assert root_uncommented.children[0].value_entry.is_commented is False
