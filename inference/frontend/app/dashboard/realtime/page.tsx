'use client';
import dynamic from 'next/dynamic';
import { useEffect } from 'react';
import { usePageContext } from '@/context/PageContext';
import  TradeStatsDashboard  from "@/components/Trade_Stats/TradeStatsDashboard";
import { ConnectionStatusChecker } from '@/components/schwab_connection_status';
const UserAnnotatedStockChart = dynamic(() => import('@/components/sciChart/annot-chart'), {ssr: false});

export default function DashboardPage() {
    const { selected_session, setSelectedSession } = usePageContext();

    useEffect(() => {
        setSelectedSession(0); // Set the default session to 0 for realtime dashboard
        console.log("Selected session set to 0 for realtime dashboard");
    }, []);

    return (
       <>
            <div style={{ height: '100vh', width: '100%' }}>   
                <ConnectionStatusChecker />
                <UserAnnotatedStockChart />
            </div>
            <div>
                <TradeStatsDashboard />
            </div>
        </>
    );
}