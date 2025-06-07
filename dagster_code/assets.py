from dagster import asset, MetadataValue, MaterializeResult
import pandas as pd

from trading_functions.common import transform
from resources import TrainingConfig, MLFlowResource
from trading_functions.training.utility import (
    save_df_parquet_link, 
    generate_model_id, 
    get_first_directory,
    get_all_training_features
)

from trading_functions.training.ml_pipeline import (
    get_filtered_data,
    quick_save_parquet_link,
    add_labels_high_low,
    get_train_test_split,
    get_quantile_dmatrix,
    optimize_parameters,
    train_model,
    add_indicators,
    close_diff_transform,
    normalize_timegaps_transform,
    scale_features,
    get_model_evaluation
)

from datetime import datetime
import os
import mlflow



@asset
def model_metadata(context, training_config: TrainingConfig) -> dict:
    """
    Create metadata for the model run.
    
    Args:
        training_config (TrainingConfig): Configuration for the training run.

    Returns:
        MaterializeResult: Metadata for the model run.
    """
    conf = training_config.load()
    cfg = conf['training_details']
    model_id = generate_model_id(model_name=cfg['model_name'])
    context.log.info(f"Model id: {model_id}")
    model_metadata_dict = {'model_id': model_id,}
    return model_metadata_dict


@asset
def raw_data(context, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Load the complete data from an Excel file
    
    Args:
        sheet_names (str): Comma-separated string of sheet names to load.
        all_data_path (str): Path to the Excel file.

    Returns:
        pd.DataFrame:  DataFrame containing the loaded data.
    """
    conf = training_config.load()
    cfg = conf['training_details']
    # Split the sheet names into a list
    sheet_names = cfg["sheet_names"]
    all_data_path = cfg["all_data_path"]

    sheet_names = [sheet.strip() for sheet in sheet_names.split(",")]
    context.log.info(f"Config training details: {cfg}")
    # Load data from the specified sheets
    data = pd.concat(pd.read_excel(all_data_path, sheet_name=sheet_names), ignore_index=True)

    # Convert 'Date' column to datetime format
    data['Date'] = pd.to_datetime(data['Date'])

    #Remove symbol column
    data.drop(columns=['Symbol'], inplace=True)
    parq_link = quick_save_parquet_link(
        df=data,
        config=conf,
        context=context,
        filename="Initial_data_load",
        model_metadata=model_metadata
    )
    row_count = data.shape[0]
    context.log.info(f"Number of rows in the filtered data: {row_count}")
    context.log.info(f"Parquet file link: {parq_link}")
    context.add_output_metadata(
        {
            "row_count": MetadataValue.int(row_count),
            "sample_head": MetadataValue.md(data.head().to_markdown()),
            "Parquet_Init_Load_Link": MetadataValue.url(parq_link),
        }
    )
    return data


@asset
def training_data(context, raw_data, training_config: TrainingConfig, model_metadata):
    conf = training_config.load()
    cfg = conf['training_details']

    train_start_date_str = str(cfg["train_start_date"])
    train_end_date_str = str(cfg["train_end_date"])
    # Filter data based on the provided date range
    train_data = get_filtered_data(raw_data, train_start_date_str, train_end_date_str)
    row_count = train_data.shape[0]
    parq_link = quick_save_parquet_link(
        df=train_data,
        config=conf,
        context=context,
        filename="Training_data",
        model_metadata=model_metadata
    )
    context.add_output_metadata(
        {
            "row_count": MetadataValue.int(row_count),
            "start_date": MetadataValue.text(train_start_date_str),
            "end_date": MetadataValue.text(train_end_date_str),
            "sample_head": MetadataValue.md(train_data.head().to_markdown()),
            "Parquet_Training_Data_Link": MetadataValue.url(parq_link),
        }
    )
    return train_data


@asset
def test_data(context, raw_data, training_config: TrainingConfig, model_metadata):
    conf = training_config.load()
    cfg = conf['training_details']

    test_start_date_str = str(cfg["test_start_date"])
    test_end_date_str = str(cfg["test_end_date"])
    # Filter data based on the provided date range
    test_data = get_filtered_data(raw_data, test_start_date_str, test_end_date_str)
    row_count = test_data.shape[0]
    parq_link = quick_save_parquet_link(
        df=test_data,
        config=conf,
        context=context,
        filename="Test_data",
        model_metadata=model_metadata
    )
    context.add_output_metadata(
        {
            "row_count": MetadataValue.int(row_count),
            "start_date": MetadataValue.text(test_start_date_str),
            "end_date": MetadataValue.text(test_end_date_str),
            "sample_head": MetadataValue.md(test_data.head().to_markdown()),
            "Parquet_Test_Data_Link": MetadataValue.url(parq_link),
        }
    )
    return test_data


@asset
def normalize_timegaps_training(context, training_data: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Normalize time gaps in the loaded data.

    Args:
        load_data (pd.DataFrame): DataFrame containing the loaded data.

    Returns:
        pd.DataFrame: DataFrame with normalized time gaps.
    """
    conf = training_config.load()
    normalized_data = normalize_timegaps_transform(
        df=training_data,
        config=conf,
    ) 
    # Log the number of rows in the normalized data
    row_count = normalized_data.shape[0]
    context.log.info(f"Normalized data row count: {row_count}")
    parq_link = quick_save_parquet_link(
        df=normalized_data,
        config=conf,
        context=context,
        filename="Timegap_Normalized_Data",
        model_metadata=model_metadata
    )

    context.add_output_metadata(
        {
            "row_count": MetadataValue.int(row_count),
            "sample_head": MetadataValue.md(normalized_data.head().to_markdown()),
            "Parquet_Timegap_Normalized_Training_Link": MetadataValue.url(parq_link),
        }
    )
    return normalized_data


@asset
def add_indicators_training(context, normalize_timegaps_training: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Add technical indicators to the loaded data.

    Args:
        load_data (pd.DataFrame): DataFrame containing the loaded data.

    Returns:
        pd.DataFrame: DataFrame with added indicators.
    """
    conf = training_config.load()
    data_with_indicators, selected_indicators = add_indicators(df=normalize_timegaps_training, config=conf)
    
    # Log the number of rows in the data with indicators
    row_count = data_with_indicators.shape[0]
    column_count = data_with_indicators.shape[1]
    context.log.info(f"Data with indicators row count: {row_count}, column count: {column_count}")
    parq_link = quick_save_parquet_link(
        df=data_with_indicators,
        config=conf,
        context=context,
        filename="Indicators_Training_added",
        model_metadata=model_metadata
    )
    # Add metadata for the asset
    context.add_output_metadata(
        {
            "column_count": MetadataValue.int(column_count),
            "row_count": MetadataValue.int(row_count),
            "sample_tail": MetadataValue.md(data_with_indicators.tail().to_markdown()),
            "selected_indicators": MetadataValue.text(", ".join(selected_indicators)),
            "Parquet_Indicators_Training_Link": MetadataValue.url(parq_link),

        }
    )
    
    return data_with_indicators

@asset
def close_diff_transform_training(context, add_indicators_training: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Transform some columns by calculating the difference with Close column.

    Args:
        add_indicators (pd.DataFrame): DataFrame containing the loaded data with indicators.

    Returns:
        pd.DataFrame: DataFrame with transformed columns.
    """
    conf = training_config.load()
    transformed_data, close_diff_features = close_diff_transform(
        df=add_indicators_training,
        config=conf,
    )
    # Log the number of rows in the transformed data
    row_count = transformed_data.shape[0]
    parq_link = quick_save_parquet_link(
        df=transformed_data,
        config=conf,
        context=context,
        filename="After_Close_Diff_Transform_Training",
        model_metadata=model_metadata
    )

    context.log.info(f"Transformed data row count: {row_count}")
    context.add_output_metadata(
        {
            "row_count": MetadataValue.int(row_count),
            "sample_tail": MetadataValue.md(transformed_data.tail().to_markdown()),
            "close_transform_columns": MetadataValue.text(", ".join(close_diff_features)),
            "Parquet_Close_Transform_Training_Link": MetadataValue.url(parq_link),

        }
    )
    return transformed_data

@asset
def add_labels_training(context, close_diff_transform_training: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Add labels for high and low prices based on the configuration.
    Args:
        close_diff_transform_step (pd.DataFrame): DataFrame containing the loaded data with transformed columns.
    Returns:
        pd.DataFrame: DataFrame with added labels for high and low prices.
    """
    conf = training_config.load()
    cfg = conf['common_config']
    # Add labels for high and low prices
    labeled_data = add_labels_high_low(close_diff_transform_training, config=cfg)
    parq_link = quick_save_parquet_link(
        df=labeled_data,
        config=conf,
        context=context,
        filename="After_Adding_Labels",
        model_metadata=model_metadata
    )

    context.add_output_metadata(
        {
            "column_count": MetadataValue.int(labeled_data.shape[1]),
            "sample_tail": MetadataValue.md(labeled_data.tail().to_markdown()),
            "Parquet_Add_Labels_Training_Link": MetadataValue.url(parq_link),

        }
    )
    return labeled_data

@asset
def scale_data_training(context, add_labels_training: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Scale the data using Min-Max scaling.
    
    Args:
        add_labels (pd.DataFrame): DataFrame containing the loaded data with added labels.

    Returns:
        pd.DataFrame: Scaled DataFrame.
    """
    conf = training_config.load()
    scaled_data = scale_features(
        df=add_labels_training,
        config=conf,
        context=context,
        model_metadata=model_metadata,
        train_or_test='train',
        scaler_path=''
    )

    return scaled_data



@asset
def input_output_df_training(context, scale_data_training: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> dict:

    conf = training_config.load()
    training_features = get_all_training_features(conf)
    high_label = conf['training_details']['high_label_column']
    low_label = conf['training_details']['low_label_column']
    output_dict = {
        'input_df': scale_data_training[training_features],
        'output_high_df': scale_data_training[[high_label]],
        'output_low_df': scale_data_training[[low_label]],
    }
    
    run_id = context.run_id
    parq_filename = f"Training_Features_With_Labels.parquet"
    parq_link = save_df_parquet_link(
        pd.concat([output_dict['input_df'], output_dict['output_high_df'], output_dict['output_low_df']], axis=1),
        config=conf,
        run_id=run_id,
        filename=parq_filename,
        model_metadata=model_metadata
    )

    context.add_output_metadata(
        {
            "input_columns": MetadataValue.text(", ".join(training_features)),
            "input_column_number": MetadataValue.int(len(training_features)),
            "output_high_column": MetadataValue.text(high_label),
            "output_low_column": MetadataValue.text(low_label),
            "sample_input_head": MetadataValue.md(scale_data_training[training_features].head().to_markdown()),
            "sample_output_high_head": MetadataValue.md(scale_data_training[[high_label]].head().to_markdown()),
            "sample_output_low_head": MetadataValue.md(scale_data_training[[low_label]].head().to_markdown()),
            "Parquet_Input_Output_Link": MetadataValue.url(parq_link),
        }
    )

    return output_dict


@asset
def train_test_split_high_model(context, input_output_df_training: dict, training_config: TrainingConfig, model_metadata) -> dict:
    """
    Split the data into training and testing sets for the buy model.
    
    Args:
        input_output_df_training (dict): Dictionary containing input and output DataFrames.

    Returns:
        dict: Dictionary containing training and testing sets for the buy model.
    """
    conf = training_config.load()
    output_dict = get_train_test_split(
        dfs=input_output_df_training, 
        config=conf, 
        context=context, 
        model_metadata=model_metadata,
        high_low='high'
    )
    
    return output_dict

@asset
def train_test_split_low_model(context, input_output_df_training: dict, training_config: TrainingConfig, model_metadata) -> dict:
    """
    Split the data into training and testing sets for the sell model.
    
    Args:
        input_output_df_training (dict): Dictionary containing input and output DataFrames.

    Returns:
        dict: Dictionary containing training and testing sets for the sell model.
    """
    conf = training_config.load()
    output_dict = get_train_test_split(
        dfs=input_output_df_training, 
        config=conf, 
        context=context, 
        model_metadata=model_metadata,
        high_low='low'
    )
    
    return output_dict


@asset
def hyperparameter_tuning_high(context, train_test_split_high_model: dict, training_config: TrainingConfig, model_metadata) -> dict:
    """
    Perform hyperparameter tuning for the buy model.
    
    Args:
        train_test_split_high_model (dict): Dictionary containing training and testing sets for the buy model.

    Returns:
        dict: Dictionary containing the best hyperparameters for the buy model.
    """
    conf = training_config.load()
    
    best_params = optimize_parameters(
        df_dict=train_test_split_high_model,
        config=conf,
        context=context,
        model_metadata=model_metadata,
        high_low='high'
    )
    
    return best_params


@asset
def hyperparameter_tuning_low(context, train_test_split_low_model: dict, training_config: TrainingConfig, model_metadata) -> dict:
    """
    Perform hyperparameter tuning for the sell model.
    
    Args:
        train_test_split_low_model (dict): Dictionary containing training and testing sets for the sell model.

    Returns:
        dict: Dictionary containing the best hyperparameters for the sell model.
    """
    conf = training_config.load()
    
    best_params = optimize_parameters(
        df_dict=train_test_split_low_model,
        config=conf,
        context=context, 
        model_metadata=model_metadata,
        high_low='low'
    )
    
    return best_params

@asset
def start_mlflow_parent_run(context, training_config: TrainingConfig, mlflow_resource: MLFlowResource, hyperparameter_tuning_high: dict, hyperparameter_tuning_low: dict) -> dict:
    """
    Start a parent run for the training pipeline.
    
    Args:
        training_config (TrainingConfig): Configuration for the training run.

    Returns:
        str: The run ID of the parent run.
    """
    conf = training_config.load()
    
  
    exp_id = mlflow_resource.experiment_id
    run_name = mlflow_resource.run_name
    model_name = mlflow_resource.model_name


    context.log.info(f"Starting parent run for model: {model_name} with run name: {run_name} , experiment ID: {exp_id}")
    #context.log.info(f"MLflow artifact URI: {artifact_uri}")
    if mlflow.active_run() is not None:
        context.log.warning("There is an active MLflow run. It will be ended before starting a new one.")
        mlf.end_run()
    with mlflow.start_run(run_name=run_name, experiment_id=exp_id) as run:
        run_id = run.info.run_id
        context.log.info(f"Parent run started with ID: {run_id}")

    output_dict = {
        'parent_run_id': run_id,
        'parent_run_name': run_name,
    }
    context.add_output_metadata(
        {
            "parent_run_id": MetadataValue.text(run_id),
            "parent_run_name": MetadataValue.text(run_name),
        }
    )
    return output_dict


@asset
def train_model_high(context, start_mlflow_parent_run: dict, train_test_split_high_model: dict, hyperparameter_tuning_high: dict, training_config: TrainingConfig, mlflow_resource: MLFlowResource) -> dict:
    """
    Train the buy model using the best hyperparameters.
    
    Args:
        train_test_split_high_model (dict): Dictionary containing training and testing sets for the buy model.
        hyperparameter_tuning_high (dict): Dictionary containing the best hyperparameters for the buy model.

    Returns:
        dict: Dictionary containing the trained model and its metadata.
    """
    conf = training_config.load()
    parent_run_id = start_mlflow_parent_run['parent_run_id']
    exp_id = mlflow_resource.experiment_id
    mlflow_resource_dict = {
        'parent_run_id': parent_run_id,
        'experiment_id': exp_id,
    }
    xgb_model_high_info = train_model(
        df_dict=train_test_split_high_model,
        params=hyperparameter_tuning_high,
        config=conf, 
        context=context, 
        high_low='high',
        mlflow_resource_dict=mlflow_resource_dict
    )
    
    return xgb_model_high_info  


@asset
def train_model_low(context, start_mlflow_parent_run: dict, train_test_split_low_model: dict, hyperparameter_tuning_low: dict, training_config: TrainingConfig, mlflow_resource: MLFlowResource) -> dict:
    """
    Train the sell model using the best hyperparameters.
    
    Args:
        train_test_split_low_model (dict): Dictionary containing training and testing sets for the sell model.
        hyperparameter_tuning_low (dict): Dictionary containing the best hyperparameters for the sell model.

    Returns:
        dict: Dictionary containing the trained model and its metadata.
    """
    conf = training_config.load()
    run_id = start_mlflow_parent_run['parent_run_id']
    exp_id = mlflow_resource.experiment_id
    mlflow_resource_dict = {
        'parent_run_id': run_id,
        'experiment_id': exp_id,
    }

    xgb_model_low_info = train_model(
        df_dict=train_test_split_low_model,
        params=hyperparameter_tuning_low,
        config=conf, 
        context=context, 
        high_low='low',
        mlflow_resource_dict=mlflow_resource_dict
    )
    
    return xgb_model_low_info

@asset
def normalize_timegaps_test(context, test_data: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Normalize time gaps in the test data.
    
    Args:
        test_data (pd.DataFrame): DataFrame containing the test data.

    Returns:
        pd.DataFrame: DataFrame with normalized time gaps.
    """
    conf = training_config.load()
    normalized_data = normalize_timegaps_transform(
        df=test_data,
        config=conf,
    ) 
    # Log the number of rows in the normalized data
    row_count = normalized_data.shape[0]
    context.log.info(f"Normalized test data row count: {row_count}")
    parq_link = quick_save_parquet_link(
        df=normalized_data,
        config=conf,
        context=context,
        filename="Timegap_Normalized_Test_Data",
        model_metadata=model_metadata
    )

    context.add_output_metadata(
        {
            "row_count": MetadataValue.int(row_count),
            "sample_head": MetadataValue.md(normalized_data.head().to_markdown()),
            "Parquet_Timegap_Normalized_Test_Link": MetadataValue.url(parq_link),
        }
    )
    
    return normalized_data

@asset
def add_indicators_test(context, normalize_timegaps_test: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Add technical indicators to the test data.
    Args:
        normalize_timegaps_test (pd.DataFrame): DataFrame containing the normalized test data.  
    Returns:
        pd.DataFrame: DataFrame with added indicators.
    """
    conf = training_config.load()
    data_with_indicators, selected_indicators = add_indicators(df=normalize_timegaps_test, config=conf)
    
    # Log the number of rows in the data with indicators
    row_count = data_with_indicators.shape[0]
    column_count = data_with_indicators.shape[1]
    context.log.info(f"Test data with indicators row count: {row_count}, column count: {column_count}")
    parq_link = quick_save_parquet_link(
        df=data_with_indicators,
        config=conf,
        context=context,
        filename="Indicators_Test_added",
        model_metadata=model_metadata
    )
    # Add metadata for the asset
    context.add_output_metadata(
        {
            "column_count": MetadataValue.int(column_count),
            "row_count": MetadataValue.int(row_count),
            "sample_tail": MetadataValue.md(data_with_indicators.tail().to_markdown()),
            "selected_indicators": MetadataValue.text(", ".join(selected_indicators)),
            "Parquet_Indicators_Test_Link": MetadataValue.url(parq_link),

        }
    )
    
    return data_with_indicators

@asset
def close_diff_transform_test(context, add_indicators_test: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Transform some columns by calculating the difference with Close column in the test data.
    
    Args:
        add_indicators_test (pd.DataFrame): DataFrame containing the test data with indicators.

    Returns:
        pd.DataFrame: DataFrame with transformed columns.
    """
    conf = training_config.load()
    transformed_data, close_diff_features = close_diff_transform(
        df=add_indicators_test,
        config=conf,
    )
    # Log the number of rows in the transformed data
    row_count = transformed_data.shape[0]
    parq_link = quick_save_parquet_link(
        df=transformed_data,
        config=conf,
        context=context,
        filename="After_Close_Diff_Transform_Test",
        model_metadata=model_metadata
    )

    context.log.info(f"Transformed test data row count: {row_count}")
    context.add_output_metadata(
        {
            "row_count": MetadataValue.int(row_count),
            "sample_tail": MetadataValue.md(transformed_data.tail().to_markdown()),
            "close_transform_columns": MetadataValue.text(", ".join(close_diff_features)),  
            "Parquet_Close_Transform_Test_Link": MetadataValue.url(parq_link),
        }
    )   
    return transformed_data

@asset
def add_labels_test(context, close_diff_transform_test: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Add labels for high and low prices based on the configuration in the test data.
    
    Args:
        close_diff_transform_test (pd.DataFrame): DataFrame containing the test data with transformed columns.

    Returns:
        pd.DataFrame: DataFrame with added labels for high and low prices.
    """
    conf = training_config.load()
    cfg = conf['common_config']
    # Add labels for high and low prices
    labeled_data = add_labels_high_low(close_diff_transform_test, config=cfg)
    parq_link = quick_save_parquet_link(
        df=labeled_data,
        config=conf,
        context=context,
        filename="After_Adding_Labels_Test",
        model_metadata=model_metadata
    )

    context.add_output_metadata(
        {
            "column_count": MetadataValue.int(labeled_data.shape[1]),
            "sample_tail": MetadataValue.md(labeled_data.tail().to_markdown()),
            "Parquet_Add_Labels_Test_Link": MetadataValue.url(parq_link),

        }
    )
    return labeled_data


@asset
def scale_data_test(context, add_labels_test: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> pd.DataFrame:
    """
    Scale the test data using Min-Max scaling.
    
    Args:
        add_labels_test (pd.DataFrame): DataFrame containing the test data with added labels.

    Returns:
        pd.DataFrame: Scaled DataFrame.
    """
    conf = training_config.load()
    scaled_data = scale_features(
        df=add_labels_test,
        config=conf,
        context=context,
        model_metadata=model_metadata,
        train_or_test='test',
        scaler_path=''
    )

    return scaled_data

@asset
def input_output_df_test(context, scale_data_test: pd.DataFrame, training_config: TrainingConfig, model_metadata) -> dict:
    """
    Prepare input and output DataFrames for the test data.
    
    Args:
        scale_data_test (pd.DataFrame): DataFrame containing the scaled test data.

    Returns:
        dict: Dictionary containing input and output DataFrames.
    """
    conf = training_config.load()
    training_features = get_all_training_features(conf)
    high_label = conf['training_details']['high_label_column']
    low_label = conf['training_details']['low_label_column']
    output_dict = {
        'input_df': scale_data_test[training_features],
        'output_high_df': scale_data_test[[high_label]],
        'output_low_df': scale_data_test[[low_label]],
    }
    
    run_id = context.run_id
    parq_filename = f"Test_Features_With_Labels.parquet"
    parq_link = save_df_parquet_link(
        pd.concat([output_dict['input_df'], output_dict['output_high_df'], output_dict['output_low_df']], axis=1),
        config=conf,
        run_id=run_id,
        filename=parq_filename,
        model_metadata=model_metadata
    )

    context.add_output_metadata(
        {
            "input_columns": MetadataValue.text(", ".join(training_features)),
            "input_column_number": MetadataValue.int(len(training_features)),
            "output_high_column": MetadataValue.text(high_label),
            "output_low_column": MetadataValue.text(low_label),
            "sample_input_head": MetadataValue.md(scale_data_test[training_features].head().to_markdown()),
            "sample_output_high_head": MetadataValue.md(scale_data_test[[high_label]].head().to_markdown()),
            "sample_output_low_head": MetadataValue.md(scale_data_test[[low_label]].head().to_markdown()),
            "Parquet_Input_Output_Test_Link": MetadataValue.url(parq_link),
        }
    )

    return output_dict

@asset
def evaluate_model(context, input_output_df_test: dict, scale_data_test:pd.DataFrame, train_model_high, train_model_low, mlflow_resource:MLFlowResource, training_config: TrainingConfig, model_metadata, start_mlflow_parent_run) -> pd.DataFrame:
    models_dict = {
        'train_model_high': train_model_high,
        'train_model_low': train_model_low
    }

    conf = training_config.load()
    evaluation_results = get_model_evaluation(
        input_output_df_test=input_output_df_test,
        models=models_dict,
        config=conf,
        context=context,
        model_metadata=model_metadata,
        mlflow_resource=mlflow_resource,
        parent_run_id=start_mlflow_parent_run['parent_run_id'],
        original_data=scale_data_test
    )
    return evaluation_results

