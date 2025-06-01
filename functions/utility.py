from datetime import datetime
import os

def save_df_parquet_link(df, config, run_id, filename, model_metadata={}):
    """
    Save DataFrame to a Parquet file and provide a download link.
    
    Parameters:
    df (pd.DataFrame): The DataFrame to save.
    filename (str): The name of the file to save the DataFrame as.
    
    Returns:
    None
    """
    details_cfg = config['training_details']
    # Save the DataFrame to a Parquet file
    file_path = get_dagster_run_id_path(config, run_id, filename, model_metadata)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    df.to_parquet(file_path, index=False)
    file_path_viewer = get_file_viewer_link(config, run_id, filename, model_metadata)
    parquet_viewer_link = f'{details_cfg['parquet_viewer_link']}?file={file_path_viewer}'
    return parquet_viewer_link


def get_dagster_runs_folder_path(config):
    details_cfg = config['training_details']
    runs_folder = details_cfg['runs_folder']
    return f"../{runs_folder}"

def get_dagster_run_id_path(config, run_id, filename, model_metadata={}):
    first_directory = get_first_directory(config, model_metadata)
    runs_folder = get_dagster_runs_folder_path(config)
    return os.path.join(runs_folder, f'{first_directory}', f'Run_{run_id}', filename)

def get_file_viewer_link(config, run_id, filename, model_metadata={}):
    details_cfg = config['training_details']
    runs_folder = details_cfg['runs_folder']
    first_directory = get_first_directory(config, model_metadata)
    file_path_viewer = f"{runs_folder}/{first_directory}/Run_{run_id}/{filename}"
    return file_path_viewer

def get_ma_columns(value):
    ma_columns = []
    for ind in value.split(","):
        if ind.startswith("ma_"):
            ma_columns.append(ind.replace("ma_", "MA"))
    return ma_columns

def get_ema_columns(value):
    ema_columns = []
    for ind in value.split(","):
        if ind.startswith("ema_"):
            ema_columns.append(ind.replace("ema_", "EMA"))
    return ema_columns

def get_fourier_columns(config):
    fourier_cols = []
    period = config['indicators']['parameters']['fourier']['period']
    n_components = (period - 2) // 2 
    for i in range(1, n_components+1):
        fourier_cols.append(f'fourier_real_{i}')
        fourier_cols.append(f'fourier_imag_{i}')
    return fourier_cols

def get_columns_mapping(value, config):
    """
    Get the mapping of columns based on the value passed on value argument.
    Columns are obtained from columns parameter in the indicator parameters in config.
    
    Args:
        value (str): The name of the indicator.
        config (dict): The configuration dictionary.
    
    Returns:
        str: The mapped column name.
    """
    columns_list = []
    value_list = value.split(",")
    ma_columns = get_ma_columns(value)
    ema_columns = get_ema_columns(value)
    columns_list.extend(ma_columns)
    columns_list.extend(ema_columns)
    if 'fourier' in value_list:
        fourier_columns = get_fourier_columns(config)
        columns_list.extend(fourier_columns)
    for val in value_list:
        if val in config['indicators']['parameters']:
            if 'columns' in config['indicators']['parameters'][val]:
                columns_list.extend(config['indicators']['parameters'][val]['columns'].split(","))

    return columns_list
    
def get_all_training_features(config):
    features = []
    selected_features_str = config['indicators']['selected']
    if selected_features_str and selected_features_str != '':
        features = get_columns_mapping(selected_features_str, config)
    return features


def generate_model_id(model_name):
    return f"{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    

def get_first_directory(config, model_metadata):
    details_cfg = config['training_details']
    model_id = model_metadata.get('model_id', '')
    start_date = details_cfg['train_start_date']
    end_date = details_cfg['train_end_date']
    return f"{model_id}_{start_date}_{end_date}"