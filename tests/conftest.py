"""Allow client/model tests without booting Home Assistant."""
import sys
import types
from pathlib import Path
pkg = types.ModuleType("mfb")
pkg.__path__ = [str(Path(__file__).parents[1] / "custom_components" / "myfoodbag")]
sys.modules["mfb"] = pkg
