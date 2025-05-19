from dagster import Definitions, load_assets_from_modules
from .resources import IndicatorConfig

from . import assets

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    resources={"indicator_config": IndicatorConfig()} ,
)
