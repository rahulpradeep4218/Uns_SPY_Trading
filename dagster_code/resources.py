from logging import config
import yaml
from dagster import ConfigurableResource, resource
import mlflow

class TrainingConfig(ConfigurableResource):
    """
    Configuration for all training pipeline
    """

    config_path: str

    def load(self) -> dict:
        """
        Load the configuration details.
        """
        with open(self.config_path, 'r') as file:
            conf = yaml.safe_load(file)
            return conf
        return {}
    

class MLFlowResource(ConfigurableResource):
    """
    MLflow as a resource for tracking experiments.
    """
    experiment_name: str
    model_name: str
    experiment_id: str = None
    run_name: str = None
