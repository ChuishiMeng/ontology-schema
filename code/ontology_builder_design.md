# Ontology 构建实验代码设计

> **目的**: 实现 LLM 半自动 Ontology 构建，验证构建时间和质量
> **目标**: ≤2 小时/数据库，覆盖率 > 80%

---

## 代码结构

```
ontology-schema/code/
├── ontology_builder/
│   ├── __init__.py
│   ├── schema_analyzer.py      # Step 1: DDL 解析
│   ├── ontology_generator.py   # Step 2-3: Ontology 生成
│   ├── quality_evaluator.py    # Step 5: 质量评估
│   └── utils/
│       ├── llm_client.py       # LLM API 调用封装
│       └── db_parser.py        # DDL 解析工具
├── data/
│   ├── bird_sample/            # BIRD 数据集样本
│   └── ontologies/             # 生成的 Ontology 文件
├── experiments/
│   ├── build_ontology.py       # 主实验脚本
│   └ evaluate_coverage.py      # 覆盖率评估
│   └── compare_baseline.py     # 与手工对比
└── configs/
    └── llm_config.yaml         # LLM 配置
```

---

## Step 1: Schema Analyzer (schema_analyzer.py)

```python
class SchemaAnalyzer:
    """解析 DDL，提取表、列、外键"""

    def parse_ddl(self, ddl_text: str) -> dict:
        """
        输入: DDL 文本
        输出: {
            'tables': [{'name', 'columns', 'primary_key'}],
            'foreign_keys': [{'from_table', 'from_col', 'to_table', 'to_col'}]
        }
        """

    def to_ontology_draft(self, schema_info: dict) -> dict:
        """
        从 Schema 生成 Ontology 草案
        输出: {
            'concepts': [{'name', 'attributes'}],
            'relations': [{'from', 'to', 'type'}]
        }
        """
```

---

## Step 2-3: Ontology Generator (ontology_generator.py)

```python
class OntologyGenerator:
    """LLM 增强 Ontology"""

    def __init__(self, llm_client):
        self.llm = llm_client

    def enhance_with_documents(self, ontology_draft: dict,
                               business_docs: str = None) -> dict:
        """
        Step 2: 从业务文档提取术语和规则
        输入: Ontology 草案 + 业务文档（可选）
        输出: 增强 Ontology（添加业务术语）
        """

    def generate_ontology(self, ddl: str,
                          docs: str = None) -> dict:
        """
        Step 1-3: 完整生成流程
        """
        # Step 1: Schema 分析
        schema_info = self.analyzer.parse_ddl(ddl)
        ontology_draft = self.analyzer.to_ontology_draft(schema_info)

        # Step 2: 文档增强
        if docs:
            ontology_draft = self.enhance_with_documents(ontology_draft, docs)

        # Step 3: 合并
        return ontology_draft
```

---

## Step 5: Quality Evaluator (quality_evaluator.py)

```python
class OntologyQualityEvaluator:
    """评估 Ontology 质量"""

    def evaluate_coverage(self, ontology: dict,
                          ground_truth_sqls: list) -> dict:
        """
        覆盖率评估
        输入: Ontology + Ground Truth SQL 列表
        输出: {
            'table_coverage': X%,
            'column_coverage': X%,
            'term_coverage': X%
        }
        """

    def evaluate_accuracy(self, ontology: dict,
                          manual_validation: dict) -> float:
        """
        准确率评估（人工校验）
        """
```

---

## 实验流程 (experiments/build_ontology.py)

```python
def run_ontology_building_experiment(db_name: str):
    """
    Ontology 构建实验
    """
    # 1. 加载 DDL
    ddl = load_bird_ddl(db_name)

    # 2. LLM 构建 Ontology
    start_time = time.time()
    generator = OntologyGenerator(LLMClient())
    ontology = generator.generate_ontology(ddl)
    build_time = time.time() - start_time

    # 3. 人工校验（可选）
    # ontology = manual_validate(ontology)

    # 4. 质量评估
    evaluator = OntologyQualityEvaluator()
    gt_sqls = load_bird_ground_truth(db_name)
    coverage = evaluator.evaluate_coverage(ontology, gt_sqls)

    # 5. 输出
    print(f"Database: {db_name}")
    print(f"Build Time: {build_time:.1f}s")
    print(f"Coverage: {coverage}")

    return ontology, build_time, coverage
```

---

## LLM 配置 (configs/llm_config.yaml)

```yaml
provider: bailian  # 或 openai, anthropic
model: qwen3.5-plus  # 或 gpt-4, claude-3

ontology_generation:
  schema_analysis_prompt: |
    分析以下数据库 Schema，提取：
    1. 每个表的业务含义
    2. 每个列的语义解释
    3. 外键关系表示的业务关联

    DDL:
    {ddl}

  document_enhancement_prompt: |
    从以下业务文档中提取：
    1. 业务术语及其含义
    2. 计算规则（如"高价值客户"如何定义）
    3. 术语到数据库字段的映射建议

    业务文档:
    {docs}
```

---

## 评估指标

| 指标 | 计算方式 | 目标 |
|------|----------|------|
| **构建时间** | 实测秒数 | ≤2 小时 |
| **表覆盖率** | Ontology 表数 / GT SQL 涉及表数 | > 80% |
| **列覆盖率** | Ontology 列数 / GT SQL 涉及列数 | > 70% |
| **术语覆盖** | Ontology 术语数 / 问题中业务术语数 | > 60% |
| **映射准确率** | 人工校验 | > 90% |

---

## 下一步

- [ ] 实现 schema_analyzer.py
- [ ] 实现 ontology_generator.py
- [ ] 在 BIRD 样本数据库上测试
- [ ] 测量实际构建时间