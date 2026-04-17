'use client';
import { DateTime } from "luxon";
import { useEffect, useState, useRef } from 'react';

import { usePageContext } from '@/context/PageContext';
import { TradeTable } from '@/components/Trade_Stats/Trade_Records_Table';
import { TradeStatsDisplay } from '@/components/Trade_Stats/Trade_Scorecard';
import { Box, Grid, Typography, Button } from '@mui/material';

import { renderTradeMarkers } from '@/components/sciChart/renderTradeMarkers';
import { init } from "next/dist/compiled/webpack/webpack";
import { defaultSimulationOptions } from "@/components/SimulationOptions";
import { last } from "lodash";



export default function TradeStatsDashboard() {
    const { 
        wsConnection, 
        setWsConnection, 
        tradeStats, 
        setTradeStats, 
        tradeRecords, 
        setTradeRecords, 
        selected_session, 
        setSelectedSession, 
        simulationOptions, 
        setSimulationOptions,
        sciChartSurfaceRef,
        tradeMarkerMapRef,
        simulationRun, // for candle simulation
        setSimulationRun, // for candle simulation
        candleDataSeriesRef,
        realtimeSeriesRef,
        buyTakeProfitRef,
        sellTakeProfitRef,
        isRealtime,
        setIsRealtime,
        sim_type
    } = usePageContext();

    const currentCandleRef = useRef<{
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    } | null>(null);

    const [connectionStatus, setConnectionStatus] = useState('Disconnected');
    const [isSimulationRunning, setIsSimulationRunning] = useState(false);
    const [loading, setLoading] = useState(true);

    const initializeWebSocket = () => {
        console.log("Initialize web socket, selected session:", selected_session, "isRealtime:", isRealtime);

        if (selected_session === null || selected_session === undefined) {
            console.error("No selected session set. Cannot initialize WebSocket.");
            return;
        }
        
        setLoading(true);
        setConnectionStatus('Connecting....');
        const rawUrl = process.env.NEXT_PUBLIC_INF_URL;
        const strippedUrl = rawUrl?.replace(/^https?:\/\//, "");
        //const wsProtocol = rawUrl?.startsWith('https') ? 'wss' : 'ws';
        const wsProtocol = 'wss'; // Force WebSocket Secure (wss) for all connections
        const window_url = window.location.origin.replace(/^http/, 'ws');
        const sim_text = sim_type === 'RLSimulated' ? 'simulation_rl' : 'simulation';
        let socketUrl = '';
        if (process.env.NEXT_PUBLIC_DEV_MODE === 'true') {
            socketUrl = isRealtime 
            ? `${process.env.NEXT_PUBLIC_INF_URL!.replace(/^http/, 'ws')}/api/process/ws/realtime`
            : `${process.env.NEXT_PUBLIC_INF_URL!.replace(/^http/, 'ws')}/api/process/ws/${sim_text}/${selected_session}`;
        }
        else {
            socketUrl = isRealtime 
            ? `${window_url}/${strippedUrl}/api/process/ws/realtime`
            : `${window_url}/${strippedUrl}/api/process/ws/${sim_text}/${selected_session}`;
        }
        console.log("WebSocket URL:", socketUrl);
        const socket = new WebSocket(socketUrl);
        setWsConnection(socket);
        console.log("Going to open WebSocket connection");
        socket.onopen = () => {
            console.log("WebSocket connection established");
            setConnectionStatus('Connected');
            setLoading(false);
            setIsSimulationRunning(true);
            setSimulationRun(true);

            if (simulationOptions) {
                socket.send(JSON.stringify({
                    type: 'start_simulation',
                    options: simulationOptions
                }));
            }
            else{
                console.error("Simulation options are not set. Cannot start simulation.");
            }
        };
        
        socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'trade_stats') {
                setTradeStats(data.data);
            }
            else if (data.type === 'trade_table') {
                setTradeRecords(data.data);
                if (sciChartSurfaceRef?.current) {
                    //console.log("Rendering trade markers on the chart");
                    renderTradeMarkers(
                        sciChartSurfaceRef.current, 
                        data.data,
                        tradeMarkerMapRef,
                        sim_type
                    );
                }
            }
            else if(data.type === 'take_profits'){
                const takeProfitData = data.data;
                if (takeProfitData.time.length > 1) {
                    const x_TakeProfit = takeProfitData.time.map((t: string) => {
                        const dt = DateTime.fromISO(t, { zone: "America/New_York" });
                        if (!dt.isValid) {
                            console.error("Invalid date in take profits data:", t);
                            return null; // or handle the error as needed
                        }
                        return dt.toMillis();
                    }).filter((x: number | null) => x !== null);
                    buyTakeProfitRef?.current?.clear();
                    sellTakeProfitRef?.current?.clear();

                    buyTakeProfitRef?.current?.appendRange(
                        x_TakeProfit,
                        takeProfitData.buy_take_profit
                    );
                    sellTakeProfitRef?.current?.appendRange(
                        x_TakeProfit,
                        takeProfitData.sell_take_profit
                    );
                }
                else if (takeProfitData.time.length === 1) {
                    const t = takeProfitData.time[0];
                    const dt = DateTime.fromISO(t, { zone: "America/New_York" });
                    const buy_dataseries = buyTakeProfitRef?.current;
                    const sell_dataseries = sellTakeProfitRef?.current;
                    if (!buy_dataseries || !sell_dataseries) return;
                    const xValues = buy_dataseries.getNativeXValues();
                    let foundIndex = -1;
                    for (let i = buy_dataseries.count() - 1; i >= 0; i--) {
                        if (xValues.get(i) === dt.toMillis()) {
                            foundIndex = i;
                            break;
                        }
                    }
                    //
                    if (foundIndex >= 0) {
                        console.log("Updating existing take profit at index:", foundIndex, "with time:", t);
                        buy_dataseries.removeAt(foundIndex);
                        sell_dataseries.removeAt(foundIndex);
                    }
                    buyTakeProfitRef?.current?.append(
                        dt.toMillis(),
                        takeProfitData.buy_take_profit[0]
                    );
                    sellTakeProfitRef?.current?.append(
                        dt.toMillis(),
                        takeProfitData.sell_take_profit[0]
                    );
                }
            }
            else if (data.type === "candle_data"){
                const ohlcData = data.data;

                if (ohlcData.length > 1) {
                    const xValues = ohlcData.map((candle: any) => {
                        const dt = DateTime.fromISO(candle.time, { zone: 'America/New_York' });
                        if (!dt.isValid) {
                            console.error("Invalid date format in candle data:", candle.time);
                            return 0; // or handle the error as needed
                        }
                        return dt.toMillis();
                    });
                    const openValues = ohlcData.map((candle: any) => candle.open);
                    const highValues = ohlcData.map((candle: any) => candle.high);
                    const lowValues = ohlcData.map((candle: any) => candle.low);
                    const closeValues = ohlcData.map((candle: any) => candle.close);

                    candleDataSeriesRef?.current?.clear();
                    candleDataSeriesRef?.current?.appendRange(
                        xValues,
                        openValues,
                        highValues,
                        lowValues,
                        closeValues
                    );
                }
                else if (ohlcData.length === 1) {
                    //console.log("History - Received single candle data:", ohlcData[0]);
                    const candle = ohlcData[0];
                    const candleTime = DateTime.fromISO(candle.time, { zone: 'America/New_York' }).toMillis();

                    const dataSeries = candleDataSeriesRef?.current;
                    if (! dataSeries)  return;

                    const xValues = dataSeries.getNativeXValues();
                    let foundIndex = -1;
                    for (let i = dataSeries.count() - 1; i >= 0; i--) {
                        if (xValues.get(i) === candleTime) {
                            foundIndex = i;
                            break;
                        }
                    }
                    console.log("Price history - Found index for candle time:", foundIndex, "for time:", candleTime);
                    if (foundIndex >= 0) {
                        console.log("History - Updating existing candle at index:", foundIndex, "with data:", candle);
                        dataSeries.removeAt(foundIndex);
                        dataSeries.append(
                            candleTime,
                            candle.open,
                            candle.high,
                            candle.low,
                            candle.close
                        );
                    }
                    else{
                        dataSeries.append(
                            candleTime,
                            candle.open,
                            candle.high,
                            candle.low,
                            candle.close
                        );
                    }
                }
            }
            else if (data.type === 'realtime_data') {
                
                const { price, time } = data.data;
                console.log("Received realtime data:", price, "  ",  time);
                const minuteTimestamp = Math.floor(time / 60000) * 60000 + 60000; // Round to the nearest minute

                const dataseries = realtimeSeriesRef?.current;
                if (!dataseries) return;
                
                dataseries?.clear();
                if (currentCandleRef.current && currentCandleRef.current.time === minuteTimestamp) {
                    currentCandleRef.current.high = Math.max(currentCandleRef.current.high, price);
                    currentCandleRef.current.low = Math.min(currentCandleRef.current.low, price);
                    currentCandleRef.current.close = price;
                    console.log("Realtime info :", minuteTimestamp, "with price:", currentCandleRef.current);
                    dataseries.append(
                        minuteTimestamp,
                        currentCandleRef.current.open,
                        currentCandleRef.current.high,
                        currentCandleRef.current.low,
                        currentCandleRef.current.close
                    );

                }
                else{
                    currentCandleRef.current = {
                        time: minuteTimestamp,
                        open: price,
                        high: price,
                        low: price,
                        close: price
                    };
                    dataseries.append(
                        minuteTimestamp,
                        currentCandleRef.current.open,
                        currentCandleRef.current.high,
                        currentCandleRef.current.low,
                        currentCandleRef.current.close
                    );
                }
            }
        };
        socket.onclose = () => {
            console.log("WebSocket connection closed");
            setConnectionStatus('Disconnected');
            setIsSimulationRunning(false);
            setLoading(false);
        };

        socket.onerror = (error) => {
            console.error("WebSocket error:", error);
            setConnectionStatus('Socket Connection Error');
            setLoading(false);
            setIsSimulationRunning(false);
        };
        return socket;
        

    };


    const startSimulation = () => {
        if (!simulationOptions) {
            console.error("Simulation options are not set. Cannot start simulation.");
            return;
        }

        if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
            wsConnection.send(JSON.stringify({
                type: 'start_simulation',
                options: simulationOptions
            }));
            setIsSimulationRunning(true);
            setSimulationRun(true);
        } else {
            initializeWebSocket();
        }
    };

    const stopSimulation = () => {
        if (wsConnection) {
            if (wsConnection.readyState === WebSocket.OPEN) {
                wsConnection.send(JSON.stringify({ type: 'stop_simulation' }));
                setIsSimulationRunning(false);
            }
            wsConnection.close();
        }
        setIsSimulationRunning(false);
        setConnectionStatus('Stopped - Disconnected');
    };

    const resetSimulation = () => {
        setSimulationRun(false);
    };

    const clearTrades = async() => {
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_INF_URL}/api/process/remove_all_trades/0`, {
                method: 'GET'
            });
            if (!res.ok) {
                const errorText = await res.text();
                throw new Error(`Failed to clear trades: status : ${res.status} , text :  ${errorText}`);
            }

            const data = await res.json();
            console.log("Delete response:", data);
            //updateCurrentSessionData(selected_session);
        } catch (error) {
            console.error("Error clearing trades:", error);
            alert(`Failed to clear trades because of error: ${error}`);
        }
    }

    return (
        <>

        <Box sx={{ 
                display: 'flex', 
                width: '100%', 
                mb: 2,
                '& > button': {
                    flex: 1,
                    py: 1, // Makes the buttons lean (less tall)
                    borderRadius: 0, // Optional: for sharp edges
                }
            }}>
                <Button 
                    variant="contained" 
                    color="success" 
                    onClick={startSimulation}
                    disabled={isSimulationRunning}
                    sx={{ 
                        mr: 0.5,
                        backgroundColor: isSimulationRunning ? 'grey.500' : 'success.main',
                        '&:hover': {
                            backgroundColor: isSimulationRunning ? 'grey.600' : 'success.dark'
                        }
                    }}
                >
                    Start Simulation
                </Button>
                <Button 
                    variant="contained" 
                    color="error" 
                    onClick={stopSimulation}
                    disabled={!isSimulationRunning}
                    sx={{ 
                        ml: 0.5,
                        backgroundColor: !isSimulationRunning ? 'grey.500' : 'error.main',
                        '&:hover': {
                            backgroundColor: !isSimulationRunning ? 'grey.600' : 'error.dark'
                        }
                    }}
                >
                    Stop Simulation
                </Button>
            {isRealtime && (
                <Button 
                    variant="contained" 
                    color="error" 
                    onClick={clearTrades}
                    sx={{ 
                        ml: 0.5,
                        backgroundColor: 'blue',
                        '&:hover': {
                            backgroundColor: 'blue.dark'
                        }
                    }}
                >
                    Clear Trades
                </Button>
            )}

        </Box>

        <Box sx={{ flexGrow: 1 }}>
            <Typography variant="h5" gutterBottom sx={{ mb:3 }}>
                Trade Statistics
            </Typography>

            <Grid container spacing={3} sx={{m: 0, width: '100%'}}>
                <Grid size={{xs: 12, md: 6 }} sx={{ p: 0}}>
                    <TradeStatsDisplay stats={tradeStats} />
                </Grid>
                <Grid size={{xs: 12, md: 6 }} sx={{ p: 0 }}>
                    <TradeTable trades={tradeRecords} />
                </Grid>
            </Grid>
        </Box>
        </>
    );
}
