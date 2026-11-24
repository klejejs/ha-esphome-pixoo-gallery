"""Load the converter on its own, without Home Assistant."""

import importlib.util
import sys
from pathlib import Path

PATH = Path(__file__).parents[1] / "custom_components" / "esphome_pixoo_gallery" / "convert.py"
spec = importlib.util.spec_from_file_location("pixoo_convert", PATH)
module = importlib.util.module_from_spec(spec)
sys.modules["pixoo_convert"] = module
spec.loader.exec_module(module)
