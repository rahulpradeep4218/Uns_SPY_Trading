import { useState } from 'react';
import {
    Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Typography, Button,
    Snackbar, Alert
} from '@mui/material';
import AssignmentIcon from '@mui/icons-material/Assignment';
import { TradeRecord } from '@/app/types';
import { usePageContext } from '@/context/PageContext';

export const TradeTable = ({ trades }: { trades: TradeRecord[] }) => {
    const { selected_session } = usePageContext();
    const [loading, setLoading] = useState(false);

    // Snackbar state
    const [snackbarOpen, setSnackbarOpen] = useState(false);
    const [snackbarMessage, setSnackbarMessage] = useState('');
    const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error' | 'info'>('info');

    const handleOpenSnackbar = (message: string, status: string) => {
        setSnackbarMessage(message);
        setSnackbarSeverity(status.toLowerCase() === 'success' ? 'success' :
            status.toLowerCase() === 'error' ? 'error' : 'info');
        setSnackbarOpen(true);
    };

    const handleCloseSnackbar = (_?: unknown, reason?: string) => {
        if (reason === 'clickaway') return;
        setSnackbarOpen(false);
    };

    const handlePlaceOrder = async (trade: TradeRecord) => {
        setLoading(true);
        try {
            console.log("Placing Schwab order:", `${process.env.NEXT_PUBLIC_INF_URL}/api/schwab/add-schwab-order?session_id=${selected_session}&trade_time=${trade.trade_time}`);
            const res = await fetch(
                `${process.env.NEXT_PUBLIC_INF_URL}/api/schwab/add-schwab-order`,
                { method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: selected_session,
                        trade_time: trade.trade_time
                    })
                 }
            );
            const data = await res.json();

            // Show backend message & status in short-lived popup
            handleOpenSnackbar(data.message || 'Order placed.', data.status || 'info');
        } catch (err) {
            console.error("Error placing Schwab order:", err);
            handleOpenSnackbar('Failed to place order', 'error');
        } finally {
            setLoading(false);
        }
    };

    return (
        <Paper sx={{ p: 3, height: '100%' }}>
            <Typography variant="h6" gutterBottom sx={{ mb: 2 }}>Trade Records</Typography>
            <TableContainer component={Paper} variant="outlined" sx={{
                maxHeight: '400px',
                overflow: 'auto',
            }}>
                <Table size="small" stickyHeader>
                    <TableHead>
                        <TableRow>
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
                            <TableRow key={String(trade.trade_time)} hover>
                                <TableCell>
                                    <Button
                                        variant="outlined"
                                        size="small"
                                        startIcon={<AssignmentIcon />}
                                        onClick={() => handlePlaceOrder(trade)}
                                        disabled={loading}
                                    >
                                        {loading ? 'Placing...' : 'Place Order'}
                                    </Button>
                                </TableCell>
                                <TableCell>
                                    <Typography variant="body2">
                                        {new Date(trade.trade_time).toLocaleString()}
                                    </Typography>
                                </TableCell>
                                <TableCell align="right">
                                    <Typography variant="body2"
                                        color={trade.profit >= 0 ? 'success.main' : 'error.main'}>
                                        ${trade.profit.toFixed(2)}
                                    </Typography>
                                </TableCell>
                                <TableCell>
                                    <Typography variant="body2"
                                        color={trade.status === 'OPEN' ? 'primary' : 'text.secondary'}>
                                        {trade.status}
                                    </Typography>
                                </TableCell>
                                <TableCell>
                                    <Typography variant="body2"
                                        color={trade.signal === 1 ? 'success.main' :
                                            trade.signal === -1 ? 'error.main' : 'text.secondary'}>
                                        {trade.signal === 1 ? 'Buy' :
                                            trade.signal === -1 ? 'Sell' : 'None'}
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

            {/* Snackbar */}
            <Snackbar
                open={snackbarOpen}
                autoHideDuration={3000}
                onClose={handleCloseSnackbar}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            >
                <Alert
                    onClose={handleCloseSnackbar}
                    severity={snackbarSeverity}
                    sx={{ width: '100%' }}
                >
                    {snackbarMessage}
                </Alert>
            </Snackbar>
        </Paper>
    );
};
