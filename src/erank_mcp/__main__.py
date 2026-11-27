"""Entry point: python -m erank_mcp"""

from __future__ import annotations


def main() -> None:
    from erank_mcp.server import run

    run()


if __name__ == "__main__":
    main()
