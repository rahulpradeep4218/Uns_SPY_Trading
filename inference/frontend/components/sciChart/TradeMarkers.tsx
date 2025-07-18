"use client";
import { usePageContext } from "@/context/PageContext";
import {
    AnnotationHoverModifier,
    BoxAnnotation,
    CustomAnnotation,
    ECoordinateMode,
    EHorizontalAnchorPoint,
    EVerticalAnchorPoint,
    IChartModifierBase,
    NumberRange,
    AxisMarkerAnnotation,
    ELabelPlacement
} from "scichart";
import { Button } from "@mui/material";

import { TradeSignalOverlay } from "@/app/types";

export default function TradeSignalControls() {
    const { sciChartSurfaceRef } = usePageContext();

    const addTrades = () => {
        const surface = sciChartSurfaceRef?.current;
        if (!surface) return;

        const trades: TradeSignalOverlay[] = [
            {
                time: new Date("2024-01-12T10:17:00"),
                signal: 1,
                price: 475.92,
                stop_loss: 475,
                take_profit: 478,
            },
            {
                time: new Date("2024-01-12T11:28:00"),
                signal: -1,
                price: 476.76,
                stop_loss: 478,
                take_profit: 475,
            },
        ];

        for (const trade of trades) {
            const price = trade.price;
            console.log("Demo trade time : ", trade.time.getTime());
            const marker = new CustomAnnotation({
                x1: trade.time.getTime(),
                y1: trade.price,
                verticalAnchorPoint:
                    trade.signal === 1 ? EVerticalAnchorPoint.Top : EVerticalAnchorPoint.Bottom,
                horizontalAnchorPoint: EHorizontalAnchorPoint.Center,
                svgString: `<svg xmlns="http://www.w3.org/2000/svg">
                    <path style="fill:${trade.signal === 1 ? '#50C878' : '#FF4C4C'};fill-opacity:0.77;stroke:$
                    {trade.signal === 1 ? '#50C878' : '#FF4C4C'};stroke-width:2px;"
                    d="${trade.signal === 1
                        ? 'M0,20 L10,0 L20,20 H13 V30 H7 V20 Z'
                        : 'M0,0 L10,20 L20,0 H13 V-10 H7 V0 Z'}"/>
                </svg>`
            });

            let slBox: BoxAnnotation | undefined;
            let tpBox: BoxAnnotation | undefined;
            let slLabel: AxisMarkerAnnotation | undefined;
            let tpLabel: AxisMarkerAnnotation | undefined;

            
            marker.hovered.subscribe((args) => {
                if (args?.isHovered && !slBox && !tpBox) {
                    const chartStart = surface.xAxes.get(0).visibleRange.min;
                    const chartEnd = surface.xAxes.get(0).visibleRange.max;

                    const slY1 = trade.signal === 1 ? price: trade.stop_loss;
                    const slY2 = trade.signal === 1 ? trade.stop_loss : price;

                    const tpY1 = trade.signal === 1 ? price : trade.take_profit;
                    const tpY2 = trade.signal === 1 ? trade.take_profit : price;
                    
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

                    surface.annotations.add(slBox);
                    surface.annotations.add(tpBox);

                    //Auto expand y axis
                    const yMin = Math.min(slY1, slY2, tpY1, tpY2);
                    const yMax = Math.max(slY1, slY2, tpY1, tpY2);
                    const yAxis = surface.yAxes.get(0);
                    const vr = yAxis.visibleRange;
                    if (yMin < vr.min || yMax > vr.max) {
                        const pad = (yMax - yMin) * 0.2 || 1; 
                        yAxis.visibleRange = new NumberRange(yMin - pad, yMax + pad);
                    }

                    slLabel = new AxisMarkerAnnotation({
                        y1: trade.stop_loss,
                        backgroundColor: "rgba(255, 0, 0, 0.5)",
                        color: "white",
                        fontSize: 12,
                        formattedValue: trade.stop_loss.toFixed(2),
                    })

                    tpLabel = new AxisMarkerAnnotation({
                        y1: trade.take_profit,
                        backgroundColor: "rgba(0, 255, 0, 0.5)",
                        color: "white",
                        fontSize: 12,
                        formattedValue: trade.take_profit.toFixed(2),
                    });

                    surface.annotations.add(slLabel);
                    surface.annotations.add(tpLabel);
                    //surface.annotations.add(tpLabel);

                } else if (!args?.isHovered) {
                    if (slBox) surface.annotations.remove(slBox);
                    if (tpBox) surface.annotations.remove(tpBox);
                    if (slLabel) surface.annotations.remove(slLabel);
                    if (tpLabel) surface.annotations.remove(tpLabel);
                    slBox = tpBox = undefined;
                }
            });

            surface.annotations.add(marker);
        }

        const modifiersArray: IChartModifierBase[] = surface.chartModifiers.asArray();
        const hasHoverModifier = modifiersArray.some(mod => mod instanceof AnnotationHoverModifier);

        if (!hasHoverModifier) {
            surface.chartModifiers.add(
                new AnnotationHoverModifier({
                    targets: (modifier) =>
                        modifier.getAllTargets().filter(a => a instanceof CustomAnnotation),
                })
            );
        }
    };

    return (
        <div style={{ padding: "10px" }}>
            <Button variant="contained" onClick={addTrades}>
                Add Trade Signals
            </Button>
        </div>
    );
}
