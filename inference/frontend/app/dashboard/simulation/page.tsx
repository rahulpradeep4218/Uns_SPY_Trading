'use client';
import dynamic from 'next/dynamic';
import TradeSessionsTable from '@/components/TradeSessionsTable';

const UserAnnotatedStockChart = dynamic(() => import('@/components/sciChart/annot-chart'), {ssr: false});

export default function SimulationPage(){
    return (
        <>
            <div style={{ height: '100vh', width: '100%' }}>   
                <UserAnnotatedStockChart />
            </div>
            <div>
                <TradeSessionsTable />
            </div>
        </>
    );
}