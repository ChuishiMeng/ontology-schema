# P16 解读: Sequeda et al. (2023) - KG 对企业 Text-to-SQL 的影响

> **论文**: A Benchmark to Understand the Role of Knowledge Graphs on LLM's Accuracy for QA on Enterprise SQL Databases
> **作者**: Juan F. Sequeda, Dean Allemang, Bryon Jacob (data.world)
> **年份**: 2023 | **会议**: arXiv Technical Report / GRADES-SIGMOD
> **相关性**: ⭐⭐⭐⭐⭐ (最直接相关，必须引用)

---

## 核心贡献

1. **企业级 Benchmark**: 保险领域 13 表 + 43 个自然语言问题 + OWL Ontology + R2RML 映射
2. **关键发现**: GPT-4 直接查 SQL 准确率 16.7%，通过 KG (SPARQL) 准确率 54.2%（提升 3x）
3. **高 Schema 复杂度时 SQL 完全失效**（>5 表时准确率 0%），KG 仍能保持 35-38%

---

## 方法论

### 实验设计
| 条件 | 方法 | 准确率 |
|------|------|--------|
| w/o KG | NL → SQL (GPT-4 zero-shot) | 16.7% |
| w/ KG | NL → SPARQL → SQL (GPT-4 zero-shot) | 54.2% |

### 问题分类（2x2 象限）
| | Low Schema (≤4表) | High Schema (>4表) |
|--|-------------------|-------------------|
| **Low Question** (报表) | SQL 25.5% / KG 71.1% | SQL **0%** / KG 35.7% |
| **High Question** (KPI) | SQL 37.4% / KG 66.9% | SQL **0%** / KG 38.5% |

### KG 构建方式
- OWL Ontology 定义业务概念 + R2RML 映射 SQL→RDF
- **手工构建**，领域专家参与
- 本质上是 OBDA (Ontology-Based Data Access) 范式

---

## 与本研究的区别（关键差异化）

| 维度 | Sequeda et al. (2023) | 本研究 |
|------|----------------------|--------|
| **研究类型** | 实证评估（Benchmark） | **方法创新**（联合召回算法） |
| **查询路径** | NL → SPARQL → SQL | NL → 联合召回 → SQL |
| **KG 用途** | 作为替代查询接口 | **作为召回中间层** |
| **Schema 处理** | 使用完整 Schema 或完整 KG | **最小完备集提取** |
| **Ontology 构建** | 手工 OWL + R2RML | LLM 半自动构建 |
| **召回机制** | 无（全量 Schema/KG） | **联合召回 + 元路径约束** |
| **LLM 调用** | 1 次 zero-shot | 1-2 次 |
| **评估方式** | SPARQL vs SQL 对比 | 在 BIRD 上与 SOTA 对比 |

### 核心区别
Sequeda 证明"KG 有用"，但没有解决"如何高效利用 KG"。
- 他的方法是把整个 KG 作为 Prompt，不做筛选
- 我们的方法是联合召回最小完备集，减少噪声
- 他的 KG 是手工 OWL，我们探索半自动构建

---

## 可借鉴内容

1. **KG 显著提升准确率的实证** — 可作为本研究 Motivation 的强有力支撑
2. **高 Schema 复杂度时 SQL 完全失效** — 直接支持我们的"最小完备集提取"的必要性
3. **Partial Accuracy 概念** — 可用于我们的评估指标设计
4. **问题分类象限** — Low/High Question × Low/High Schema，可用于我们的案例分析

---

## 局限性（我们可以改进的）

1. ❌ 只用 GPT-4 zero-shot，没有对比其他方法（如 SchemaGraphSQL, RSL-SQL）
2. ❌ KG 是手工构建的，没有讨论构建成本
3. ❌ 只在保险领域 13 表上测试，泛化性未知
4. ❌ 使用完整 Schema/KG，没有做召回/筛选
5. ❌ 不涉及 Schema Linking 问题

---

## 对本项目的影响

1. **P2 必须引用** — 作为"KG 对 Text-to-SQL 有用"的核心证据
2. **P1 Motivation 可强化** — 引用其 "SQL >5表准确率0%" 的发现
3. **P4 差异化清晰** — 联合召回 vs 全量 KG、最小完备集 vs 完整 Schema
4. **风险评估** — 审稿人可能说"Sequeda 已经证明 KG 有效，你的增量贡献是什么？" → 必须强调"方法创新"而非"效果验证"
