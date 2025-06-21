'use client';

import { createContext, useContext, useState, ReactNode } from 'react';

type PageContextType = {
    sidebar_fields?: ReactNode;
    setSidebarFields: (node: ReactNode) => void;
    model: string;
    setModel: (value: string) => void;
    model_alias: string;
    setModelAlias: (value: string) => void;
    timeRange: {
        start: string | null;
        end: string | null;
    };
    setTimeRange: (range: { start: string | null; end: string | null }) => void;
    showTimePickerFor: 'start' | 'end' | null;
    setShowTimePickerFor: (type: 'start' | 'end' | null) => void;
};

const PageContext = createContext<PageContextType | undefined>(undefined);

export const PageContextProvider = ({ children }: { children: ReactNode }) => {
    const [sidebar_fields, setSidebarFields] = useState<ReactNode>(null);
    const [model, setModel] = useState<string>('');
    const [model_alias, setModelAlias] = useState<string>('');
    const [timeRange, setTimeRange] = useState<{ start: string | null; end: string | null }>({
        start: null,
        end: null
    });
    const [showTimePickerFor, setShowTimePickerFor] = useState<'start' | 'end' | null>(null);

    return (
        <PageContext.Provider 
        value={{ 
            sidebar_fields, 
            setSidebarFields, 
            model, 
            setModel, 
            model_alias, 
            setModelAlias,
            timeRange,
            setTimeRange,
            showTimePickerFor,
            setShowTimePickerFor
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
