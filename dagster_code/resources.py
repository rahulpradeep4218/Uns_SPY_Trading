import yaml
from dagster import ConfigurableResource
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
    tracking_uri: str
    experiment_name: str
    model_name: str
    run_name: str = None

    def get_experiment_id(self):
        mlflow.set_tracking_uri(self.tracking_uri)
        exp = mlflow.get_experiment_by_name(self.experiment_name)
        if exp is None:
            return mlflow.create_experiment(self.experiment_name)
        return exp.experiment_id