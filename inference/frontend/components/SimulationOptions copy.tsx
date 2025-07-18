import { SimulationOptions, SimulationOptionsFormProps } from "@/app/types";

import { usePageContext } from "@/context/PageContext";

import React from "react";

import { useEffect } from "react";

import {
    Box, 
    Checkbox,
    FormControlLabel,
    FormControl,
    FormGroup,
    InputLabel,
    MenuItem,
    Select,
    TextField,
    Typography,
    Paper,
    Slider,
    SelectChangeEvent,
    Divider,
    Button,
    Grid,
    Stack
} from "@mui/material";
import { set } from "lodash";

export const defaultSimulationOptions: SimulationOptions = {
    close_at_eod: false,
    max_hold_time: 120, // in minutes
    sl_type: "percent",
    sl_value: 0.5, // 50%
    tp_type: "abs",
    tp_value: 2, // $2.00
    max_gap_days_allowed: 5,
    sell_or_buy_threshold: 3, // 3%
    risk_threshold: 0.8, // 80%
    allow_multiple_open_trades: true,
    close_using_signal: true,
    speed: 2, // Fast speed
};

export const SimulationOptionsForm: React.FC<SimulationOptionsFormProps> = ({
    onSubmit,
    initialValues = {}
}) => {
    const [formValues, setFormValues] = React.useState<SimulationOptions>({
        ...defaultSimulationOptions,
        ...initialValues
    });

    const { simulationOptions, setSimulationOptions } = usePageContext();

    useEffect(() => {
        setSimulationOptions?.(initialValues)
    }, [initialValues, setSimulationOptions]);

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value, type, checked } = e.target;
        const newValue = type === "checkbox" ? checked : value;
        const updatedValues = {
            ...formValues,
            [name]: newValue
        };
        setFormValues(updatedValues);
        onSubmit(updatedValues);
    };

    const handleSelectChange = (e: SelectChangeEvent) => {
        const { name, value } = e.target;
        const updatedValues = {
            ...formValues,
            [name]: value
        };
        setFormValues(updatedValues);
        onSubmit(updatedValues);
    };

    const handleSliderChange = (name: keyof SimulationOptions) =>
        (e: Event, value: number | number[]) => {
        const updatedValues = {
            ...formValues,
            [name]: Array.isArray(value) ? value[0] : value
        };
        setFormValues(updatedValues);
        onSubmit(updatedValues);
    };

    return (
         <Box sx={{ 
            display: 'flex', 
            flexDirection: 'column',
            height: '300px', // Ensure the container takes full height
            width: '100%',
        }}>
            <Typography variant="subtitle1" gutterBottom>
                Simulation Settings
            </Typography>
            
            {/* Fixed height scrollable area */}
            <Paper 
                sx={{
                    flex: 1,
                    overflowY: 'auto',
                    p: 2,
                    backgroundColor: 'rgba(250, 250, 250, 0.96)',
                    borderRadius: 1,
                    mb: 2, // Space between scroll area and button
                    '&::-webkit-scrollbar': {
                        width: '6px',
                    },
                    '&::-webkit-scrollbar-track': {
                        background: 'rgba(0,0,0,0.05)',
                        borderRadius: '3px',
                    },
                    '&::-webkit-scrollbar-thumb': {
                        background: 'rgba(0,0,0,0.2)',
                        borderRadius: '3px',
                    },
                    '&::-webkit-scrollbar-thumb:hover': {
                        background: 'rgba(0,0,0,0.3)',
                    }
                }}
            >
                <Stack spacing={2} sx={{ 
                    fontSize: '0.75rem',
                    '& .MuiTextField-root': {
                        fontSize: '0.75rem',
                        '& .MuiInputBase-root': {
                            fontSize: 'inherit',
                        },
                    },
                    '& .MuiFormControlLabel-root': {
                        margin: 0,
                        padding: '2px 0',
                        '& .MuiFormControlLabel-label': {
                            fontSize: '0.75rem',
                            marginTop: '1px'
                        },
                    },
                }}>
                    {/* Boolean Options */}
                    <FormControlLabel
                        control={
                            <Checkbox
                                size="small"
                                checked={formValues.close_at_eod}
                                onChange={handleInputChange}
                                name="close_at_eod"
                            />
                        }
                        label="Close at EOD"
                    />

                    <FormControlLabel 
                        control={
                            <Checkbox
                                size="small"
                                checked={formValues.allow_multiple_open_trades}
                                onChange={handleInputChange}
                                name="allow_multiple_open_trades"
                            />
                        }
                        label="Multiple Trades"
                    />

                    <FormControlLabel
                        control={
                            <Checkbox
                                size="small"
                                checked={formValues.close_using_signal}
                                onChange={handleInputChange}
                                name="close_using_signal"
                            />
                        }
                        label="Close on Signal"
                    />

                    {/* Numeric Inputs */}
                    <TextField
                        size="small"
                        label="Max Hold (min)"
                        type="number"
                        name="max_hold_time"
                        value={formValues.max_hold_time}
                        onChange={handleInputChange}
                        fullWidth
                        InputProps={{
                            inputProps: {
                                min: 1,
                                step: 1,
                            },
                        }}
                    />

                    <TextField
                        size="small"
                        label="Max Gap Days"
                        type="number"
                        name="max_gap_days_allowed"
                        value={formValues.max_gap_days_allowed}
                        onChange={handleInputChange}
                        fullWidth
                        InputProps={{
                            inputProps: {
                                min: 0,
                            },
                        }}
                    />

                    <TextField
                        size="small"
                        label="Sell/Buy Threshold (%)"
                        type="number"
                        name="sell_or_buy_threshold"
                        value={formValues.sell_or_buy_threshold}
                        onChange={handleInputChange}
                        fullWidth
                        InputProps={{
                            inputProps: {
                                min: 0,
                                max: 100,
                                step: 0.1,
                            },
                        }}
                    />

                    <TextField
                        size="small"
                        label="Risk Threshold"
                        type="number"
                        name="risk_threshold"
                        value={formValues.risk_threshold}
                        onChange={handleInputChange}
                        fullWidth
                        InputProps={{
                            inputProps: {
                                min: 0,
                                max: 1,
                                step: 0.01,
                            },
                        }}
                    />

                    {/* Stop Loss */}
                    <FormControl size="small" fullWidth>
                        <InputLabel>SL Type</InputLabel>
                        <Select
                            name="sl_type"
                            value={formValues.sl_type}
                            label="SL Type"
                            onChange={handleSelectChange}
                        >
                            <MenuItem value="percent">%</MenuItem>
                            <MenuItem value="abs">$</MenuItem>
                            <MenuItem value="model">Model</MenuItem>
                        </Select>
                    </FormControl>

                    <TextField
                        size="small"
                        label={
                            formValues.sl_type === "percent"
                                ? "SL Value (%)"
                                : "SL Value ($)"
                        }
                        type="number"
                        name="sl_value"
                        value={formValues.sl_value}
                        onChange={handleInputChange}
                        fullWidth
                        InputProps={{
                            inputProps: {
                                min: 0,
                                step: formValues.sl_type === "percent" ? 0.1 : 0.01,
                            },
                        }}
                    />

                    {/* Take Profit */}
                    <FormControl size="small" fullWidth>
                        <InputLabel>TP Type</InputLabel>
                        <Select
                            name="tp_type"
                            value={formValues.tp_type}
                            label="TP Type"
                            onChange={handleSelectChange}
                        >
                            <MenuItem value="abs">$</MenuItem>
                            <MenuItem value="model">Model</MenuItem>
                        </Select>
                    </FormControl>

                    <TextField
                        size="small"
                        label="TP Value"
                        type="number"
                        name="tp_value"
                        value={formValues.tp_value}
                        onChange={handleInputChange}
                        fullWidth
                        InputProps={{
                            inputProps: {
                                min: 0,
                                step: 0.01,
                            },
                        }}
                    />

                    {/* Speed Slider */}
                    <Box>
                        <Typography variant="body2" gutterBottom>
                            Speed: {formValues.speed}
                        </Typography>
                        <Slider
                            size="small"
                            value={formValues.speed}
                            onChange={handleSliderChange("speed")}
                            valueLabelDisplay="auto"
                            step={1}
                            marks
                            min={1}
                            max={10}
                        />
                    </Box>
                </Stack>
            </Paper>
        </Box>
    );

}