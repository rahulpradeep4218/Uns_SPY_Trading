'use client';
import { DateTime } from "luxon";
import { useEffect, useState } from 'react';

import { usePageContext } from '@/context/PageContext';
import { TradeTable } from '@/components/Trade_Stats/Trade_Records_Table';
import { TradeStatsDisplay } from '@/components/Trade_Stats/Trade_Scorecard';
import { Box, Grid, Typography, Button } from '@mui/material';

import { renderTradeMarkers } from '@/components/sciChart/renderTradeMarkers';
import { init } from "next/dist/compiled/webpack/webpack";
import { defaultSimulationOptions } from "@/components/SimulationOptions";



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
        isRealtime,
        setIsRealtime
    } = usePageContext();

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
        const wsProtocol = rawUrl?.startsWith('https') ? 'wss' : 'ws';
        const socketUrl = isRealtime 
            ? `${wsProtocol}://${strippedUrl}/api/process/ws/realtime`
            : `${wsProtocol}://${strippedUrl}/api/process/ws/simulation/${selected_session}`;

        const socket = new WebSocket(socketUrl);
        setWsConnection(socket);

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
                        tradeMarkerMapRef
                    );
                }
            }
            else if (data.type === "candle_data"){
                const ohlcData = data.data;
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

                <Button 
                    variant="contained" 
                    color="error" 
                    onClick={resetSimulation}
                    sx={{ 
                        ml: 0.5,
                        backgroundColor: 'blue',
                        '&:hover': {
                            backgroundColor: 'blue.dark'
                        }
                    }}
                >
                    Reset
                </Button>

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
