import mlflow
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
import optuna
import numpy as np
import pandas as pd
import os
import yaml
import json
import xgboost as xgb
import joblib
from sklearn.model_selection import train_test_split
from pathlib import Path
from trading_functions.common.data import type_dict
from trading_functions.training.utility import (
    get_columns_mapping,
    save_df_parquet_link,
    get_first_directory,
    get_file_viewer_link,
    get_dagster_run_id_path
)
from trading_functions.common.indicators import get_fourier_columns
import xgboost as xgb
from sklearn.preprocessing import MinMaxScaler, StandardScaler, RobustScaler
from trading_functions.db.session import SessionLocal, INF_DATABASE_URL
from sqlalchemy.orm import Session
from trading_functions.db.models import PriceData
                               
from dagster import MetadataValue


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

def get_data_from_db(start_date, end_date, context=None):
    db: Session = SessionLocal()
    if context:
        context.log.info(f"Fetching data from database with url: {INF_DATABASE_URL}")
        for key, value in os.environ.items():
            if "POSTGRES" in key or "INF" in key:
                context.log.info(f"Environ : {key}: {value}")
    candles = db.query(PriceData).filter(
        PriceData.time >= start_date,
        PriceData.time <= end_date
    ).all()
    if not candles:
        df = pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    else:
        df = pd.DataFrame([{
            "Date": candle.time,
            "Open": candle.open,
            "High": candle.high,
            "Low": candle.low,
            "Close": candle.close,
            "Volume": candle.volume
        } for candle in candles])
    return df

def get_first_directory_with_runs_folder(config, model_metadata):
    """
    Get the first directory containing the 'runs' folder based on the configuration and model metadata.

    Args:
        config (dict): Configuration dictionary.
        model_metadata (dict): Metadata dictionary for the model.

    Returns:
        str: Path to the first directory with a 'runs' folder.
    """
    runs_folder = config['training_details']['runs_folder']
    first_directory = get_first_directory(config, model_metadata)
    return os.path.join(runs_folder, first_directory)


def get_scaler_path(config, model_metadata):
    """
    Get the path to the scaler file based on the configuration and model metadata.
    
    Args:
        config (dict): Configuration dictionary.
        model_metadata (dict): Metadata dictionary for the model.
    
    Returns:
        str: Path to the scaler file.
    """
    first_direct_with_runs = get_first_directory_with_runs_folder(config, model_metadata)
    scaler_file_path = os.path.join(f"{first_direct_with_runs}", "scalers.pkl")
    return scaler_file_path


def scale_features(df, config, context, model_metadata, train_or_test='train', scaler_path = ''):
    scale_cfg = config['scaling']
    
    scaled_data = df.copy()

    minmax_features = get_columns_mapping(scale_cfg['minmax']['columns'], config)
    standard_features = get_columns_mapping(scale_cfg['standard']['columns'], config)
    robust_features = get_columns_mapping(scale_cfg['robust']['columns'], config)
    fourier_columns = get_fourier_columns(config)
    minmax_scaler = MinMaxScaler()
    standard_scaler = StandardScaler()
    robust_scaler = RobustScaler()

    label_features = ['High_Label', 'Low_Label']
    label_scaling = config['common_config']['label_scale']
    if label_scaling == 'standard':
        standard_features = standard_features + label_features
    elif label_scaling == 'minmax':
        minmax_features = minmax_features + label_features
    elif label_scaling == 'robust':
        robust_features = robust_features + label_features

    if train_or_test == 'train':
        #minmax scaling
        context.log.info(f"Applying Fit Transform Min-Max scaling to features: {minmax_features}")
        if len(minmax_features) > 0:
            if 'fourier' in minmax_features:
                minmax_features = [f for f in minmax_features if f != 'fourier'] + fourier_columns
            scaled_data[minmax_features] = minmax_scaler.fit_transform(scaled_data[minmax_features])
        else:
            minmax_scaler = None

        #Standard scaling
        context.log.info(f"Applying Fit Transform Standard scaling to features: {standard_features}")
        if len(standard_features) > 0:
            if 'fourier' in standard_features:
                standard_features = [f for f in standard_features if f != 'fourier'] + fourier_columns
            scaled_data[standard_features] = standard_scaler.fit_transform(scaled_data[standard_features])
        else:
            standard_scaler = None
        
        #Robust Scaling
        context.log.info(f"Applying Fit Transform Robust scaling to features: {robust_features}")
        if len(robust_features) > 0:
            if 'fourier' in robust_features:
                robust_features = [f for f in robust_features if f != 'fourier'] + fourier_columns
            scaled_data[robust_features] = robust_scaler.fit_transform(scaled_data[robust_features])
        else:
            robust_scaler = None

        #Save scalers to model directory
        scalers = {
            'minmax': minmax_scaler,
            'standard': standard_scaler,
            'robust': robust_scaler
        }
        scaler_file_path = get_scaler_path(config, model_metadata)
        os.makedirs(os.path.dirname(scaler_file_path), exist_ok=True)
        joblib.dump(scalers, scaler_file_path)
        context.log.info(f"Scalers saved to {scaler_file_path} using joblib")
    else:
        if scaler_path == '':
            scaler_path = get_scaler_path(config, model_metadata)


        scalers = joblib.load(scaler_path)
        #minmax scaling
        if scalers['minmax'] is not None and len(minmax_features) > 0:
            if 'fourier' in minmax_features:
                minmax_features = [f for f in minmax_features if f != 'fourier'] + fourier_columns
            context.log.info(f"Applying Transform Min-Max scaling to features: {minmax_features}")
            scaled_data[minmax_features] = scalers['minmax'].transform(scaled_data[minmax_features])
        else:
            context.log.info("No Min-Max scaler found or no features to scale.")
        #Standard scaling
        if scalers['standard'] is not None and len(standard_features) > 0:
            if 'fourier' in standard_features:
                standard_features = [f for f in standard_features if f != 'fourier'] + fourier_columns
            context.log.info(f"Applying Transform Standard scaling to features: {standard_features}")
            scaled_data[standard_features] = scalers['standard'].transform(scaled_data[standard_features])
        else:
            context.log.info("No Standard scaler found or no features to scale.")
        #Robust Scaling
        if scalers['robust'] is not None and len(robust_features) > 0:
            if 'fourier' in robust_features:
                robust_features = [f for f in robust_features if f != 'fourier'] + fourier_columns
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
            "scaler_file_path": MetadataValue.url(scaler_path),
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
    # label_scaling_multiplier = config['label_scaling_multiplier']
    df['High_Label'] = df['High'].rolling(window=num_bars).max().shift(-num_bars+1)
    df['Low_Label'] = df['Low'].rolling(window=num_bars).min().shift(-num_bars+1)
    df['High_Label'] = df['High_Label'] - df['Close']
    df['Low_Label'] = df['Close'] - df['Low_Label']
    df['High_Label'] = df['High_Label'] / df['Close']
    df['Low_Label'] = df['Low_Label'] / df['Close']
    # df['High_Label'] = df['High_Label'] / df['Close'] * label_scaling_multiplier
    # df['Low_Label'] = df['Low_Label'] / df['Close'] * label_scaling_multiplier
    df.dropna(inplace=True)
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
            "test_size": MetadataValue.float(test_size),
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
    if type == 'str' or type == 'bool':
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
            param_cfg['name']: get_trial_suggestion(trial, param_cfg['name'], param_cfg)
            for param_cfg in cfg['params_list'] if param_cfg['name'] in active_params
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
        y_test_values = y_test.values.ravel()  # Flatten the y_test array
        score = quantile_loss(y_test_values, preds, q_alpha)
        
        context.log.info(f"Trial {trial.number}: Best iteration = {xgb_model.best_iteration}, test rmse = {score}")

        return score
    
    return objective

def optimize_parameters(df_dict, config, context, model_metadata, high_low=''):
    """
    Optimize parameters using Optuna for quantile regression.
    
    Args:
        df_dict (dict): Dictionary containing DataFrames for training and testing.
        config (dict): Configuration dictionary.
        context: Dagster context for logging and metadata.
        high_low (str): Indicates whether to use 'high' or 'low' labels.
    
    Returns:
        xgb.Booster: Trained XGBoost model.
    """
    num_boosting_rounds = config['training_details']['num_boost_rounds']
    eval_metric = config['training_details']['eval_metric']
    q_alpha = config['training_details'][f'qalpha_{high_low}']
    q_alpha = float(q_alpha)
    dtrain = xgb.QuantileDMatrix(df_dict[f'X_train_{high_low}'], df_dict[f'y_train_{high_low}'])
    dtest = xgb.QuantileDMatrix(df_dict[f'X_test_{high_low}'], df_dict[f'y_test_{high_low}'], ref=dtrain)
    
    objective = get_objective(
        dtrain=dtrain,
        dtest=dtest,
        y_test=df_dict[f'y_test_{high_low}'],
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
    file_path_hp = os.path.join(f"{runs_folder}", f'{first_directory}', filename)
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
            "eval_metric": MetadataValue.md(str(eval_metric)),
            "best_params_file": MetadataValue.url(f"{runs_folder}/{first_directory}/{filename}"),
        }
    )
 
    output_dict = {
        'best_params': best_params,
        'best_iteration': best_trial.user_attrs.get('best_iteration', None)
    }
    return output_dict

def get_other_non_hp_params(config):
    """
    Get the non-hyperparameter parameters from the configuration.
    
    Args:
        config (dict): Configuration dictionary.
    
    Returns:
        dict: Dictionary of non-hyperparameter parameters.
    """
    training_params_config = config['training_parameters']
    active_params = training_params_config['active_parameters'].split(',')
    hp_params = [param_cfg['name'] for param_cfg in training_params_config['params_list'] if param_cfg.get('hp', False)]
    other_non_hp_params = {
        param_cfg['name']: param_cfg['value'] for param_cfg in training_params_config['params_list'] if param_cfg['name'] not in hp_params and param_cfg['name'] in active_params
    }
    return other_non_hp_params

def train_model(df_dict, params, config, context, model_metadata, high_low='', mlflow_resource_dict={}):
    """
    Train the XGBoost model using the optimized parameters.
    
    Args:
        df_dict (dict): Dictionary containing DataFrames for training and testing.
        config (dict): Configuration dictionary.
        context: Dagster context for logging and metadata.
        high_low (str): Indicates whether to use 'high' or 'low' labels.
    
    Returns:
        xgb.Booster: Trained XGBoost model.
    """
    client = MlflowClient()
    parent_run_id = mlflow_resource_dict.get('parent_run_id', None)
    exp_id = mlflow_resource_dict.get('experiment_id', None)
    model_name = config['training_details']['model_name']
    scaler_path = get_scaler_path(config, model_metadata)
    best_params = params['best_params']
    non_hp_params = get_other_non_hp_params(config)
    best_params.update(non_hp_params)
    quantile_alpha = config['training_details'][f'qalpha_{high_low}']
    quantile_alpha = float(quantile_alpha)
    best_params['quantile_alpha'] = quantile_alpha
    context.log.info(f"Training model {high_low} with parameters: {best_params}")
    best_iteration = params['best_iteration']
    dtrain = xgb.QuantileDMatrix(df_dict[f'X_train_{high_low}'], df_dict[f'y_train_{high_low}'])
    dtest = xgb.QuantileDMatrix(df_dict[f'X_test_{high_low}'], df_dict[f'y_test_{high_low}'], ref=dtrain)
    ytest = df_dict[f'y_test_{high_low}']
    Xtest = df_dict[f'X_test_{high_low}']
    if best_iteration is None:
        context.log.warning("Best iteration not found in parameters, using default num_boost_rounds.")
        best_iteration = config['training_details']['num_boost_rounds']
    with mlflow.start_run(run_name=f"{model_name}_run_{high_low}", nested=True, parent_run_id=parent_run_id, experiment_id=exp_id) as run:
        mlflow.log_params(best_params)
        xgb_model = xgb.train(
            params=best_params,
            dtrain=dtrain,
            num_boost_round=best_iteration,
            evals=[(dtest, 'test')],
            verbose_eval=False
        )
        preds = xgb_model.predict(dtest)
        input_example = Xtest.iloc[:5]
        preds_example = preds[:5]
        signature = infer_signature(input_example, preds_example)
        y_test_values = ytest.values.ravel()  # Flatten the y_test array

        # Changed this to use just 1 quantile alpha for each model high and low
        # loss1 = quantile_loss(y_test_values, preds[:, 0], quantile_alpha[0])
        # loss2 = quantile_loss(y_test_values, preds[:, 1], quantile_alpha[1])
        # q_loss = np.mean([loss1, loss2])
        q_loss = quantile_loss(y_test_values, preds, quantile_alpha)

        
        context.log.info(f"Quantile loss for {high_low} labels: {q_loss}")
        mlflow.log_metric(f'quantile_loss_{high_low}', q_loss)
        mlflow.log_metric('best_iteration', best_iteration)
        mlflow.log_artifact(scaler_path, artifact_path='run_model')
        context.log.info(f"Model {high_low} scalers logged from path: {scaler_path}")
        
        #Log config dictionary as an artifact
        first_directory_with_runs = get_first_directory_with_runs_folder(config, model_metadata)
        config_file_path = os.path.join(f"{first_directory_with_runs}", config['training_details']['mlflow_config_artifact_name'])
        with open(config_file_path, 'w') as f:
            yaml.dump(config, f)
        context.log.info(f"Config file saved to {config_file_path} , and artifact uri : {run.info.artifact_uri}")
        mlflow.log_artifact(config_file_path, artifact_path='run_model')
        
        mlflow.xgboost.log_model(
            xgb_model,
            name="model",
            signature=signature,
            input_example=input_example,
            registered_model_name=f"{model_name}_{high_low}"
        )
        model_versions = client.search_model_versions(f"name='{model_name}_{high_low}'")
        model_versions_sorted = sorted(model_versions, key=lambda x: int(x.version), reverse=True)
        latest_version = int(model_versions_sorted[0].version) if model_versions_sorted else 1
        
        client.set_model_version_tag(
            name=f"{model_name}_{high_low}",
            version=str(latest_version),
            key="training_start",
            value=config['training_details']['train_start_date'] + " 00:00:00"
        )
        client.set_model_version_tag(
            name=f"{model_name}_{high_low}",
            version=str(latest_version),
            key="training_end",
            value=config['training_details']['train_end_date'] + " 23:59:00"
        )

        mlflow_run_id = run.info.run_id
        exp_id = run.info.experiment_id
        tracking_url = mlflow.get_tracking_uri()
        mlflow_run_url = f"{tracking_url}/#/experiments/{exp_id}/runs/{mlflow_run_id}"
    context.add_output_metadata(
        {
            "mlflow_run_url": MetadataValue.url(mlflow_run_url),
            "quantile_loss": MetadataValue.float(float(q_loss)),
            "best_iteration": MetadataValue.int(best_iteration),
            "best_params": MetadataValue.md(str(best_params)),
            "quantile_alpha": MetadataValue.md(str(quantile_alpha)),
        }
    )
    
    context.log.info(f"Trained model for {high_low} labels with params : {best_params} and best iteration: {best_iteration}")
    model_info = {
        'mlflow_run_id': mlflow_run_id,
        'exp_id': exp_id,
        'tracking_url': tracking_url,
        'mlflow_run_url': mlflow_run_url,
        'model_name': f"XGBoost_Power_{high_low}",
        'artifact_path': f"xgboost_model_power_{high_low}",
        'model': xgb_model,
    }
    return model_info


def get_model_evaluation(context, config, input_output_df_test:dict, models:dict, model_metadata, mlflow_resource, parent_run_id, original_data, scaler_path = ''):
    """
    Evaluate the trained model using the test dataset.
    
    Args:
        context: Dagster context for logging and metadata.
        model: Trained XGBoost model.
        dmat_dict (dict): Dictionary containing DMatrix objects for training and testing.
        config (dict): Configuration dictionary.
        high_low (str): Indicates whether to use 'high' or 'low' labels.
    
    Returns:
        dict: Evaluation metrics for the model.
    """
    high_model_info = models['train_model_high']
    low_model_info = models['train_model_low']
    train_model_high = high_model_info['model']
    train_model_low = low_model_info['model']

    if scaler_path == '':
        scaler_path = get_scaler_path(config, model_metadata)


    scalers = joblib.load(scaler_path)

    # label_scaling_multiplier = config['common_config']['label_scaling_multiplier']
    label_scale_type = config['common_config']['label_scale']
    high_label = config['training_details']['high_label_column']
    low_label = config['training_details']['low_label_column']
    trade_init_ratio_threshold = config['trade_parameters']['trade_init_ratio_threshold']
    trade_risk_ratio_threshold = config['trade_parameters']['trade_risk_ratio_threshold']

    initial_columns = config['common_config']['initial_columns'].split(',')
    init_columns_df = original_data[initial_columns]

    test_df = input_output_df_test['input_df']
    output_high_df = input_output_df_test['output_high_df']
    output_low_df = input_output_df_test['output_low_df']
    amount_per_trade = config['trade_parameters']['amount_per_trade']
    quantile_dmatrix = xgb.QuantileDMatrix(test_df)
    high_preds = train_model_high.predict(quantile_dmatrix)
    low_preds = train_model_low.predict(quantile_dmatrix)
    output_df = test_df.copy()
    output_df = pd.concat([init_columns_df, output_df, output_high_df, output_low_df], axis=1)
    
    low_label_index = -2
    high_label_index = -1
    output_df['pred_sell_stop'] = high_preds
    output_df['pred_buy_take'] = high_preds
    output_df['pred_sell_take'] = low_preds
    output_df['pred_buy_stop'] = low_preds
    # output_df[low_label] = scalers[label_scale_type].inverse_transform(output_df[[low_label]])
    if label_scale_type == 'standard':

        output_df[low_label] = output_df[low_label] * scalers[label_scale_type].scale_[low_label_index] + scalers[label_scale_type].mean_[low_label_index]
        output_df[high_label] = output_df[high_label] * scalers[label_scale_type].scale_[high_label_index] + scalers[label_scale_type].mean_[high_label_index]
        output_df['pred_sell_stop'] = output_df['pred_sell_stop'] * scalers[label_scale_type].scale_[high_label_index] + scalers[label_scale_type].mean_[high_label_index]
        output_df['pred_buy_take'] = output_df['pred_buy_take'] * scalers[label_scale_type].scale_[high_label_index] + scalers[label_scale_type].mean_[high_label_index]
        output_df['pred_sell_take'] = output_df['pred_sell_take'] * scalers[label_scale_type].scale_[low_label_index] + scalers[label_scale_type].mean_[low_label_index]
        output_df['pred_buy_stop'] = output_df['pred_buy_stop'] * scalers[label_scale_type].scale_[low_label_index] + scalers[label_scale_type].mean_[low_label_index]

    output_df[low_label] = output_df['Close'] - (output_df[low_label] * output_df['Close'].values)
    output_df[high_label] = output_df['Close'] + (output_df[high_label] * output_df['Close'].values)
    output_df['pred_sell_stop'] = output_df['pred_sell_stop'] + output_df['Close']
    output_df['pred_buy_take'] = output_df['pred_buy_take'] + output_df['Close']
    output_df['pred_sell_take'] = output_df['Close'] - output_df['pred_sell_take']
    output_df['pred_buy_stop'] = output_df['Close'] - output_df['pred_buy_stop']

    output_df['buy_risk_reward'] = (output_df['pred_buy_take'] - output_df['Close']) / (output_df['Close'] - output_df['pred_buy_stop'])
    output_df['sell_risk_reward'] = (output_df['Close'] - output_df['pred_sell_take']) / (output_df['pred_sell_stop'] - output_df['Close'])

    output_df['buy_sell_ratio'] = (output_df['pred_buy_take'] - output_df['Close']) / (output_df['Close'] - output_df['pred_sell_take'])
    output_df['sell_buy_ratio'] = (output_df['Close'] - output_df['pred_sell_take']) / (output_df['pred_buy_take'] - output_df['Close'])

    output_df['buy_signal'] = (output_df['buy_sell_ratio'] > trade_init_ratio_threshold) & (output_df['buy_risk_reward'] > trade_risk_ratio_threshold)
    output_df['sell_signal'] = (output_df['sell_buy_ratio'] > trade_init_ratio_threshold) & (output_df['sell_risk_reward'] > trade_risk_ratio_threshold)
    output_df['risk_reward'] = np.where(
        output_df['buy_signal'], 
        output_df['buy_risk_reward'], 
        np.where(output_df['sell_signal'], output_df['sell_risk_reward'], 0)
    )

    cond1 = (output_df['buy_signal']) & (output_df[low_label] < output_df['pred_buy_stop'])
    cond2 = (output_df['sell_signal']) & (output_df[high_label] > output_df['pred_sell_stop'])
    cond3 = (output_df['buy_signal']) & (output_df[high_label] > output_df['pred_buy_take'])
    cond4 = (output_df['sell_signal']) & (output_df[low_label] < output_df['pred_sell_take'])

    output_df['win'] = np.select(
        condlist=[cond1 | cond2, cond3 | cond4],
        choicelist=[1, -1],  # 1 for win, -1 for loss
        default=0  # 0 for no trade
    )
    output_df['win'] = output_df['win'].astype(int)
    output_df['profit'] = np.where(
        output_df['win'] == 1,
        amount_per_trade,
        np.where(output_df['win'] == -1, -amount_per_trade / output_df['risk_reward'], 0)
    )

    total_trades = output_df['win'].value_counts().get(1, 0) + output_df['win'].value_counts().get(-1, 0)
    total_wins = output_df['win'].value_counts().get(1, 0)
    total_losses = output_df['win'].value_counts().get(-1, 0)
    win_percentage = (total_wins / total_trades * 100) if total_trades > 0 else 0
    total_profit = output_df['profit'].sum()
    parq_link = quick_save_parquet_link(
        df=output_df,
        config=config,
        context=context,
        filename='Model_Evaluation_Output',
        model_metadata=model_metadata
    )
    run_ids = [high_model_info['mlflow_run_id'], low_model_info['mlflow_run_id']]
    exp_id = mlflow_resource.experiment_id
    dagster_run_id = context.run_id
    artifact_path = get_dagster_run_id_path(
        config=config,
        run_id=dagster_run_id,
        filename='Model_Evaluation_Output.parquet',
        model_metadata=model_metadata
    )

    for run_id in run_ids:
        with mlflow.start_run(run_id=run_id, experiment_id=exp_id, parent_run_id=parent_run_id, nested=True) as run:
            mlflow.log_params({
                'total_trades': total_trades,
                'total_wins': total_wins,
                'total_losses': total_losses,
                'win_percentage': win_percentage,
                'total_profit': total_profit
            })
            mlflow.log_artifact(artifact_path, artifact_path='evaluation_output')

    context.add_output_metadata(
        {
            "total_trades": MetadataValue.int(int(total_trades)),
            "total_wins": MetadataValue.int(int(total_wins)),
            "total_losses": MetadataValue.int(int(total_losses)),
            "win_percentage": MetadataValue.float(float(win_percentage)),
            "total_profit": MetadataValue.float(float(total_profit)),
            "sample_output_df": MetadataValue.md(output_df.head().to_markdown()),
            "parquet_link": MetadataValue.url(parq_link),
            "label_scale_type": MetadataValue.md(label_scale_type),
        }
    )
    return output_df

