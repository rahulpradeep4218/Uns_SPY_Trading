'use client';

import {
    Paper,
    Typography,
    LinearProgress,
    Box,
    Grid
 } from '@mui/material';

import { TradeStats } from '@/app/types';

 const StatItem = ({ label, value, isProfit }: { 
    label: string; 
    value: number | string; 
    isProfit?: boolean 
}) => {
    let valueColor = 'text.primary';
    if (isProfit !== undefined) {
        valueColor = isProfit ? 'success.main' : 'error.main';
    }

    return (
        <Box>
            <Typography variant="body2" color="text.secondary">{label}</Typography>
            <Typography
                variant="body1"
                color={valueColor}
                fontWeight="medium"
            >
                {value}
            </Typography>
        </Box>
    );
};


export const TradeStatsDisplay = ({ stats }: { stats: TradeStats }) => {
    return (
        <Paper sx={{ p: 3, height: '100%', width: '100%' }}>
            <Typography variant="h6" gutterBottom>Trade Stats</Typography>
            <Grid container spacing={2}>
                <Grid size={{xs: 6}} >
                    <StatItem label="Total Trades" value={stats.total_trades} />
                </Grid>
                <Grid size={{xs: 6}} >
                    <StatItem label="Winning Trades" value={stats.winning_trades} isProfit />
                </Grid>
                <Grid size={{xs: 6}} >
                    <StatItem label="Losing Trades" value={stats.losing_trades} />
                </Grid>
                <Grid size={{xs: 6}} >
                    <StatItem label="Winning Percentage" value={`${stats.winning_percentage}%`} />
                </Grid>
                <Grid size={{xs: 6}} >
                    <StatItem label="Average Profit" value={`$${stats.average_profit.toFixed(2)}`} isProfit={stats.average_profit >= 0} />
                </Grid>
                <Grid size={{xs: 6}} >
                    <StatItem label="Total Profit" value={`$${stats.total_profit.toFixed(2)}`} isProfit={stats.total_profit >= 0} />
                </Grid>
                <Grid size={{xs: 6}} >
                    <StatItem label="Unrealized Profit" value={`$${stats.unrealized_profit.toFixed(2)}`} isProfit={stats.unrealized_profit >= 0} />
                </Grid>
                <Grid size={{xs: 12}}>
                    <Box sx={{ mt: 2 }}>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                            Progress: {stats.percent_complete.toFixed(2)}%
                        </Typography>
                        <LinearProgress 
                            variant="determinate" 
                            value={stats.percent_complete}
                            sx={{ height: 8, borderRadius: 4 }}
                            />
                        <Typography variant="caption" color="text.secondary" align="right">
                            {stats.percent_complete}%
                        </Typography>
                    </Box>
                </Grid>
            </Grid>
        </Paper>
    );
};