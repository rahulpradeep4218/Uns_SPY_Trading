from dagster import Definitions, load_assets_from_modules
from .resources import TrainingConfig, MLFlowResource

from . import assets

all_assets = load_assets_from_modules([assets])
config_path = "../Config/training.yaml"
training_config = TrainingConfig(config_path=config_path).load()
defs = Definitions(
    assets=all_assets,
    resources={"training_config": TrainingConfig(config_path="../Config/training.yaml"),
               "mlflow_resource": MLFlowResource(
                     tracking_uri=training_config['mlflow']['tracking_uri'],
                     experiment_name=training_config['mlflow']['experiment_name']
               )
               } 
)
