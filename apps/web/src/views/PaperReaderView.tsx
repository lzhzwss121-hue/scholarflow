import type { ComponentProps } from "react";
import { ProductPaperReaderPanel } from "./PaperReaderPanel";


export function ProductPaperReaderView(
  props: ComponentProps<typeof ProductPaperReaderPanel>,
) {
  return <ProductPaperReaderPanel {...props} />;
}
