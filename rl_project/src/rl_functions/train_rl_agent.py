from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from rl_functions.trading_env import TradingEnv
from rl_functions.utils import get_inf_config, get_observation_features
import datetime
from trading_functions.db.session import SessionLocal
from dotenv import load_dotenv
from pathlib import Path
import os

env_path = Path.cwd() / '.env'
print(f"env_path: {env_path}")
load_dotenv(dotenv_path=env_path, override=True)
print(os.getenv('POSTGRES_USER'))

inf_config = get_inf_config()
obs_features = get_observation_features(inf_config)


db = SessionLocal()


def main():
    print("Observation features:", obs_features)
    START_DATE = datetime.date(2025, 7, 18)
    END_DATE = datetime.date(2025, 8, 11)

    def make_env():
        return TradingEnv(db=db,
                          symbol='SPY',
                          start_date=START_DATE,
                          end_date=END_DATE,
                          initial_balance=10000,
                          trade_fee=0.5,
                          max_trade_loss_percent=2.0,
                          obs_features=obs_features,
                            price_multiplier=10
                          )   
    
    env = DummyVecEnv([make_env])
    env = VecNormalize(
            env, 
            norm_obs=True, 
            norm_reward=True, 
            clip_obs=10.0
        )
    
    model = PPO(
        policy='MlpPolicy',
        env=env,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=128,
        gamma=0.98,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,
        verbose=1,
    )

    model.learn(total_timesteps=50000)

    model.save("ppo_trading_agent")
    env.save("vec_normalize_trading_env.pkl")
    

if __name__ == "__main__":
    main()
    