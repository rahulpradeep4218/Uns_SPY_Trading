from pdb import run
from webbrowser import get
from matplotlib.pyplot import sca
from sklearn import base
import mlflow
import optuna
import numpy as np
import os
import pickle
import json
import xgboost as xgb
from sklearn.model_selection import train_test_split
from pathlib import Path
from functions.indicators import add_all_indicators
from functions.transform import normalize_timegaps
from functions.utility import (
    get_columns_mapping,
    save_df_parquet_link,
    get_first_directory
)
import xgboost as xgb
from sklearn.preprocessing import MinMaxScaler, StandardScaler, RobustScaler
                               
from dagster import MetadataValue


type_dict = {
    'int': int,
    'float': float,
    'str': str,
    'bool': bool
}

def quick_save_parquet_link(df, config, context, filename, model_metadata=None):
    run_id = context.run_id
    parq_filename = f"{filename}.parquet"
    parq_link = save_df_parquet_link(
        df=df,
        config=config,
        run_id=run_id,
        filename=parq_filename,
        model_metadata=model_metadata
    )
    return parq_link

def get_filtered_data(df, start_date_str, end_date_str):
    start_date = pd.to_datetime(start_date_str)
    end_date = pd.to_datetime(end_date_str)
    filtered_data = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]
    filtered_data = filtered_data.reset_index(drop=True)
    return filtered_data

def normalize_timegaps_transform(df, config):
    cfg = config['common_config']
    time_gap_threshold = cfg['normalize_timegap_threshold']
    # Normalize time gaps
    normalized_data = normalize_timegaps(df, time_gap_threshold)
    return normalized_data


def add_indicators(df, config):
    cfg = config['indicators']
    selected_indicators = cfg['selected'].split(",")
    ma_periods = [int(maperiod[3:]) for maperiod in selected_indicators if maperiod.startswith('ma_')]
    ema_periods = [int(maperiod[4:]) for maperiod in selected_indicators if maperiod.startswith('ema_')]
    cfg_parameters = cfg['parameters']
    # Add all indicators to the data
    func_list = []
    if len(ma_periods) > 0:
        func_list.append(cfg['functions']['ma'])
        cfg_parameters['ma_periods'] = ma_periods
    if len(ema_periods) > 0:
        func_list.append(cfg['functions']['ema'])
        cfg_parameters['ema_periods'] = ema_periods
    rest_functions = [cfg['functions'][indicator] for indicator in selected_indicators if not indicator.startswith(('ma_', 'ema_')) ]
    func_list.extend(rest_functions)
    data_with_indicators = add_all_indicators(df, config=cfg_parameters, func_list=func_list)
    return data_with_indicators, selected_indicators

def close_diff_transform(df, config):
    cfg = config['common_config']
    close_diff_features = cfg['close_transform_columns'].split(',')
    # Transform the 'Close' column
    df[close_diff_features] = df[close_diff_features].sub(df['Close'], axis=0).div(df['Close'], axis=0)
    return df, close_diff_features

def scale_features(df, config, context, model_metadata, train_or_test='train', scaler_path = ''):
    scale_cfg = config['scaling']
    
    first_directory = get_first_directory(config, model_metadata)
    
    scaled_data = df.copy()

    minmax_features = scale_cfg['minmax']['columns'].split(',')
    standard_features = scale_cfg['standard']['columns'].split(',')
    robust_features = scale_cfg['robust']['columns'].split(',')
    minmax_scaler = MinMaxScaler()
    standard_scaler = StandardScaler()
    robust_scaler = RobustScaler()

    if train_or_test == 'train':
        #minmax scaling
        context.log.info(f"Applying Fit Transform Min-Max scaling to features: {minmax_features}")
        if len(minmax_features) > 0:
            scaled_data[minmax_features] = minmax_scaler.fit_transform(scaled_data[minmax_features])
        else:
            minmax_scaler = None

        #Standard scaling
        context.log.info(f"Applying Fit Transform Standard scaling to features: {standard_features}")
        if len(standard_features) > 0:
            scaled_data[standard_features] = standard_scaler.fit_transform(scaled_data[standard_features])
        else:
            standard_scaler = None
        
        #Robust Scaling
        context.log.info(f"Applying Fit Transform Robust scaling to features: {robust_features}")
        if len(robust_features) > 0:
            scaled_data[robust_features] = robust_scaler.fit_transform(scaled_data[robust_features])
        else:
            robust_scaler = None

        #Save scalers to model directory
        scalers = {
            'minmax': minmax_scaler,
            'standard': standard_scaler,
            'robust': robust_scaler
        }
        runs_folder = config['training_details']['runs_folder']
        scaler_file_path = os.path.join(f"../{runs_folder}", f'{first_directory}', "scalers.pkl")
        os.makedirs(os.path.dirname(scaler_file_path), exist_ok=True)
        with open(scaler_file_path, 'wb') as f:
            pickle.dump(scalers, f)
        context.log.info(f"Scalers saved to {scaler_file_path}")
    else:
        if scaler_path == '':
            runs_folder = config['training_details']['runs_folder']
            scaler_path = os.path.join(f"../{runs_folder}", f'{first_directory}', "scalers.pkl")
        
        with open(scaler_path, 'rb') as f:
            scalers = pickle.load(f)
        #minmax scaling
        if scalers['minmax'] is not None and len(minmax_features) > 0:
            context.log.info(f"Applying Transform Min-Max scaling to features: {minmax_features}")
            scaled_data[minmax_features] = scalers['minmax'].transform(scaled_data[minmax_features])
        else:
            context.log.info("No Min-Max scaler found or no features to scale.")
        #Standard scaling
        if scalers['standard'] is not None and len(standard_features) > 0:
            context.log.info(f"Applying Transform Standard scaling to features: {standard_features}")
            scaled_data[standard_features] = scalers['standard'].transform(scaled_data[standard_features])
        else:
            context.log.info("No Standard scaler found or no features to scale.")
        #Robust Scaling
        if scalers['robust'] is not None and len(robust_features) > 0:
            context.log.info(f"Applying Transform Robust scaling to features: {robust_features}")
            scaled_data[robust_features] = scalers['robust'].transform(scaled_data[robust_features])
        else:
            context.log.info("No Robust scaler found or no features to scale.")


    # Save the scaled data to a Parquet file
    parq_link = quick_save_parquet_link(
        df=scaled_data,
        config=config,
        context=context,
        filename=f'Scaled_Data_{train_or_test}',
        model_metadata=model_metadata
    )
    context.log.info(f"Scaled data saved to {parq_link}")
    context.add_output_metadata(
        {
            "type": MetadataValue.md(train_or_test),
            "sample_tail": MetadataValue.md(scaled_data.tail().to_markdown()),
            "Parquet_Scaling_Link": MetadataValue.url(parq_link),
            "scaler_file_path": MetadataValue.url(scaler_file_path),
            "minmax_features": MetadataValue.text(", ".join(minmax_features)),
            "standard_features": MetadataValue.text(", ".join(standard_features)),
            "robust_features": MetadataValue.text(", ".join(robust_features)),
        }
    )
    return scaled_data


def quantile_loss(ytrue, y_pred, quantile):
    residual = ytrue - y_pred
    return np.mean(np.maximum(quantile * residual, (quantile - 1) * residual))


def add_labels_high_low(df, config):
    num_bars = config['num_bars_to_look_labels']
    df['High_Label'] = df['High'].rolling(window=num_bars).max().shift(-num_bars+1)
    df['Low_Label'] = df['Low'].rolling(window=num_bars).min().shift(-num_bars+1)
    df['High_Label'] = df['High_Label'] - df['Close']
    df['Low_Label'] = df['Close'] - df['Low_Label']
    df['High_Label'] = df['High_Label'] / df['Close'] * 10000
    df['Low_Label'] = df['Low_Label'] / df['Close'] * 10000
    return df

def get_train_test_split(dfs, config, context, model_metadata, high_low=''):
    cfg = config['training_details']
    test_size = cfg['test_size']
    random_state = cfg['random_state']
    X_train, X_test, y_train, y_test = train_test_split(
        dfs['input_df'], 
        dfs[f'output_{high_low}_df'], 
        test_size=test_size, 
        random_state=random_state
    )
    x_train_parq = quick_save_parquet_link(
        df=X_train,
        config=config,
        context=context,
        filename=f'X_train_{high_low}',
        model_metadata=model_metadata
    )   
    x_test_parq = quick_save_parquet_link(
        df=X_test,
        config=config,
        context=context,
        filename=f'X_test_{high_low}',
        model_metadata=model_metadata
    )

    y_train_parq = quick_save_parquet_link(
        df=y_train,
        config=config,
        context=context,
        filename=f'y_train_{high_low}',
        model_metadata=model_metadata
    )

    y_test_parq = quick_save_parquet_link(
        df=y_test,
        config=config,
        context=context,
        filename=f'y_test_{high_low}',
        model_metadata=model_metadata
    )


    context.add_output_metadata(
        {
            "type": MetadataValue.md(high_low),
            "test_size": MetadataValue.int(test_size),
            "random_state": MetadataValue.int(random_state),
            "train_shape": MetadataValue.md(f"X_train: {X_train.shape}, y_train: {y_train.shape}"),
            "test_shape": MetadataValue.md(f"X_test: {X_test.shape}, y_test: {y_test.shape}"),
            "Sample_Train": MetadataValue.md(X_train.head().to_markdown()),
            "Sample_Test": MetadataValue.md(X_test.head().to_markdown()),
            "Sample_Train_Labels": MetadataValue.md(y_train.head().to_markdown()),
            "Sample_Test_Labels": MetadataValue.md(y_test.head().to_markdown()),
            f"X_train_{high_low}_parq": MetadataValue.url(x_train_parq),
            f"X_test_{high_low}_parq": MetadataValue.url(x_test_parq),
            f"y_train_{high_low}_parq": MetadataValue.url(y_train_parq),
            f"y_test_{high_low}_parq": MetadataValue.url(y_test_parq)
        }
    )
    output_dict = {
        f'X_train_{high_low}': X_train,
        f'X_test_{high_low}': X_test,
        f'y_train_{high_low}': y_train,
        f'y_test_{high_low}': y_test
    }
    return output_dict

def get_quantile_dmatrix(df_dict, context, high_low=''):
    """
    Create DMatrix for quantile regression from the input DataFrame.
    
    Args:
        df_dict (dict): Dictionary containing input DataFrame and labels.
        config (dict): Configuration dictionary.
        high_low (str): Indicates whether to use 'high' or 'low' labels.
    
    Returns:
        xgb.DMatrix: DMatrix object for quantile regression.
    """
    dtrain = xgb.DMatrix(df_dict[f'X_train_{high_low}'], df_dict[f'y_train_{high_low}'])
    dtest = xgb.DMatrix(df_dict[f'X_test_{high_low}'], df_dict[f'y_test_{high_low}'])
    context.log.info(f"Created DMatrix for {high_low} labels ")
    output_dict = {
        f'dtrain_{high_low}': dtrain,
        f'dtest_{high_low}': dtest,
    }
    return output_dict

def get_base_param_dict(training_params_config):
    base_params = training_params_config['base_parameters'].split(',')
    base_params_dict = {
        param['name']: param['value'] for param in training_params_config['params_list'] if param['name'] in base_params
            
    }
    return base_params_dict


def get_trial_suggestion(trial, param_name, param_cfg):
    type = param_cfg['type']
    value = param_cfg['value']
    if type == 'float':
        return trial.suggest_float(param_name, param_cfg['min'], param_cfg['max'], log=param_cfg.get('log', False)) if param_cfg['hp'] else value
    elif type == 'int':
        return trial.suggest_int(param_name, param_cfg['min'], param_cfg['max'], log=param_cfg.get('log', False)) if param_cfg['hp'] else value
    elif type == 'str':
        return trial.suggest_categorical(param_name, value.split(',')) if param_cfg['hp'] else value
    elif type == 'bool':
        return bool(value)
    else:
        raise ValueError(f"Unsupported parameter type: {type} for parameter {param_name}")
    


##### CReate the objective function for optuna to tune tree parameters
def get_objective(dtrain, dtest, y_test, q_alpha, config, eval_metric, num_boosting_rounds, context):
    def objective(trial):
        cfg = config['training_parameters']
        active_params = cfg['active_parameters'].split(',')
        params = {
            name: get_trial_suggestion(trial, name, param_cfg)
            for name, param_cfg in cfg['params_list'].items() if name in active_params
        }
        params['quantile_alpha'] = q_alpha
        base_params = get_base_param_dict(cfg)
        #'scale_pos_weight': trial.suggest_float('scale_pos_weight', min(buying_weight, selling_weight), max(buying_weight, selling_weight))
        params.update(base_params)
        #print(f"qalpha : {q_alpha}")
        #thresholds = [trial.suggest_float(f'threshold_{i}', 0.1, 0.9) for i in ]
        pruning_callback = optuna.integration.XGBoostPruningCallback(trial, f'test-{eval_metric}')

        xgb_model = xgb.train(params=params, dtrain=dtrain, num_boost_round=num_boosting_rounds, 
                            evals=[(dtest, 'test')],
                            early_stopping_rounds=config['training_details']['early_stopping_rounds'],
                            verbose_eval=False,
                            callbacks=[pruning_callback],
                            )
        trial.set_user_attr("best_iteration", xgb_model.best_iteration)
        preds = xgb_model.predict(dtest)
        loss1 = quantile_loss(y_test, preds[:, 0], q_alpha[0])
        loss2 = quantile_loss(y_test, preds[:, 1], q_alpha[1])
        combined_score = np.mean([loss1, loss2])
        
        context.log.info(f"Trial {trial.number}: Best iteration = {xgb_model.best_iteration}, test rmse = {combined_score}")

        return combined_score
    
    return objective

def optimize_parameters(dmat_dict, config, context, model_metadata, high_low=''):
    """
    Optimize parameters using Optuna for quantile regression.
    
    Args:
        dmat_dict (dict): Dictionary containing DMatrix objects for training and testing.
        config (dict): Configuration dictionary.
        context: Dagster context for logging and metadata.
        high_low (str): Indicates whether to use 'high' or 'low' labels.
    
    Returns:
        xgb.Booster: Trained XGBoost model.
    """
    num_boosting_rounds = config['training_details']['num_boost_rounds']
    eval_metric = config['training_details']['eval_metric']
    q_alpha = config['training_details'][f'qalpha_{high_low}'].split(',')
    
    objective = get_objective(
        dtrain=dmat_dict[f'dtrain_{high_low}'], 
        dtest=dmat_dict[f'dtest_{high_low}'], 
        y_test=dmat_dict[f'y_test_{high_low}'], 
        q_alpha=q_alpha, 
        config=config, 
        eval_metric=eval_metric, 
        num_boosting_rounds=num_boosting_rounds,
        context=context
    )
    
    study = optuna.create_study(direction='minimize')
    study.optimize(objective, n_trials=config['training_details']['num_trials'])
    
    best_trial = study.best_trial
    context.log.info(f"Best trial: {best_trial.number} with value: {best_trial.value}")
    
    best_params = best_trial.params
    context.log.info(f"Best parameters: {best_params}")


    #Save the best hyperparameter values to a file
    first_directory = get_first_directory(config, model_metadata)
    runs_folder = config['training_details']['runs_folder']
    filename= f'best_params_{high_low}.json'
    file_path_hp = os.path.join(f"../{runs_folder}", f'{first_directory}', filename)
    os.makedirs(os.path.dirname(file_path_hp), exist_ok=True)
    with open(file_path_hp, 'w') as f:
        json.dump(best_params, f, indent=4)

    context.add_output_metadata(
        {
            "best_trial": MetadataValue.int(best_trial.number),
            "best_value": MetadataValue.float(best_trial.value),
            "best_params": MetadataValue.md(str(best_params)),
            "q_alpha": MetadataValue.md(str(q_alpha)),
            "num_boosting_rounds": MetadataValue.int(num_boosting_rounds),
            "eval_metric": MetadataValue.str(eval_metric),
            "best_params_file": MetadataValue.url(f"{runs_folder}/{first_directory}/{filename}"),
        }
    )
 
    output_dict = {
        'best_params': best_params,
        'best_iteration': best_trial.user_attrs.get('best_iteration', None)
    }
    return output_dict

def train_model(dmat_dict, params, config, context, high_low='', mlflow_resource=None):
    """
    Train the XGBoost model using the optimized parameters.
    
    Args:
        dmat_dict (dict): Dictionary containing DMatrix objects for training and testing.
        config (dict): Configuration dictionary.
        context: Dagster context for logging and metadata.
        high_low (str): Indicates whether to use 'high' or 'low' labels.
    
    Returns:
        xgb.Booster: Trained XGBoost model.
    """
    best_params = params['best_params']
    best_iteration = params['best_iteration']
    quantile_alpha = best_params['quantile_alpha']
    if best_iteration is None:
        context.log.warning("Best iteration not found in parameters, using default num_boost_rounds.")
        best_iteration = config['training_details']['num_boost_rounds']
    with mlflow_resource.start_run(run_name=f"XGBoost_Power_{high_low}") as run:
        mlflow_resource.log_params(best_params)
        xgb_model = xgb.train(
            params=best_params,
            dtrain=dmat_dict[f'dtrain_{high_low}'],
            num_boost_round=best_iteration,
            evals=[(dmat_dict[f'dtest_{high_low}'], 'test')],
            verbose_eval=False
        )
        preds = xgb_model.predict(dmat_dict[f'dtest_{high_low}'])
        loss1 = quantile_loss(dmat_dict[f'y_test_{high_low}'], preds[:, 0], quantile_alpha[0])
        loss2 = quantile_loss(dmat_dict[f'y_test_{high_low}'], preds[:, 1], quantile_alpha[1])
        q_loss = np.mean([loss1, loss2])
        context.log.info(f"Quantile loss for {high_low} labels: {q_loss}")
        mlflow_resource.log_metric(f'quantile_loss_{high_low}', q_loss)
        mlflow_resource.log_metric('best_iteration', best_iteration)
        mlflow_resource.xgboost.log_model(
            xgb_model,
            artifact_path=f"xgboost_model_power_{high_low}",
            registered_model_name=f"XGBoost_Power_{high_low}"
        )
        mlflow_run_id = run.info.run_id
        exp_id = run.info.experiment_id
        tracking_url = mlflow_resource.get_tracking_uri()
        mlflow_run_url = f"{tracking_url}/#/experiments/{exp_id}/runs/{mlflow_run_id}"
    context.add_output_metadata(
        {
            "mlflow_run_url": MetadataValue.url(mlflow_run_url),
            "quantile_loss": MetadataValue.float(q_loss),
            "best_iteration": MetadataValue.int(best_iteration),
            "best_params": MetadataValue.md(str(best_params)),
            "quantile_alpha": MetadataValue.md(str(quantile_alpha)),
        }
    )
    
    context.log.info(f"Trained model for {high_low} labels with params : {best_params} and best iteration: {best_iteration}")
    
    return xgb_model