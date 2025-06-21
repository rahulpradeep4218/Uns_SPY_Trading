'use client';

import { usePageContext } from "@/context/PageContext";
import { useState, useEffect } from "react";

export default function RealtimeConfig() {
    const { setSidebarFields, model, setModel, model_alias, setModelAlias } = usePageContext();

    useEffect(() => {

        const fetchModelAliases = async ()=> {
            try{
                const inf_url = process.env.NEXT_PUBLIC_INF_URL;
                const res = await fetch(`${inf_url}/api/mlflow/aliases`);
                const data = await res.json();
                console.log("Model Aliases:", data);
                return data;
            } catch (error) {
                console.error("Error fetching model aliases:", error);
            }
        };
        const update_config = async () => {
            const modelAliases_mlflow = await fetchModelAliases();

            setSidebarFields(
                <div>
                    <label className="text-sm text-gray-50">Model</label>
                    <select 
                        className="w-full p-1 mt-1 rounded bg-gray-700 text-white"
                        value={model || ''}
                        onChange={(e) => {
                            setModel(e.target.value);
                            setModelAlias(''); // Reset alias when model changes
                        }}
                    >
                        <option value="">Select Model</option>
                        {Object.keys(modelAliases_mlflow).map((m) => (
                            <option key={m}>{m}</option>
                        ))}
                    </select>
                    <label className="text-sm text-gray-50 mt-2">Alias</label>
                    <select
                        className="w-full p-1 mt-1 rounded bg-gray-700 text-white"
                        value={model_alias || ''}
                        onChange={(e) => setModelAlias(e.target.value)}
                    >
                        <option value="">Select Alias</option>
                        {( modelAliases_mlflow[model] || []).map((al) => (
                            <option key={al}>{al}</option>
                        ))}
                    </select>
                </div>
            );
        }
        update_config();
    }, [model, model_alias]);
        
    return null; // This component does not render anything directly
    
}