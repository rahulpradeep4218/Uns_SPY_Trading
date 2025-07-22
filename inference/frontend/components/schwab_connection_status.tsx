'use client';

import { useEffect, useState, useRef } from 'react';
import { usePageContext } from '@/context/PageContext';
import { set } from 'lodash';

type CheckResponse = {
    status: string;
    reauth_link?: string;
};



export const ConnectionStatusChecker = () => {
    const { schwabConnStatus, setSchwabConnStatus } = usePageContext();
    const [schwabStatusMessage, setSchwabStatusMessage] = useState<string>('NOT_CONNECTED');
    const [reauthUrl, setReauthUrl] = useState<string | null>(null);
    const [isPolling, setIsPolling] = useState<boolean>(true);
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    const checkConnection = async ()=> {
        try {
            const inf_url = process.env.NEXT_PUBLIC_INF_URL;
            const res = await fetch(`${inf_url}/api/schwab/check_connection`);
            const data: CheckResponse = await res.json();
            if ( data.status === "UPDATE_REFRESH_TOKEN") {
                setSchwabConnStatus(false);
                setSchwabStatusMessage("Update Refresh Token");
                setReauthUrl(data.reauth_link || null);
                setIsPolling(false);
            }
            else if (data.status === "NETWORK_ERROR") {
                setSchwabConnStatus(false);
                setSchwabStatusMessage("Network Error.");
                setReauthUrl(null);
                setIsPolling(true);
            } else if (data.status === "SUCCESS") {
                setSchwabConnStatus(true);
                setSchwabStatusMessage("Schwab Connection successful");
                setReauthUrl(null);
                setIsPolling(true);
            }
            else {
                setSchwabConnStatus(false);
                setSchwabStatusMessage("Unknown error occurred, response: " + JSON.stringify(data));
                setReauthUrl(null);
                setIsPolling(false);
            }


        }
        catch (error) {
            console.error("Error checking Schwab connection:", error);
            setSchwabConnStatus(false);
            setSchwabStatusMessage("Error checking connection: " + error);
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
        setReauthUrl(null);
        setIsPolling(true);
    };

    return (
        <div style = {{ position: 'fixed', top: 10, right: 50 }}>
           {schwabStatusMessage === 'Update Refresh Token' && reauthUrl ? (
                <div>
                    <span style={{ color: 'red' }}>Session expired</span>
                    <a 
                        href={reauthUrl} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        onClick={() => {
                            const popup = window.open(reauthUrl, '_blank');
                            const timer = setInterval(() => {
                                if (popup && popup.closed) {
                                    clearInterval(timer);
                                    handleReauthClick();
                                }
                            }, 1000);
                        }}
                        style = {{ marginLeft: '5px', color: 'yellow', textDecoration: 'underline' , cursor: 'pointer' }}
                    >   
                        Click here to Reauthorize
                    </a>
                </div>
            ) : (
                    <p style = {{ color: 'green' }}>Status: {schwabStatusMessage}</p>
                )
            }
        </div>
    );
};