"""Terminal judging: show a pair blind and read one arrow keypress."""

from __future__ import annotations

import os
import sys
import termios
import tty
from collections.abc import Callable

from evals.models import Side
from evals.pairs import Pair, render_pair

_ARROWS = {b"\x1b[D": "left", b"\x1b[C": "right", b"\x1b[A": "up", b"\x1b[B": "down"}
_CHOICES = {"left": "first", "right": "second", "up": "tie", "down": "tie", "q": "quit"}
_KEYS_HELP = "← first better   → second better   ↑/↓ tie   q quit"


def read_key() -> str:
    """Reads one keypress: 'left' / 'right' / 'up' / 'down' for arrows, else the character."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        data = os.read(fd, 3)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return _ARROWS.get(data, data.decode(errors="ignore"))


def ask_human(pair: Pair, first: Side, title: str, read_key: Callable[[], str]) -> str:
    """Shows the pair blind and returns 'first', 'second', 'tie', or 'quit' from one keypress."""
    print()
    print(f"=== {title}")
    print(render_pair(pair, first))
    print()
    print(_KEYS_HELP)
    while (choice := _CHOICES.get(read_key())) is None:
        pass
    return choice
