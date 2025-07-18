'use client';

import {
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Paper,
    Typography,

} from '@mui/material';

import { TradeRecord } from '@/app/types';

export const TradeTable = ({ trades }: { trades: TradeRecord[] }) => {
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
        </Paper>
    );
};