'use client';

import { createContext, useContext, useState, ReactNode, useRef, Dispatch, SetStateAction } from 'react';
import { TradeStats , TradeRecord, SimulationOptions, OHLCDataPoint } from '@/app/types';
import { initializeCandleStickChart } from '@/components/sciChart/initializeCandleStickChart';

import { CustomAnnotation, SciChartSurface } from 'scichart';
import { TResolvedReturnType } from 'scichart-react';
import { OhlcDataSeries } from 'scichart';

type PageContextType = {
    sidebar_fields?: ReactNode;
    setSidebarFields: (node: ReactNode) => void;
    model_high_alias: string;
    setModelHighAlias: (value: string) => void;
    model_low_alias: string;
    setModelLowAlias: (value: string) => void;
    model_high_version: number | string;
    setModelHighVersion: (value: number | string) => void;
    model_low_version: number | string;
    setModelLowVersion: (value: number | string) => void;
    selected_session: number | null;
    training_start: string | null;
    setTrainingStart: (start: string | null) => void;
    training_end: string | null;
    setTrainingEnd: (end: string | null) => void;
    setSelectedSession: (sessionId: number | null) => void;
    timeRange: {
        start: string | null;
        end: string | null;
    };
    setTimeRange: Dispatch<SetStateAction<{ 
        start: string | null; 
        end: string | null; 
    }>>;
    
    showTimePickerFor: 'start' | 'end' | null;
    setShowTimePickerFor: Dispatch<SetStateAction<'start' | 'end' | null>>;

    tradeStats: TradeStats;
    setTradeStats: (stats: TradeStats) => void;

    tradeRecords: TradeRecord[];
    setTradeRecords: (records: TradeRecord[]) => void;

    wsConnection: WebSocket | null;
    setWsConnection: (ws: WebSocket | null) => void;

    simulationOptions?: SimulationOptions;
    setSimulationOptions?: (options: SimulationOptions) => void;

    sciChartSurfaceRef?: React.RefObject<SciChartSurface | null>;
    chartControlsRef: React.RefObject<TResolvedReturnType<typeof initializeCandleStickChart>["controls"] | null>;
    tradeMarkerMapRef: React.RefObject<Map<number, CustomAnnotation>>;
    candleDataSeriesRef?: React.RefObject<OhlcDataSeries | null>;


    simulationRun: boolean;
    setSimulationRun: (run: boolean) => void;

    schwabConnStatus: boolean;
    setSchwabConnStatus: (status: boolean) => void;

    isRealtime?: boolean;
    setIsRealtime?: (isRealtime: boolean) => void;

};

const PageContext = createContext<PageContextType | undefined>(undefined);

export const PageContextProvider = ({ children }: { children: ReactNode }) => {
    const [sidebar_fields, setSidebarFields] = useState<ReactNode>(null);
    const [model_high_alias, setModelHighAlias] = useState<string>('');
    const [model_low_alias, setModelLowAlias] = useState<string>('');
    const [model_high_version, setModelHighVersion] = useState<number | string>('');
    const [model_low_version, setModelLowVersion] = useState<number | string>('');
    const [training_start, setTrainingStart] = useState<string | null>(null);
    const [training_end, setTrainingEnd] = useState<string | null>(null);
    const [selected_session, setSelectedSession] = useState<number | null>(null);
    const [timeRange, setTimeRange] = useState<{ start: string | null; end: string | null }>({
        start: null,
        end: null
    });
    const [showTimePickerFor, setShowTimePickerFor] = useState<'start' | 'end' | null>(null);

    const [tradeStats, setTradeStats] = useState<TradeStats>({
        total_trades: 0,
        winning_trades: 0,
        losing_trades: 0,
        winning_percentage: 0,
        average_profit: 0,
        total_profit: 0,
        unrealized_profit: 0,
        percent_complete: 0,
        
    });
    const [tradeRecords, setTradeRecords] = useState<TradeRecord[]>([]);
    const [wsConnection, setWsConnection] = useState<WebSocket | null>(null);
    const [simulationOptions, setSimulationOptions] = useState<SimulationOptions | undefined>(undefined);

    const sciChartSurfaceRef = useRef<SciChartSurface>(null);
    const chartControlsRef = useRef<TResolvedReturnType<typeof initializeCandleStickChart>["controls"]>(null);
    const tradeMarkerMapRef = useRef<Map<number, CustomAnnotation>>(new Map());
    const candleDataSeriesRef = useRef<OhlcDataSeries | null>(null);


    const [simulationRun, setSimulationRun] = useState<boolean>(false);

    const [schwabConnStatus, setSchwabConnStatus] = useState<boolean>(false);

    const [isRealtime, setIsRealtime] = useState<boolean>(false);

    return (
        <PageContext.Provider 
        value={{ 
            sidebar_fields, 
            setSidebarFields, 
            model_high_alias, 
            setModelHighAlias, 
            model_low_alias, 
            setModelLowAlias,
            model_high_version,
            setModelHighVersion,
            model_low_version,
            setModelLowVersion,
            training_start,
            setTrainingStart,
            training_end,
            setTrainingEnd,
            timeRange,
            setTimeRange,
            showTimePickerFor,
            setShowTimePickerFor,
            tradeStats,
            setTradeStats,
            tradeRecords,
            setTradeRecords,
            wsConnection,
            setWsConnection,
            selected_session,
            setSelectedSession,
            simulationOptions,
            setSimulationOptions,
            sciChartSurfaceRef,
            chartControlsRef,
            tradeMarkerMapRef,
            simulationRun,
            setSimulationRun,
            candleDataSeriesRef,
            schwabConnStatus,
            setSchwabConnStatus,
            isRealtime,
            setIsRealtime
        }}
        >
            {children}
        </PageContext.Provider>
    );
};


export const usePageContext = (): PageContextType => {
    const context = useContext(PageContext);
    if (!context) {
        throw new Error('usePageContext must be used within a PageContextProvider');
    }
    return context;
};
