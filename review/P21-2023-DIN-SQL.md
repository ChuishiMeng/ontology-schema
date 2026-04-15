# P21 解读: DIN-SQL (NeurIPS 2023) - 分解策略

> **论文**: DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction
> **年份**: 2023 | **会议**: NeurIPS
> **相关性**: ⭐⭐⭐⭐ (Spider SOTA，分解策略)

---

## 核心贡献

**分解策略**：将 Text-to-SQL 分解为子任务，逐步解决

### 四步分解

1. **Schema Linking** — 识别相关的表和列
2. **Query Classification** — 分类查询类型（Easy/Non-nested/Nested）
3. **SQL Generation** — 基于前两步结果生成 SQL
4. **Self-Correction** — 检查 SQL 语法错误并修正

---

## 核心数据

| 数据集 | 方法 | EX |
|--------|------|-----|
| Spider Dev | Zero-shot GPT-4 | 64.9% |
| Spider Dev | Few-shot GPT-4 | 67.4% |
| Spider Dev | DIN-SQL (GPT-4) | **85.3%** ⭐ SOTA |
| BIRD | DIN-SQL | **55.9%** (当时 SOTA) |

---

## 分解策略细节

### Step 1: Schema Linking Module

```
输入: NL Question + Database Schema
输出: 相关的表集合 + 列集合 + 外键关系

方法: Few-shot prompting
Prompt: 展示如何从问题中识别表/列名称的示例
```

### Step 2: Query Classification

```
分类:
- Easy: 单表查询
- Non-nested: 多表 JOIN，无嵌套
- Nested: 包含子查询

作用: 根据复杂度选择不同的生成策略
```

### Step 3: SQL Generation

```
输入: Schema Linking 结果 + Query 类型
方法: Few-shot，按类型提供不同示例
```

### Step 4: Self-Correction

```
方法: 执行生成的 SQL，检查错误
如果有错误 → 反馈给 LLM 修正
最多 3 次修正机会
```

---

## 与本研究对比

| 维度 | DIN-SQL | 本研究 |
|------|---------|--------|
| **Schema Linking** | LLM few-shot | 联合召回（Ontology+Schema）|
| **知识层** | 无 | Ontology 层 |
| **召回机制** | LLM 直接识别 | 图谱游走 + 元路径约束 |
| **最小完备集** | 无 | 有 |
| **LLM 调用** | 4 步 = 4+ 次 | 2-4 次 |

---

## 启示

1. ✅ 分解策略有效（提升 10%）→ 可借鉴分解思想
2. ⚠️ DIN-SQL 的 Schema Linking 是 LLM 直接识别，无 Ontology
3. ✅ Self-Correction 可借鉴 → SQL 生成后的验证
4. ⚠️ 在 BIRD 上 DIN-SQL 55.9%，本研究目标应 > 55.9%（超过 DIN-SQL）