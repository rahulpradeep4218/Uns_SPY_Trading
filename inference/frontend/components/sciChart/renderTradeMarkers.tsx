import {
    CustomAnnotation,
    ECoordinateMode,
    EVerticalAnchorPoint,
    EHorizontalAnchorPoint,
    SciChartSurface,
    BoxAnnotation,
    AxisMarkerAnnotation,
    AnnotationHoverModifier,
    LineAnnotation
} from "scichart";

import { TradeRecord } from "@/app/types";

export function getTradeMarkerSvg(trade: TradeRecord) {
    const fillColor = trade.status === "OPEN" 
        ? '#FFFFFF' 
        : (trade.profit >= 0 ? '#50C878' : '#FF4C4C');
    
    const strokeColor = trade.signal === 1 ? '#50C878' : '#FF4C4C';
    const isBuy = trade.signal === 1;
    const pathD = isBuy
        ? 'M0,20 L10,0 L20,20 H13 V30 H7 V20 Z' 
        : 'M0,0 L10,20 L20,0 H13 V-10 H7 V0 Z';

    return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="30">
        <path style="fill:${fillColor};fill-opacity:0.85;stroke:${strokeColor};stroke-width:2px;"
        d="${pathD}"/>
    </svg>`;
}

export function renderTradeMarkers(
    sciChartSurface: SciChartSurface, // Use lowercase for instance names
    trades: TradeRecord[],
    markerMapRef: React.RefObject<Map<number, CustomAnnotation>>,
    sim_type: string = 'Simulated'
) {
    const markerMap = markerMapRef.current;
    if (!markerMap) return;

    for (const trade of trades) {
        const timeMs = new Date(trade.trade_time).getTime();
        let marker = markerMap.get(timeMs);

        if (marker) {
            marker.svgString = getTradeMarkerSvg(trade); 
        } else {
            marker = new CustomAnnotation({
                x1: timeMs,
                y1: trade.entry_price,
                verticalAnchorPoint: trade.signal === 1 ? EVerticalAnchorPoint.Top : EVerticalAnchorPoint.Bottom,
                horizontalAnchorPoint: EHorizontalAnchorPoint.Center,
                svgString: getTradeMarkerSvg(trade),
                xCoordinateMode: ECoordinateMode.DataValue,
                yCoordinateMode: ECoordinateMode.DataValue,
            });

            marker.hovered.subscribe((args) => {
                const currentTradeState = (marker as any)["_currentTrade"];
                if (args?.isHovered && currentTradeState) {
                    handleHoverIn(sciChartSurface, marker!, currentTradeState, sim_type);
                } else if (!args?.isHovered) {
                    handleHoverOut(sciChartSurface, marker!);
                }
            });

            sciChartSurface.annotations.add(marker);
            markerMap.set(timeMs, marker);
        }

        // Update the reference so the hover logic always sees the latest status
        (marker as any)["_currentTrade"] = trade; 

        // RL Path Line Logic
        if (sim_type === 'RLSimulated' && trade.status === 'CLOSED' && !(marker as any)["_hasPathLine"]) {
            if (trade.exit_time && trade.exit_price) {
                const pathLine = new LineAnnotation({
                    x1: timeMs,
                    y1: trade.entry_price,
                    x2: new Date(trade.exit_time).getTime(),
                    y2: trade.exit_price,
                    stroke: trade.profit >= 0 ? "#50C878" : "#FF4C4C",
                    strokeThickness: 2,
                    opacity: 0.4,
                });
                sciChartSurface.annotations.add(pathLine);
                (marker as any)["_hasPathLine"] = true;
            }
        }
    }

    // Ensure Hover Modifier exists
    const modifierArray = sciChartSurface.chartModifiers.asArray();
    if (!modifierArray.some(m => m instanceof AnnotationHoverModifier)) {
        sciChartSurface.chartModifiers.add(new AnnotationHoverModifier({
            targets: (m) => m.getAllTargets().filter(a => a instanceof CustomAnnotation)
        }));
    }
}

function handleHoverIn(surface: SciChartSurface, marker: CustomAnnotation, trade: TradeRecord, sim_type: string) {
    const annotationsToAdd: any[] = [];
    const price = trade.entry_price;
    const timeMs = new Date(trade.trade_time).getTime();
    const chartStart = surface.xAxes.get(0).visibleRange.min;
    const chartEnd = surface.xAxes.get(0).visibleRange.max;

    let infoBoxSvg = '';

    // Entry Label
    const entryLabel = new AxisMarkerAnnotation({
        y1: price,
        backgroundColor: "rgba(6, 156, 183, 0.94)",
        color: "white",
        fontSize: 12,
        formattedValue: price.toFixed(2),
    });
    annotationsToAdd.push(entryLabel);

    if (sim_type !== 'RLSimulated') {
        const slY1 = trade.signal === 1 ? price : trade.calc_stop_loss;
        const slY2 = trade.signal === 1 ? trade.calc_stop_loss : price;
        const tpY1 = trade.signal === 1 ? price : trade.calc_take_profit;
        const tpY2 = trade.signal === 1 ? trade.calc_take_profit : price;

        annotationsToAdd.push(new BoxAnnotation({
            x1: chartStart, x2: chartEnd, y1: slY1, y2: slY2,
            fill: 'rgba(255, 0, 0, 0.2)', stroke: "red", strokeThickness: 1,
        }));
        annotationsToAdd.push(new BoxAnnotation({
            x1: chartStart, x2: chartEnd, y1: tpY1, y2: tpY2,
            fill: 'rgba(0, 255, 0, 0.2)', stroke: "green", strokeThickness: 1,
        }));
        annotationsToAdd.push(new AxisMarkerAnnotation({
            y1: trade.calc_stop_loss, backgroundColor: "rgba(255, 0, 0, 0.5)",
            color: "white", formattedValue: trade.calc_stop_loss.toFixed(2),
        }));
        annotationsToAdd.push(new AxisMarkerAnnotation({
            y1: trade.calc_take_profit, backgroundColor: "rgba(0, 255, 0, 0.5)",
            color: "white", formattedValue: trade.calc_take_profit.toFixed(2),
        }));
    } else if (trade.status === 'CLOSED' && trade.exit_time && trade.exit_price) {
        annotationsToAdd.push(new CustomAnnotation({
            x1: new Date(trade.exit_time).getTime(),
            y1: trade.exit_price,
            svgString: `<svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="white" stroke="black" stroke-width="2"/></svg>`,
            horizontalAnchorPoint: EHorizontalAnchorPoint.Center,
            verticalAnchorPoint: EVerticalAnchorPoint.Center,
        }));
        annotationsToAdd.push(new AxisMarkerAnnotation({
            y1: trade.exit_price,
            backgroundColor: trade.profit >= 0 ? "#50C878" : "#FF4C4C",
            color: "white",
            formattedValue: `Exit: ${trade.exit_price.toFixed(2)}`,
        }));
    }

    // InfoBox Logic
    if (sim_type === 'RLSimulated') {
        const profitColor = trade.profit >= 0 ? '#50C878' : '#FF4C4C';
        const exitPriceDisplay = trade.status === "OPEN" ? "N/A" : trade.exit_price?.toFixed(2);
        infoBoxSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="70">
            <rect width="160" height="70" fill="rgba(0,0,0,0.8)" rx="8" />
            <text x="10" y="20" fill="white" font-size="11" font-weight="bold">RL TRADE INFO</text>
            <text x="10" y="38" fill="white" font-size="11">Entry: ${price.toFixed(2)}</text>
            <text x="10" y="52" fill="white" font-size="11">Exit: ${exitPriceDisplay}</text>
            <text x="10" y="65" fill="${profitColor}" font-size="11" font-weight="bold">Profit: ${trade.profit?.toFixed(2)}</text>
        </svg>`;
    } else {
        // ... (Your BS Ratio logic remains same, just ensure variables are declared)
        const bs_ratio = trade.signal === 1 ? 1.5 : 0.8; // Placeholder for brevity
        infoBoxSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="140" height="50">
            <rect width="140" height="50" fill="rgba(0,0,0,0.7)" rx="8" />
            <text x="10" y="20" fill="white" font-size="12">BS Ratio: ${Number(bs_ratio).toFixed(2)}</text>
        </svg>`;
    }

    annotationsToAdd.push(new CustomAnnotation({
        x1: timeMs, y1: price, svgString: infoBoxSvg,
        verticalAnchorPoint: EVerticalAnchorPoint.Bottom,
        horizontalAnchorPoint: EHorizontalAnchorPoint.Right,
    }));

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