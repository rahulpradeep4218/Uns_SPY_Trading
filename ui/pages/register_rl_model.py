import streamlit as st
import mlflow
from mlflow.tracking import MlflowClient
from pathlib import Path
import yaml
import os
import re


config_path_env = os.getenv('CONFIG_CONTAINER_PATH', '/app/config.yaml')
CONFIG_PATH = Path(config_path_env)
with open(CONFIG_PATH, 'r') as file:
    conf = yaml.safe_load(file)

# --- Configuration ---
MLFLOW_TRACKING_URI = conf['mlflow']['tracking_uri']
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


def register_and_tag_model(run_id: str, checkpoint_folder: str, model_name: str):
    """Registers a model and adds a 'checkpoint' tag with the extracted number."""
    client = MlflowClient()
    try:
        # 1. Register the model
        model_uri = f"runs:/{run_id}/{checkpoint_folder}"
        result = mlflow.register_model(model_uri, model_name)
        
        # 2. Extract number from 'checkpoint_1000' -> '1000'
        # Uses regex to find all digits in the folder name
        match = re.search(r'(\d+)', checkpoint_folder)
        checkpoint_num = match.group(1) if match else "unknown"
        
        # 3. Set the tag on the specific VERSION created
        client.set_model_version_tag(
            name=model_name,
            version=result.version,
            key="checkpoint",
            value=checkpoint_num
        )
        
        return result, checkpoint_num
    except Exception as e:
        st.error(f"Error: {e}")
        return None, None

# --- Streamlit UI ---
st.set_page_config(page_title="MLflow Registry Tool", page_icon="🏷️")

st.title("🏷️ Smart Checkpoint Registrar")
st.info("This tool automatically extracts the checkpoint number and tags it in MLflow.")

with st.form("reg_form"):
    run_id = st.text_input("Run ID", placeholder="e.g., ab12345...")
    checkpoint_folder = st.text_input("Checkpoint Folder", placeholder="checkpoint_500")
    model_name = st.text_input("Model Name", placeholder="my_awesome_model")
    
    submit = st.form_submit_button("Register & Tag")

if submit:
    if run_id and checkpoint_folder and model_name:
        with st.spinner("Registering and applying tags..."):
            result, cp_val = register_and_tag_model(run_id, checkpoint_folder, model_name)
            
            if result:
                st.success(f"✅ Registered **{model_name}** Version **{result.version}**")
                st.markdown(f"**Tag Applied:** `checkpoint: {cp_val}`")
                st.balloons()
    else:
        st.warning("All fields are required.")