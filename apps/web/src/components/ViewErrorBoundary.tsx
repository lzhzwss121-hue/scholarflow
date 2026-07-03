import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import type { ViewId } from "../mockData";

export class ViewErrorBoundary extends Component<
  { children: ReactNode; view: ViewId },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ScholarFlow view render failed", error, errorInfo);
  }

  componentDidUpdate(previousProps: { view: ViewId }) {
    if (previousProps.view !== this.props.view && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <section className="view-error-state" role="alert">
          <AlertTriangle size={24} />
          <div>
            <h2>当前视图渲染失败，请刷新或检查 artifact JSON 结构。</h2>
            <p>其他页面仍可继续使用；错误详情已保留在浏览器 Console 中。</p>
          </div>
        </section>
      );
    }

    return this.props.children;
  }
}
