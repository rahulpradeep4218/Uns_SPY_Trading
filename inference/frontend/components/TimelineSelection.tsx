'use client';
import { Chart, LinearScale, TimeScale, BarElement, Tooltip, Legend, scales, ChartOptions, ChartTypeRegistry, CategoryScale } from 'chart.js';
import annotationPlugin from 'chartjs-plugin-annotation';
import 'chartjs-adapter-date-fns';
import { Bar, getElementAtEvent } from 'react-chartjs-2';
import { useEffect, useState, useRef } from 'react';
import { bottomNavigationActionClasses } from '@mui/material';
import { color } from 'chart.js/helpers';
import zoomPlugin from 'chartjs-plugin-zoom';

Chart.register(LinearScale, TimeScale, CategoryScale, BarElement, Tooltip, Legend, annotationPlugin, zoomPlugin);

interface Gap {
    gap_start: string | null;
    gap_end: string | null;
}

interface DataRange {
    start: string;
    end: string;
    gaps: Gap[];
}

interface TimelineSelectionProps {
    symbol: string;
    onChange: (time: string) => void;
    onClose: () => void;
    selectedStart?: string | null;
    selectedEnd?: string | null;
}


export default function TimelineSelection({ 
        symbol, 
        onChange, 
        onClose,
        selectedStart,
        selectedEnd  
    } : TimelineSelectionProps) {
    const chartRef = useRef<any>(null);
    const [dataRange, setDataRange] = useState<DataRange | null>(null);
    const [cursorPosition, setCursorPosition] = useState<number | null>(null);
    const [cursorTime, setCursorTime] = useState<string>('');
    
    
    useEffect(() => {
        const fetchGaps = async () => {
            try {
                const inf_url = process.env.NEXT_PUBLIC_INF_URL;
                const response = await fetch(`${inf_url}/api/trades/ohlc/gaps?symbol=${symbol}`);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                setDataRange(data);
            } catch (error) {
                console.error("Error fetching gaps:", error);
            }
        };
        fetchGaps();

    }, [symbol]);

    const handleMouseMove = (event: React.MouseEvent<HTMLCanvasElement>) => {
        if(!chartRef.current) return;

        const chart = chartRef.current;
        const canvas = chart.canvas;
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left; // Get mouse x position relative to canvas
        const xScale = chart.scales.x;
        const value = xScale.getValueForPixel(x);

        setCursorPosition(value);

        const date = new Date(value);
        const formattedTime = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`;
        setCursorTime(formattedTime);
    };

    const handleMouseLeave = () => {
        setCursorPosition(null);
        setCursorTime('');
    };

    const onClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
        if(!chartRef.current) return;

        const chart = chartRef.current;
        const elements = getElementAtEvent(chart, event);

        if (elements.length === 0) return;

        // GEt click position
        const canvasPosition = chart.canvas.getBoundingClientRect();
        const x = event.clientX - canvasPosition.left;

        //Get value from x scale
        const xScale = chart.scales.x;
        const value = xScale.getValueForPixel(x);
        console.log(`Clicked at:` , new Date(value));
        const date = new Date(value);
        onChange(date.toISOString());
        onClose();
    };

    if (!dataRange) {
        return <div>Loading TimelineSelection...</div>;
    }

    const fullStart = new Date(dataRange.start).getTime();
    const fullEnd = new Date(dataRange.end).getTime();

    const data = {
        labels: ["Data availability"],
        datasets: [
            {
                label: "Available Data",
                data: [[fullStart, fullEnd]],
                backgroundColor: 'rgba(28, 121, 228, 0.7)',  // Vibrant blue (data available)
                borderColor: 'rgba(67, 148, 242, 1)',
                borderWidth: 1,
                barPercentage: 1.0,
                categoryPercentage: 1.0,
                z: 10
            },
        ],
    };

    const annotations: Record<string, any> = {};

    if (selectedStart) {
        const startTime = new Date(selectedStart).getTime();
        annotations['selectedStart'] = {
            type: 'line',
            xMin: startTime,
            xMax: startTime,
            yMin: -0.5,
            yMax: 0.5,
            z: 40,
            borderColor: '#4394F2',
            borderWidth: 5,
            label: {
                content: `START: ${new Date(startTime).toLocaleString()}`,
                enabled: true,
                position: 'center',
                xAdjust: 20,
                display: true,
            }
        };
    }

    if (selectedEnd) {
        const endTime = new Date(selectedEnd).getTime();
        annotations['selectedEnd'] = {
            type: 'line',
            xMin: endTime,
            xMax: endTime,
            yMin: -0.5,
            yMax: 0.5,
            z: 40,
            borderColor: '#E64A19',
            borderWidth: 5,
            label: {
                content: `End: ${new Date(endTime).toLocaleString()}`,
                enabled: true,
                display: true,
                position: 'center',
                xAdjust: 20,
            }
        };
    }
    //Gaps
    dataRange.gaps.forEach((gap: Gap, i: number) => {
        const xMin = gap.gap_start !== null ? new Date(gap.gap_start).getTime() : fullStart;
        const xMax = gap.gap_end !== null ? new Date(gap.gap_end).getTime() : fullEnd;
        console.log(`Gap ${i}:`, xMin, xMax);
        let labelText = "Gap";
        if (gap.gap_start === null) labelText = "No data before";
        else if (gap.gap_end === null) labelText = "No data after";
        
        annotations[`gap-${i}`] = {
            type: 'box',
            xMin,
            xMax,
            yMin: -0.5,
            yMax: 0.5,
            z: 15,
            backgroundColor: 'rgba(168, 14, 14, 0.9)',  // Grayish-white
            borderColor: 'rgba(220, 220, 220, 1)',       // Light gray border
            borderWidth: 1,
            label: {
                content: labelText,
                enabled: true,
                position: 'center',
            },
        };
    });

    if (cursorPosition !== null) {
        annotations['cursorLine'] = {
            type: 'line',
            xMin: cursorPosition,
            xMax: cursorPosition,
            yMin: -0.5,
            yMax: 0.5,
            z: 50,
            borderColor: 'rgba(0, 0, 0, 0.8)',
            borderWidth: 2,
            label: {
                content: cursorTime,
                enabled: true,
                position: 'top',
                backgroundColor: 'rgba(255, 255, 255, 0.8)',
                color: 'black',
                font: {
                    weight: 'bold',
                },
            }
        };
    }
    const options: ChartOptions<"bar"> = {
        responsive: true,
        indexAxis: 'y',
        scales: {
            x: {
                type: 'time',
                time: {
                    unit: 'hour',
                    displayFormats: {
                        hour: 'HH:mm',
                        day: 'MMM dd',
                    },
                    parser: (label) => new Date(label),
                    tooltipFormat: 'MMM dd HH:mm',
                },
                min: fullStart,
                max: fullEnd,
                ticks: {
                    //callback to format ticks
                    callback: function(value, index, values){
                        const date = new Date(value);
                        if (date.getHours() === 0 && date.getMinutes() === 0) {
                            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                        }
                        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

                    },
                    autoSkip: true,
                    autoSkipPadding: 20,
                    maxTicksLimit: 20,
                    maxRotation: 0,
                    major: {
                        enabled: true, // This helps emphasize day boundaries
                    }
                },
                grid: {
                    drawOnChartArea: true,
                    color: function(context) {
                        const date = new Date(context.tick.value);
                        return date.getHours() === 0 ? 'rgba(0, 0, 0, 0.5)' : 'rgba(0, 0, 0, 0.1)';
                    }
                },
            },
            y: {
                display: false,
            },
        },
        plugins: {
            legend: {
                display: false,
            },
            annotation: { annotations },
            zoom: {
                pan: {
                    enabled: true,
                    mode: 'x',
                },
                zoom: {
                    wheel: {
                        enabled: true,
                    },
                    pinch: {
                        enabled: true,
                    },
                    drag: {
                        enabled: true,
                        modifierKey: 'ctrl',
                    },
                    mode: 'x',
                },
                limits: {
                    x: {
                        min: fullStart,
                        max: fullEnd,
                    },
                }
            },
            /*
            tooltip: {
                callbacks: {
                    label: (context) => {
                        const start = new Date(context.parsed.x);
                        const end = new Date(context.parsed.x1);
                        return `Available from ${start.toLocaleTimeString()} to ${end.toLocaleTimeString()}`;
                    },
                },
            },
            */
        },
    };

    return (
        <div style={{ position: 'relative'}}>
        <Bar 
            ref={chartRef} 
            data={data} 
            options={options} 
            onClick={onClick}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
        />
        {cursorTime && (
            <div 
                style={{
                    position: 'absolute',
                    top: 10,
                    right: 10,
                    padding: '5px 10px',
                    backgroundColor: 'rgba(255, 255, 255, 0.8)',
                    borderRadius: '4',
                    border: '1px solid #ddd',
                    fontFamily: 'monospace',
                    color: 'black',
                    fontWeight: 'bold',
                }}>
                {cursorTime}
            </div>
        )}
        </div>
    );
}