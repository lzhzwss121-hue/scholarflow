export function formatDecisionStatus(status: string): string {
  return status === "complete" ? "已完成" : status === "partial" ? "证据待补" : status === "blocked" ? "已阻塞" : status;
}

export function formatRiskLevel(level: string): string {
  return level === "high" ? "高" : level === "medium" ? "中" : level === "low" ? "低" : "未评估";
}

export function formatGapKind(kind: string): string {
  return kind === "true_gap"
    ? "跨论文研究空白"
    : kind === "engineering_gap"
      ? "工程改进机会"
      : kind === "pseudo_gap"
        ? "疑似伪空白"
        : "待分类";
}

export function formatGapSupportStatus(status: string | undefined): string {
  return status === "corroborated"
    ? "多论文一致"
    : status === "conflicted"
      ? "证据冲突"
      : status === "single_source"
        ? "单一来源"
        : "证据不足";
}

export function formatConfidence(confidence: string | undefined): string {
  return confidence === "high" ? "高置信" : confidence === "medium" ? "中置信" : "低置信";
}

export function formatContributionType(value: string): string {
  const labels: Record<string, string> = {
    analysis: "分析研究",
    benchmark: "评测基准",
    dataset: "数据集研究",
    evaluation: "评测研究",
    method: "方法研究",
    survey: "综述研究",
    system: "系统研究",
    theory: "理论研究",
  };
  return labels[value] ?? value;
}

export function formatFeasibility(value: string): string {
  const labels: Record<string, string> = {
    "one-day": "1 天",
    "one-month": "约 1 个月",
    "one-week": "约 1 周",
    blocked: "当前阻塞",
    partial: "仍需补充条件",
  };
  return labels[value] ?? value;
}
