from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Protocol


AgentStepStatus = str
DEFAULT_OPENROUTER_MODEL = "minimax/minimax-m2.5"
DEFAULT_OPENROUTER_RAG_MODEL = "qwen/qwen3-embedding-8b"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_APP_URL = "https://github.com/lzhzwss121-hue/scholarflow"
DEFAULT_OPENROUTER_APP_TITLE = "ScholarFlow"


@dataclass
class AgentPlanStep:
    id: str
    title: str
    detail: str
    tool: str
    status: AgentStepStatus = "queued"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentPlanDraft:
    provider: str
    rationale: str
    steps: list[AgentPlanStep]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "rationale": self.rationale,
            "steps": [step.to_dict() for step in self.steps],
        }


class ModelProvider(Protocol):
    name: str
    model: str

    def create_plan(self, task: str, project: dict[str, Any]) -> AgentPlanDraft:
        ...


class DeepSeekProvider:
    name = "deepseek"

    def __init__(self) -> None:
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        self.fast_model = os.getenv("DEEPSEEK_FAST_MODEL", "deepseek-v4-flash")

    def create_plan(self, task: str, project: dict[str, Any]) -> AgentPlanDraft:
        # Keep DeepSeek available as an optional provider without making it the default path.
        return build_default_plan(task, project, provider=f"{self.name}:{self.model}")


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self) -> None:
        self.model = os.getenv("OPENROUTER_MODEL") or os.getenv("DDO_LLM_MODEL") or DEFAULT_OPENROUTER_MODEL
        self.fast_model = os.getenv("OPENROUTER_FAST_MODEL", self.model)
        self.rag_model = (
            os.getenv("OPENROUTER_RAG_MODEL") or os.getenv("DDO_LLM_RAG_MODEL") or DEFAULT_OPENROUTER_RAG_MODEL
        )
        self.base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).rstrip("/")
        self.api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("DDO_OPENROUTER_API_KEY") or ""
        self.app_url = os.getenv("OPENROUTER_APP_URL", DEFAULT_OPENROUTER_APP_URL)
        self.app_title = os.getenv("OPENROUTER_APP_TITLE", DEFAULT_OPENROUTER_APP_TITLE)
        self.timeout_seconds = _parse_timeout(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "40"))

    def create_plan(self, task: str, project: dict[str, Any]) -> AgentPlanDraft:
        provider_label = f"{self.name}:{self.model}"
        if not self.api_key:
            return build_fallback_plan(
                task,
                project,
                provider_label,
                "未检测到 OPENROUTER_API_KEY，已使用本地确定性计划作为 fallback。",
            )

        try:
            payload = self._create_chat_payload(task, project)
            response = self._post_chat_completion(payload)
            content = response["choices"][0]["message"]["content"]
            actual_model = response.get("model") or self.model
            return build_plan_from_model_content(
                task,
                project,
                content,
                provider=f"{self.name}:{actual_model}",
            )
        except (KeyError, TypeError, ValueError, urllib.error.URLError, TimeoutError) as error:
            return build_fallback_plan(
                task,
                project,
                provider_label,
                f"OpenRouter 调用失败（{error.__class__.__name__}），已使用本地确定性计划作为 fallback。",
            )

    def _create_chat_payload(self, task: str, project: dict[str, Any]) -> dict[str, Any]:
        project_context = {
            "title": project.get("title", ""),
            "description": project.get("description", ""),
            "keyword": project.get("keyword", ""),
            "field": project.get("field", ""),
            "language": project.get("language", "zh-CN"),
            "workflow": project.get("workflow", ""),
        }
        return {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 900,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are ScholarFlow's planning model for AI research workflows. "
                        "Return strict JSON only. Do not invent papers, citations, datasets, "
                        "metrics, or experiment results."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": task,
                            "project": project_context,
                            "allowed_tools": [
                                "create_plan",
                                "search_mock_papers",
                                "save_artifact",
                                "update_timeline",
                            ],
                            "required_json_shape": {
                                "focus": "short research focus in Chinese",
                                "rationale": "why this plan should run first in Chinese",
                                "step_details": {
                                    "create_plan": "detail for the planning step",
                                    "search_mock_papers": "detail for paper candidate step",
                                    "save_artifact": "detail for artifact saving step",
                                    "update_timeline": "detail for timeline step",
                                },
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }

    def _post_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.app_url,
                "X-Title": self.app_title,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class LocalHeuristicProvider:
    name = "local"
    model = "heuristic-planner"

    def create_plan(self, task: str, project: dict[str, Any]) -> AgentPlanDraft:
        return build_default_plan(task, project, provider=f"{self.name}:{self.model}")


@dataclass
class ToolContext:
    run_id: str
    project: dict[str, Any]
    task: str
    plan: dict[str, Any]
    papers: list[dict[str, str]] = field(default_factory=list)
    artifact_id: str | None = None


@dataclass
class ToolResult:
    tool: str
    status: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)


ToolHandler = Callable[[ToolContext], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}
        self._descriptions: dict[str, str] = {}

    def register(self, name: str, handler: ToolHandler, description: str) -> None:
        self._handlers[name] = handler
        self._descriptions[name] = description

    def run(self, name: str, context: ToolContext) -> ToolResult:
        handler = self._handlers.get(name)
        if handler is None:
            raise KeyError(f"Tool is not registered: {name}")
        return handler(context)

    def describe(self) -> list[dict[str, str]]:
        return [{"name": name, "description": description} for name, description in self._descriptions.items()]


def get_model_provider(provider_name: str | None = None) -> ModelProvider:
    selected = (provider_name or os.getenv("SCHOLARFLOW_MODEL_PROVIDER") or "openrouter").lower()
    if selected.startswith("local") or selected.startswith("heuristic"):
        return LocalHeuristicProvider()
    if selected.startswith("deepseek"):
        return DeepSeekProvider()
    return OpenRouterProvider()


def build_fallback_plan(task: str, project: dict[str, Any], provider: str, note: str) -> AgentPlanDraft:
    draft = build_default_plan(task, project, provider=f"{provider}:local-fallback")
    draft.rationale = f"{draft.rationale} {note}"
    return draft


def build_default_plan(task: str, project: dict[str, Any], provider: str) -> AgentPlanDraft:
    focus = infer_research_focus(task, project)
    return AgentPlanDraft(
        provider=provider,
        rationale=(
            f"先把任务收敛到“{focus}”，再用 mock paper table 和 artifact 保存验证最小 agent loop。"
        ),
        steps=[
            AgentPlanStep(
                id="create_plan",
                title="生成 Research Plan",
                detail="解析用户任务、项目关键词和 workflow，形成可确认的最小执行计划。",
                tool="create_plan",
                status="done",
            ),
            AgentPlanStep(
                id="search_mock_papers",
                title="检索 mock paper candidates",
                detail="使用本地 mock 数据生成结构化 paper table，验证工具调用和输出格式。",
                tool="search_mock_papers",
            ),
            AgentPlanStep(
                id="save_artifact",
                title="保存 Agent 输出 artifact",
                detail="把 plan、mock paper table、下一步建议保存为 Markdown 和 JSON artifact。",
                tool="save_artifact",
            ),
            AgentPlanStep(
                id="update_timeline",
                title="写入执行 timeline",
                detail="把本次 agent run 的关键动作写入 session timeline，供前端实时回读。",
                tool="update_timeline",
            ),
        ],
    )


def build_plan_from_model_content(
    task: str,
    project: dict[str, Any],
    content: str,
    provider: str,
) -> AgentPlanDraft:
    model_json = parse_json_object(content)
    draft = build_default_plan(task, project, provider=provider)
    rationale = str(model_json.get("rationale") or "").strip()
    focus = str(model_json.get("focus") or "").strip()
    if rationale:
        draft.rationale = rationale[:700]
    elif focus:
        draft.rationale = f"先把任务收敛到“{focus}”，再生成可确认、可追踪的科研执行计划。"

    step_details = model_json.get("step_details")
    if isinstance(step_details, dict):
        for step in draft.steps:
            detail = step_details.get(step.tool)
            if isinstance(detail, str) and detail.strip():
                step.detail = detail.strip()[:360]
    return draft


def parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("OpenRouter response did not contain a JSON object")
        text = text[start : end + 1]

    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("OpenRouter response JSON must be an object")
    return parsed


def _parse_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError:
        return 40.0
    return max(5.0, min(timeout, 120.0))


def infer_research_focus(task: str, project: dict[str, Any]) -> str:
    text = f"{task} {project.get('keyword', '')} {project.get('field', '')}".lower()
    if "hallucination" in text or "vlm" in text or "multimodal" in text or "多模态" in text:
        return "VLM hallucination / trustworthy multimodal evaluation"
    if "agent" in text or "workflow" in text or "科研" in text:
        return "AI research workflow agent"
    if "llm" in text or "alignment" in text:
        return "LLM alignment and reliability"
    return project.get("field") or project.get("keyword") or "AI research direction"


def build_mock_papers(task: str, project: dict[str, Any]) -> list[dict[str, str]]:
    focus = infer_research_focus(task, project)
    if "workflow agent" in focus:
        return [
            {
                "title": "Agentic Workflows for Literature Review and Scientific Discovery",
                "year": "2026",
                "type": "System",
                "venue": "arXiv",
                "relation": "对应科研流程自动化和任务编排",
                "priority": "High",
                "code": "none",
            },
            {
                "title": "Tool-Augmented Language Agents for Research Assistance",
                "year": "2025",
                "type": "Agent",
                "venue": "ACL",
                "relation": "提供 tool registry 与可追踪 timeline 参考",
                "priority": "High",
                "code": "partial",
            },
            {
                "title": "Evaluating Reliability of AI Research Assistants",
                "year": "2025",
                "type": "Evaluation",
                "venue": "NeurIPS",
                "relation": "关注 citation、claim 和 artifact faithfulness",
                "priority": "Medium",
                "code": "none",
            },
        ]

    return [
        {
            "title": "Evaluating Object Hallucination in Large Vision-Language Models",
            "year": "2025",
            "type": "Benchmark",
            "venue": "arXiv",
            "relation": "直接对应 hallucination evaluation",
            "priority": "High",
            "code": "available",
        },
        {
            "title": "Faithful Visual Question Answering Requires Grounded Evidence",
            "year": "2025",
            "type": "Method",
            "venue": "ACL",
            "relation": "把答案正确性和证据一致性分开",
            "priority": "High",
            "code": "partial",
        },
        {
            "title": "Benchmark Bias in Multimodal Foundation Model Evaluation",
            "year": "2024",
            "type": "Analysis",
            "venue": "NeurIPS",
            "relation": "解释评测集捷径和分布偏差",
            "priority": "High",
            "code": "available",
        },
        {
            "title": "A Survey of Trustworthy Vision-Language Models",
            "year": "2026",
            "type": "Survey",
            "venue": "arXiv",
            "relation": "补全研究图谱和术语",
            "priority": "Medium",
            "code": "none",
        },
    ]


def render_plan_markdown(task: str, project: dict[str, Any], plan: dict[str, Any]) -> str:
    step_lines = [
        f"{index}. {step['title']} ({step['tool']})\n   - {step['detail']}"
        for index, step in enumerate(plan["steps"], start=1)
    ]
    return "\n\n".join(
        [
            "# ScholarFlow Agent Plan",
            f"Project: {project.get('title', '')}",
            f"Task: {task}",
            f"Provider: {plan.get('provider', '')}",
            f"Rationale: {plan.get('rationale', '')}",
            "## Steps",
            "\n".join(step_lines),
            "## Phase Boundary",
            "当前只执行 mock tools，用于验证 Plan Mode、Tool Registry、Timeline 和 Artifact 保存链路。",
        ],
    )


def render_execution_markdown(
    task: str,
    project: dict[str, Any],
    plan: dict[str, Any],
    papers: list[dict[str, str]],
) -> str:
    paper_rows = [
        f"| {paper['title']} | {paper['year']} | {paper['type']} | {paper['priority']} | {paper['relation']} |"
        for paper in papers
    ]
    step_rows = [f"- [{step['status']}] {step['title']} -> `{step['tool']}`" for step in plan["steps"]]
    return "\n\n".join(
        [
            "# ScholarFlow Agent Run",
            f"Project: {project.get('title', '')}",
            f"Task: {task}",
            f"Provider: {plan.get('provider', '')}",
            "## Executed Plan",
            "\n".join(step_rows),
            "## Mock Paper Table",
            "| Paper | Year | Type | Priority | Relation |",
            "| --- | --- | --- | --- | --- |",
            "\n".join(paper_rows),
            "## Next Step",
            "进入 Phase 6 后，将把 `search_mock_papers` 替换为 arXiv / OpenAlex / Semantic Scholar 检索适配器。",
        ],
    )
