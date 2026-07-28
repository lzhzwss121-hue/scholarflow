import type { ComponentProps } from "react";
import { ProductPaperReaderView as ProductPaperReaderRuntime } from "./shared/ProductViewRuntime";


export function ProductPaperReaderView(
  props: ComponentProps<typeof ProductPaperReaderRuntime>,
) {
  return <ProductPaperReaderRuntime {...props} />;
}
