'use client';

import { useEffect, useState, useRef } from 'react';

type CheckResponse = {
    reauth_link?: string;
    last_realtime_sync?: string;
    last_history_sync?: string;
    last_candle_time?: string;
    sync_enabled?: string;
    sync_account_enabled?: string;
    reauth_link_account?: string;
};



export const ConnectionStatusChecker = () => {
    const [reauthUrl, setReauthUrl] = useState<string | null>(null);
    const [reauthUrlAccount, setReauthUrlAccount] = useState<string | null>(null);
    const [lastRealtimeSync, setLastRealtimeSync] = useState<string | null>(null);
    const [lastHistorySync, setLastHistorySync] = useState<string | null>(null);
    const [lastCandleTime, setLastCandleTime] = useState<string | null>(null);
    const [syncEnabled, setSyncEnabled] = useState<string>("No");
    const [syncAccountEnabled, setSyncAccountEnabled] = useState<string>("No");

    const [isPolling, setIsPolling] = useState<boolean>(true);
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    const checkConnection = async ()=> {
        try {
            const inf_url = process.env.NEXT_PUBLIC_INF_URL;
            const res = await fetch(`${inf_url}/api/schwab/check_connection`);
            const data: CheckResponse = await res.json();

            setReauthUrl(data.reauth_link || null);
            setReauthUrlAccount(data.reauth_link_account || null);
            setLastRealtimeSync(data.last_realtime_sync || null);
            setLastHistorySync(data.last_history_sync || null);
            setLastCandleTime(data.last_candle_time || null);
            setSyncEnabled(data.sync_enabled || "No");
            setSyncAccountEnabled(data.sync_account_enabled || "No");




        }
        catch (error) {
            console.error("Error checking Schwab connection:", error);
            setReauthUrl(null);
            setIsPolling(false);
        }
    };

    useEffect(() => {
        if (isPolling) {
            checkConnection();
            intervalRef.current = setInterval(checkConnection, 10000);
        }
        return () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
            }
        };
    }, [isPolling]);


    const handleReauthClick = () => {
        setIsPolling(true);
    };

    return (
        <div style = {{ position: 'fixed', top: 10, right: 50, fontSize: '12px' }}>

                <div>
                    <span style={{ color: 'red' }}>sync enabled : {syncEnabled}</span>
                    <span style={{ color: 'red', marginLeft: '10px' }}>account sync enabled : {syncAccountEnabled}</span>
                    <span style={{ color: '#55FF55', marginLeft: '10px' }}>Last Realtime Sync: {lastRealtimeSync || 'N/A'}</span>
                    <span style={{ color: '#00BFFF', marginLeft: '10px' }}>Last History Sync: {lastHistorySync || 'N/A'}</span>
                    <span style={{ color: '#FFB6FF', marginLeft: '10px' }}>Last Candle Time: {lastCandleTime || 'N/A'}</span>
                    <a
                        target="_blank" 
                        rel="noopener noreferrer"
                        onClick={() => {
                            const popup = window.open(reauthUrl ?? '', '_blank');
                        }}
                        style = {{ marginLeft: '10px', color: 'yellow', textDecoration: 'underline' , cursor: 'pointer' }}
                    >   
                        Reauthorize Market
                    </a>
                    <a
                        target="_blank" 
                        rel="noopener noreferrer"
                        onClick={() => {
                            const popup = window.open(reauthUrlAccount ?? '', '_blank');

                        }}
                        style = {{ marginLeft: '10px', color: 'yellow', textDecoration: 'underline' , cursor: 'pointer' }}
                    >   
                        Reauthorize Account
                    </a>
                </div>

        </div>
    );
};