
import trading_functions.inference.inf_functions as inf_functions

conf = inf_functions.get_config()


max_period = inf_functions.get_maximum_period(conf)
print(f"Max period for inference: {max_period}")