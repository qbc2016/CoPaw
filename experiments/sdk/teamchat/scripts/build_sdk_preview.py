# -*- coding: utf-8 -*-
"""Build the SDK core candidate without editing the release manifest."""

import argparse
from pathlib import Path
import shutil


def build(destination):
    source = Path(__file__).resolve().parents[1]
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("sdk_entry.py", "sdk_agents.py", "roundtable.py", "LICENSE"):
        shutil.copyfile(source / name, destination / name)
    shutil.copyfile(source / "sdk-preview.json", destination / "plugin.json")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    build(parser.parse_args().destination)
