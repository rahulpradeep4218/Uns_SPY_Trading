'use client';
import dynamic from 'next/dynamic';
import TradeSessionsTable from '@/components/TradeSessionsTable';
import  TradeStatsDashboard  from "@/components/Trade_Stats/TradeStatsDashboard";
import { usePageContext } from '@/context/PageContext';
import { Typography } from '@mui/material';
import TradeSignalControls from '@/components/sciChart/TradeMarkers';

const UserAnnotatedStockChart = dynamic(() => import('@/components/sciChart/annot-chart'), {ssr: false});

export default function SimulationPage(){
    const { selected_session, setSelectedSession } = usePageContext();


    return (
        <>
            <div style={{ height: '100vh', width: '100%' }}>   
                <UserAnnotatedStockChart />
            </div>
            <div>
                <TradeStatsDashboard />
            </div>
            <div style={{ height: '100vh', width: '100%', marginTop: '20px' }}>
                <Typography variant="h5" sx={{ mb: 2, textAlign: 'center' }}>
                    Selected Session ID: {selected_session !== null ? selected_session : 'None'}
                </Typography>
                <TradeSessionsTable />
            </div>
        </>
    );
}