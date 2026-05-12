
import os
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


MODEL_PATH = BASE_DIR / "models" / "Engineering Drawings"


PREPROCESSOR_CONFIG = MODEL_PATH / "preprocessor_config.json"
MODEL_CONFIG = MODEL_PATH / "config.json"


with open(PREPROCESSOR_CONFIG, "r") as f:
    PREPROCESSOR_CFG = json.load(f)


IMAGE_MEAN = PREPROCESSOR_CFG["image_mean"]
IMAGE_STD = PREPROCESSOR_CFG["image_std"]
RESCALE_FACTOR = PREPROCESSOR_CFG["rescale_factor"]
IMAGE_SIZE = PREPROCESSOR_CFG["size"]
DO_RESIZE = PREPROCESSOR_CFG["do_resize"]
DO_NORMALIZE = PREPROCESSOR_CFG["do_normalize"]
DO_RESCALE = PREPROCESSOR_CFG["do_rescale"]





OUTPUT_DIR = BASE_DIR / "outputs"
CROP_DIR = BASE_DIR / "cropped_regions"


OUTPUT_DIR.mkdir(exist_ok=True)
CROP_DIR.mkdir(exist_ok=True)
