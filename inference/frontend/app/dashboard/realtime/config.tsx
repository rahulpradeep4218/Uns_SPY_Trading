'use client';

import { usePageContext } from "@/context/PageContext";
import { useState, useEffect } from "react";
import { SimulationOptionsForm, defaultSimulationOptions } from "@/components/SimulationOptions";
import { SimulationOptions, TradeSession } from "@/app/types";
import axios from "axios";
import { DateTime } from "luxon";
import { renderTradeMarkers } from '@/components/sciChart/renderTradeMarkers';
import { set } from "lodash";

export default function RealtimeConfig() {
    const { setSidebarFields,
        model_high_alias,
        setModelHighAlias,
        model_low_alias,
        setModelLowAlias,
        simulationOptions,
        setSimulationOptions,
        model_high_version,
        setModelHighVersion,
        model_low_version,
        setModelLowVersion,
        tradeStats,
        setTradeStats,
        tradeRecords,
        setTradeRecords,
        candleDataSeriesRef,
        sciChartSurfaceRef,
        tradeMarkerMapRef,
        isRealtime,
        setIsRealtime,
        selected_session,
        setSelectedSession,
     } = usePageContext();

    const low_model_name = process.env.NEXT_PUBLIC_LOW_MODEL_NAME || 'low_model';
    const high_model_name = process.env.NEXT_PUBLIC_HIGH_MODEL_NAME || 'high_model';
    const realtime_session_id = 0;
    const handleOptionsSubmit = (options: SimulationOptions) => {
        setSimulationOptions?.(options);
    };
    
    const inf_url = process.env.NEXT_PUBLIC_INF_URL;
    console.log("INF URL:", inf_url);
    const syncRealtimeSession = async (updates: Partial<TradeSession>) => {
        try{
            await axios.put(`${inf_url}/api/trade_sessions/${realtime_session_id}`, updates);
            console.log("Realtime session updated successfully:", updates);
        } catch (error) {
            console.error("Error updating realtime session:", error);
        }
    };

    const fetchModelAliases = async ()=> {
        try{
            
            const res = await fetch(`${inf_url}/api/mlflow/models_info`);
            const data = await res.json();
            console.log("Model Aliases:", data);
            return data;
        } catch (error) {
            console.error("Error fetching model aliases:", error);
        }
    };


    useEffect(() => {
        const updateCurrentSessionData = (sess_id: number) => {
            const fetchSessionDetails = async () => {
                try{
                    console.log("Fetching session details for ID:", sess_id);
                    const response = await axios.get(`${process.env.NEXT_PUBLIC_INF_URL}/api/process/get_session/${sess_id}/`);
                    console.log("Session details response:", response.data);
                    const session_record = response.data.session
                    const trade_stats = response.data.trade_stats;
                    const trade_records = response.data.trades;
                    const last_trade_signal_time = response.data.last_trade_signal_time;
                    console.log("Fetched session details:", session_record);
                    setModelHighAlias(session_record.model_high_alias);
                    console.log("Setting model_high_alias to:", session_record.model_high_alias);
                    setModelHighVersion(session_record.model_high_version);
                    setModelLowAlias(session_record.model_low_alias);
                    setModelLowVersion(session_record.model_low_version);

                    setTradeStats(trade_stats);
                    setTradeRecords(trade_records);

                    setIsRealtime?.(true); // Ensure realtime is set to true for this component
                    

                    const inf_url = process.env.NEXT_PUBLIC_INF_URL;
                    let ohlcDataUrl = `${inf_url}/api/price_data/${session_record.symbol}`;
                    if (last_trade_signal_time) {
                        ohlcDataUrl += `?end_time=${last_trade_signal_time}`;
                    }
                        
                    const res = await fetch(ohlcDataUrl)
                    const ohlcData = await res.json();
                    const xValues = ohlcData.map((item: any) => {
                        const dt = DateTime.fromISO(item.time, { zone: "America/New_York" });
                        if (!dt.isValid) {
                            console.error("Invalid date in OHLC data:", item.time);
                            return null; // or handle the error as needed
                        }
                        return dt.toMillis();
                    });
                    const openValues = ohlcData.map((item: any) => item.open);
                    const highValues = ohlcData.map((item: any) => item.high);
                    const lowValues = ohlcData.map((item: any) => item.low);
                    const closeValues = ohlcData.map((item: any) => item.close);
                    
                    await candleDataSeriesRef?.current?.clear();
                    await candleDataSeriesRef?.current?.appendRange(
                        xValues,
                        openValues,
                        highValues,
                        lowValues,
                        closeValues
                    );

                    //sciChartSurfaceRef.current?.zoomExtents();
                    renderTradeMarkers?.(
                            sciChartSurfaceRef?.current!,
                            trade_records,
                            tradeMarkerMapRef
                        );


                } catch (error) {
                    console.error("Error fetching session details:", error);
                }
            };
            fetchSessionDetails();
        }
        updateCurrentSessionData(realtime_session_id);

    }, []);


    useEffect(() => {
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
                                onChange={async (e) => {
                                    const alias = e.target.value;
                                    const version = modelAliases_mlflow[high_model_name][alias]?.version || '';
                                    setModelHighAlias(alias);
                                    setModelHighVersion(version);
                                    console.log("Version type :", typeof version);
                                    await syncRealtimeSession({
                                        model_high_alias: alias,
                                        model_high_version: version
                                    });
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
                                onChange={async (e) => {
                                    const alias = e.target.value;
                                    const version = modelAliases_mlflow[low_model_name][alias]?.version || '';
                                    setModelLowAlias(alias);
                                    setModelLowVersion(version);

                                    await syncRealtimeSession({
                                        model_low_alias: alias,
                                        model_low_version: version
                                    });
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
    
                    </div>
    
                    
                    <SimulationOptionsForm onSubmit={handleOptionsSubmit} initialValues={defaultSimulationOptions}/>
                </>
            );
        }
        update_config();
    }, [model_high_alias, model_low_alias]);
        
    return null; // This component does not render anything directly
    
}