'use client';
import { Chart, LinearScale, TimeScale, BarElement, Tooltip, Legend, scales, ChartOptions, ChartTypeRegistry, CategoryScale } from 'chart.js';
import annotationPlugin from 'chartjs-plugin-annotation';
import 'chartjs-adapter-date-fns';
import { Bar, getElementAtEvent } from 'react-chartjs-2';
import { useEffect, useState, useRef, useMemo, useCallback, use } from 'react';
import { bottomNavigationActionClasses } from '@mui/material';
import { color } from 'chart.js/helpers';
import zoomPlugin, { zoom } from 'chartjs-plugin-zoom';
import { set, throttle } from 'lodash';
import Slider from '@mui/material/Slider';
import { styled } from '@mui/material/styles';


const RangeSliderContainer = styled('div')({
  padding: '20px 40px',
  marginTop: '-20px', // Pull it up closer to the chart
});



Chart.register(LinearScale, TimeScale, CategoryScale, BarElement, Tooltip, Legend, annotationPlugin, zoomPlugin);

interface Coverage {
    start: string | null;
    end: string | null;
}

interface DataRange {
    start: string;
    end: string;
    coverage: Coverage[];
}

interface TimelineSelectionProps {
    symbol: string;
    onChange: (time: string) => void;
    onClose: () => void;
    selectedStart?: string | null;
    selectedEnd?: string | null;
}

interface ZoomRange {
  min: number;
  max: number;
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
    const [zoomRange, setZoomRange] = useState<ZoomRange>({
    min: 0,
    max: 0
    });
    const [fullRange, setFullRange] = useState<{ start: number; end: number }>({
        start: 0,
        end: 0
    });
    
    useEffect(() => {
        const fetchCoverage = async () => {
            try {
                const inf_url = process.env.NEXT_PUBLIC_INF_URL;
                const response = await fetch(`${inf_url}/api/trades/ohlc/coverage?symbol=${symbol}`);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                setDataRange(data);

                //Calculate extended range
                const extendedStart = new Date(data.start);
                extendedStart.setDate(extendedStart.getDate() - 5); // Extend start by five days
                const extendedEnd = new Date(data.end);
                extendedEnd.setDate(extendedEnd.getDate() + 5); // Extend end by

                const fullStart = extendedStart.getTime();
                const fullEnd = extendedEnd.getTime();
                setFullRange({
                    start: fullStart,
                    end: fullEnd
                });
                setZoomRange({
                    min: fullStart,
                    max: fullEnd
                });

            } catch (error) {
                console.error("Error fetching coverage:", error);
            }
        };
        fetchCoverage();

    }, [symbol]);

    const handleMouseMove = useMemo(() => {
        return throttle((event: React.MouseEvent<HTMLCanvasElement>) => {
            if(!chartRef.current) return;

            const chart = chartRef.current;
            const canvas = chart.canvas;
            const rect = canvas.getBoundingClientRect();
            const x = event.clientX - rect.left; // Get mouse x position relative to canvas
            const xScale = chart.scales.x;
            const value     = xScale.getValueForPixel(x);

            setCursorPosition(value);

            const date = new Date(value);
            const formattedTime = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
            setCursorTime(formattedTime);
        }, 100);
    }, []);


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
        onChange(date.toLocaleString('sv-SE').replace(' ', 'T')); // Convert to ISO format
        onClose();
    };


    const handleZoomRangeChange = useCallback((event: Event, newValue: number | number[], activeThumb: number) => {
        if (!Array.isArray(newValue)) return;
        
        if (newValue[0] >= newValue[1]) return;
        
        setZoomRange({
            min: newValue[0],
            max: newValue[1]
        });

        if (chartRef.current) {
            const chart = chartRef.current;
            chart.options.scales.x.min = newValue[0];
            chart.options.scales.x.max = newValue[1];
            chart.update();
        }

    }, [chartRef, fullRange.start, fullRange.end]);

    const getSliderMarks = () => {
        if (!dataRange) return [];

        const marks = [];
        const start = new Date(fullRange.start);
        const end = new Date(fullRange.end);

        const totalDays = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));

        const step = Math.max(1, Math.floor(totalDays / 5)); // Adjust step to ensure marks are not too dense

        for (let i = 0; i <= totalDays; i += step) {
            const markDate = new Date(start);
            markDate.setDate(start.getDate() + i);
            marks.push({
                value: markDate.getTime(),
                label: markDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
            });
        }

        return marks;
    };

    if (!dataRange) {
        return <div>Loading TimelineSelection...</div>;
    }
    const data = {
        labels: ["Full Range"],
        datasets: [
            {
                label: "Full Range",
                data: [[fullRange.start, fullRange.end]],
                backgroundColor: 'rgba(234, 242, 250, 0.7)',  // Vibrant blue (data available)
                borderColor: 'rgb(194, 219, 248)',
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
    dataRange.coverage.forEach((cov: Coverage, i: number) => {
        const xMin = new Date(cov.start).getTime();
        const xMax = new Date(cov.end).getTime();
        console.log(`Coverage ${i}:`, xMin, xMax);
        let labelText = "Coverage";
        if (cov.start === null) labelText = "No data before";
        else if (cov.end === null) labelText = "No data after";
        
        annotations[`coverage-${i}`] = {
            type: 'box',
            xMin,
            xMax,
            yMin: -0.5,
            yMax: 0.5,
            z: 15,
            backgroundColor: 'rgba(168, 14, 14, 0.9)',  // Grayish-white
            borderColor: 'rgb(223, 56, 56)',       // Light gray border
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
        animation: false,
        scales: {
            x: {
                type: 'time',
                time: {
                    unit: 'day',
                    displayFormats: {
                        minute: 'HH:mm',
                        hour: "HH:mm",
                        day: 'MMM dd',
                    },
                    parser: (label) => new Date(label),
                    tooltipFormat: 'MMM dd HH:mm',
                },
                min: zoomRange.min,
                max: zoomRange.max,
                afterFit: (scale) => {
                    scale.min = zoomRange.min;
                    scale.max = zoomRange.max;
                },
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
            annotation: { 
                annotations: annotations,
                clip: false, // Ensure annotations are not clipped 
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
        <RangeSliderContainer>
            <Slider
                value={[zoomRange.min, zoomRange.max]}
                onChange={handleZoomRangeChange}
                valueLabelDisplay="auto"
                valueLabelFormat={(value) => new Date(value).toLocaleDateString()}
                min={fullRange.start}
                max={fullRange.end}
                step={60 * 60 * 1000} // Step by one day
                marks={getSliderMarks()}
                sx={{
                    '& .MuiSlider-thumb': {
                        height: 20,
                        width: 10,
                        borderRadius: '4px',
                    },
                    '& .MuiSlider-track': {
                        height: 8,
                    },
                    '& .MuiSlider-rail': {
                        height: 8,
                        opacity: 0.5,
                    },
                }}
            />
        </RangeSliderContainer>
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