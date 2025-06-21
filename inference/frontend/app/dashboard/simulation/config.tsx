'use client';

import { usePageContext } from "@/context/PageContext";
import { useState, useEffect, useRef } from "react";
import TimelineSelection from "@/components/TimelineSelection";

export default function SimulationConfig() {
    const { 
        setSidebarFields, 
        model, 
        setModel, 
        model_alias, 
        setModelAlias, 
        timeRange,
        setTimeRange,
        showTimePickerFor,
        setShowTimePickerFor
    } = usePageContext();
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
        return date.toLocaleString();
    };

    const buttonRefs = {
        start: useRef<HTMLButtonElement>(null),
        end: useRef<HTMLButtonElement>(null)
    }
    useEffect(() => {

        const fetchModelAliases = async ()=> {
            try{
                const inf_url = process.env.NEXT_PUBLIC_INF_URL;
                const res = await fetch(`${inf_url}/api/mlflow/aliases`);
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
                        <label className="text-sm text-gray-50">Model</label>
                        <select 
                            className="w-full p-1 mt-1 rounded bg-gray-700 text-white"
                            value={model || ''}
                            onChange={(e) => {
                                setModel(e.target.value);
                                setModelAlias(''); // Reset alias when model changes
                            }}
                        >
                            <option value="">Select Model</option>
                            {Object.keys(modelAliases_mlflow).map((m) => (
                                <option key={m}>{m}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="text-sm text-gray-50 mt-2">Alias</label>
                        <select
                            className="w-full p-1 mt-1 rounded bg-gray-700 text-white"
                            value={model_alias || ''}
                            onChange={(e) => setModelAlias(e.target.value)}
                        >
                            <option value="">Select Alias</option>
                            {( modelAliases_mlflow[model] || []).map((al) => (
                                <option key={al}>{al}</option>
                            ))}
                        </select>
                    </div>

                    {['start', 'end'].map((timeType) => (
                        <div key={timeType} className="w-full">
                            <label className="block text-sm text-gray-50 mb-1">
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
                    ))},
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
                </>
            );
        }
        update_config();
    }, [model, model_alias, timeRange, showTimePickerFor]);
        
    return null; // This component does not render anything directly
    
}