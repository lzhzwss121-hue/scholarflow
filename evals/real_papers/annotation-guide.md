# ScholarFlow real-paper 双人标注与裁决指南

## 1. 不可越过的边界

正式 gold 只能来自人工阅读固定论文版本后的独立判断。生成模型可以帮助整理候选问题，但不得生成或决定 `gold_claim`、`answerability`、citation、页码、版本冲突结论或裁决结果。任何 AI 辅助草稿必须保持 `review_status=draft`，且不能写入审核者或裁决者身份。

仓库不保存完整 PDF 或大段正文。每条案例只保存稳定论文标识、固定版本 URL、PDF SHA-256、总页数、最多 500 字符的短证据片段和可人工定位的页码/章节/表格/图片/公式位置。本地 PDF 映射只写入被忽略的 `resources.local.json`。

## 2. 角色与独立性

- Annotator A 与 Annotator B 必须是两个真实、可追溯且不同的人。
- 两人先独立完成结果，不能先查看对方答案再填写 `independently_completed=true`。
- 裁决者必须在 A/B 完成后查看分歧；进入 `expert_labelled` 时，裁决者不得与 A/B 是同一人。
- 公开数据可使用稳定 reviewer ID 保护隐私，但项目负责人必须在不入库的审核登记表中保存 ID 与真实人员、资质和时间记录的映射。
- 不得用模型、脚本或仓库维护者身份冒充第二审核者或裁决者。

## 3. 状态机

```text
draft
  -> independently_reviewed
  -> adjudicated
  -> expert_labelled
```

CLI 每次只能前进一个状态：

1. `draft`：允许录入 0–2 份审核结果，但不代表审核完成。
2. `independently_reviewed`：A/B 均已完成、身份不同，系统计算 `disagreement_fields`。
3. `adjudicated`：裁决者逐项解决全部分歧；顶层 gold 必须与裁决结果一致。
4. `expert_labelled`：上述记录完整、`label_origin=human_annotation`，且通过版本、locator、split 和重复检查。

禁止跳级。即使 A/B 完全一致，也必须有独立裁决记录后才能成为正式 expert 案例。

## 4. 单条案例操作

1. 固定论文：记录 DOI/arXiv/OpenAlex ID、精确版本 URL、PDF SHA-256 和总页数。
2. 先按 `paper_id` 分配 `train/dev/test`；同一论文的所有问题必须保持同一 split。
3. 编写问题并标记 case type。拒答案例只有在固定版本全文中不存在直接支持时才能标记 `refusal`。
4. A/B 分别填写完整的 `answerability`、claim、evidence type/level、locator、acceptable citations 和备注；固定 PDF 运行后再人工核对 `acceptable_source_anchors` 的 chunk/excerpt hash。
5. 运行一次 `promote` 形成 `independently_reviewed` 并检查自动生成的分歧字段。
6. 裁决者填写最终结果、理由和 `resolved_disagreement_fields`，再晋级到 `adjudicated`。
7. 复核顶层 gold、版本和 citation，最后单步晋级到 `expert_labelled`。

示例命令（所有晋级输出到新文件，避免覆盖审计输入）：

```bash
PYTHONPATH=services/api/src .venv/bin/python \
  -m scholarflow_api.real_paper_dataset promote \
  --cases /private/tmp/annotation-round-1.json \
  --case-id <case-id> \
  --output /private/tmp/annotation-round-2.json
```

## 5. Gold 与拒答判断

- `answerable`：固定版本中存在直接、可定位且资格足够的证据；必须有至少一个匹配论文、版本、hash 的 citation。正式机器定位评测还要求至少一个经人工核对、状态为 `verified` 的 chunk hash 或 evidence excerpt hash。
- `refusal`：问题要求的结论在固定版本中没有直接可靠证据；`gold_claim` 和 acceptable citation 必须为空，`direct_support_found=false`。
- `metadata_only` 或 `abstract_only` 不能支持需要实验数值、公式推导、表格、图或执行细节的问题。
- 相关性不能升级成因果性；条件性或范围限定不得扩展；数值与单位、数据集、指标、比较对象、主论文与补充材料必须分别核对。
- 预印本/正式版或 arXiv 版本不一致时，citation 必须指向当前案例的 `paper_version + source_hash`，并在 `version_notes` 记录差异。
- `acceptable_citations` 仅作为人工阅读和旧数据兼容字段；跨运行匹配不得依赖其 `citation_id`。`acceptable_source_anchors` 才是固定版本的机器锚点，未运行或未复核时必须保持 `pending`，不得猜测 chunk hash。
- `semantic_locator` 只有在解析器真实识别表格、图片、公式、段落或摘要结构后才能用于系统准确率；pypdf 普通文本即使含有 “Table 2” 也不能据此标为结构化表格。

## 6. 目标覆盖矩阵（75 条）

该表是招募与抽样目标，不是已经完成的数据。

| 维度 | 目标 |
| --- | ---: |
| 总案例 | 75（允许正式范围 50–100） |
| 论文 | 20（允许 15–25） |
| 领域 | 至少 5；建议每领域 12–18 条 |
| answerable | 52–56 |
| refusal | 19–23（约 25%–31%） |
| table | 至少 10 |
| figure/figure caption | 至少 8 |
| equation | 至少 6 |
| experiment setup | 至少 8 |
| dataset/metric | 至少 12 |
| numeric/unit/condition | 至少 10 |
| correlation/causality | 至少 6 |
| supplemental material | 至少 6 |
| version conflict | 至少 6 |
| metadata/abstract insufficient | 至少 8 |
| no reliable hit | 至少 8 |

建议领域：视觉语言与多模态、自然语言处理、机器翻译、机器学习可靠性、计算机视觉、科学/生物医学信息检索。最终分布由实际可获得且可裁决的论文证据决定，不为凑比例篡改答案标签。

## 7. 抽检规则

- 每轮新增后随机抽检至少 20%，且不少于 10 条；当轮少于 10 条时全部抽检。
- 对 refusal、版本冲突、公式、图表和补充材料案例执行 100% 抽检。
- 抽检重新核对 source hash、页数、locator、claim 范围与 reviewer/adjudicator 独立性。
- 任一严重错误（错误版本、越界页码、gold 无证据、拒答存在直接支持、身份不真实）触发同批次 100% 复核。
- 一致性指标只能从真实双人独立结果计算，并明确样本量、字段和统计方法；当前仓库没有此类真实数据，因此不得报告一致性数值。

## 8. 发布前检查

```bash
PYTHONPATH=services/api/src .venv/bin/python \
  -m scholarflow_api.real_paper_dataset validate \
  --cases evals/real_papers/cases.expert.json

PYTHONPATH=services/api/src .venv/bin/python \
  -m scholarflow_api.real_paper_dataset coverage \
  --cases evals/real_papers/cases.expert.json

PYTHONPATH=services/api/src .venv/bin/python \
  -m scholarflow_api.real_paper_dataset disagreements \
  --cases evals/real_papers/cases.expert.json

PYTHONPATH=services/api/src .venv/bin/python \
  -m scholarflow_api.real_paper_dataset split-check \
  --cases evals/real_papers/cases.expert.json
```

只有 expert 数量至少 50、论文至少 15、领域至少 5、无未裁决分歧且全部案例为 `expert_labelled` 时，默认 evaluator 才接受该数据集。
