'use client'
import { DateTime } from "luxon";
import React, { useState, useEffect, useRef } from 'react';
import { DataGrid, GridColDef, GridActionsCellItem, GridRowSelectionModel } from '@mui/x-data-grid';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField } from '@mui/material';
import { Delete, Edit } from '@mui/icons-material';
import axios from 'axios';

import { usePageContext } from '@/context/PageContext';

import { renderTradeMarkers } from '@/components/sciChart/renderTradeMarkers';

import { TradeSession } from '@/app/types';

import { GridPaginationModel } from '@mui/x-data-grid';

export default function TradeSessionsTable() {

    const isMountedRef = useRef(false);

    const [paginationModel, setPaginationModel] = React.useState<GridPaginationModel>({
        pageSize: 10,
        page: 0
    });
    const [sessions, setSessions] = useState<TradeSession[]>([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [currentSession, setCurrentSession] = useState<TradeSession | null>(null);

    useEffect(() => {
        isMountedRef.current = true;
        setLoading(true);
        return () => {
            isMountedRef.current = false;
        };
    }, []);


    const { 
        timeRange, setTimeRange, 
        model_high_alias, setModelHighAlias, 
        model_high_version, setModelHighVersion, 
        model_low_alias, setModelLowAlias, 
        model_low_version, setModelLowVersion, 
        selected_session, setSelectedSession,
        tradeStats, setTradeStats,
        tradeRecords, setTradeRecords,
        setTrainingStart,
        setTrainingEnd,
        sciChartSurfaceRef,
        tradeMarkerMapRef,
        candleDataSeriesRef
     } = usePageContext();
    // Fetch data from API

    const handleRowSelection = (model: {
        type: 'include' | 'exclude';
        ids: Set<number | string>;
    }) => {
        const { ids, type } = model;
        if (ids.size === 0) {
            setSelectedSession(null);
            return;
        }

        // We care only when type is include
        if (type == 'include') {
            const arrayIds = Array.from(ids)
                .filter((id): id is number => typeof id === 'number');

            const lastSelectedId = arrayIds[arrayIds.length - 1];
            //console.log("Last selected id :", lastSelectedId);
            setSelectedSession(lastSelectedId);
            updateCurrentSessionData(lastSelectedId);
        }
    };


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
                setTimeRange({
                    start: session_record.trade_start,
                    end: session_record.trade_end
                });

                setTradeStats(trade_stats);
                setTradeRecords(trade_records);
                
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
                const high_model_name = process.env.NEXT_PUBLIC_HIGH_MODEL_NAME || 'high_model';
                const modelAliases_mlflow = await fetchModelAliases();
                if (modelAliases_mlflow[high_model_name][session_record.model_high_alias]['training_start']) {
                    setTrainingStart(modelAliases_mlflow[high_model_name][session_record.model_high_alias]['training_start']);
                }
                if (modelAliases_mlflow[high_model_name][session_record.model_high_alias]['training_end']) {
                    setTrainingEnd(modelAliases_mlflow[high_model_name][session_record.model_high_alias]['training_end']);
                }
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
                renderTradeMarkers(
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

    useEffect(() => {
        const fetchData = async () => {
            const inf_url = process.env.NEXT_PUBLIC_INF_URL;
            console.log("Fetching trade sessions from:", inf_url);
            const response = await axios.get(`${inf_url}/api/trade_sessions?type=Simulated`);
            // console.log("API data sample:", {
            //     firstItem: response.data[0],
            //     keys: Object.keys(response.data[0]),
            //     types: {
            //         trade_start: typeof response.data[0].trade_start,
            //         trade_end: typeof response.data[0].trade_end
            //     }
            // });
            const sessionsWithDates = response.data.map((session: TradeSession) => ({
                ...session,
                // Preserve original string dates for debugging
                original_start: session.trade_start,
                original_end: session.trade_end,
                // Convert to Date objects
                trade_start: new Date(session.trade_start ?? ''),
                trade_end: new Date(session.trade_end ?? '')
            }));
            setSessions(sessionsWithDates);
            console.log("Fetched trade sessions:", sessionsWithDates);
            setLoading(false);
        };
        fetchData();
    }, []);

    const handleDelete = async (id: number) => {
        await axios.delete(`${process.env.NEXT_PUBLIC_INF_URL}/api/trade_sessions/${id}/`);
        setSessions(sessions.filter(session => session.id !== id));
    };

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!currentSession) return;
        
        const inf_url = process.env.NEXT_PUBLIC_INF_URL;
        if (currentSession) {
            if (timeRange.start === null || timeRange.end === null) {
                alert("Please select a valid time range.");
                return;
            }
            // console.log("Trade start : ", timeRange.start);
            // console.log("Trade end : ", timeRange.end);
            currentSession.trade_start = timeRange.start;
            currentSession.trade_end = timeRange.end;
            currentSession.model_high_alias = model_high_alias;
            currentSession.model_high_version = model_high_version ? Number(model_high_version) : undefined;
            currentSession.model_low_alias = model_low_alias;
            currentSession.model_low_version = model_low_version ? Number(model_low_version) : undefined;
            console.log("Time start :", timeRange.start);

            const response = currentSession.id
                ? await axios.put(`${inf_url}/api/trade_sessions/${currentSession.id}/`, currentSession)
                : await axios.post(`${inf_url}/api/trade_sessions/`, currentSession);

            setSessions(currentSession.id
                ? sessions.map(session => session.id === currentSession.id ? response.data : session)
                : [...sessions, response.data]);
        } 


        setOpen(false);
    };

    const formatDateForGrid = (value: Date | string | null): string => {
        //console.log("Formatting date for grid:", value);
        if (!value) return '+';
        
        try {
            const date = value instanceof Date ? value : new Date(value);
            return isNaN(date.getTime()) 
                ? '+' 
                : date.toLocaleString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
        } catch {
            return '*';
        }
    };

    // Column Configuration
    const columns: GridColDef[] = [
        { field: 'id', headerName: 'ID', width: 30 },
        { field: 'symbol', headerName: 'Symbol', width: 60 },
        { field: 'trade_start', 
            headerName: 'Trade Start', 
            width: 180,
            renderCell: (params) => {
                const value = params.row.trade_start;
                return formatDateForGrid(value);
            }
        },
        {   field: 'trade_end', 
            headerName: 'Trade End', 
            width: 180,
            renderCell: (params) => {
                const value = params.row.trade_end;
                return formatDateForGrid(value);
            }
        },
        { field: 'model_high_version', headerName: 'Model High Version', width: 180 },
        { field: 'model_high_alias', headerName: 'Model High Alias', width: 180 },
        { field: 'model_low_version', headerName: 'Model Low Version', width: 180 },
        { field: 'model_low_alias', headerName: 'Model Low Alias', width: 180 },
        {
            field: 'actions',
            type: 'actions',
            headerName: 'Actions',
            width: 100,
            getActions: (params) => [
                <GridActionsCellItem
                    icon={<Edit />}
                    label="Edit"
                    onClick={() => {
                        setCurrentSession(params.row);
                        setOpen(true);
                    }
                }
                />,
                <GridActionsCellItem
                    icon={<Delete />}
                    label="Delete"
                    onClick={() => handleDelete(params.id as number)}
                />,
            ],
        },
    ];

    if (loading){
        return <div>Loading Trading Sessions...</div>;
    }

    return (
        <div style={{ height: 500, width: '100%' }}>
            <Button
            variant="contained"
            sx={{mb: 2}}
            onClick={() => {
                setCurrentSession({...currentSession,
                    type: 'Simulated', 
                    symbol: 'SPY', 
                });
                setOpen(true);
            }}
            >
                Create New 
            </Button>
            <Button
            variant="contained"
            sx={{mb: 2, ml: 2}}
            onClick={async () => {
                if (!selected_session) {
                    alert("Please select a session to clear trades.");
                    return;
                }
                const deleteResponse = await axios.get(`${process.env.NEXT_PUBLIC_INF_URL}/api/process/remove_all_trades/${selected_session}`);
                console.log("Delete response:", deleteResponse.data);
                updateCurrentSessionData(selected_session);
            }}
            >
                Clear All Trades 
            </Button>

            <DataGrid
                rows={sessions}
                columns={columns}
                checkboxSelection
                disableRowSelectionOnClick
                onRowSelectionModelChange={handleRowSelection}
                loading={loading}
                getRowId={(row) => row.id}
                paginationModel={paginationModel}
                onPaginationModelChange={setPaginationModel}
                pageSizeOptions={[10]}

                initialState={{
                    pagination: { paginationModel },
                }}
            />

            <Dialog open={open} onClose={() => setOpen(false)}>
                <DialogTitle>{currentSession?.id ? 'Edit' : 'Create'} Trade Session</DialogTitle>
                <form onSubmit={handleSubmit}>
                    <DialogContent>
    
                        <TextField
                            label="Symbol"
                            value={currentSession?.symbol || ''}
                            onChange={(e) => setCurrentSession({ ...currentSession, symbol: e.target.value })}
                            fullWidth
                            margin="normal"
                        />
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={() => setOpen(false)} color="primary">
                            Cancel
                        </Button>
                        <Button type="submit" color="primary">
                            {currentSession?.id ? 'Update' : 'Create'}
                        </Button>
                    </DialogActions>
                </form>
            </Dialog>
        </div>
    );
}

