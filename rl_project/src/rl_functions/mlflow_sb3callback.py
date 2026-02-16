import os
import mlflow
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import VecNormalize
from sqlalchemy.orm import Session
from rl_functions.utils import get_env


class EmptyPyfunc(mlflow.pyfunc.PythonModel):
    pass

class MLflowRLCallback(BaseCallback):
    def __init__(self, 
                 run_id: str,
                 artifact_subdir: str,
                 model_name: str,
                 db: Session,
                 config: dict,
                 verbose=0):
        super().__init__(verbose)
        self.run_id = run_id
        self.checkpoint_freq = config['rl']['checkpoint_freq']
        self.episode_metrics_freq = config['rl']['episode_metrics_freq']
        self.artifact_subdir = artifact_subdir
        self.model_name = model_name
        self.db = db
        self.config = config

    def _on_step(self) -> bool:
        dones = self.locals.get("dones")
        infos = self.locals.get("infos")

        info = infos[0]
        episode_id = info['episode_id']

        # Example: log custom metrics from env
        if hasattr(self.training_env, "get_attr"):
            pass
        
        # Log episode metrics at specified frequency
        if dones is not None and infos is not None and episode_id % self.episode_metrics_freq == 0:

            if dones[0]:
                
                mlflow.log_metric(
                    "ending_balance",
                    info['total_pnl'],
                    step=self.num_timesteps
                )
                mlflow.log_metric(
                    "max_drawdown_percent",
                    info['max_drawdown_percent'],
                    step=self.num_timesteps
                )
                mlflow.log_metric(
                    "no_trades_completed",
                    info['no_trades_completed'],
                    step=self.num_timesteps
                )
                mlflow.log_metric(
                    "avg_trade_duration",
                    info['avg_trade_duration'],
                    step=self.num_timesteps
                )
        # Checkpoint saving
        if self.num_timesteps % self.checkpoint_freq == 0:
            # Log total timesteps
            mlflow.log_metric(
                "timestep",
                self.num_timesteps,
                step=self.num_timesteps
            )
            self._log_checkpoint()
            _, vec_path = self._get_model_and_vec_paths()
            self._run_evaluation(vec_path=vec_path)

        return True
    
    def _run_evaluation(self, vec_path):

        # Recreate fresh eval env
        eval_env = get_env(
            config=self.config,
            db=self.db,
            eval_mode=True
        )

        # Load normalization stats from this checkpoint
        eval_env = VecNormalize.load(vec_path, eval_env)

        # Freeze normalization
        eval_env.training = False
        eval_env.norm_reward = False

        obs = eval_env.reset()
        done = False

        total_reward = 0

        while not done:
            action, _ = self.model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = eval_env.step(action)
            done = terminated or truncated
            total_reward += reward

        return {
            "eval_total_trades_number": info.get("no_trades_completed"),
            "eval_ending_balance": info.get("Balance"),
            "eval_avg_trade_duration": info.get("avg_trade_duration"),
            "eval_total_pnl": info.get("total_pnl"),
            "eval_max_drawdown_percent": info.get("max_drawdown_percent"),
        }

    def _get_model_and_vec_paths(self):
        checkpoint_folder = f"{self.artifact_subdir}/checkpoint_{self.num_timesteps}"
        os.makedirs(checkpoint_folder, exist_ok=True)

        model_path = os.path.join(checkpoint_folder, "model.zip")
        vec_path = os.path.join(checkpoint_folder, "vec_normalize.pkl")
        return model_path, vec_path

    def _log_checkpoint(self):

        model_path, vec_path = self._get_model_and_vec_paths()

        # Save model + vecnormalize
        self.model.save(model_path)
        self.training_env.save(vec_path)

        # Log folder as artifact
        # mlflow.log_artifacts(checkpoint_folder, artifact_path=checkpoint_folder)

        mlflow.pyfunc.log_model(
            artifact_path=f"checkpoint_{self.num_timesteps}",
            artifacts={
                "model": model_path,
                "vec_normalize": vec_path
            },
            python_model=EmptyPyfunc(),
        )

        # Store last timestep as tag
        mlflow.set_tag("last_checkpoint_step", self.num_timesteps)

        print(f"Checkpoint saved at {self.num_timesteps}")
