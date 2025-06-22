'use client'

import React, { useState, useEffect } from 'react';
import { DataGrid, GridColDef, GridActionsCellItem } from '@mui/x-data-grid';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField } from '@mui/material';
import { Delete, Edit } from '@mui/icons-material';
import axios from 'axios';


interface TradeSession {
    id: number;
    type: string,
    symbol: string,
    trade_start: string,
    trade_end: string,
    model_high_version: number,
    model_high_alias: string,
    model_low_version: number,
    model_low_alias: string,
}

export default function TradeSessionsTable() {
    const [sessions, setSessions] = useState<TradeSession[]>([]);
    const [open, setOpen] = useState(false);
    const [currentSession, setCurrentSession] = useState<TradeSession | null>(null);

    // Fetch data from API
    useEffect(() => {
        const fetchData = async () => {
            const inf_url = process.env.NEXT_PUBLIC_INF_URL;
            const response = await axios.get(`${inf_url}/api/trade_sessions/`);
            setSessions(response.data);
        };
        fetchData();
    }, []);

    const handleDelete = async (id: number) => {
        await axios.delete(`${process.env.NEXT_PUBLIC_INFERENCE_URL}/api/trade_sessions/${id}/`);
        setSessions(sessions.filter(session => session.id !== id));
    };

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!currentSession) return;

        const inf_url = process.env.NEXT_PUBLIC_INFERENCE_URL;
        if (currentSession) {
            const response = currentSession.id
                ? await axios.put(`${inf_url}/api/trade_sessions/${currentSession.id}/`, currentSession)
                : await axios.post(`${inf_url}/api/trade_sessions/`, currentSession);

            setSessions(currentSession.id
                ? sessions.map(session => session.id === currentSession.id ? response.data : session)
                : [...sessions, response.data]);
        } 


        setOpen(false);
    };


    // Column Configuration
    const columns: GridColDef[] = [
        { field: 'id', headerName: 'ID', width: 30 },
        { field: 'symbol', headerName: 'Symbol', width: 60 },
        { field: 'trade_start', 
            headerName: 'Trade Start', 
            width: 180,
            valueFormatter: (params) => params.value ? new Date(params.value).toLocaleString() : '-',
        },
        {   field: 'trade_end', 
            headerName: 'Trade End', 
            width: 180,
            valueFormatter: (params) => params.value ? new Date(params.value).toLocaleString() : '-',
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

    return (
        <div style={{ height: 500, width: '100%' }}>
            <Button
            variant="contained"
            sx={{mb: 2}}
            onClick={() => {
                setCurrentSession({ id: 0, 
                    type: 'trade', 
                    symbol: '', 
                    trade_start: '', 
                    trade_end: '', 
                    model_high_version: 0, 
                    model_high_alias: '', 
                    model_low_version: 0, 
                    model_low_alias: '' 
                });
                setOpen(true);
            }}
            >
                Create New 
            </Button>

            <DataGrid
                rows={sessions}
                columns={columns}
                pageSize={10}
                rowsPerPageOptions={[10]}
                checkboxSelection
                disableSelectionOnClick
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
                        <TextField
                            label="Trade Start"
                            type="datetime-local"
                            value={currentSession?.trade_start || ''}
                            onChange={(e) => setCurrentSession({ ...currentSession, trade_start: e.target.value })}
                            fullWidth
                            margin="normal"
                        />
                        <TextField
                            label="Trade End"
                            type="datetime-local"
                            value={currentSession?.trade_end || ''}
                            onChange={(e) => setCurrentSession({ ...currentSession, trade_end: e.target.value })}
                            fullWidth
                            margin="normal"
                        />
                        <TextField
                            label="Model High Version"
                            value={currentSession?.model_high_version || ''}
                            onChange={(e) => setCurrentSession({ ...currentSession, model_high_version: e.target.value })}
                            fullWidth
                            margin="normal"
                        />
                        <TextField
                            label="Model High Alias"
                            value={currentSession?.model_high_alias || ''}
                            onChange={(e) => setCurrentSession({ ...currentSession, model_high_alias: e.target.value })}
                            fullWidth
                            margin="normal"
                        />
                        <TextField
                            label="Model Low Version"
                            value={currentSession?.model_low_version || ''}
                            onChange={(e) => setCurrentSession({ ...currentSession, model_low_version: e.target.value })}
                            fullWidth
                            margin="normal"
                        />
                        <TextField
                            label="Model Low Alias"
                            value={currentSession?.model_low_alias || ''}
                            onChange={(e) => setCurrentSession({ ...currentSession, model_low_alias: e.target.value })}
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

