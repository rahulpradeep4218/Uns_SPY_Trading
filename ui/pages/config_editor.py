from numpy import save
import streamlit as st
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarfloat import ScalarFloat
from pathlib import Path
from streamlit import rerun
from io import StringIO


CONFIG_PATH = Path("Config/training.yaml")
CONFIG_PATH2 = Path("Config/training2.yaml")
yaml = YAML()
yaml.preserve_quotes = True

type_dict = {
    'int': int,
    'float': float,
    'str': str,
    'bool': bool
}

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

def sanitize_yaml(data):
    if isinstance(data, CommentedMap):
        return {k: sanitize_yaml(v) for k, v in data.items()}
    elif isinstance(data, CommentedSeq):
        return [sanitize_yaml(i) for i in data]
    elif isinstance(data, ScalarFloat):
        return float(data)
    else:
        return data
    

def save_config(config):
    #find_yaml_issue_ruamel(config)
    config = sanitize_yaml(config)
    with open(CONFIG_PATH, 'w') as file:
        yaml.dump(config, file)
        st.success("Configuration saved successfully!")



def update_config_available(config):
    if config['indicators'] is not None:
        config['indicators']['available'] = ",".join(st.session_state['available'])
        #save_config(config)
    else:
        st.error("No configuration found to save.")

def indicator_state_transform_init(ind):
    """
    Initialize the state of the indicator transform.
    """
    st.session_state['transform'][ind] = {}
    st.session_state['transform'][ind]['close_transform'] = False
    st.session_state['transform'][ind]['minmax'] = False
    st.session_state['transform'][ind]['standard'] = False
    st.session_state['transform'][ind]['robust'] = False

config = load_config()

indicator_config = config.get('indicators', {})

#Load Configuration
if 'available' not in st.session_state:
    #Initialize session state
    st.session_state['available'] = indicator_config.get('available', "").split(',')
    st.session_state['selected'] = indicator_config.get('selected', "").split(',')
    close_transform_lst = (config['common_config'].get('close_transform_columns', '') or '').split(',')
    minmax_scaling_lst = (config['scaling']['minmax']['columns'] or '').split(',')
    standard_scaling_lst = (config['scaling']['standard']['columns'] or '').split(',')
    robust_scaling_lst = (config['scaling']['robust']['columns'] or '').split(',')
    model_parameters = config['training_parameters']['params_list']
    active_model_parameters = config['training_parameters']['active_parameters'].split(',')
    base_model_parameters = config['training_parameters']['base_parameters'].split(',')


    st.session_state['transform'] = {}
    for ind in st.session_state['available']:
        st.session_state['transform'][ind] = {}
        st.session_state['transform'][ind]['close_transform'] = True if ind in close_transform_lst else False
        st.session_state['transform'][ind]['minmax'] = True if ind in minmax_scaling_lst else False
        st.session_state['transform'][ind]['standard'] = True if ind in standard_scaling_lst else False
        st.session_state['transform'][ind]['robust'] = True if ind in robust_scaling_lst else False
    st.session_state['model_parameters'] = {}
    for par in model_parameters:
        par_name = par['name']
        st.session_state['model_parameters'][par_name] = {}
        st.session_state['model_parameters'][par_name]['active'] = True if par_name in active_model_parameters else False
        st.session_state['model_parameters'][par_name]['type'] = par['type']
        st.session_state['model_parameters'][par_name]['value'] = par.get('value', '')
        st.session_state['model_parameters'][par_name]['hp'] = True if par.get('hp', False) else False
        st.session_state['model_parameters'][par_name]['min'] = par.get('min', '')
        st.session_state['model_parameters'][par_name]['max'] = par.get('max', '')
        st.session_state['model_parameters'][par_name]['base'] = True if par_name in base_model_parameters else False
        st.session_state['model_parameters'][par_name]['log'] = par.get('log', False)

        


        
    st.session_state['ma_periods'] = [maperiod for maperiod in st.session_state['available'] if maperiod.startswith('ma_')]
    st.session_state['ema_periods'] = [maperiod for maperiod in st.session_state['available'] if maperiod.startswith('ema_')]


#UI
st.title("Configuration Editor")
selected_indicators_ctl = st.multiselect(
    "Select Indicators",
    options=st.session_state['available'],
    default=st.session_state['selected'],
)

st.subheader("Training Parameters")
training_parameters = config.get('training_details', {})
for key, value in training_parameters.items():
    new_Value = st.text_input(f"training_{key}", value=str(value))
    if new_Value != value:
        config['training_details'][key] = type(value)(new_Value)

st.subheader("Common Configuration")
common_config = config.get('common_config', {})
for key, value in common_config.items():
    new_value = st.text_input(f"common_{key}", value=str(value))
    if new_value != value:
        config['common_config'][key] = type(value)(new_value)
# UI for managing MA and EMA
st.subheader("Moving Averages / Exponential Averages Management")
tab1, tab2 = st.tabs(["MA", "EMA"])

with tab1:
    st.subheader("MA Periods")
    new_ma = st.text_input("Add MA Period", key="ma_input")
    if st.button("Add MA Period"):
        period_key = f"ma_{new_ma}"
        if period_key not in st.session_state['ma_periods']:
            st.session_state['ma_periods'].append(period_key)
            st.session_state['available'].append(period_key)
            indicator_state_transform_init(period_key)
            rerun()
    
    for period in st.session_state['ma_periods']:
        col1, col2 = st.columns([6, 1])
        col1.write(period)
        if col2.button("remove" , key = f"remove_ma_{period}"):
            st.session_state['ma_periods'].remove(period)
            st.session_state['available'].remove(period)
            # Remove from selected if it was selected
            if period in st.session_state['selected']:
                st.session_state['selected'].remove(period)
            rerun()

with tab2:
    st.subheader("EMA Periods")
    new_ema = st.text_input("Add EMA Period", key="ema_input")
    if st.button("Add EMA Period"):
        period_key = f"ema_{new_ema}"
        if period_key not in st.session_state['ema_periods']:
            st.session_state['ema_periods'].append(period_key)
            st.session_state['available'].append(period_key)
            indicator_state_transform_init(period_key)
            rerun()
    
    for period in st.session_state['ema_periods']:
        col1, col2 = st.columns([6, 1])
        col1.write(period)
        if col2.button("remove" , key = f"remove_ema_{period}"):
            st.session_state['ema_periods'].remove(period)
            st.session_state['available'].remove(period)
            # Remove from selected if it was selected
            if period in st.session_state['selected']:
                st.session_state['selected'].remove(period)
            rerun()

skip_keys = ['available', 'selected']

indicator_parameters = indicator_config.get('parameters', {})
for name, settings in indicator_parameters.items():

    st.subheader(f"{name.upper()} SETTINGS")
    for key, value in settings.items():
        new_value = st.text_input(f"{name} -> {key}", value=str(value))
        if new_value != value:
            config['indicators']['parameters'][name][key] = type(value)(new_value)


# Table for close transform and scaling
updated_config = {}
st.subheader("Close Transform and Scaling")
header = st.columns([3,2,2,2,2])
header[0].markdown("**Indicator**")
header[1].markdown("**MinMax Scaling**")
header[2].markdown("**Standard Scaling**")
header[3].markdown("**Robust Scaling**")
header[4].markdown("**Close Transform**")



for ind in st.session_state['available']:
    row = st.columns([3,2,2,2,2])
    row[0].markdown(f"**{ind}**")
    minmax_scaling = row[1].checkbox("MinMax", value=st.session_state['transform'][ind]['minmax'], key=f"minmax_{ind}")
    standard_scaling = row[2].checkbox("Standard", value=st.session_state['transform'][ind]['standard'], key=f"standard_{ind}")
    robust_scaling = row[3].checkbox("Robust", value=st.session_state['transform'][ind]['robust'], key=f"robust_{ind}")
    close_transform = row[4].checkbox("Close", value=st.session_state['transform'][ind]['close_transform'], key=f"close_transform_{ind}")
    st.session_state['transform'][ind] = {
        'minmax': minmax_scaling,
        'standard': standard_scaling,
        'robust': robust_scaling,
        'close_transform': close_transform
    }

st.subheader("Model Parameters and Hyperparameters")

header = st.columns([3,2,3,2,2,2,2,2,4])
header[0].markdown("**Name**")
header[1].markdown("**Active**")
header[2].markdown("**Type**")
header[3].markdown("**HP?**")
header[4].markdown("**Min**")
header[5].markdown("**Max**")
header[6].markdown("**Base**")
header[7].markdown("**Log**")
header[8].markdown("**Value**")

for par, settings in st.session_state['model_parameters'].items():
    row = st.columns([3,2,3,2,2,2,2,2,4])
    row[0].markdown(f"**{par}**")
    active = row[1].checkbox("", value=settings['active'], key=f"active_{par}")
    type_ = row[2].selectbox("", options=["int", "float", "str"], label_visibility="collapsed", index=["int", "float", "str"].index(settings['type']), key=f"type_{par}")
    hp = row[3].checkbox("", value=settings['hp'], key=f"hp_{par}")
    min_ = row[4].text_input("", value=str(settings['min']), label_visibility="collapsed", key=f"min_{par}")
    max_ = row[5].text_input("", value=str(settings['max']), label_visibility="collapsed", key=f"max_{par}")
    base = row[6].checkbox("", value=settings['base'], key=f"base_{par}")
    log = row[7].checkbox("", value=settings['log'], key=f"log_{par}")
    value = row[8].text_input("", value=str(settings['value']), label_visibility="collapsed", key=f"value_{par}")

    st.session_state['model_parameters'][par] = {
        'active': active,
        'type': type_,
        'hp': hp,
        'min': type_dict[type_](min_) if min_ != '' else '',
        'max': type_dict[type_](max_) if max_ != '' else '',
        'base': base,
        'log': log,
        'value': type_dict[type_](value) if value != '' else ''
    }




if st.button("Save Configuration"):

    if config['indicators'] is not None:
        config['indicators']['selected'] = ",".join(selected_indicators_ctl)
        #save_config(config)
    else:
        st.error("No configuration found to save.")
    update_config_available(config)
    minmax_scaling_lst = [ind for ind in st.session_state['available'] if st.session_state['transform'][ind]['minmax']]
    standard_scaling_lst = [ind for ind in st.session_state['available'] if st.session_state['transform'][ind]['standard']]
    robust_scaling_lst = [ind for ind in st.session_state['available'] if st.session_state['transform'][ind]['robust']]
    close_transform_lst = [ind for ind in st.session_state['available'] if st.session_state['transform'][ind]['close_transform']]
    config['common_config']['close_transform_columns'] = ",".join(close_transform_lst)
    config['scaling']['minmax']['columns'] = ",".join(minmax_scaling_lst)
    config['scaling']['standard']['columns'] = ",".join(standard_scaling_lst)
    config['scaling']['robust']['columns'] = ",".join(robust_scaling_lst)

    config['training_parameters']['params_list'] = []
    config['training_parameters']['active_parameters'] = ','.join([ind for ind in st.session_state['model_parameters'] if st.session_state['model_parameters'][ind]['active']])
    config['training_parameters']['base_parameters'] = ','.join([ind for ind in st.session_state['model_parameters'] if st.session_state['model_parameters'][ind]['base']])
    for par, settings in st.session_state['model_parameters'].items():
        config['training_parameters']['params_list'].append({
            'name': par,
            'type': settings['type'],
            'hp': settings['hp'],
            'log': settings['log'],
            **({'min': settings['min']} if settings['min'] != '' else {}),
            **({'max': settings['max']} if settings['max'] != '' else {}),
            **({'value': settings['value']} if settings['value'] != '' else {}),
        })


    save_config(config)
    rerun()



# === Debug Info === (Optional)
st.markdown("---")
st.text("Available: " + str(st.session_state["available"]))
st.text("MA Periods: " + str(st.session_state["ma_periods"]))
st.text("Selected: " + str(st.session_state["selected"]))