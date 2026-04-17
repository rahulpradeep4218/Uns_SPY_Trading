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
    LineAnnotation
} from "scichart";

import { TradeRecord } from "@/app/types";
import { get } from "lodash";
import { info } from "console";

import { usePageContext } from '@/context/PageContext';



export function getTradeMarkerSvg(trade: TradeRecord) {
    const fillColor = trade.status === "OPEN" 
        ? '#FFFFFF' // White-ish for open trades
        : (trade.profit >= 0 ? '#50C878' : '#FF4C4C'); // Green/Red for closed trades
    
    const strokeColor = trade.signal === 1 ? '#50C878' : '#FF4C4C'; // Keep stroke color by signal
    
    const isBuy = trade.signal === 1;
    const pathD = isBuy
        ? 'M0,20 L10,0 L20,20 H13 V30 H7 V20 Z' // up arrow (points up)
        : 'M0,0 L10,20 L20,0 H13 V-10 H7 V0 Z'; // down arrow (points down)

    return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="30">
        <path style="fill:${fillColor};fill-opacity:0.85;stroke:${strokeColor};stroke-width:2px;"
        d="${pathD}"/>
    </svg>`;
}


export function renderTradeMarkers(
    SciChartSurface: SciChartSurface,
    trades: TradeRecord[],
    markerMapRef: React.RefObject<Map<number, CustomAnnotation>>,
    sim_type: string = 'Simulated'
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
        let marker = markerMap.get(timeMs);
        //console.log("Actual time : ", timeMs);
        //console.log("Processing trade at time:", new Date(timeMs).toLocaleString(), "with signal:", trade.signal);
        if (marker) {
            // If marker already exists, 
            marker.svgString = getTradeMarkerSvg(trade); // Update SVG in case status/profit changed
        }
        else{
            marker = new CustomAnnotation({
                x1: timeMs,
                y1: trade.entry_price,
                verticalAnchorPoint: trade.signal === 1 ? EVerticalAnchorPoint.Top : EVerticalAnchorPoint.Bottom,
                horizontalAnchorPoint: EHorizontalAnchorPoint.Center,
                svgString: getTradeMarkerSvg(trade),
                xCoordinateMode: ECoordinateMode.DataValue,
                yCoordinateMode: ECoordinateMode.DataValue,
                
            });

            // ATTACH HOVER LISTENER (Only once per marker)
            marker.hovered.subscribe((args) => {
                // IMPORTANT: We pull the LATEST trade data that was "stuck" to this marker
                const currentTradeState = (marker as any)["_currentTrade"];
                if (args?.isHovered && currentTradeState) {
                    handleHoverIn(SciChartSurface, marker!, currentTradeState, sim_type);
                } else if (!args?.isHovered) {
                    handleHoverOut(SciChartSurface, marker!);
                }
            });

            SciChartSurface.annotations.add(marker);
            markerMap.set(timeMs, marker);
        }

        (marker as any)["_currentTrade"] = trade; // Always update the trade data reference for hover info

        // --- RLSimulated Path Line Logic ---
        // If it's RL and closed, draw a line from entry to exit
        if (sim_type === 'RLSimulated' && trade.status === 'CLOSED' && !(marker as Any)["_hasPathLine"]) {
            if (trade.exit_time && trade.exit_price) {
                const pathLine = new LineAnnotation({
                    x1: timeMs,
                    y1: trade.entry_price,
                    x2: new Date(trade.exit_time).getTime(),
                    y2: trade.exit_price,
                    stroke: trade.profit >= 0 ? "#50C878" : "#FF4C4C",
                    strokeThickness: 2,
                    opacity: 0.4, // Subtle line showing the trade path
                    xCoordinateMode: ECoordinateMode.DataValue,
                    yCoordinateMode: ECoordinateMode.DataValue,
                });
                SciChartSurface.annotations.add(pathLine);
                (marker as any)["_hasPathLine"] = true; // Mark that we've added the path line for this trade
            }
        }

        let slBox: BoxAnnotation | undefined;
        let tpBox: BoxAnnotation | undefined;
        let slLabel: AxisMarkerAnnotation | undefined;
        let tpLabel: AxisMarkerAnnotation | undefined;
        let entryLabel: AxisMarkerAnnotation | undefined;
        
        marker.hovered.subscribe((args) => {
            if (args?.isHovered) {
                const annotationsToAdd: any[] = [];
                const price = trade.entry_price;
                const chartStart = SciChartSurface.xAxes.get(0).visibleRange.min;
                const chartEnd = SciChartSurface.xAxes.get(0).visibleRange.max;

                let infoBoxSvg = '';
                
                // Shared Label
                entryLabel = new AxisMarkerAnnotation({
                    y1: trade.entry_price,
                    backgroundColor: "rgba(6, 156, 183, 0.94)",
                    color: "white",
                    fontSize: 12,
                    formattedValue: (trade.entry_price).toFixed(2),
                });
                annotationsToAdd.push(entryLabel);



                // Condition A - Standard Simulation: Show SL/TP boxes for all trades
                
                if (sim_type !== 'RLSimulated') {
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

                    annotationsToAdd.push(slBox, tpBox, slLabel, tpLabel);
                }

                // Condition B - RL Simulation
                else if (sim_type === 'RLSimulated' && trade.status === 'CLOSED' && trade.exit_time && trade.exit_price) {
                    const exitMarker = new CustomAnnotation({
                        x1: new Date(trade.exit_time!).getTime(),
                        y1: trade.exit_price,
                        svgString: `<svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="white" stroke="black" stroke-width="2"/></svg>`,
                        horizontalAnchorPoint: EHorizontalAnchorPoint.Center,
                        verticalAnchorPoint: EVerticalAnchorPoint.Center,
                    });
                    const exitLabel = new AxisMarkerAnnotation({
                        y1: trade.exit_price,
                        backgroundColor: trade.profit >= 0 ? "#50C878" : "#FF4C4C",
                        color: "white",
                        formattedValue: `Exit: ${trade.exit_price.toFixed(2)}`,
                    });
                    annotationsToAdd.push(exitMarker, exitLabel);
                }
                
                
                if (sim_type === 'RLSimulated') {
                    const profitColor = trade.profit >= 0 ? '#50C878' : '#FF4C4C';
                    const exitPriceDisplay = trade.status === "OPEN" ? "N/A" : trade.exit_price?.toFixed(2);
                    
                    infoBoxSvg = `
                        <svg xmlns="http://www.w3.org/2000/svg" width="160" height="70">
                            <rect width="160" height="70" fill="rgba(0,0,0,0.8)" rx="8" />
                            <text x="10" y="20" fill="white" font-size="11" font-weight="bold">RL TRADE INFO</text>
                            <text x="10" y="38" fill="white" font-size="11">Entry: ${price.toFixed(2)}</text>
                            <text x="10" y="52" fill="white" font-size="11">Exit: ${exitPriceDisplay}</text>
                            <text x="10" y="65" fill="${profitColor}" font-size="11" font-weight="bold">Profit: ${trade.profit?.toFixed(2)}</text>
                        </svg>`;
                }
                else {
                    const signal = trade.signal;
                    const buy_take = trade.buy_take_profit;
                    const sell_take = trade.sell_take_profit;
                    const buy_stop = trade.buy_stop_loss;
                    const sell_stop = trade.sell_stop_loss;

                    const buy_diff = buy_take - price;
                    const sell_diff = price - sell_take;

                    const buy_risk = price - buy_stop;
                    const sell_risk = sell_stop - price;

                    // ✅ Risk ratios (unchanged)
                    const buy_risk_ratio = buy_diff !== 0 ? buy_risk / buy_diff : 0;
                    const sell_risk_ratio = sell_diff !== 0 ? sell_risk / sell_diff : 0;

                    // ✅ Sell/Buy Ratio (bearish boost + denominator smoothing)
                    let sell_buy_ratio;
                    if (buy_diff < 0) {
                    // Bearish case: buy TP is below current price -> boost SELL
                    sell_buy_ratio = (Math.abs(buy_diff) + 1) * sell_diff;
                    } else {
                    // Normal case: smooth denominator by adding +1
                    sell_buy_ratio = buy_diff !== 0 ? sell_diff / (buy_diff + 1) : 0;
                    }

                    // ✅ Buy/Sell Ratio (bullish boost + denominator smoothing)
                    let buy_sell_ratio;
                    if (sell_diff < 0) {
                    // Bullish case: sell TP is above current price -> boost BUY
                    buy_sell_ratio = (Math.abs(sell_diff) + 1) * buy_diff;
                    } else {
                    // Normal case: smooth denominator by adding +1
                    buy_sell_ratio = sell_diff !== 0 ? buy_diff / (sell_diff + 1) : 0;
                    }

                    // ✅ Select ratio & risk based on trade direction (1 = buy signal, else sell)
                    const bs_ratio = signal === 1 ? buy_sell_ratio : sell_buy_ratio;
                    const bs_risk = signal === 1 ? buy_risk_ratio : sell_risk_ratio;
                    infoBoxSvg = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="140" height="50">
                        <rect width="140" height="50" fill="rgba(0,0,0,0.7)" rx="8" />
                        <text x="10" y="20" fill="white" font-size="12">BS Ratio: ${Number(bs_ratio || 0).toFixed(2)}</text>
                        <text x="10" y="38" fill="white" font-size="12">Risk Ratio: ${Number(bs_risk || 0).toFixed(2)}</text>
                    </svg>`;
                }

                const infoBox = new CustomAnnotation({
                    x1: timeMs,
                    y1: price,
                    xCoordinateMode: ECoordinateMode.DataValue,
                    yCoordinateMode: ECoordinateMode.DataValue,
                    verticalAnchorPoint: EVerticalAnchorPoint.Bottom,
                    horizontalAnchorPoint: EHorizontalAnchorPoint.Right,
                    svgString: infoBoxSvg,
                });

                annotationsToAdd.push(infoBox);

                annotationsToAdd.forEach(ann => SciChartSurface.annotations.add(ann));
                (marker as any)["_extraAnnotations"] = annotationsToAdd;


            } else if (!args?.isHovered && (marker as any)["_extraAnnotations"]) {
                for (const ann of (marker as any)["_extraAnnotations"]) {
                    SciChartSurface.annotations.remove(ann);
                }
                (marker as any)["_extraAnnotations"] = [];
                slBox = tpBox = slLabel = tpLabel = entryLabel = undefined;
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


// HELPER: To keep the loop clean, move the big hover logic here
function handleHoverIn(surface: SciChartSurface, marker: CustomAnnotation, trade: TradeRecord, sim_type: string) {
    const annotationsToAdd: any[] = [];
    const price = trade.entry_price;
    const timeMs = new Date(trade.trade_time).getTime();
    
    // ... Copy your existing SL/TP Box and InfoBox logic here ...
    // ... Use 'trade' passed into this function ...

    // Store for cleanup
    (marker as any)["_extraAnnotations"] = annotationsToAdd;
    annotationsToAdd.forEach(ann => surface.annotations.add(ann));
}

function handleHoverOut(surface: SciChartSurface, marker: CustomAnnotation) {
    const extras = (marker as any)["_extraAnnotations"];
    if (extras) {
        extras.forEach((ann: any) => surface.annotations.remove(ann));
        (marker as any)["_extraAnnotations"] = [];
    }
}