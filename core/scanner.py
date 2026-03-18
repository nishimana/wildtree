"""ファイルスキャナ — cards ディレクトリ内の YAML ファイルを再帰的に検出する。

Stage 1 of the v2 パーサーパイプライン。
ファイルシステムとの対話のみを担当し、パースロジックは含まない。

用途:
  cards_dir を受け取り、その中の全 .yaml / .yml ファイルのパスリストを返す。
  返却されるリストはパスでソートされ、後続のレジストリ構築で
  安定した「後勝ち」動作を保証する。
"""

from __future__ import annotations

from pathlib import Path


def scan_yaml_files(cards_dir: Path) -> list[Path]:
    """cards ディレクトリ内の YAML ファイルを再帰的に検出する。

    .yaml と .yml の両方を対象とする。
    返却リストは Path のデフォルト順序でソートされ、
    レジストリ構築時の「後勝ち」動作が予測可能になる。

    Args:
        cards_dir: スキャン対象のルートディレクトリ。

    Returns:
        ソート済みの YAML ファイルパスリスト。
        ファイルが1つもない場合は空リスト。

    Raises:
        FileNotFoundError: cards_dir が存在しない場合。
        NotADirectoryError: cards_dir がディレクトリでない場合。
    """
    # 存在チェック
    if not cards_dir.exists():
        raise FileNotFoundError(f"ディレクトリが存在しません: {cards_dir}")

    # ディレクトリチェック
    if not cards_dir.is_dir():
        raise NotADirectoryError(f"ディレクトリではありません: {cards_dir}")

    # .yaml と .yml を再帰的に収集し、ソートして返す
    yaml_files: list[Path] = []
    for p in cards_dir.rglob("*"):
        if p.is_file() and p.suffix in (".yaml", ".yml"):
            yaml_files.append(p)

    return sorted(yaml_files)
