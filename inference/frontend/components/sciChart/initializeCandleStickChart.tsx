import { DateTime } from "luxon";

import {
    AnnotationClickEventArgs,
    buildDataSeries,
    CategoryAxis,
    chartReviver,
    configure2DSurface,
    CursorModifier,
    CursorTooltipSvgAnnotation,
    CustomAnnotation,
    DateTimeNumericAxis,
    EAutoRange,
    EBaseType,
    ECoordinateMode,
    EDataSeriesType,
    EExecuteOn,
    EFillPaletteMode,
    EHorizontalAnchorPoint,
    EMultiLineAlignment,
    ENumericFormat,
    ESeriesType,
    EVerticalAnchorPoint,
    FastCandlestickRenderableSeries,
    FastColumnRenderableSeries,
    FastLineRenderableSeries,
    FastMountainRenderableSeries,
    FastOhlcRenderableSeries,
    GradientParams,
    IFillPaletteProvider,
    IPointMetadata,
    IRenderableSeries,
    MouseWheelZoomModifier,
    NativeTextAnnotation,
    NumberRange,
    NumericAxis,
    OhlcDataSeries,
    OhlcSeriesInfo,
    parseColorToUIntArgb,
    Point,
    registerFunction,
    SciChartOverview,
    SciChartSurface,
    SeriesInfo,
    SmartDateLabelProvider,
    TOhlcSeriesData,
    XyDataSeries,
    XyMovingAverageFilter,
    ZoomExtentsModifier,
    ZoomPanModifier,
    PinchZoomModifier,
    EXyDirection,
    LabelProviderBase2D,
    EAxisType,
    DateLabelProvider,
    DataLabelProvider,
    EDataPointWidthMode,
} from "scichart";

import { appTheme } from "@/app/theme";

import { CreateLineAnnotationModifier } from "@/components/sciChart/CreateLineAnnotationModifier";
import { CreateHorizontalLineModifier } from "@/components/sciChart/CreateHorizLineModifier";
import { CreateTradeMarkerModifier } from "@/components/sciChart/CreateTradeMarkerModifier";
import { ExampleDataProvider } from "@/components/sciChart/ExampleDataProvider";
import { VerticalYRulerModifier } from "@/components/sciChart/RulerModifier";
import { OHLCDataPoint } from "@/app/types";


const deleteOnClick = (args: AnnotationClickEventArgs) => {
    if (args.sender.isSelected && args.mouseArgs.ctrlKey) {
        args.sender.parentSurface.annotations.remove(args.sender, true);
    }
};

registerFunction(EBaseType.OptionFunction, "deleteOnClick", deleteOnClick);

/*
function optimalDataPointWidth(xVal: number[]){
    const xMin = xVal[0]
    const xMax = xVal[xVal.length - 1];
    const totalTimeRange = xMax - xMin;
    console.log("Total time range:", totalTimeRange);
    const expectedCandleCount = totalTimeRange / (60*180000); // Assuming 1 minute candles
    console.log("Expected candle count:", expectedCandleCount);
    const returnVal = Math.min(0.6, Math.max(0.00000000000000001, 5 / expectedCandleCount)); 
    console.log("Calculated dataPointWidth:", returnVal);
    return returnVal;
}
    */


export const initializeCandleStickChart = async (
    divElementId: string | HTMLDivElement,
    candleDataSeriesRef: React.RefObject<OhlcDataSeries | null>,
    realtimeSeriesRef: React.RefObject<OhlcDataSeries | null>,
    buyTakeProfitRef: React.RefObject<XyDataSeries | null>,
    sellTakeProfitRef: React.RefObject<XyDataSeries | null>,
) => {
    SciChartSurface.configure({
        wasmUrl: "/trading/ui/scichart2d.wasm",
        dataUrl: "/trading/ui/scichart2d.data",
    });
    const { sciChartSurface, wasmContext } = await SciChartSurface.create(divElementId, {
        theme: appTheme.SciChartJsTheme,
    });
    
    const inf_url = process.env.NEXT_PUBLIC_INF_URL;
    const res = await fetch(`${inf_url}/api/price_data/SPY`)
    const ohlcData = await res.json();

    const utcProvider = new SmartDateLabelProvider({
        labelFormat: ENumericFormat.Date_HHMM,
        cursorLabelFormat: ENumericFormat.Date_HHMM,
    });

    utcProvider.formatLabel = (value: number) => 
        DateTime
            .fromMillis(value, { zone: "America/New_York" })
            .toFormat("HH:mm");

    utcProvider.formatCursorLabel = (value: number) => 
        DateTime
            .fromMillis(value, { zone: "America/New_York" })
            .toFormat("yyyy-MM-dd HH:mm");
    
    const xValues = ohlcData.map((item: any) => {
        const dt = DateTime.fromISO(item.time, { zone: "America/New_York" });
        if (!dt.isValid) {
            console.error("Invalid date in OHLC data:", item.time);
            return null; // or handle the error as needed
        }
        return dt.toMillis();
    });
    const openValues = ohlcData.map((item: any) => item.open);
    const highValues = ohlcData.map((item: any) => item.high);
    const lowValues = ohlcData.map((item: any) => item.low);
    const closeValues = ohlcData.map((item: any) => item.close);

    const candleDataSeries = new OhlcDataSeries(wasmContext, {
        xValues: xValues,
        openValues: openValues,
        highValues: highValues,
        lowValues: lowValues,
        closeValues: closeValues,
        dataSeriesName: "Rahul9 Historic Candles",
    });
    candleDataSeriesRef.current = candleDataSeries; 
    
    
    
    const realtimeDataSeries = new OhlcDataSeries(wasmContext, {
        dataSeriesName: "Rahul9 Realtime Candles",
    });
    realtimeSeriesRef.current = realtimeDataSeries;

    const buyTakeProfitDataSeries = new XyDataSeries(wasmContext, {
        dataSeriesName: "Buy Take Profits",
    });
    buyTakeProfitRef.current = buyTakeProfitDataSeries;

    const sellTakeProfitDataSeries = new XyDataSeries(wasmContext, {
        dataSeriesName: "Sell Take Profits",
    });
    sellTakeProfitRef.current = sellTakeProfitDataSeries;

    const xAxis = new DateTimeNumericAxis(wasmContext, {
        // autoRange.never as we're setting visibleRange explicitly below. If you dont do this, leave this flag default
        autoRange: EAutoRange.Never,
        labelFormat: ENumericFormat.Date_HHMMSS,
        drawMajorGridLines: false,
        drawMinorGridLines: false,
        majorDelta: 1,
        minorDelta: 0.2,
        growBy: new NumberRange(0.05, 0.05),
        labelProvider: utcProvider,
    });

    sciChartSurface.xAxes.add(xAxis);

    // ✅ Set visible range to last 100 candles
    const startIdx = Math.max(0, xValues.length - 100);
    xAxis.visibleRange = new NumberRange(xValues[startIdx], xValues[xValues.length - 1]);



    const candlestickSeries = new FastCandlestickRenderableSeries(wasmContext, {
        id: "Candles",
        dataSeries: candleDataSeriesRef.current,
        //dataPointWidth: 0.005, // width of the candle
        dataPointWidthMode: EDataPointWidthMode.Range,
        dataPointWidth: 30000, // width of the candle in pixels
        stroke: appTheme.ForegroundColor, // used by cursorModifier below
        strokeThickness: 1,
        brushUp: appTheme.VividGreen + "77",
        brushDown: appTheme.MutedRed + "77",
        strokeUp: appTheme.VividGreen,
        strokeDown: appTheme.MutedRed,
    });

    const realtimeSeries = new FastCandlestickRenderableSeries(wasmContext, {
        id: "Realtime Candles",
        dataSeries: realtimeSeriesRef.current,
        dataPointWidthMode: EDataPointWidthMode.Range,
        dataPointWidth: 40000, // width of the candle in pixels
        brushUp: "rgba(57, 255, 20, 0.7)",   // Neon green fill
        brushDown: "rgba(255, 7, 58, 0.7)",  // Neon red fill
        strokeUp: "#39FF14",   // Neon outline
        strokeDown: "#FF073A",
        strokeThickness: 2,
    });

    const buyTakeProfitSeries = new FastLineRenderableSeries(wasmContext, {
        id: "Buy Take Profits",
        dataSeries: buyTakeProfitRef.current,
        stroke: "rgba(93, 247, 59, 0.5)", // Cyan color
        strokeThickness: 2,
    });

    const sellTakeProfitSeries = new FastLineRenderableSeries(wasmContext, {
        id: "Sell Take Profits",
        dataSeries: sellTakeProfitRef.current,
        stroke: "rgba(252, 75, 31, 0.5)", // Orange color
        strokeThickness: 2,
    });

    sciChartSurface.renderableSeries.add(candlestickSeries);
    sciChartSurface.renderableSeries.add(realtimeSeries);
    sciChartSurface.renderableSeries.add(buyTakeProfitSeries);
    sciChartSurface.renderableSeries.add(sellTakeProfitSeries);



    // Add some moving averages using SciChart's filters/transforms API
    // when candleDataSeries updates, XyMovingAverageFilter automatically recomputes
    sciChartSurface.renderableSeries.add(
        new FastLineRenderableSeries(wasmContext, {
            dataSeries: new XyMovingAverageFilter(candleDataSeries, {
                dataSeriesName: "Moving Average (20)",
                length: 20,
            }),
            stroke: appTheme.VividSkyBlue,
        })
    );

    sciChartSurface.renderableSeries.add(
        new FastLineRenderableSeries(wasmContext, {
            dataSeries: new XyMovingAverageFilter(candleDataSeries, {
                dataSeriesName: "Moving Average (50)",
                length: 50,
            }),
            stroke: appTheme.VividPink,
        })
    );


    const cursorModifier = new CursorModifier({
        crosshairStroke: appTheme.MutedOrange,
        axisLabelFill: appTheme.VividOrange,
        tooltipLegendTemplate: getTooltipLegendTemplate,
        showAxisLabels: true,
    });


    // Optional: Add some interactivity modifiers
    sciChartSurface.chartModifiers.add(
        new ZoomExtentsModifier(),
        new MouseWheelZoomModifier(),
        new ZoomPanModifier({ 
            id: "pan",
            xyDirection: EXyDirection.XyDirection,
            enableZoom: true,
            horizontalGrowFactor: 0.005,
            verticalGrowFactor: 0.005,
        }),
        new CreateTradeMarkerModifier({ id: "marker" }),
        new CreateLineAnnotationModifier({ id: "line" }),
        new CreateHorizontalLineModifier({ id: "horline" }),
        cursorModifier,
    );
    sciChartSurface.chartModifiers.getById("marker").isEnabled = false;
    sciChartSurface.chartModifiers.getById("line").isEnabled = false;
    sciChartSurface.chartModifiers.getById("horline").isEnabled = false;
    


    // Create a NumericAxis on the YAxis with 2 Decimal Places
    sciChartSurface.yAxes.add(
        new NumericAxis(wasmContext, {
            growBy: new NumberRange(0.1, 0.1),
            labelFormat: ENumericFormat.Decimal,
            labelPrecision: 2,
            labelPrefix: "$",
            autoRange: EAutoRange.Always,
        })
    );
    const helpAnnotation = new NativeTextAnnotation({
        x1: 20,
        y1: 20,
        xCoordinateMode: ECoordinateMode.Pixel,
        yCoordinateMode: ECoordinateMode.Pixel,
        verticalAnchorPoint: EVerticalAnchorPoint.Top,
        multiLineAlignment: EMultiLineAlignment.Left,
        textColor: appTheme.ForegroundColor,
    });
    // Add this to modifierAnnotations so it is not saved/loaded
    sciChartSurface.modifierAnnotations.add(helpAnnotation);

    const getDefinition = () => {
        return {
            visibleRange: xAxis.visibleRange,
            annotations: sciChartSurface.annotations.asArray().map((annotation) => annotation.toJSON()),
            data: candleDataSeries.toJSON(),
        };
    };
    const applyDefinition = (definition: any) => {
        if (definition) {
            configure2DSurface({ annotations: definition.annotations }, sciChartSurface, wasmContext);
            xAxis.visibleRange = definition.visibleRange;
            const newData = definition.data.options as TOhlcSeriesData;
            candleDataSeries.clear();
            candleDataSeries.appendRange(
                newData.xValues!,
                newData.openValues!,
                newData.highValues!,
                newData.lowValues!,
                newData.closeValues!
            );
        }
    };


    const setChartMode = (mode: string) => {
        sciChartSurface.chartModifiers.getById("marker").isEnabled = mode === "marker";
        sciChartSurface.chartModifiers.getById("line").isEnabled = mode === "line";
        sciChartSurface.chartModifiers.getById("pan").isEnabled = mode === "pan";
        sciChartSurface.chartModifiers.getById("horline").isEnabled = mode === "horline";

        helpAnnotation.text = {
            pan: `Click and drag to pan the chart`,
            line: `Click and drag to draw a line. Ctrl + click a line to delete it`,
            marker: `Left click to place a buy marker. Right click to place a sell marker. Ctrl + Click to delete a marker`,
            horline: `Click and drag to draw a horizontal line. Ctrl + click a line to delete it`,
        }[mode] ?? 'Select a tool mode';
    };

    // const resetChart = () => {
    //     sciChartSurface.annotations.clear(true);
    //     // Zoom to the latest 100 candles
    //     const startIdx = Math.max(0, xValues.length - 100);
    //     const total = xValues.length;
    //     xAxis.visibleRange = new NumberRange(xValues[startIdx], xValues[total - 1]);
    // };

    // resetChart();
    setChartMode("pan");

    return {
        sciChartSurface,
        controls: { getDefinition, applyDefinition, setChartMode },
    };
};    

// Override the standard tooltip displayed by CursorModifier
const getTooltipLegendTemplate = (seriesInfos: SeriesInfo[], svgAnnotation: CursorTooltipSvgAnnotation) => {
    let outputSvgString = "";

    // Foreach series there will be a seriesInfo supplied by SciChart. This contains info about the series under the house
    seriesInfos.forEach((seriesInfo, index) => {
        const y = 20 + index * 20;
        const textColor = seriesInfo.stroke;
        let legendText = seriesInfo.formattedYValue;
        if (seriesInfo.dataSeriesType === EDataSeriesType.Ohlc) {
            const o = seriesInfo as OhlcSeriesInfo;
            legendText = `Open=${o.formattedOpenValue} High=${o.formattedHighValue} Low=${o.formattedLowValue} Close=${o.formattedCloseValue}`;
        }
        outputSvgString += `<text x="500" y="${y}" font-size="13" font-family="Verdana" fill="${textColor}">
            ${seriesInfo.seriesName}: ${legendText}
        </text>`;
    });

    return `<svg width="100%" height="100%">
                ${outputSvgString}
            </svg>`;
};