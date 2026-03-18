"""Shared fixtures for WildTree tests.

Factory functions for generating test YAML data in temporary directories.
All YAML files are written with encoding="utf-8" explicitly (W1).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# QApplication fixture (session scope, offscreen)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Create a single QApplication instance for the entire test session.

    Uses QT_QPA_PLATFORM=offscreen to avoid window display.
    Returns the existing instance if one has already been created.
    """
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(["wildtree-test"])
    return app


# ---------------------------------------------------------------------------
# GUI window fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def wildtree_main_window(qapp):
    """Create a MainWindow instance without loading a cards directory.

    Requires the qapp fixture for QApplication initialization.
    The window is created with no cards_dir (initial empty state).
    """
    from gui.main_window import MainWindow

    window = MainWindow(cards_dir=None)
    yield window
    window.close()


@pytest.fixture()
def wildtree_main_window_with_data(qapp, simple_cards_dir: Path):
    """Create a MainWindow instance loaded with the simple_cards_dir data.

    Provides a window with a resolver and tree already populated.
    """
    from gui.main_window import MainWindow

    window = MainWindow(cards_dir=simple_cards_dir)
    yield window
    window.close()


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, content: str) -> Path:
    """Write a YAML file with explicit UTF-8 encoding.

    Args:
        path: Destination file path.
        content: YAML content string.

    Returns:
        The written file path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Factory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def yaml_factory(tmp_path: Path):
    """Factory function to create YAML files in tmp_path.

    Usage::

        def test_something(yaml_factory):
            path = yaml_factory("sub/dir/file.yaml", '''
                key1:
                  - value1
                  - value2
            ''')
    """

    def _factory(relative_path: str, content: str) -> Path:
        full_path = tmp_path / relative_path
        return _write_yaml(full_path, content)

    return _factory


@pytest.fixture()
def simple_cards_dir(tmp_path: Path) -> Path:
    """A minimal cards directory with a single YAML file.

    Structure::

        cards/
          simple.yaml
            greeting:
              - hello
              - __farewell__

            farewell:
              - goodbye
    """
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    _write_yaml(
        cards_dir / "simple.yaml",
        (
            "greeting:\n"
            "  - hello\n"
            "  - __farewell__\n"
            "\n"
            "farewell:\n"
            "  - goodbye\n"
        ),
    )
    return cards_dir


@pytest.fixture()
def multi_file_cards_dir(tmp_path: Path) -> Path:
    """A cards directory with multiple files and subdirectories.

    Structure::

        cards/
          main.yaml
            メイン:
              - __シーンまとめ__
              - __デフォルト__

          SAO/
            CH_asada/
              asada.yaml
                朝田詩乃:
                  - __朝田詩乃体格__
                  - __朝田詩乃髪型__

                朝田詩乃体格:
                  - slender body
                  - __cards/SAO/options/エイジスライダー__

            options/
              options.yaml
                エイジスライダー:
                  - age slider -0.5

          BA/
            CH_shiroko/
              shiroko.yaml
                シロコ:
                  - __シロコ体格__

                シロコ体格:
                  - athletic body

          scenes.yaml
            シーンまとめ:
              - __cards/SAO/CH_asada/朝田詩乃__
              - __cards/BA/CH_shiroko/シロコ__

            デフォルト:
              - default lighting
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
        cards_dir / "SAO" / "CH_asada" / "asada.yaml",
        (
            "朝田詩乃:\n"
            "  - __朝田詩乃体格__\n"
            "  - __朝田詩乃髪型__\n"
            "\n"
            "朝田詩乃体格:\n"
            "  - slender body\n"
            "  - __cards/SAO/options/エイジスライダー__\n"
        ),
    )

    _write_yaml(
        cards_dir / "SAO" / "options" / "options.yaml",
        (
            "エイジスライダー:\n"
            "  - age slider -0.5\n"
        ),
    )

    _write_yaml(
        cards_dir / "BA" / "CH_shiroko" / "shiroko.yaml",
        (
            "シロコ:\n"
            "  - __シロコ体格__\n"
            "\n"
            "シロコ体格:\n"
            "  - athletic body\n"
        ),
    )

    _write_yaml(
        cards_dir / "scenes.yaml",
        (
            "シーンまとめ:\n"
            "  - __cards/SAO/CH_asada/朝田詩乃__\n"
            "  - __cards/BA/CH_shiroko/シロコ__\n"
            "\n"
            "デフォルト:\n"
            "  - default lighting\n"
        ),
    )

    return cards_dir


@pytest.fixture()
def circular_ref_cards_dir(tmp_path: Path) -> Path:
    """A cards directory containing circular references.

    Structure::

        cards/
          circular.yaml
            alpha:
              - __beta__

            beta:
              - __alpha__
    """
    cards_dir = tmp_path / "cards"
    _write_yaml(
        cards_dir / "circular.yaml",
        (
            "alpha:\n"
            "  - __beta__\n"
            "\n"
            "beta:\n"
            "  - __alpha__\n"
        ),
    )
    return cards_dir


@pytest.fixture()
def duplicate_key_cards_dir(tmp_path: Path) -> Path:
    """A cards directory with the same key name in multiple files.

    The key 'common_style' appears in both file_a.yaml and file_b.yaml.
    Since files are sorted by path, file_a.yaml is scanned first,
    and file_b.yaml wins for short-form resolution (last-wins).

    Structure::

        cards/
          file_a.yaml
            common_style:
              - style from file A

          file_b.yaml
            common_style:
              - style from file B

          user.yaml
            user:
              - __common_style__
    """
    cards_dir = tmp_path / "cards"

    _write_yaml(
        cards_dir / "file_a.yaml",
        (
            "common_style:\n"
            "  - style from file A\n"
        ),
    )

    _write_yaml(
        cards_dir / "file_b.yaml",
        (
            "common_style:\n"
            "  - style from file B\n"
        ),
    )

    _write_yaml(
        cards_dir / "user.yaml",
        (
            "user:\n"
            "  - __common_style__\n"
        ),
    )

    return cards_dir


@pytest.fixture()
def nested_ref_cards_dir(tmp_path: Path) -> Path:
    """A cards directory with nested (brace) references.

    Structure::

        cards/
          nested.yaml
            season:
              - spring
              - winter

            character:
              - asada

            scene:
              - __{__season__}_{__character__}__
    """
    cards_dir = tmp_path / "cards"
    _write_yaml(
        cards_dir / "nested.yaml",
        (
            "season:\n"
            "  - spring\n"
            "  - winter\n"
            "\n"
            "character:\n"
            "  - asada\n"
            "\n"
            "scene:\n"
            "  - __{__season__}_{__character__}__\n"
        ),
    )
    return cards_dir


@pytest.fixture()
def diamond_ref_cards_dir(tmp_path: Path) -> Path:
    """A cards directory where the same key appears in multiple branches.

    This is NOT circular -- 'shared' appears under both 'branch_a' and
    'branch_b', but there is no cycle.

    Structure::

        cards/
          diamond.yaml
            root:
              - __branch_a__
              - __branch_b__

            branch_a:
              - __shared__

            branch_b:
              - __shared__

            shared:
              - leaf value
    """
    cards_dir = tmp_path / "cards"
    _write_yaml(
        cards_dir / "diamond.yaml",
        (
            "root:\n"
            "  - __branch_a__\n"
            "  - __branch_b__\n"
            "\n"
            "branch_a:\n"
            "  - __shared__\n"
            "\n"
            "branch_b:\n"
            "  - __shared__\n"
            "\n"
            "shared:\n"
            "  - leaf value\n"
        ),
    )
    return cards_dir


# ---------------------------------------------------------------------------
# コメントアウト参照テスト用フィクスチャ
# ---------------------------------------------------------------------------


@pytest.fixture()
def commented_ref_cards_dir(tmp_path: Path) -> Path:
    """コメントアウトされた参照を含むカードディレクトリ。

    ``シーンまとめ`` は2つの参照を持つが、シロコへの参照は
    コメントアウトされているためスキップされるべき。

    Structure::

        cards/
          scenes.yaml
            シーンまとめ:
              - __朝田詩乃__
              # - __シロコ__  <- コメントアウト

            朝田詩乃:
              - slender body

            シロコ:
              - athletic body
    """
    cards_dir = tmp_path / "cards"

    _write_yaml(
        cards_dir / "scenes.yaml",
        (
            "シーンまとめ:\n"
            "  - __朝田詩乃__\n"
            "  # - __シロコ__\n"
            "\n"
            "朝田詩乃:\n"
            "  - slender body\n"
            "\n"
            "シロコ:\n"
            "  - athletic body\n"
        ),
    )

    return cards_dir


# ---------------------------------------------------------------------------
# W2: Broken (unresolved) reference fixtures
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# W3: Search feature fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def wildtree_main_window_with_multi_data(qapp, multi_file_cards_dir: Path):
    """Create a MainWindow instance loaded with the multi_file_cards_dir data.

    Provides a window with a resolver and tree already populated.
    Useful for search tests that need multiple nodes to match against.

    The multi_file_cards_dir contains keys:
        メイン, シーンまとめ, デフォルト,
        朝田詩乃, 朝田詩乃体格, 朝田詩乃髪型,
        エイジスライダー, シロコ, シロコ体格
    """
    from gui.main_window import MainWindow

    window = MainWindow(cards_dir=multi_file_cards_dir)
    yield window
    window.close()


@pytest.fixture()
def broken_ref_cards_dir(tmp_path: Path) -> Path:
    """A cards directory containing broken (unresolved) references.

    ``entry`` has two references: ``existing_key`` (resolvable) and
    ``non_existent_key`` (unresolvable / broken).

    Structure::

        cards/
          test.yaml
            entry:
              - __existing_key__
              - __non_existent_key__

            existing_key:
              - leaf value
    """
    cards_dir = tmp_path / "cards"
    _write_yaml(
        cards_dir / "test.yaml",
        (
            "entry:\n"
            "  - __existing_key__\n"
            "  - __non_existent_key__\n"
            "\n"
            "existing_key:\n"
            "  - leaf value\n"
        ),
    )
    return cards_dir


@pytest.fixture()
def broken_ref_fullpath_cards_dir(tmp_path: Path) -> Path:
    """A cards directory with a broken full-path reference.

    ``entry`` references ``__cards/SAO/CH_asada/unknown_key__`` which
    cannot be resolved. The display name should be ``unknown_key``
    (last segment after slash).

    Structure::

        cards/
          test.yaml
            entry:
              - __cards/SAO/CH_asada/unknown_key__
    """
    cards_dir = tmp_path / "cards"
    _write_yaml(
        cards_dir / "test.yaml",
        (
            "entry:\n"
            "  - __cards/SAO/CH_asada/unknown_key__\n"
        ),
    )
    return cards_dir


@pytest.fixture()
def all_broken_ref_cards_dir(tmp_path: Path) -> Path:
    """A cards directory where all references are broken.

    ``entry`` has two references, both pointing to non-existent keys.

    Structure::

        cards/
          test.yaml
            entry:
              - __broken_ref_1__
              - __broken_ref_2__
    """
    cards_dir = tmp_path / "cards"
    _write_yaml(
        cards_dir / "test.yaml",
        (
            "entry:\n"
            "  - __broken_ref_1__\n"
            "  - __broken_ref_2__\n"
        ),
    )
    return cards_dir


@pytest.fixture()
def broken_and_circular_cards_dir(tmp_path: Path) -> Path:
    """A cards directory with both broken and circular references.

    ``parent`` references ``child_circular`` (which references back
    to ``parent``, creating a cycle) and ``broken_ref`` (non-existent).

    Structure::

        cards/
          test.yaml
            parent:
              - __child_circular__
              - __broken_ref__

            child_circular:
              - __parent__
    """
    cards_dir = tmp_path / "cards"
    _write_yaml(
        cards_dir / "test.yaml",
        (
            "parent:\n"
            "  - __child_circular__\n"
            "  - __broken_ref__\n"
            "\n"
            "child_circular:\n"
            "  - __parent__\n"
        ),
    )
    return cards_dir
