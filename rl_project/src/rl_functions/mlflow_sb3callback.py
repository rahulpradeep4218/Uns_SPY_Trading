import os
import mlflow
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import VecNormalize
from sqlalchemy.orm import Session
from rl_functions.pnl_metrics import PnLMetrics

class EmptyPyfunc(mlflow.pyfunc.PythonModel):
    pass

class MLflowRLCallback(BaseCallback):
    def __init__(self, 
                 run_id: str,
                 artifact_subdir: str,
                 model_name: str,
                 db: Session,
                 config: dict,
                 eval_num: int = 1,
                 dagster_logger=None,
                 verbose=0):
        super().__init__(verbose)

        self.run_id = run_id
        self.checkpoint_freq = config['rl']['checkpoint_freq']
        self.episode_metrics_freq = config['rl']['episode_metrics_freq']
        self.artifact_subdir = artifact_subdir
        self.model_name = model_name
        self.db = db
        self.config = config
        self.dagster_logger = dagster_logger
        self.eval_num = eval_num
        self.pnl_list = [0.0]

    def _on_step(self) -> bool:
        dones = self.locals.get("dones")
        infos = self.locals.get("infos")

        info = infos[0]
        episode_id = info['episode_id']
        self.pnl_list.append(info['total_pnl'])

        # Example: log custom metrics from env
        if hasattr(self.training_env, "get_attr"):
            pass
        # Log episode metrics at specified frequency
        if dones is not None and infos is not None:

            if episode_id % self.episode_metrics_freq == 0:
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
                    mlflow.log_metric(
                        "episodes",
                        episode_id,
                        step=self.num_timesteps
                    )

                    pnl_metrics = PnLMetrics(
                        pnl_list=self.pnl_list,
                        initial_balance=self.config['rl']['initial_balance'],
                    )
                    mlflow.log_metric(
                        "sharpe_ratio",
                        pnl_metrics.calculate_sharpe(),
                        step=self.num_timesteps
                    )
                    mlflow.log_metric(
                        "sortino_ratio",
                        pnl_metrics.calculate_sortino(),
                        step=self.num_timesteps
                    )
            
            if dones[0]:
                self.pnl_list = [0.0]  # Reset PnL list for next episode
        

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

        ## Cycle value of ent coeff
        cycle_steps = self.config['rl']['cyclic_entropy_update_freq']
        cycle_pos = self.num_timesteps % cycle_steps

        #Sawtooth logic to update ent coeff so only spike at 0.04
        fraction = cycle_pos / cycle_steps
        new_ent_coeff = 0.04 - (0.03 * fraction)  # Linearly decrease from 0.04 to 0.01

        #Update ent coeff in the model's policy
        self.model.ent_coeff = max(new_ent_coeff, 0.01)  # Ensure it doesn't go below 0.01
        return True
    
    def _run_evaluation(self, vec_path):

        from rl_functions.utils import get_env
        # Recreate fresh eval env
        eval_env = get_env(
            config=self.config,
            db=self.db,
            eval_mode=True,
            dagster_logger=self.dagster_logger
        )

        # Load normalization stats from this checkpoint
        eval_env = VecNormalize.load(vec_path, eval_env)

        # Freeze normalization
        eval_env.training = False
        eval_env.norm_reward = False

        obs = eval_env.reset()
        done = False
        self.dagster_logger.info(f"Starting evaluation for checkpoint at timestep {self.num_timesteps} with model {self.model_name}")

        total_reward = 0
        eval_pnl_list = [0.0]
        while not done:
            action, _ = self.model.predict(obs, deterministic=True)
            obs, reward, dones, infos = eval_env.step(action)
            done = dones[0]
            total_reward += reward[0]
            info = infos[0]
            eval_pnl_list.append(info['total_pnl'])
        info = infos[0]
        eval_pnl_metrics = PnLMetrics(
            pnl_list=eval_pnl_list,
            initial_balance=self.config['rl']['initial_balance'],
        )

        mlflow.log_metric(
            "eval_sharpe_ratio",
            eval_pnl_metrics.calculate_sharpe(),
            step=self.eval_num
        )

        mlflow.log_metric(
            "eval_sortino_ratio",
            eval_pnl_metrics.calculate_sortino(),
            step=self.eval_num
        )

        mlflow.log_metric(
            "eval_total_trades_number",
            info.get("no_trades_completed"),
            step=self.eval_num
        )
        mlflow.log_metric(
            "eval_ending_balance",
            info.get("Balance"),
            step=self.eval_num
        )
        mlflow.log_metric(
            "eval_avg_trade_duration",
            info.get("avg_trade_duration"),
            step=self.eval_num
        )
        mlflow.log_metric(
            "eval_total_pnl",
            info.get("total_pnl"),
            step=self.eval_num
        )
        mlflow.log_metric(
            "eval_max_drawdown_percent",
            info.get("max_drawdown_percent"),
            step=self.eval_num
        )
        self.eval_num += 1
        # return {
        #     "eval_total_trades_number": info.get("no_trades_completed"),
        #     "eval_ending_balance": info.get("Balance"),
        #     "eval_avg_trade_duration": info.get("avg_trade_duration"),
        #     "eval_total_pnl": info.get("total_pnl"),
        #     "eval_max_drawdown_percent": info.get("max_drawdown_percent"),
        # }

    def _get_model_and_vec_paths(self):
        checkpoint_folder = f"{self.artifact_subdir}/checkpoint_{self.num_timesteps}"
        os.makedirs(checkpoint_folder, exist_ok=True)

        model_path = os.path.join(checkpoint_folder, "model.zip")
        vec_path = os.path.join(checkpoint_folder, "vec_normalize.pkl")
        return model_path, vec_path

    def _log_checkpoint(self):

        model_path, vec_path = self._get_model_and_vec_paths()

        vec_normalize_env = self.model.get_vec_normalize_env()
        if vec_normalize_env is not None:
            vec_normalize_env.save(vec_path)
        else:
            raise ValueError("VecNormalize environment not found. Cannot save normalization stats.")

        # Save model + vecnormalize
        self.model.save(model_path)
        # self.training_env.save(vec_path)

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

        if self.dagster_logger:
            self.dagster_logger.info(f"Logged checkpoint at timestep {self.num_timesteps} to MLflow with model path: {model_path} and vec_normalize path: {vec_path}")
