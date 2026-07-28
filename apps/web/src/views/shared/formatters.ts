import type { ApiSignalEvidence } from "@scholarflow/schemas";


export function formatAcademicText(value: string): string {
  return value
    .replace(/\$\s*(\d+)\^\{\\circ\}\s*\$/g, "$1°")
    .replace(/(\d+)\^\{\\circ\}/g, "$1°")
    .replace(/\s+/g, " ")
    .trim();
}


export function formatEvidenceLevel(level: string): string {
  if (level === "full_text") return "已验证 PDF 全文";
  if (level === "supplemental_text") return "用户补充文本，未通过 PDF 验证";
  if (level === "abstract_only") return "摘要级证据";
  if (level === "metadata_only") return "元数据级证据";
  return level || "未知证据等级";
}


export function formatSignalEvidenceLocation(evidence?: ApiSignalEvidence): string {
  if (!evidence) return "未找到可定位的原文证据";
  const location = [
    evidence.source || "unknown source",
    evidence.section || "unknown section",
    typeof evidence.page === "number" ? `p.${evidence.page}` : "",
  ].filter(Boolean);
  return `${location.join(" · ")} · 抽取置信度 ${evidence.confidence || "low"}`;
}


export function formatResearchSignal(
  value: string | undefined,
  fallback = "未从已解析材料中定位",
): string {
  const normalized = formatAcademicText(value ?? "");
  if (
    !normalized ||
    normalized.startsWith("当前证据不足") ||
    normalized.startsWith("无法判断") ||
    normalized.startsWith("未发现")
  ) {
    return fallback;
  }
  return normalized
    .replace(
      /^(?:方法证据|核心 claim 证据|本论文自身局限|已有研究不足|贡献证据|Baseline evidence)\s*[：:]\s*/i,
      "",
    )
    .trim();
}
