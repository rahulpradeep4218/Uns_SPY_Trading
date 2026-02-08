import { ChartModifierBase2D } from "scichart/Charting/ChartModifiers/ChartModifierBase2D";
import { ModifierMouseArgs } from "scichart/Charting/ChartModifiers/ModifierMouseArgs";
import { HorizontalLineAnnotation } from "scichart/Charting/Visuals/Annotations/HorizontalLineAnnotation";
import { translateFromCanvasToSeriesViewRect } from "scichart";

export class CreateHorizontalLineModifier extends ChartModifierBase2D {
    public readonly type: string = "CreateHorizontalLineModifier";

    public override modifierMouseDown(args: ModifierMouseArgs): void {
        super.modifierMouseDown(args);
        if (!this.isEnabled) return;
        if (!args.ctrlKey) {
            const mousePoint = translateFromCanvasToSeriesViewRect(args.mousePoint, this.parentSurface.seriesViewRect);
            const yAxis = this.parentSurface.yAxes.get(0);

            const yValue = yAxis.getCurrentCoordinateCalculator().getDataValue(mousePoint.y);

            const annotation = new HorizontalLineAnnotation({
                y1: yValue,
                strokeThickness: 2,
                stroke: "#FF6600",
                isEditable: true,
                showLabel: true,
                labelValue: yValue.toFixed(2),
                yAxisId: yAxis.id,
                onClick: "deleteOnClick",
            });

            this.parentSurface.annotations.add(annotation);
        }
    }
}
