from dagster import asset, MetadataValue, MaterializeResult
import pandas as pd
from functions.indicators import add_all_indicators

@asset(config_schema={
    "sheet_names": str,
    "all_data_path": str,
    "start_date": str,
    "end_date": str,
})
def load_data(context) -> pd.DataFrame:
    """
    Load data from an Excel file and filter it based on the provided date range.
    
    Args:
        sheet_names (str): Comma-separated string of sheet names to load.
        all_data_path (str): Path to the Excel file.
        start_date (str): Start date for filtering data.
        end_date (str): End date for filtering data.

    Returns:
        pd.DataFrame: Filtered DataFrame containing the loaded data.
    """

    cfg = context.op_config
    # Split the sheet names into a list
    sheet_names = cfg["sheet_names"]
    all_data_path = cfg["all_data_path"]
    start_date = cfg["start_date"]
    end_date = cfg["end_date"]

    sheet_names = [sheet.strip() for sheet in sheet_names.split(",")]

    # Load data from the specified sheets
    data = pd.concat(pd.read_excel(all_data_path, sheet_name=sheet_names), ignore_index=True)

    # Convert 'Date' column to datetime format
    data['Date'] = pd.to_datetime(data['Date'])

    # Filter data based on the provided date range
    train_start_date = pd.to_datetime(start_date)
    train_end_date = pd.to_datetime(end_date)
    filtered_data = data[(data['Date'] >= train_start_date) & (data['Date'] <= train_end_date)]
    filtered_data = filtered_data.reset_index(drop=True)

    #Remove symbol column
    filtered_data.drop(columns=['Symbol'], inplace=True)
    row_count = filtered_data.shape[0]
    context.log.info(f"Number of rows in the filtered data: {row_count}")
    context.add_output_metadata(
        {
            "row_count": MetadataValue.int(row_count),
            "start_date": MetadataValue.text(start_date),
            "end_date": MetadataValue.text(end_date),
            "sample": MetadataValue.md(filtered_data.head().to_markdown()),
        }
    )
    return filtered_data

@asset
def add_indicators(context, load_data: pd.DataFrame) -> pd.DataFrame:
    """
    Add technical indicators to the loaded data.

    Args:
        load_data (pd.DataFrame): DataFrame containing the loaded data.

    Returns:
        pd.DataFrame: DataFrame with added indicators.
    """
    cfg = context.op_config
    # Add all indicators to the data
    data_with_indicators = add_all_indicators(load_data, cfg)
    
    # Log the number of rows in the data with indicators
    row_count = data_with_indicators.shape[0]
    context.log.info(f"Number of rows in the data with indicators: {row_count}")
    
    # Add metadata for the asset
    context.add_output_metadata(
        {
            "column_count": MetadataValue.int(data_with_indicators.shape[1]),
            "row_count": MetadataValue.int(row_count),
            "sample": MetadataValue.md(data_with_indicators.head().to_markdown()),
        }
    )
    
    return data_with_indicators