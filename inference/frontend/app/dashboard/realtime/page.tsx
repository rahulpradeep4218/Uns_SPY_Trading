'use client';
import dynamic from 'next/dynamic';
import { use } from 'react';
import { usePageContext } from '@/context/PageContext';
import  TradeStatsDashboard  from "@/components/Trade_Stats/TradeStatsDashboard";
const UserAnnotatedStockChart = dynamic(() => import('@/components/sciChart/annot-chart'), {ssr: false});

export default function DashboardPage() {
    const { selected_session, setSelectedSession } = usePageContext();
    setSelectedSession(0);
    return (
       <>
            <div style={{ height: '100vh', width: '100%' }}>   
                <UserAnnotatedStockChart />
            </div>
            <div>
                <TradeStatsDashboard />
            </div>
        </>
    );
}