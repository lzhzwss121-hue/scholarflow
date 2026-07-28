import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const API_BASE_URL = "http://127.0.0.1:18010";
const acceptanceRoot =
  process.env.SCHOLARFLOW_ACCEPTANCE_ROOT ??
  "/private/tmp/scholarflow-real-backend-e2e";

test("real FastAPI closes project, PDF, Paper Card, RAG refusal and blocked Experiment loop", async ({
  page,
}) => {
  await mkdir(acceptanceRoot, { recursive: true });
  const pdfPath = path.join(acceptanceRoot, "verified-paper.pdf");
  await writeFile(pdfPath, buildResearchPdf());

  const coreApiResponses: Array<{ method: string; path: string; status: number }> = [];
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.origin === API_BASE_URL) {
      coreApiResponses.push({
        method: response.request().method(),
        path: url.pathname,
        status: response.status(),
      });
    }
  });

  await page.goto("/#new-project");
  await expect(page.getByRole("heading", { name: "新建科研项目" })).toBeVisible();
  await expect(page.getByText("online", { exact: true })).toBeVisible();

  await page.getByPlaceholder("例如：多模态大模型在视觉问答证据真实性研究").fill(
    "真实后端最终验收",
  );
  await page.getByPlaceholder("输入关键词，多个关键词请用英文逗号分隔").fill(
    "object hallucination vision language model evidence faithfulness",
  );
  await page.getByRole("button", { name: "创建项目" }).click();
  await expect(page.getByRole("heading", { name: "论文表格 · Literature Search" })).toBeVisible();

  const queryInput = page.getByLabel("论文检索关键词");
  await queryInput.fill(
    "object hallucination vision language model evidence faithfulness",
  );
  const literatureResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/literature/search") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "重新检索" }).click();
  const literatureResponse = await literatureResponsePromise;
  expect(literatureResponse.status()).toBe(200);
  const literaturePayload = (await literatureResponse.json()) as {
    papers: Array<{ id: string; title: string }>;
  };
  expect(literaturePayload.papers).toHaveLength(10);
  await expect(page.locator(".product-paper-table tbody tr")).toHaveCount(10);
  for (const paper of literaturePayload.papers) {
    await expect(
      page.locator(".product-paper-table tbody").getByText(paper.title, { exact: true }),
    ).toBeVisible();
  }

  await page.goto("/#paper-reader");
  await expect(
    page.locator(".reader-title-row").getByText(literaturePayload.papers[0].title, { exact: false }),
  ).toBeVisible();
  await page.getByText("补充正文证据", { exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(pdfPath);
  await expect(page.getByText(/PDF 已解析 \d+ 页/)).toBeVisible({ timeout: 30_000 });
  await expect(
    page.getByLabel("paper card evidence summary").getByText("已验证 PDF 全文", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("12/12 已生成", { exact: true })).toBeVisible();

  await page.reload();
  await expect(
    page.locator(".reader-title-row").getByText(literaturePayload.papers[0].title, { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByLabel("paper card evidence summary").getByText("已验证 PDF 全文", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("12/12 已生成", { exact: true })).toBeVisible();

  await page.goto("/#paper-memory");
  const ragQuestion = page.getByLabel("原文 RAG 问题");
  await ragQuestion.fill("What is the orbital period of a planet in the Kepler-999 system?");
  await page.getByRole("button", { name: "检索原文并回答" }).click();
  await expect(page.getByRole("heading", { name: "当前原文索引无法可靠回答" })).toBeVisible();

  await page.goto("/#experiment-planner");
  await page.getByLabel("实验目标").fill(
    "Use Dataset Z with Baseline Q and Metric Omega while excluding Dataset A.",
  );
  await page.getByRole("button", { name: "生成实验计划" }).click();
  const experimentStatus = page.locator(".experiment-status-badge");
  await expect(experimentStatus).toHaveAttribute("data-status", "blocked");

  await page.goto("/#new-project");
  await page.getByPlaceholder("例如：多模态大模型在视觉问答证据真实性研究").fill(
    "真实后端隔离项目",
  );
  await page.getByPlaceholder("输入关键词，多个关键词请用英文逗号分隔").fill(
    "unrelated project isolation",
  );
  await page.getByRole("button", { name: "创建项目" }).click();
  await expect(page.locator(".product-paper-table tbody tr")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "本次没有可展示论文" })).toBeVisible();

  await page.getByLabel("项目").selectOption({ label: "真实后端最终验收" });
  await expect(page.locator(".product-paper-table tbody tr")).toHaveCount(10);

  expect(coreApiResponses.some((item) => item.path === "/projects" && item.method === "POST" && item.status === 201)).toBe(true);
  expect(coreApiResponses.some((item) => item.path.includes("/literature/search") && item.status === 200)).toBe(true);
  expect(coreApiResponses.some((item) => item.path.includes("/full-text") && item.status === 200)).toBe(true);
  expect(coreApiResponses.some((item) => item.path.includes("/rag-answer") && item.status === 201)).toBe(true);
  expect(coreApiResponses.some((item) => item.path.includes("/research-decisions") && item.status === 201)).toBe(true);
});

function buildResearchPdf(): Buffer {
  const pageTexts = [
    [
      "Abstract",
      "This paper studies evidence grounded object hallucination evaluation in vision language models.",
      "Introduction",
      "Grounded Method improves citation precision by 10% on Dataset A compared with Baseline B.",
      "Method X does not reduce hallucination rate on Dataset A.",
      "The reported association is correlated with retrieval quality and does not establish causation.",
    ],
    [
      "Method",
      "Grounded Method aligns visual objects with directly locatable evidence before answering.",
      "Experiments",
      "We evaluate Dataset A with Baseline B, citation precision, hallucination rate, and three random seeds.",
      "Ten percent is reported as a relative percentage and not as ten percentage points.",
      "Higher citation precision is better while lower hallucination rate is better.",
    ],
    [
      "Results",
      "Grounded Method improves citation precision by 10% on Dataset A compared with Baseline B.",
      "Method X does not reduce hallucination rate on Dataset A.",
      "Limitations",
      "The evaluation may improve evidence faithfulness under the tested conditions but cannot prove general causality.",
      "Conclusion",
      "All claims remain conditional on Dataset A, Baseline B, and the documented evaluation protocol.",
    ],
  ].map((lines, pageIndex) => {
    const repeated = Array.from({ length: 22 }, (_, index) =>
      `Page ${pageIndex + 1} evidence note ${index + 1}: Dataset A, Baseline B, citation precision, object hallucination, and evidence faithfulness remain explicitly documented.`,
    );
    return [...lines, ...repeated];
  });

  const objects: string[] = [];
  objects[1] = "<< /Type /Catalog /Pages 2 0 R >>";
  objects[2] = "<< /Type /Pages /Kids [3 0 R 5 0 R 7 0 R] /Count 3 >>";
  for (let pageIndex = 0; pageIndex < 3; pageIndex += 1) {
    const pageObject = 3 + pageIndex * 2;
    const streamObject = pageObject + 1;
    objects[pageObject] =
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] ` +
      `/Resources << /Font << /F1 9 0 R >> >> /Contents ${streamObject} 0 R >>`;
    const stream = pageTexts[pageIndex]
      .map((line, index) => {
        const escaped = line.replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
        return `BT /F1 9 Tf 36 ${760 - index * 24} Td (${escaped}) Tj ET`;
      })
      .join("\n");
    objects[streamObject] =
      `<< /Length ${Buffer.byteLength(stream, "utf8")} >>\nstream\n${stream}\nendstream`;
  }
  objects[9] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>";

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [0];
  for (let index = 1; index < objects.length; index += 1) {
    offsets[index] = Buffer.byteLength(pdf, "utf8");
    pdf += `${index} 0 obj\n${objects[index]}\nendobj\n`;
  }
  const xrefOffset = Buffer.byteLength(pdf, "utf8");
  pdf += `xref\n0 ${objects.length}\n`;
  pdf += "0000000000 65535 f \n";
  for (let index = 1; index < objects.length; index += 1) {
    pdf += `${String(offsets[index]).padStart(10, "0")} 00000 n \n`;
  }
  pdf +=
    `trailer\n<< /Size ${objects.length} /Root 1 0 R >>\n` +
    `startxref\n${xrefOffset}\n%%EOF\n`;
  return Buffer.from(pdf, "utf8");
}
