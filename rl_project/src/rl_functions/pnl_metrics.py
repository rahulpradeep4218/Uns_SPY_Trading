import numpy as np

class PnLMetrics:
    def __init__(self, pnl_list, initial_balance, freq='1min'):
        """
        pnl_list: List of cumulative PnL (e.g., [0, 10, -5, 20...])
        initial_balance: Your starting account size (e.g., 10000)
        """
        self.initial_balance = float(initial_balance)
        self.pnl_list = np.array(pnl_list, dtype=float)
        
        # 1. Reconstruct Balance Curve
        # Balance_t = Initial + Cumulative_PnL_t
        self.balances = self.initial_balance + self.pnl_list
        
        # 2. Calculate Returns Safely
        if len(self.balances) < 2:
            self.returns = np.array([])
        else:
            # Change in PnL between steps
            pnl_diffs = np.diff(self.pnl_list) 
            # The capital at the START of each interval
            starting_capitals = self.balances[:-1]
            
            # Safe division to get percentage returns
            self.returns = np.divide(
                pnl_diffs, 
                starting_capitals, 
                out=np.zeros_like(pnl_diffs), 
                where=starting_capitals != 0
            )
            
            # If the account was blown (starting_capital was 0), return is -100%
            self.returns[starting_capitals <= 0] = -1.0

        # Annualization Factors
        factors = {
            '1min': 98280, '1hour': 1638, 'daily': 252, 'crypto_1min': 525600
        }
        self.ann_factor = np.sqrt(factors.get(freq, 252))

    def calculate_sharpe(self, risk_free_rate=0.0):
        if len(self.returns) < 2 or np.std(self.returns) == 0:
            return 0.0
        # Adjust risk_free_rate if it's an annual rate (e.g., 0.04 / factors['1min'])
        excess = self.returns - risk_free_rate
        return self.ann_factor * (np.mean(excess) / np.std(self.returns))

    def calculate_sortino(self, target_return=0.0):
        if len(self.returns) < 2:
            return 0.0
        excess = self.returns - target_return
        downside_diff = excess[excess < 0]
        if len(downside_diff) == 0: return np.inf
        
        downside_dev = np.sqrt(np.sum(downside_diff**2) / len(self.returns))
        return self.ann_factor * (np.mean(excess) / downside_dev) if downside_dev > 0 else 0.0

    def calculate_max_drawdown(self):
        """Calculates Max DD based on the reconstructed balance."""
        if len(self.balances) < 1: return 0.0
        cumulative_max = np.maximum.accumulate(self.balances)
        # Avoid division by zero
        safe_max = np.where(cumulative_max <= 0, 1e-9, cumulative_max)
        drawdowns = (self.balances - safe_max) / safe_max
        return np.min(drawdowns)

# --- Example Usage ---
# You started with $10,000. 
# Your PnL after 4 minutes was: $0, then +$100, then +$50, then +$200
# pnl_history = [0, 100, 50, 200] 
# metrics = PnLMetrics(pnl_history, initial_balance=10000, freq='1min')

# print(f"Annualized Sharpe: {metrics.calculate_sharpe():.4f}")
# print(f"Max Drawdown: {metrics.calculate_max_drawdown()*100:.2f}%")