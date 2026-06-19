"""Shared command-line helpers for runnable examples."""

from __future__ import annotations

import argparse
from pathlib import Path


def example_parser(description: str, default_output: Path | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    if default_output is not None:
        parser.add_argument("--output", type=Path, default=default_output)
        parser.add_argument("--no-save", action="store_true")
    return parser


def should_save(args: argparse.Namespace) -> bool:
    return bool(
        hasattr(args, "output") and not args.no_save and args.frames is not None and args.frames > 0
    )


def save_once(args: argparse.Namespace, frame_count: int, save) -> None:
    if should_save(args) and frame_count == 0:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        save(str(args.output), overwrite=True)
