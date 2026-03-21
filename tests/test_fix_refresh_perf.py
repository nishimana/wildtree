"""Fix: refresh_full_path_index の Path.resolve() ボトルネック修正 — テスト。

修正内容:
  - refresh_full_path_index() 内の kd.file_path.resolve() == target_path を
    kd.file_path == file_path に変更し、パフォーマンスを改善。

テスト対象:
  - refresh_full_path_index(file_path, registry, full_path_index, cards_dir) -> None

テスト命名規則: test_<対象>_<条件>_<期待結果>
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.models import (
    FullPathIndex,
    KeyDefinition,
    KeyRegistry,
    ValueEntry,
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


def _make_value_entry(
    raw_text: str,
    line_number: int = 2,
    is_commented: bool = False,
) -> ValueEntry:
    """テスト用 ValueEntry を生成するヘルパー。"""
    return ValueEntry(
        raw_text=raw_text,
        line_number=line_number,
        is_commented=is_commented,
        refs=[],
        literals=[],
    )


def _make_registry(*entries: tuple[str, KeyDefinition]) -> KeyRegistry:
    """テスト用 KeyRegistry を生成するヘルパー。

    同名キーは同じリストに追加される。
    """
    registry: KeyRegistry = {}
    for key_name, key_def in entries:
        registry.setdefault(key_name, []).append(key_def)
    return registry


# =========================================================================
# パス比較方式のテスト
# =========================================================================


class TestRefreshPathComparison:
    """refresh_full_path_index が Path.resolve() を使わずに
    Path == 比較で正しく動作することを確認するテスト。"""

    def test_refresh_同一Pathオブジェクトで一致する(self):
        """同一の Path オブジェクトをレジストリとファイルパス引数で使った場合、
        インデックスが正しく更新される。"""
        cards_dir = Path("C:/cards")
        shared_path = cards_dir / "test.yaml"

        kd_old = _make_key_def("keyA", shared_path, values=[
            _make_value_entry("old_value"),
        ])
        kd_new = _make_key_def("keyA", shared_path, values=[
            _make_value_entry("new_value"),
        ])

        registry = _make_registry(("keyA", kd_new))
        full_path_index: FullPathIndex = {"keyA": kd_old}

        # 同一の Path オブジェクトを引数に渡す
        refresh_full_path_index(shared_path, registry, full_path_index, cards_dir)

        assert full_path_index["keyA"] is kd_new

    def test_refresh_異なるPathオブジェクトで同じパスなら一致する(self):
        """異なる Path オブジェクトだが同じパス文字列を持つ場合、
        Path == 比較で一致しインデックスが正しく更新される。"""
        cards_dir = Path("C:/cards")

        # レジストリ内の KeyDefinition が保持する Path
        kd_path = Path("C:/cards/sub/test.yaml")
        # refresh_full_path_index に渡す Path（別オブジェクト）
        arg_path = Path("C:/cards/sub/test.yaml")

        # 異なるオブジェクトであることを確認
        assert kd_path is not arg_path
        # しかし等値であることを確認
        assert kd_path == arg_path

        kd_old = _make_key_def("keyA", kd_path, values=[
            _make_value_entry("old_value"),
        ])
        kd_new = _make_key_def("keyA", kd_path, values=[
            _make_value_entry("new_value"),
        ])

        registry = _make_registry(("keyA", kd_new))
        full_path_index: FullPathIndex = {"sub/keyA": kd_old}

        refresh_full_path_index(arg_path, registry, full_path_index, cards_dir)

        assert full_path_index["sub/keyA"] is kd_new

    def test_refresh_パスが異なればスキップされる(self):
        """レジストリ内の KeyDefinition のパスと引数のパスが異なる場合、
        その KeyDefinition は更新されない。"""
        cards_dir = Path("C:/cards")

        kd_other = _make_key_def(
            "keyB", cards_dir / "other.yaml", values=[
                _make_value_entry("other_value"),
            ]
        )
        kd_target_old = _make_key_def(
            "keyA", cards_dir / "target.yaml", values=[
                _make_value_entry("old_value"),
            ]
        )
        kd_target_new = _make_key_def(
            "keyA", cards_dir / "target.yaml", values=[
                _make_value_entry("new_value"),
            ]
        )

        registry = _make_registry(
            ("keyA", kd_target_new),
            ("keyB", kd_other),
        )
        full_path_index: FullPathIndex = {
            "keyA": kd_target_old,
            "keyB": kd_other,
        }

        refresh_full_path_index(
            cards_dir / "target.yaml", registry, full_path_index, cards_dir
        )

        # target.yaml のキーは更新される
        assert full_path_index["keyA"] is kd_target_new
        # other.yaml のキーは変更されない
        assert full_path_index["keyB"] is kd_other


# =========================================================================
# パフォーマンステスト
# =========================================================================


class TestRefreshPerformance:
    """refresh_full_path_index のパフォーマンステスト。

    Path.resolve() を使わない実装で、大量データでも高速に動作することを確認する。
    """

    def test_refresh_10000件のキー定義で0_1秒以内に完了する(self):
        """10,000 件のキー定義を含むレジストリに対して
        refresh_full_path_index が 0.1 秒以内に完了することを確認する。"""
        cards_dir = Path("C:/cards")
        target_file = cards_dir / "target.yaml"

        # 10,000 件のキー定義を生成
        # うち 10 件が target_file に属し、残りは別ファイル
        registry: KeyRegistry = {}
        full_path_index: FullPathIndex = {}

        # target_file のキー定義（10件）
        for i in range(10):
            name = f"target_key_{i}"
            kd = _make_key_def(name, target_file, line_number=i + 1, values=[
                _make_value_entry(f"value_{i}"),
            ])
            registry.setdefault(name, []).append(kd)
            full_path_index[name] = kd

        # 別ファイルのキー定義（9,990件）
        for i in range(9990):
            file_path = cards_dir / f"dir_{i % 100}" / f"file_{i}.yaml"
            name = f"other_key_{i}"
            kd = _make_key_def(name, file_path, line_number=1, values=[
                _make_value_entry(f"other_value_{i}"),
            ])
            registry.setdefault(name, []).append(kd)
            dir_name = f"dir_{i % 100}"
            full_path_index[f"{dir_name}/{name}"] = kd

        # パフォーマンス計測
        start = time.perf_counter()
        refresh_full_path_index(target_file, registry, full_path_index, cards_dir)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, (
            f"refresh_full_path_index が {elapsed:.3f} 秒かかった（上限: 0.1 秒）"
        )

    def test_refresh_大量データで結果が正しい(self):
        """パフォーマンステストと同じ大量データで、
        更新結果が正しいことも併せて確認する。"""
        cards_dir = Path("C:/cards")
        target_file = cards_dir / "target.yaml"

        registry: KeyRegistry = {}
        full_path_index: FullPathIndex = {}
        old_target_kds: dict[str, KeyDefinition] = {}
        other_kds: dict[str, KeyDefinition] = {}

        # target_file のキー定義（古いオブジェクト）をインデックスに設定
        for i in range(10):
            name = f"target_key_{i}"
            kd_old = _make_key_def(name, target_file, line_number=i + 1, values=[
                _make_value_entry(f"old_value_{i}"),
            ])
            old_target_kds[name] = kd_old
            full_path_index[name] = kd_old

        # target_file の新しいキー定義をレジストリに設定
        for i in range(10):
            name = f"target_key_{i}"
            kd_new = _make_key_def(name, target_file, line_number=i + 1, values=[
                _make_value_entry(f"new_value_{i}"),
            ])
            registry.setdefault(name, []).append(kd_new)

        # 別ファイルのキー定義
        for i in range(100):
            file_path = cards_dir / f"dir_{i}" / f"file_{i}.yaml"
            name = f"other_key_{i}"
            kd = _make_key_def(name, file_path, line_number=1, values=[
                _make_value_entry(f"other_value_{i}"),
            ])
            registry.setdefault(name, []).append(kd)
            fp = f"dir_{i}/{name}"
            full_path_index[fp] = kd
            other_kds[fp] = kd

        refresh_full_path_index(target_file, registry, full_path_index, cards_dir)

        # target_file のキーは新しいオブジェクトに更新されている
        for i in range(10):
            name = f"target_key_{i}"
            assert full_path_index[name] is not old_target_kds[name], (
                f"{name} が古いオブジェクトのまま"
            )
            assert full_path_index[name] is registry[name][-1], (
                f"{name} がレジストリの最新と一致しない"
            )

        # 別ファイルのキーは変更されていない
        for fp, kd in other_kds.items():
            assert full_path_index[fp] is kd, (
                f"{fp} が不正に変更された"
            )


# =========================================================================
# 回帰テスト — 修正後の基本動作
# =========================================================================


class TestRefreshRegression:
    """refresh_full_path_index 修正後の回帰テスト。

    Path.resolve() を Path == に変更しても、
    基本的な差分更新動作が正しく動作することを確認する。
    """

    def test_変更ファイルのキー定義のみが更新される(self):
        """refresh_full_path_index で変更対象ファイルのキー定義のみが
        新しいオブジェクトに差し替えられ、他は変更されない。"""
        cards_dir = Path("C:/cards")
        file_changed = cards_dir / "changed.yaml"
        file_unchanged = cards_dir / "unchanged.yaml"

        # 変更ファイルのキー定義
        kd_changed_old = _make_key_def(
            "changed_key", file_changed, values=[
                _make_value_entry("old_value"),
            ]
        )
        kd_changed_new = _make_key_def(
            "changed_key", file_changed, values=[
                _make_value_entry("new_value"),
            ]
        )

        # 変更されないファイルのキー定義
        kd_unchanged = _make_key_def(
            "unchanged_key", file_unchanged, values=[
                _make_value_entry("stable_value"),
            ]
        )

        registry = _make_registry(
            ("changed_key", kd_changed_new),
            ("unchanged_key", kd_unchanged),
        )
        full_path_index: FullPathIndex = {
            "changed_key": kd_changed_old,
            "unchanged_key": kd_unchanged,
        }

        refresh_full_path_index(
            file_changed, registry, full_path_index, cards_dir
        )

        # 変更ファイルのキーは新しいオブジェクトに更新
        assert full_path_index["changed_key"] is kd_changed_new
        assert full_path_index["changed_key"] is not kd_changed_old

        # 変更されないファイルのキーは同一オブジェクトのまま
        assert full_path_index["unchanged_key"] is kd_unchanged

    def test_サブディレクトリ内のファイルのキー定義が正しく更新される(self):
        """cards_dir のサブディレクトリにあるファイルのキー定義も
        正しく更新される。"""
        cards_dir = Path("C:/cards")
        file_sub = cards_dir / "SAO" / "character.yaml"

        kd_old = _make_key_def("char_key", file_sub, values=[
            _make_value_entry("old_char"),
        ])
        kd_new = _make_key_def("char_key", file_sub, values=[
            _make_value_entry("new_char"),
        ])

        registry = _make_registry(("char_key", kd_new))
        full_path_index: FullPathIndex = {"SAO/char_key": kd_old}

        refresh_full_path_index(
            file_sub, registry, full_path_index, cards_dir
        )

        assert full_path_index["SAO/char_key"] is kd_new

    def test_複数キーを含むファイルで全キーが更新される(self):
        """1つのファイルに複数のキー定義がある場合、
        全キーが新しいオブジェクトに更新される。"""
        cards_dir = Path("C:/cards")
        file_multi = cards_dir / "multi.yaml"

        kd_a_old = _make_key_def("keyA", file_multi, line_number=1, values=[
            _make_value_entry("old_a"),
        ])
        kd_b_old = _make_key_def("keyB", file_multi, line_number=5, values=[
            _make_value_entry("old_b"),
        ])
        kd_a_new = _make_key_def("keyA", file_multi, line_number=1, values=[
            _make_value_entry("new_a"),
        ])
        kd_b_new = _make_key_def("keyB", file_multi, line_number=5, values=[
            _make_value_entry("new_b"),
        ])

        # 他のファイルのキー
        kd_other = _make_key_def(
            "keyC", cards_dir / "other.yaml", values=[
                _make_value_entry("other_value"),
            ]
        )

        registry = _make_registry(
            ("keyA", kd_a_new),
            ("keyB", kd_b_new),
            ("keyC", kd_other),
        )
        full_path_index: FullPathIndex = {
            "keyA": kd_a_old,
            "keyB": kd_b_old,
            "keyC": kd_other,
        }

        refresh_full_path_index(
            file_multi, registry, full_path_index, cards_dir
        )

        # multi.yaml の全キーが更新
        assert full_path_index["keyA"] is kd_a_new
        assert full_path_index["keyB"] is kd_b_new
        # other.yaml のキーは不変
        assert full_path_index["keyC"] is kd_other

    def test_cards_dir外のファイルは何も更新しない(self):
        """cards_dir 外のファイルパスを指定した場合、
        インデックスは一切変更されない。"""
        cards_dir = Path("C:/cards")
        kd = _make_key_def("keyA", cards_dir / "test.yaml", values=[
            _make_value_entry("value"),
        ])
        registry = _make_registry(("keyA", kd))
        full_path_index: FullPathIndex = {"keyA": kd}

        # cards_dir 外のパスを指定
        refresh_full_path_index(
            Path("D:/other/test.yaml"), registry, full_path_index, cards_dir
        )

        # 元のオブジェクトのまま
        assert full_path_index["keyA"] is kd

    def test_実データに近いパイプラインで差分更新が正しい(self, tmp_path: Path):
        """スキャン → パース → build_full_path_index → refresh で
        一貫した結果が得られることを確認する統合テスト。"""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        file_a = cards_dir / "a.yaml"
        file_a.write_text(
            "keyA:\n"
            "  - value1\n"
            "  - value2\n",
            encoding="utf-8",
        )
        file_b = cards_dir / "b.yaml"
        file_b.write_text(
            "keyB:\n"
            "  - valueB\n",
            encoding="utf-8",
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

        old_kd_a = full_path_index["keyA"]
        old_kd_b = full_path_index["keyB"]

        # file_a を書き換え
        file_a.write_text(
            "keyA:\n"
            "  # - value1\n"
            "  - value2\n",
            encoding="utf-8",
        )

        from core.editor import refresh_registry
        refresh_registry(file_a, registry)
        refresh_full_path_index(file_a, registry, full_path_index, cards_dir)

        # keyA は新しいオブジェクト
        assert full_path_index["keyA"] is not old_kd_a
        assert full_path_index["keyA"] is registry["keyA"][-1]

        # keyB は不変
        assert full_path_index["keyB"] is old_kd_b

        # フル再構築と同じ結果
        expected = build_full_path_index(registry, cards_dir)
        assert set(full_path_index.keys()) == set(expected.keys())
        for fp in expected:
            assert full_path_index[fp] is expected[fp]
