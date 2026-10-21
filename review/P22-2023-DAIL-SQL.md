# P22: DAIL-SQL — Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation

## 📋 基本信息

| 项目 | 内容 |
|------|------|
| **标题** | Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation |
| **作者** | Dawei Gao*, Haibin Wang*, Yaliang Li, Xiuyu Sun, Yichen Qian, Bolin Ding, Jingren Zhou |
| **机构** | 阿里巴巴集团 |
| **发表** | PVLDB, Vol. 17, No. 5, 2024 (arXiv: 2308.15363, 2023) |
| **代码** | https://github.com/BeachWang/DAIL-SQL |
| **关键词** | Text-to-SQL, LLM, Prompt Engineering, In-Context Learning, Few-shot |

---

## 1. 核心贡献和创新点

### 1.1 整体定位

DAIL-SQL 是一项**系统性的 LLM-based Text-to-SQL 基准评估研究**，不是提出全新的模型架构，而是通过系统性地分解和对比 prompt engineering 的各个维度，找到最优组合方案，刷新了 Spider 排行榜（86.6% EX）。

### 1.2 四大核心贡献

1. **系统性 Prompt Engineering 基准**
   - 首次系统对比了 **5 种问题表示** × **4 种示例选择策略** × **3 种示例组织方式** × **4 种 LLM**
   - 解答了此前各方法因实验条件不一致而无法公平比较的问题

2. **DAIL Selection（示例选择策略）**
   - 创新性地同时考虑 **问题相似度 + SQL 骨架相似度**
   - 先对问题进行 domain mask（去除领域特定词汇），再按 embedding 距离排序
   - 同时用预生成 SQL 计算 query similarity，设置阈值 τ 过滤
   - 相比单独使用 Question Similarity 或 Masked Question Similarity，显著提升

3. **DAIL Organization（示例组织方式）**
   - 在 Full-Information（完整 schema + question + SQL）和 SQL-Only 之间取折中
   - 仅保留 **question + SQL pair**，去掉重复的 database schema
   - 保留了 question→SQL 的映射关系（LLM 需要学习的核心信息）
   - 同时大幅减少 token 消耗（约为 Full-Information 的 1/3~1/4）

4. **开源 LLM 探索**
   - 首次系统评估开源 LLM（LLaMA、Vicuna、CodeLLaMA）在 Text-to-SQL 的表现
   - 发现 SFT 后开源 LLM 可达到 TEXT-DAVINCI-003 水平（~68-69% EX）
   - **但 SFT 后 in-context learning 能力退化**（加示例反而掉分）

---

## 2. 技术方法细节

### 2.1 问题表示（Question Representation）

论文系统评估了 5 种问题表示：

| 缩写 | 名称 | 特点 | 最佳适配 |
|------|------|------|----------|
| **BS_P** | Basic Prompt | 最简单，无指令 | GPT-4（偏好简洁） |
| **TR_P** | Text Representation Prompt | 自然语言描述 schema | 一般 |
| **OD_P** | OpenAI Demonstration Prompt | 用 # 注释风格，含 "with no explanation" | GPT-3.5-TURBO（最佳零样本） |
| **CR_P** | Code Representation Prompt | CREATE TABLE 语句，含主外键 | 开源 LLM、few-shot 场景（DAIL-SQL 采用） |
| **AS_P** | Alpaca SFT Prompt | Instruction/Input/Response 格式 | SFT 场景 |

**关键发现**：
- **外键信息**（FK）：对 OpenAI LLM 普遍有 0.6%-2.9% 的提升
- **"with no explanation" 规则**：对所有 LLM 普遍有效，最高提升超过 6%（EM）/ 3%（EX）
- **GPT-4 偏好简洁**的 BS_P，说明强 LLM 可以自行理解复杂 schema
- **DAIL-SQL 最终选择 CR_P**，因为它包含完整数据库信息（类型、主外键）且 LLM 在代码语料上预训练过

### 2.2 示例选择（Example Selection）

四种策略对比：

| 策略 | 使用信息 | 特点 |
|------|---------|------|
| **Random** | 无 | 基线，随机选 k 个 |
| **QTS_S**（Question Similarity） | 问题嵌入 | 用 embedding + kNN 选最相似问题 |
| **MQS_S**（Masked Question Similarity） | 遮蔽问题嵌入 | 先 mask 领域词（表名、列名、值），再算相似度 |
| **QRS_S**（Query Similarity） | SQL 骨架 | 用预模型生成 SQL，按关键字二进制向量算相似度 |
| **DAIL_S**（本文提出） | 问题 + SQL 同时考虑 | 先 mask 问题排序，再用 query similarity 阈值过滤 |

**DAIL Selection 算法流程**：
1. 对目标问题 q 和候选问题 q_i 都进行 domain-specific masking
2. 计算 masked embedding 的欧氏距离，排序
3. 用预模型（如 Graphix-T5）预生成目标 SQL s'
4. 计算 s' 与候选 SQL s_i 的 skeleton 相似度
5. 在排序结果中，优先选择 query similarity > τ 的候选
6. 选出 top-k 作为示例

### 2.3 示例组织（Example Organization）

三种策略：

| 策略 | 包含内容 | Token 成本 | 效果 |
|------|---------|-----------|------|
| **FI_O**（Full-Information） | Schema + Question + SQL | 最高（~9x） | 弱 LLM 最佳 |
| **SO_O**（SQL-Only） | 仅 SQL 查询 | 最低 | 丢失 Q→SQL 映射 |
| **DAIL_O**（本文提出） | Question + SQL pair（无 schema） | 中等（≈SO_O） | 强 LLM（GPT-4）最佳 |

**关键洞察**：
- LLM 通过 in-context learning 学习的核心是 **question → SQL 的映射关系**
- DAIL_O 保留了这个映射，同时去掉冗余的 database schema（已在目标问题部分提供过）
- 对于 GPT-4 这样强大的 LLM，DAIL_O 效果最好
- 对于较弱的 LLM（TEXT-DAVINCI-003, Vicuna），Full-Information 更好（需要更多上下文帮助理解）

### 2.4 DAIL-SQL 最终配置

```
Question Representation: CR_P (Code Representation Prompt)
Example Selection:       DAIL_S (Masked Question + Query Similarity)
Example Organization:    DAIL_O (Question-SQL pairs, no schema)
LLM:                     GPT-4
Enhancement:             Self-Consistency Voting (可选, +0.4%)
Token Cost:              ~1600 tokens/question (Spider-dev)
```

---

## 3. 实验结果

### 3.1 Spider 基准

#### 主要结果（Spider-dev）

| 方法 | Dev EM | Dev EX | Test EM | Test EX |
|------|--------|--------|---------|---------|
| **DAIL-SQL + GPT-4** | 70.0 | 83.1 | 66.5 | **86.2** |
| **DAIL-SQL + GPT-4 + SC** | 68.7 | 83.6 | 66.0 | **86.6** |
| DIN-SQL (prior SOTA) | - | - | - | 85.3 |

- **刷新 Spider 排行榜**，以 86.6% EX 获得第一名
- 超过此前 SOTA (DIN-SQL) 1.3%，且 **token 成本显著更低**

#### 示例选择策略对比（Spider-dev, GPT-4, 5-shot, FI_O）

| 选择策略 | EM | EX | Question Sim. | Query Sim. |
|---------|-----|-----|-------------|-----------|
| Random | 51.6 | 79.5 | 0.23 | 0.48 |
| Question Similarity | 58.2 | 79.9 | 0.36 | 0.61 |
| Masked Question Similarity | 66.8 | 82.0 | 0.52 | 0.77 |
| **DAIL Selection** | **71.9** | **82.4** | 0.52 | **0.94** |
| Upper Limit (用 ground truth SQL) | 74.4 | 84.4 | 0.51 | 0.97 |

**关键发现**：DAIL Selection 的 query similarity 达到 0.94（接近 Upper Limit 的 0.97），说明同时考虑 question 和 query 相似度的策略非常有效。

#### 不同 LLM 零样本表现（Spider-dev, 最佳表示）

| LLM | 最佳 EX | 最佳表示 |
|-----|---------|---------|
| GPT-4 | 72.3% | BS_P |
| GPT-3.5-TURBO | 75.5% | OD_P |
| TEXT-DAVINCI-003 | 71.7% | CR_P |
| Vicuna-33B | 43.7% | CR_P |

### 3.2 Spider-Realistic 基准

| 配置 | EX |
|------|-----|
| DAIL-SQL + GPT-4 (9-shot) | 76.0% |
| GPT-4 零样本 | 66.5% |

### 3.3 BIRD 基准

DAIL-SQL 在 BIRD benchmark 上的表现（根据外部评测数据）：
- **BIRD test set EX: ~57.41%**（GPT-4 基础版本）
- 相比 Spider 的 86.6%，BIRD 难度显著更高
- BIRD 引入了更大规模的真实数据库、外部知识需求（evidence）等挑战
- DAIL-SQL 在无 evidence 时性能下降约 20.86%，说明其对外部知识依赖较强

### 3.4 Token 效率

| 方案 | Avg Tokens | Spider-dev EX |
|------|-----------|--------------|
| DAIL-SQL (DAIL_O, 9-shot) | ~1600 | 83.5% |
| DIN-SQL | ~9100 | ~82.8% |
| STRIKE | ~3700 | ~79.0% |
| CBR-ApSQL | ~2500 | 78.2% |

DAIL-SQL 在**更高准确率的同时 token 消耗更少**，是当时性价比最高的方案。

### 3.5 开源 LLM 结果

| 模型 | 零样本 EX | SFT 后 EX |
|------|----------|----------|
| LLaMA-7B | 9.1% (avg) | ~66.7% |
| LLaMA-13B | 21.5% (avg) | ~68.6% |
| Vicuna-33B | 36.6% (avg) | - |
| CodeLLaMA-34B | 60.2% (avg) | - |
| LLaMA-2-CHAT-70B | 39.6% (avg) | - |

**SFT 关键发现**：
- SFT 大幅提升零样本性能（LLaMA-7B: 9.1% → 66.7%）
- 但 **SFT 后 in-context learning 能力退化**，加入示例反而降低准确率
- AS_P (Alpaca 格式) 在 SFT 中表现最佳

---

## 4. 与本研究（Ontology+Schema 联合召回）的对比

### 4.1 Schema 理解维度

| 维度 | DAIL-SQL | Ontology+Schema 联合召回（本研究） |
|------|---------|-------------------------------|
| **Schema 表示** | CREATE TABLE 语句（CR_P） | 本体语义层 + 物理 Schema 双重表示 |
| **Schema 理解** | LLM 直接解析 SQL DDL | 通过 Ontology 提供业务语义理解 |
| **跨域能力** | 通过 mask 消除领域特定信息 | 通过 Ontology 统一不同领域的语义 |
| **复杂 Schema** | 依赖 LLM 自身理解能力 | 通过本体关系图辅助理解 |

**核心差异**：DAIL-SQL 将 schema 作为纯文本信息提供给 LLM，依赖 LLM 的代码理解能力来解析表结构。而 Ontology+Schema 联合召回引入了**语义层**，将业务概念（如"销售额"、"退货率"）映射到物理 schema，解决了 LLM 难以理解业务含义的问题。

### 4.2 示例选择 vs. Schema 召回

| 方面 | DAIL-SQL | 本研究 |
|------|---------|--------|
| **核心机制** | 从训练集选择相似的 question-SQL pair 作为示例 | 从 Ontology 中召回相关的语义概念和 Schema 元素 |
| **知识来源** | 历史 QA 对（需要标注数据） | 领域本体（可由领域专家构建） |
| **冷启动** | 需要训练集中有相似问题 | 本体一旦构建即可使用 |
| **可扩展性** | 新场景需要新的标注数据 | 新场景只需扩展本体 |

### 4.3 本研究可借鉴的思路

1. **DAIL Selection 的"双维度选择"思想**
   - 本研究也可以同时考虑"语义相似度"和"结构相似度"来召回 schema 元素
   - 类似于 DAIL 的 question similarity + query similarity

2. **DAIL Organization 的"精简映射"思想**
   - 在构造 prompt 时，不需要塞入所有 schema 信息
   - 只需提供关键的 Ontology concept → Schema element 映射
   - 减少 token 浪费，提升效率

3. **"with no explanation" 规则的普适性**
   - 简单的 prompt 规则（如"仅输出 SQL"）可以显著提升所有方法的表现

### 4.4 DAIL-SQL 的局限性（本研究的机会）

1. **无语义理解层**：DAIL-SQL 完全依赖 LLM 的文本理解能力，缺乏显式的业务语义建模
2. **依赖标注数据**：示例选择需要大量 (question, SQL) 标注对
3. **BIRD 表现下降**：在更真实的数据库场景（BIRD ~57%）表现明显不如 Spider（~86%），说明其对复杂真实场景的泛化能力有限
4. **无外部知识集成**：无法利用数据字典、业务文档等外部知识
5. **Schema 规模瓶颈**：当数据库表/列数量大时，CR_P 的 token 成本急剧上升

---

## 5. 作为 Baseline 的价值

### 5.1 为什么 DAIL-SQL 是重要的 Baseline

1. **历史地位**：曾是 Spider 排行榜第一名（86.6% EX），代表了 ICL 路线的巅峰
2. **方法论参考**：系统性地拆解了 prompt engineering 的每个维度，为后续研究提供了清晰的对比框架
3. **可复现性强**：开源代码，清晰的实验设置，便于对比
4. **纯 prompt 方案**：不依赖额外训练或特殊模型架构，体现了"prompt engineering 的天花板"

### 5.2 Baseline 对比维度

| 对比维度 | DAIL-SQL 数据 | 本研究预期 |
|---------|-------------|----------|
| Spider-dev EX | 83.1% (GPT-4) | 目标 > 83% |
| Spider-test EX | 86.6% (GPT-4+SC) | 目标 > 86% |
| BIRD-dev EX | ~54% | 目标 > 60%（关键突破点） |
| Token/Question | ~1600 | 目标 ≤ 2000 |
| 冷启动能力 | ❌ 需要训练集 | ✅ 本体即可工作 |
| 业务语义理解 | ❌ 纯文本 | ✅ 本体语义层 |
| 外部知识利用 | ❌ | ✅ Ontology 融合 |

### 5.3 超越 DAIL-SQL 的路径

1. **语义增强 Schema 召回**：通过 Ontology 提供 LLM 无法从 DDL 获取的业务语义
2. **动态 Schema 裁剪**：用 Ontology 图结构精准定位相关表/列，减少 prompt 中的噪声
3. **零标注泛化**：本体驱动的方法不依赖历史 QA 对，在新领域有天然优势
4. **BIRD 场景突破**：BIRD 的核心难点是"外部知识"（evidence），Ontology 天然可以承载这类知识

---

## 6. 关键引用

```bibtex
@article{dail_sql,
    author  = {Dawei Gao and Haibin Wang and Yaliang Li and Xiuyu Sun and 
               Yichen Qian and Bolin Ding and Jingren Zhou},
    title   = {Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation},
    journal = {Proceedings of the VLDB Endowment},
    volume  = {17},
    number  = {5},
    pages   = {1132--1145},
    year    = {2024},
    doi     = {10.14778/3641204.3641221}
}
```

---

## 7. 阅读笔记

### 💡 核心洞察
- **Prompt engineering 有天花板**：DAIL-SQL 已经把纯 prompt 路线优化到极致，后续提升空间在于引入结构化知识
- **LLM 学的是映射关系**：DAIL Organization 证明 LLM 从 in-context 学习的核心是 question→SQL 的映射模式，而非 schema 细节
- **Query Similarity 极其重要**：DAIL Selection 中 query similarity 从 0.48（random）提升到 0.94 时，EX 从 79.5% 提升到 82.4%
- **Schema 理解是瓶颈**：从 Spider（简单 schema）到 BIRD（复杂 schema）性能下降约 30 个百分点，说明 schema 理解是核心瓶颈

### ⚠️ 注意事项
- 本地 PDF 文件内容错误（实际包含 MIMO 通信论文），本解读基于 VLDB 正式版论文内容（从作者主页获取）
- BIRD 结果为外部评测数据，原论文主要在 Spider 和 Spider-Realistic 上评估

---

*解读时间：2026-04-15*
*数据来源：VLDB 2024 正式版论文 + GitHub README + 外部评测数据*
