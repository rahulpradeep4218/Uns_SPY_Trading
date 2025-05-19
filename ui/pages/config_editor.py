from numpy import isin
import streamlit as st
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from pathlib import Path

CONFIG_PATH = Path("Config/training.yaml")
yaml = YAML()
yaml.preserve_quotes = True



def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r') as file:
            config = yaml.load(file)
            return config
    else:
        st.error("Configuration file not found!")
        # Optionally, you can return a default config or an empty dict
        # return {"indicators": {"available": "", "selected": ""}}
    return {}

def save_config(config):
    with open(CONFIG_PATH, 'w') as file:
        yaml.dump(config, file)
        st.success("Configuration saved successfully!")

#Load Configuration
config = load_config()
indicator_config = config.get('indicators', {})
available_indicators = indicator_config.get('available', "").split(',')
selected_indicators = indicator_config.get('selected', "").split(',')

#UI
st.title("Configuration Editor")
selected_indicators_ctl = st.multiselect(
    "Select Indicators",
    options=available_indicators,
    default=selected_indicators
)

skip_keys = ['available', 'selected']

for name, settings in indicator_config.items():
    #st.write(f"### {name.upper()} SETTINGS : {type(settings)}")
    if name in skip_keys or not isinstance(settings, CommentedMap):
        #st.warning(f"Skipping {name} as it is not a valid settings map.")
        continue
    
    st.subheader(f"{name.upper()} SETTINGS")
    for key, value in settings.items():
        new_value = st.text_input(f"{name} -> {key}", value=str(value))
        if new_value != value:
            config['indicators'][name][key] = type(value)(new_value)

if st.button("Save Configuration"):
    if config['indicators'] is not None:
        config['indicators']['selected'] = ",".join(selected_indicators_ctl)
        save_config(config)
    else:
        st.error("No configuration found to save.")


