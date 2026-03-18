"""Shared fixtures for WildTree tests.

Factory functions for generating test YAML data in temporary directories.
All YAML files are written with encoding="utf-8" explicitly (W1).
"""

from __future__ import annotations

from pathlib import Path

import pytest


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
              # - __cards/BA/CH_shiroko/シロコ__

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
            "  # - __cards/BA/CH_shiroko/シロコ__\n"
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
