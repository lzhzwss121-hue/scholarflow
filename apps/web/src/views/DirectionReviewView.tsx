import type { ComponentProps } from "react";
import { DirectionReviewView as DirectionReviewRuntime } from "./shared/ProductViewRuntime";


export function DirectionReviewView(
  props: ComponentProps<typeof DirectionReviewRuntime>,
) {
  return <DirectionReviewRuntime {...props} />;
}
