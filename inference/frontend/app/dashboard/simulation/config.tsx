'use client';

import { usePageContext } from "@/context/PageContext";
import { useState, useEffect, useRef } from "react";
import TimelineSelection from "@/components/TimelineSelection";
import { SimulationOptionsForm, defaultSimulationOptions } from "@/components/SimulationOptions";
import { SimulationOptions } from "@/app/types";

export default function SimulationConfig() {
    const { 
        setSidebarFields, 
        model_high_alias, 
        setModelHighAlias, 
        model_low_alias, 
        setModelLowAlias, 
        setModelHighVersion,
        setModelLowVersion,
        setTrainingStart,
        setTrainingEnd,
        timeRange,
        setTimeRange,
        showTimePickerFor,
        setShowTimePickerFor,
        simulationOptions,
        setSimulationOptions
    } = usePageContext();
    const low_model_name = process.env.NEXT_PUBLIC_LOW_MODEL_NAME || 'low_model';
    const high_model_name = process.env.NEXT_PUBLIC_HIGH_MODEL_NAME || 'high_model';
    /*
    useEffect(() => {
        console.log("Current picker state : ", showTimePickerFor);
    }, [showTimePickerFor]);
    */

    useEffect(() => {
        if (!showTimePickerFor) return;

        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                console.log("Escape key pressed, closing time picker");
                setShowTimePickerFor(null);
            }
        };

        const handleClickOutside = (event: MouseEvent) => {
            const modal = document.querySelector('.time-picker');
            if (modal && !modal.contains(event.target as Node)) {
                console.log("Clicked outside the time picker, closing it");
                setShowTimePickerFor(null);
            }
        };

        // Add event listeners
        document.addEventListener('keydown', handleKeyDown);
        document.addEventListener('mousedown', handleClickOutside);

        //cleanup
        return () => {
            document.removeEventListener('keydown', handleKeyDown);
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [showTimePickerFor, setShowTimePickerFor]);
    const formatTime = (time: string | null) => {
        if (!time) return 'Not selected';
        const date = new Date(time);
        return date.toLocaleString(undefined,{
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        }

        );
    };

    const buttonRefs = {
        start: useRef<HTMLButtonElement>(null),
        end: useRef<HTMLButtonElement>(null)
    }
    const handleOptionsSubmit = (options: SimulationOptions) => {
        setSimulationOptions(options);
    };
    useEffect(() => {

        const fetchModelAliases = async ()=> {
            try{
                const inf_url = process.env.NEXT_PUBLIC_INF_URL;
                const res = await fetch(`${inf_url}/api/mlflow/models_info`);
                const data = await res.json();
                console.log("Model Aliases:", data);
                return data;
            } catch (error) {
                console.error("Error fetching model aliases:", error);
            }
        };
        const update_config = async () => {
            const modelAliases_mlflow = await fetchModelAliases();

            
            setSidebarFields(
                <>
                <div className="space-y-4 p-2">
                    <div>
                        <label className="text-xs text-gray-50 mt-2">High Model Alias / Version</label>
                        <select
                            className="w-full p-1 mt-1 rounded bg-gray-700 text-white text-xs"
                            value={model_high_alias || ''}
                            onChange={(e) => {
                                setModelHighAlias(e.target.value);
                                setModelHighVersion(modelAliases_mlflow[high_model_name][e.target.value]['version'] || '');
                                if (modelAliases_mlflow[high_model_name][e.target.value]['training_start']) {
                                    setTrainingStart(modelAliases_mlflow[high_model_name][e.target.value]['training_start']);
                                }
                                if (modelAliases_mlflow[high_model_name][e.target.value]['training_end']) {
                                    setTrainingEnd(modelAliases_mlflow[high_model_name][e.target.value]['training_end']);
                                }
                            }}
                        >
                            <option value="">Select High Model Alias</option>
                            {Object.keys(modelAliases_mlflow[high_model_name] || {}).map((al) => (
                                <option key={al} value={al}>
                                    {al} (v{modelAliases_mlflow[high_model_name][al]['version']})
                                </option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="text-xs text-gray-50 mt-2">Low Model Alias / Version</label>
                        <select
                            className="w-full p-1 mt-1 rounded bg-gray-700 text-white text-xs"
                            value={model_low_alias || ''}
                            onChange={(e) => {
                                setModelLowAlias(e.target.value);
                                setModelLowVersion(modelAliases_mlflow[low_model_name][e.target.value]['version'] || '');
                            }}
                        >
                            <option value="">Select Low Model Alias</option>
                            {Object.keys(modelAliases_mlflow[low_model_name] || {}).map((al) => (
                                <option key={al} value={al}>
                                    {al} (v{modelAliases_mlflow[low_model_name][al]['version']})
                                </option>
                            ))}
                        </select>
                    </div>

                    {['start', 'end'].map((timeType) => (
                        <div key={timeType} className="w-full">
                            <label className="block text-xs text-gray-50 mb-1">
                                {timeType === 'start' ? 'Start Time' : 'End Time'}
                            </label>
                            <div className="flex w-full">
                                <input
                                    type="text"
                                    readOnly
                                    value={formatTime(timeRange[timeType as 'start' | 'end'])}
                                    className="flex-1 min-w-0 border rounded-l p-2 text-xs bg-gray-100 text-gray-800 truncate"
                                />
                                <button
                                    ref={buttonRefs[timeType as 'start' | 'end']}
                                    onClick = {() => {
                                        console.log("Button clicked for:", timeType);
                                        //console.log("Current showTimePickerFor:", showTimePickerFor);
                                        setShowTimePickerFor(prev => prev === timeType ? null : timeType);
                                    }}
                                    className="bg-blue-500 text-white px-2 py-1 rounded-r text-xs hover:bg-blue-600"
                                >
                                    Pick
                                </button>

                            </div>
                        </div>
                    ))}
                </div>

                

                {showTimePickerFor && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                        <div className="bg-white rounded-lg w-[90vw] max-w-4xl wifull time-picker">
                            <TimelineSelection
                                symbol='SPY'
                                //value={times[showPickerFor]}
                                onChange={(time) => {
                                        console.log("Selected time:", time);
                                        setTimeRange(prev => ({
                                            ...prev,
                                            [showTimePickerFor]: time
                                        }));

                                        //setShowTimePickerFor(null);
                                    }
                                }
                                onClose={() => setShowTimePickerFor(null)}
                                selectedStart={timeRange.start}
                                selectedEnd={timeRange.end}
                            />
                        </div>
                    </div>
                )}
                <SimulationOptionsForm onSubmit={handleOptionsSubmit} initialValues={defaultSimulationOptions}/>
                </>
            );
        }
        update_config();
    }, [model_high_alias, model_low_alias, timeRange, showTimePickerFor]);
        
    return null; // This component does not render anything directly
    
}