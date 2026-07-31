import type { ComponentProps } from "react";
import { DirectionReviewPanel } from "./DirectionReviewPanel";


export function DirectionReviewView(
  props: ComponentProps<typeof DirectionReviewPanel>,
) {
  return <DirectionReviewPanel {...props} />;
}
