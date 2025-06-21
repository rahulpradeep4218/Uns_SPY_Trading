'use client';
import dynamic from 'next/dynamic';
import { use } from 'react';
const UserAnnotatedStockChart = dynamic(() => import('@/components/sciChart/annot-chart'), {ssr: false});

export default function DashboardPage() {
    return (
        <div style={{ height: '100vh', width: '100%' }}>
            
            <UserAnnotatedStockChart />
        </div>
    );
}