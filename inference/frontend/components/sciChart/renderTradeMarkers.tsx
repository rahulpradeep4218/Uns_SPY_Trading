import {
    CustomAnnotation,
    ECoordinateMode,
    EVerticalAnchorPoint,
    EHorizontalAnchorPoint,
    SciChartSurface,
    BoxAnnotation,
    AxisMarkerAnnotation,
    ELabelPlacement,
    NumberRange,
    AnnotationHoverModifier,
    sciChartConfig,
} from "scichart";

import { TradeRecord } from "@/app/types";
import { get } from "lodash";
import { info } from "console";



export function getTradeMarkerSvg(trade: TradeRecord) {
    const fillColor = trade.status === "OPEN" 
        ? '#F2F2ED' // White-ish for open trades
        : (trade.profit >= 0 ? '#50C878' : '#FF4C4C'); // Green/Red for closed trades
    
    const strokeColor = trade.signal === 1 ? '#50C878' : '#FF4C4C'; // Keep stroke color by signal
    
    const isBuy = trade.signal === 1;
    const pathD = isBuy
        ? 'M0,20 L10,0 L20,20 H13 V30 H7 V20 Z' // Buy arrow (points up)
        : 'M0,0 L10,20 L20,0 H13 V-10 H7 V0 Z'; // Sell arrow (points down)

    return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="30">
        <path style="fill:${fillColor};fill-opacity:0.77;stroke:${strokeColor};stroke-width:2px;"
        d="${pathD}"/>
    </svg>`;
}


export function renderTradeMarkers(
    SciChartSurface: SciChartSurface,
    trades: TradeRecord[],
    markerMapRef: React.RefObject<Map<number, CustomAnnotation>>
) {

    const markerMap = markerMapRef.current;
    if (!markerMap) {
        console.error("Trade marker map is not initialized");
        return;
    } 
    //console.log("Rendering trade markers for", trades.length, "trades");  


    for (const trade of trades) {
        //console.log("Time : ", trade.trade_time, "Signal: ", trade.signal, "Entry Price: ", trade.entry_price);
        const timeMs = new Date(trade.trade_time).getTime();
        //console.log("Actual time : ", timeMs);
        //console.log("Processing trade at time:", new Date(timeMs).toLocaleString(), "with signal:", trade.signal);
        if (markerMap.has(timeMs)) {
            // If marker already exists, skip
            const existingMarker = markerMap.get(timeMs);
            if (existingMarker) {
                existingMarker.svgString = getTradeMarkerSvg(trade);
                continue;
            }
        }

        const marker = new CustomAnnotation({
            x1: timeMs,
            y1: trade.entry_price,
            verticalAnchorPoint: trade.signal === 1 ? EVerticalAnchorPoint.Top : EVerticalAnchorPoint.Bottom,
            horizontalAnchorPoint: EHorizontalAnchorPoint.Center,
            svgString: getTradeMarkerSvg(trade),
            xCoordinateMode: ECoordinateMode.DataValue,
            yCoordinateMode: ECoordinateMode.DataValue,
            
        });

        let slBox: BoxAnnotation | undefined;
        let tpBox: BoxAnnotation | undefined;
        let slLabel: AxisMarkerAnnotation | undefined;
        let tpLabel: AxisMarkerAnnotation | undefined;
        
        marker.hovered.subscribe((args) => {
            if (args?.isHovered && !slBox && !tpBox) {
                const price = trade.entry_price;
                const chartStart = SciChartSurface.xAxes.get(0).visibleRange.min;
                const chartEnd = SciChartSurface.xAxes.get(0).visibleRange.max;

                const slY1 = trade.signal === 1 ? price : trade.calc_stop_loss;
                const slY2 = trade.signal === 1 ? trade.calc_stop_loss : price;

                const tpY1 = trade.signal === 1 ? price : trade.calc_take_profit;
                const tpY2 = trade.signal === 1 ? trade.calc_take_profit : price;

                slBox = new BoxAnnotation({
                    x1: chartStart,
                    x2: chartEnd,
                    y1: slY1,
                    y2: slY2,
                    xCoordinateMode: ECoordinateMode.DataValue,
                    yCoordinateMode: ECoordinateMode.DataValue,
                    fill: 'rgba(255, 0, 0, 0.2)',
                    stroke: "red",
                    strokeThickness: 1,
                });

                tpBox = new BoxAnnotation({
                    x1: chartStart,
                    x2: chartEnd,
                    y1: tpY1,
                    y2: tpY2,
                    xCoordinateMode: ECoordinateMode.DataValue,
                    yCoordinateMode: ECoordinateMode.DataValue,
                    fill: 'rgba(0, 255, 0, 0.2)',
                    stroke: "green",
                    strokeThickness: 1,
                });

                slLabel = new AxisMarkerAnnotation({
                    y1: trade.calc_stop_loss,
                    backgroundColor: "rgba(255, 0, 0, 0.5)",
                    color: "white",
                    fontSize: 12,
                    formattedValue: (trade.calc_stop_loss).toFixed(2),
                })

                tpLabel = new AxisMarkerAnnotation({
                    y1: trade.calc_take_profit,
                    backgroundColor: "rgba(0, 255, 0, 0.5)",
                    color: "white",
                    fontSize: 12,
                    formattedValue: (trade.calc_take_profit).toFixed(2),
                });

                const signal = trade.signal;
                const buy_take = trade.buy_take_profit;
                const sell_take = trade.sell_take_profit;
                const buy_stop = trade.buy_stop_loss;
                const sell_stop = trade.sell_stop_loss;

                const buy_diff = buy_take - price;
                const sell_diff = price - sell_take;

                const buy_risk = price - buy_stop;
                const sell_risk = sell_stop - price;

                const buy_risk_ratio = buy_diff != 0 ? buy_risk / buy_diff : 0;
                const sell_risk_ratio = sell_diff != 0 ? sell_risk / sell_diff : 0;

                const sell_buy_ratio = buy_diff != 0 ? sell_diff / buy_diff : 0;
                const buy_sell_ratio = sell_diff != 0 ? buy_diff / sell_diff : 0;

                const bs_ratio = signal === 1 ? buy_sell_ratio : sell_buy_ratio;
                const bs_risk = signal === 1 ? buy_risk_ratio : sell_risk_ratio;

                const infoBox = new CustomAnnotation({
                    x1: timeMs,
                    y1: price,
                    xCoordinateMode: ECoordinateMode.DataValue,
                    yCoordinateMode: ECoordinateMode.DataValue,
                    verticalAnchorPoint: EVerticalAnchorPoint.Bottom,
                    horizontalAnchorPoint: EHorizontalAnchorPoint.Right,
                    svgString: `
                        <svg xmlns="http://www.w3.org/2000/svg" width="140" height="50">
                            <rect width="140" height="50" fill="rgba(0,0,0,0.6)" rx="8" />
                            <text x="10" y="20" fill="white" font-size="12">BS Ratio: ${bs_ratio.toFixed(2)}</text>
                            <text x="10" y="38" fill="white" font-size="12">Risk Ratio: ${bs_risk.toFixed(2)}</text>
                        </svg>
                        `,
                });

                SciChartSurface.annotations.add(slBox);
                SciChartSurface.annotations.add(tpBox);
                SciChartSurface.annotations.add(slLabel);
                SciChartSurface.annotations.add(tpLabel);
                SciChartSurface.annotations.add(infoBox);

                const yMin = Math.min(slY1, slY2, tpY1, tpY2);
                const yMax = Math.max(slY1, slY2, tpY1, tpY2);
                const yAxis = SciChartSurface.yAxes.get(0);
                const vr = yAxis.visibleRange;
                if (yMin < vr.min || yMax > vr.max) {
                    const pad = (yMax - yMin) * 0.2 || 1; 
                    yAxis.visibleRange = new NumberRange(yMin - pad, yMax + pad);
                }

                (marker as any)["_extraAnnotations"] = [slBox, tpBox, slLabel, tpLabel, infoBox];


            } else if (!args?.isHovered && (marker as any)["_extraAnnotations"]) {
                for (const ann of (marker as any)["_extraAnnotations"]) {
                    SciChartSurface.annotations.remove(ann);
                }
                (marker as any)["_extraAnnotations"] = [];
                slBox = tpBox = slLabel = tpLabel = undefined;
            }
        });
        
        SciChartSurface.annotations.add(marker);
        const modifierArray = SciChartSurface.chartModifiers.asArray();
        const hasHoverModifier = modifierArray.some(modifier => modifier instanceof AnnotationHoverModifier);

        if (!hasHoverModifier) {
            SciChartSurface.chartModifiers.add(
                new AnnotationHoverModifier({
                    targets: (modifier) => 
                        modifier.getAllTargets().filter(a => a instanceof CustomAnnotation),
                })
            );
        }

        markerMap.set(timeMs, marker);

    }
}