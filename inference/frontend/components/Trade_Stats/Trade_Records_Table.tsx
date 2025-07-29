'use client';

import { useState } from 'react';
import {
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Paper,
    Typography,
    Button,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField
} from '@mui/material';

import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import AssignmentIcon from '@mui/icons-material/Assignment';


import { TradeRecord } from '@/app/types';
import { usePageContext } from '@/context/PageContext';

export const TradeTable = ({ trades }: { trades: TradeRecord[] }) => {

    const { selected_session } = usePageContext();
    const [open, setOpen] = useState(false);
    const [tosCode, setTosCode] = useState('');
    const [loading, setLoading] = useState(false);

    const handleOpenDialog = async (trade: TradeRecord) => {
        setLoading(true);
        try{
            console.log("fetching tos code from url : ", `${process.env.NEXT_PUBLIC_INF_URL}/api/process/get-tos-order?session_id=${selected_session}&trade_time=${trade.trade_time}`);
            const res = await fetch(`${process.env.NEXT_PUBLIC_INF_URL}/api/process/get-tos-order?session_id=${selected_session}&trade_time=${trade.trade_time}`);
            const data = await res.json();
            setTosCode(data.tos_order_code);
            setOpen(true);
        } catch(err) {
            console.error("Error fetching TOS code:", err);
        } finally {
            setLoading(false);
        }
        
    };

    const handleCloseDialog = () => setOpen(false);

    const handleCopyCode = () => {
        navigator.clipboard.writeText(tosCode);
        alert("TOS code copied to clipboard!");
    };

    return (
        <Paper sx={{ p: 3, height: '100%'}}>
            <Typography variant="h6" gutterBottom sx={{ mb: 2 }}>Trade Records</Typography>
            <TableContainer component={Paper} variant="outlined" sx={{
                maxHeight: '400px',
                overflow: 'auto',
            }}>
                <Table size="small" aria-label="trades table" stickyHeader>
                    <TableHead>
                        <TableRow sx={{ backgroundColor: 'background.default' }}>
                            <TableCell><Typography variant="subtitle2">Action</Typography></TableCell>
                            <TableCell><Typography variant="subtitle2">Trade Time</Typography></TableCell>
                            <TableCell><Typography variant="subtitle2">Profit</Typography></TableCell>
                            <TableCell><Typography variant="subtitle2">Status</Typography></TableCell>
                            <TableCell><Typography variant="subtitle2">Signal</Typography></TableCell>
                            <TableCell><Typography variant="subtitle2">Entry Price</Typography></TableCell>
                            <TableCell><Typography variant="subtitle2">Exit Reason</Typography></TableCell>


                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {trades.map((trade) => (
                            <TableRow 
                                key={String(trade.trade_time)}
                                hover
                                sx={{ '&:last-child td, &:last-child th': { border: 0 } }}
                                >

                                <TableCell>
                                    <Button
                                        variant="outlined"
                                        size="small"
                                        startIcon={<AssignmentIcon />}
                                        onClick={() => handleOpenDialog(trade) }
                                    >
                                        {loading ? 'Generating...' : 'Generate TOS Code'}

                                    </Button>
                                </TableCell>

                                <TableCell component="th" scope="row">
                                    <Typography variant="body2">
                                        {new Date(trade.trade_time).toLocaleString()}
                                    </Typography>
                                </TableCell>
                                <TableCell align="right" sx={{ fontWeight: 'medium' }}>
                                    <Typography variant="body2" 
                                    color={trade.profit >= 0 ? 'success.main' : 'error.main'}
                                >
                                        ${trade.profit.toFixed(2)}
                                    </Typography>
                                </TableCell>
                                <TableCell>
                                    <Typography variant="body2" 
                                        color={trade.status === 'OPEN' ? 'primary' : 'text.secondary'}
                                    >
                                        {trade.status}
                                    </Typography>
                                </TableCell>
                                <TableCell>
                                    <Typography variant="body2" 
                                        color={trade.signal === 1 ? 'success.main' : trade.signal === -1 ? 'error.main' : 'text.secondary'}
                                    >
                                        {trade.signal === 1 ? 'Buy' : trade.signal === -1 ? 'Sell' : 'None'}
                                    </Typography>
                                </TableCell>
                                <TableCell>
                                    <Typography variant="body2">
                                        {trade.entry_price.toFixed(2)}
                                    </Typography>
                                </TableCell>
                                <TableCell>
                                    <Typography variant="body2">
                                        {trade.exit_reason}
                                    </Typography>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </TableContainer>

            {/* Popup Dialog for TOS Code */}
            <Dialog open={open} onClose={handleCloseDialog} maxWidth="md" fullWidth>
                <DialogTitle>TOS</DialogTitle>
                <DialogContent>
                    <TextField
                        fullWidth
                        multiline
                        rows={8}
                        variant="outlined"
                        value={tosCode}
                        onChange={(e) => setTosCode(e.target.value)}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCopyCode} startIcon={<ContentCopyIcon />}>
                        Copy to Clipboard
                    </Button>
                    <Button onClick={handleCloseDialog}>Close</Button>
                </DialogActions>
            </Dialog>
        </Paper>
    );
};