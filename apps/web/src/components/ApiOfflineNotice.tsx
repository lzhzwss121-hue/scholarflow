import { AlertTriangle } from "lucide-react";

export function ApiOfflineNotice() {
  return (
    <div className="api-offline-notice" role="alert">
      <AlertTriangle size={18} />
      <span>API 未连接，请先启动 ScholarFlow 后端服务。</span>
    </div>
  );
}
