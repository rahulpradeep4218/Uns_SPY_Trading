'use client';

import {
  createChart,
  ColorType,
  CandlestickData,
  CandlestickSeries,
  CrosshairMode,
} from 'lightweight-charts';


import React, { useEffect, useRef } from 'react';

type Props = {
  data: CandlestickData[]
  colors?: {
    backgroundColor?: string;
    textColor?: string;
    upColor?: string;
    downColor?: string;
    wickUpColor?: string;
    wickDownColor?: string;
  };
};


export const CandlestickChart: React.FC<Props> = ({
  data,
  colors = {},
}) => {
  const {
    backgroundColor = 'white',
    textColor = 'black',
    upColor = '#26a69a',
    downColor = '#ef5350',
    wickUpColor = '#26a69a',
    wickDownColor = '#ef5350',
  } = colors;

  const chartContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const chart = createChart(chartContainerRef.current!, {
      layout: {
        background: { type: ColorType.Solid, color: backgroundColor },
        textColor,
      },
      width: chartContainerRef.current!.clientWidth,
      height: 600,
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      grid: {
        vertLines: { color: '#eee' },
        horzLines: { color: '#eee' },
      },
      timeScale: { timeVisible: true },
      rightPriceScale: {
        scaleMargins: { top: 0.1, bottom: 0.2 },
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor,
      downColor,
      borderVisible: false,
      wickUpColor,
      wickDownColor,
    });

    candleSeries.setData(data);
    chart.timeScale().fitContent();

    const handleResize = () => {
      chart.applyOptions({ width: chartContainerRef.current!.clientWidth });
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data, backgroundColor, textColor, upColor, downColor, wickUpColor, wickDownColor]);

  return <div ref={chartContainerRef} />;
};


