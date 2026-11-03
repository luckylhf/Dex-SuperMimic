"""All runtime locations can be overridden; importing this module has no side effects."""
import os
from pathlib import Path

ROOT = Path(os.environ.get('DEX_SUPERMIMIC_ROOT', Path.cwd())).expanduser().resolve()
ASSETS = Path(os.environ.get('DEX_ASSETS', ROOT / 'assets/dex_evt')).expanduser().resolve()
