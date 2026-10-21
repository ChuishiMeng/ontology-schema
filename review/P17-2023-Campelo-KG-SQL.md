# P17: Using Knowledge Graphs to Generate SQL Queries from Textual Specifications

## 📋 基本信息

| 项目 | 内容 |
|------|------|
| **标题** | Using Knowledge Graphs to Generate SQL Queries from Textual Specifications |
| **作者** | Robson A. Campêlo¹, Alberto H. F. Laender², Altigran S. da Silva³ |
| **机构** | ¹Instituto Federal de Ciência e Tecnologia Goiano, ²UFMG, ³UFAM |
| **发表** | ER 2023 Workshops (LNCS vol 14319, pp. 85-94) |
| **DOI** | 10.1007/978-3-031-47112-4_8 |
| **关键词** | Knowledge Graphs, Natural Language Queries, SQL Queries |
| **引用数** | 0 (截至2026年) |

---

## 1. 核心贡献和创新点

### 1.1 核心思想

本文提出了一种**基于知识图谱（KG）的 NL-to-SQL 工具**，核心论点是：**关系数据库 Schema 的 KG 表示可以作为 NL→SQL 翻译过程中的辅助工具**，通过 KG 提供的语义信息来弥合自然语言与 SQL 之间的语义鸿沟。

### 1.2 两阶段方法

方法包含两个主要任务：

1. **KG 生成（KG Generation）**：从关系数据库 Schema 自动生成知识图谱
2. **NL→SQL 翻译（Query Translation）**：基于 KG 提供的语义信息，将自然语言查询翻译为 SQL

### 1.3 创新点

| 创新维度 | 具体内容 |
|----------|----------|
| **Schema→KG 自动化** | 提出从 INFORMATION_SCHEMA 元数据自动构建 KG 的方法，无需人工标注 |
| **KG 作为语义桥梁** | 利用 KG 的语义丰富性来弥补 Schema 本身语义不足的问题 |
| **RDF 三元组表示** | 将关系数据库 Schema 转化为 RDF 三元组形式的知识图谱 |
| **端到端工具** | 提供从 Schema 到 KG 到 SQL 的完整工具链 |

### 1.4 与同类工作的差异

- **vs. ATHENA (Saha et al., 2016)**：ATHENA 使用本体论（Ontology）驱动，采用 NLQ→OQL→SQL 两阶段翻译；本文直接使用 KG 作为中间表示
- **vs. Neural Text-to-SQL (TypeSQL, SQLNet 等)**：本文是基于规则/语义的方法，不依赖大规模训练数据
- **vs. ChatGPT zero-shot**：本文利用结构化的 KG 语义信息，而非纯 LLM 推理

---

## 2. 技术方法细节

### 2.1 Task 1: KG 生成流程

```
关系数据库 → INFORMATION_SCHEMA → Schema 元数据提取 → RDF 三元组生成 → 知识图谱
```

**关键步骤**：

1. **元数据提取**：通过 `INFORMATION_SCHEMA.TABLES`（表结构视图）和 `INFORMATION_SCHEMA.COLUMNS`（列信息视图）自动获取数据库结构
2. **RDF 三元组生成**：将表、列、关系映射为 RDF（Resource Description Framework）三元组
3. **语义增强**：KG 表示比原始 Schema 包含更丰富的语义关系

**技术栈**：
- **PyMySQL**：连接 MySQL 数据库
- **Pandas DataFrame**：数据处理和中间表示
- **RDF 标准**：W3C 标准的数据交换模型，支持结构化、链接和语义知识的表示

### 2.2 Task 2: NL→SQL 翻译流程

```
自然语言查询 → NLP 处理 → 语义匹配（KG） → SQL 生成
```

**关键组件**：

1. **NLP 处理**：使用 **Stanza**（Stanford NLP 工具包）进行：
   - 分词（Tokenization）
   - 词性标注（POS Tagging）
   - 依存句法分析（Dependency Parsing）
   - 命名实体识别（NER）

2. **语义匹配**：将 NLP 处理后的查询元素与 KG 中的实体/关系进行匹配
3. **SQL 构造**：基于匹配结果，按照 SQL 语法规则组装最终查询

4. **ChatGPT 集成**：论文注释中提到使用了 ChatGPT（OpenAI），可能用于辅助自然语言理解或查询生成的某个环节

### 2.3 系统架构推测

```
┌─────────────────────────────────────────────┐
│                 用户输入                      │
│           (自然语言查询)                      │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│            NLP 处理层 (Stanza)               │
│  分词 → 词性标注 → 依存分析 → 实体识别       │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│          语义匹配层                          │
│  NLP 输出 ←→ KG 实体/关系 匹配              │
│  (可能结合 ChatGPT 辅助)                     │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│          SQL 生成层                          │
│  SELECT/FROM/WHERE/JOIN/AGG 组装            │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│          知识图谱 (RDF)                      │
│  ← 自动生成自 INFORMATION_SCHEMA            │
│  表/列/关系 → RDF 三元组                     │
└─────────────────────────────────────────────┘
```

---

## 3. 实验结果和关键数据

### 3.1 评测设置

| 项目 | 详情 |
|------|------|
| **数据集** | Spider 数据集（子集） |
| **领域** | Formula 1（F1赛车） |
| **查询数量** | 82 个 NL 查询示例 |
| **验证方式** | 对比预期结果（执行结果匹配） |

### 3.2 主要结果

- **准确率**：论文声称能够**正确翻译所有 82 个查询**（100% 准确率）
- **验证方法**：通过与 benchmark 提供的预期结果进行比对

### 3.3 结果分析

**优势**：
- 在特定领域（F1）的受控实验中达到完美准确率
- 自动化的 KG 生成减少了人工干预

**局限性**：
- ⚠️ 仅在 **单一领域（Formula 1）** 上评测
- ⚠️ 仅 **82 个查询**，规模较小
- ⚠️ 未与主流 Text-to-SQL 基线模型进行对比
- ⚠️ Spider 完整数据集包含 10,000+ 查询和 200+ 数据库，本文仅使用极小子集
- ⚠️ 缺少跨域泛化性评估
- ⚠️ 0 引用量说明该工作影响力有限

---

## 4. 与本研究（Ontology+Schema 联合召回）的关联

### 4.1 核心关联

| 维度 | Campelo 2023 | 我们的研究（Ontology+Schema 联合召回） |
|------|-------------|--------------------------------------|
| **中间表示** | KG（RDF三元组） | Ontology + Schema 联合表示 |
| **语义来源** | 从 INFORMATION_SCHEMA 自动提取 | 领域本体 + 数据库 Schema 双源融合 |
| **桥梁角色** | KG 作为 NL↔SQL 的语义桥梁 | Ontology 作为业务语义桥梁 |
| **Schema 利用** | 直接从 Schema 元数据生成 KG | Schema 信息用于精确召回 |
| **自动化程度** | Schema→KG 自动化 | Ontology 需要构建，Schema 自动解析 |
| **LLM 集成** | 提到使用 ChatGPT | 深度集成 LLM 进行语义理解 |

### 4.2 共同验证的假设

1. **Schema 本身语义不足**：两者都认识到原始 Schema 无法完全捕捉业务语义
2. **需要额外的语义层**：Campelo 用 KG，我们用 Ontology，本质上都是在 Schema 之上构建语义增强层
3. **自动化构建的重要性**：Campelo 强调从 INFORMATION_SCHEMA 自动构建 KG，这与我们自动解析 Schema 的思路一致

### 4.3 差异与互补

**我们的优势**：
- **双源融合**：同时利用 Ontology（业务语义）和 Schema（结构语义），比单纯从 Schema 生成 KG 更丰富
- **领域适应性**：Ontology 可以编码特定领域知识，而非仅从 Schema 元数据推断
- **召回精度**：联合召回可以同时从语义和结构两个维度筛选相关表/列
- **可扩展性**：Ontology 支持增量更新和跨数据库复用

**Campelo 的优势**：
- **全自动化**：无需人工构建 Ontology，直接从 Schema 生成
- **低成本启动**：不需要领域专家参与
- **RDF 标准化**：基于 W3C 标准，工具生态成熟

---

## 5. 可借鉴的技术点

### 5.1 直接可借鉴

| 技术点 | 借鉴方式 | 优先级 |
|--------|----------|--------|
| **INFORMATION_SCHEMA 自动提取** | 用于 Schema 自动解析模块，自动获取表/列/关系信息 | ⭐⭐⭐ |
| **RDF 三元组表示** | 可考虑将 Ontology 概念映射为三元组形式，便于图查询和推理 | ⭐⭐ |
| **Stanza NLP 管道** | 用于 NL 查询的预处理（分词、词性、依存分析） | ⭐⭐ |
| **KG 作为语义桥梁的思路** | 验证了"中间语义层"方法的有效性，增强我们方法的理论基础 | ⭐⭐⭐ |

### 5.2 需改进后借鉴

| 技术点 | 改进方向 |
|--------|----------|
| **Schema→KG 映射规则** | 扩展为 Schema→Ontology 映射，增加业务语义层 |
| **单域评测** | 我们需要在多域 benchmark 上验证 |
| **规则式方法** | 结合 LLM 的灵活性与规则的可靠性 |
| **执行结果匹配** | 补充 Exact Match 和 Execution Accuracy 双指标 |

### 5.3 论文写作参考

- **引用价值**：可作为"KG/Ontology 辅助 Text-to-SQL"方向的相关工作引用
- **对比基线**：展示我们的方法在规模（多域）和性能上的优势
- **方法论启发**：Schema→语义层→SQL 的三阶段范式与我们的方法一致，增强论证力度

### 5.4 关键引文（用于我们的论文）

本文引用的几篇重要相关工作值得关注：

1. **ATHENA (Saha et al., 2016)** - Ontology-driven NL-to-SQL 系统，使用 OQL 中间语言，与我们的 Ontology 方法最相关
2. **ATHENA++ (Sen et al., 2020)** - 支持复杂嵌套 SQL，ATHENA 的增强版
3. **Affolter et al. (2019)** - NL 数据库接口综述
4. **Quamar et al. (2022)** - NL 数据接口综述（Foundations and Trends）
5. **Kim et al. (2020)** - NL-to-SQL 现状综述

---

## 6. 总体评价

### 6.1 优点
- ✅ 提出了清晰的两阶段方法（Schema→KG, NL→SQL via KG）
- ✅ 实现了 Schema→KG 的自动化
- ✅ 在受控实验中达到 100% 准确率
- ✅ 验证了 KG/语义层辅助 NL-to-SQL 的可行性

### 6.2 不足
- ❌ 评测规模极小（82 查询，单域）
- ❌ 无跨域泛化评估
- ❌ 未与主流基线对比（如 RESDSQL, DIN-SQL 等）
- ❌ 技术细节描述可能不够充分（仅 10 页会议短文）
- ❌ 0 引用量，学术影响力有限

### 6.3 对我们研究的价值

**价值等级：⭐⭐⭐ 中等偏高**

虽然论文本身规模和影响力有限，但其核心思想——**用语义层（KG/Ontology）桥接 Schema 与 NL 的语义鸿沟**——与我们的 Ontology+Schema 联合召回研究方向高度一致。它从另一个角度（KG 而非 Ontology）验证了相同的基本假设，可以作为我们论文 Related Work 部分的有力支撑。

**特别值得注意的是**：该论文引用了 ATHENA（Ontology-driven 方法），这表明 KG 和 Ontology 两种路线在 NL-to-SQL 领域是并行发展的。我们的 Ontology+Schema 联合召回方法可以视为两者的融合与升级。

---

## 📚 参考文献

1. Affolter, K., et al. (2019). A comparative survey of recent NL interfaces for databases. VLDB J.
2. Baik, C., et al. (2019). Bridging the semantic gap with SQL query logs in NL interfaces to databases. ICDE.
3. Basik, F., et al. (2018). DBPal: a learned NL-interface for databases. SIGMOD.
4. Hogan, A., et al. (2021). Knowledge graphs. ACM Computing Surveys.
5. Kim, H., et al. (2020). Natural language to SQL: where are we today? VLDB.
6. Liu, A., et al. (2023). A comprehensive evaluation of ChatGPT's zero-shot Text-to-SQL capability.
7. Li, F., Jagadish, H.V. (2014). Constructing an interactive NL interface for relational databases. VLDB.
8. Quamar, A., et al. (2022). Natural language interfaces to data. Found. Trends Databases.
9. Saha, D., et al. (2016). ATHENA: an ontology-driven system for NL querying over relational data stores. VLDB.
10. Sen, J., et al. (2020). Athena++: natural language querying for complex nested SQL queries. VLDB.
11. Yaghmazadeh, N., et al. (2017). SQLizer: query synthesis from natural language. OOPSLA.
12. Yu, T., et al. (2018). Spider: a large-scale human-labeled dataset for complex and cross-domain semantic parsing. EMNLP.
13. Yu, T., et al. (2018). TypeSQL: Knowledge-based type-aware neural text-to-SQL generation.
14. Xu, X., et al. (2017). SQLNet: generating structured queries from NL without reinforcement learning.

---

*解读时间：2026-04-15*
*解读者：科研小新*
*注意：本文为 Springer 付费论文，全文未公开获取。本解读基于论文摘要、元数据、注释和参考文献信息综合分析。*
