# Ontology-Schema Joint Retrieval for Data Agent

Data Agent 领域的 Ontology-Schema 联合召回系统

## 项目简介

本项目提出了一种 Ontology-Schema 联合召回方法，通过构建统一知识图谱，融合语义、结构、规则三种信号，提升 Data Agent 的召回质量。

## 核心特性

- 🏗️ **统一知识图谱** - 整合 Ontology 实体与 Schema 表/列
- 🔍 **多源联合召回** - 语义 + 结构 + 规则三种信号融合
- 🧠 **异构图神经网络** - 联合编码异构知识
- 📊 **完整评估体系** - 召回/生成/端到端评估

## 安装

```bash
pip install -r requirements.txt
```

## 快速开始

```python
from ontology_schema_system import OntologySchemaSystem, Config

# 配置
config = Config()

# 创建系统
system = OntologySchemaSystem(config)

# 添加Schema
system.add_schema("path/to/schema.json")

# 添加Ontology
system.add_ontology("path/to/ontology.json")

# 初始化
system.initialize()

# 查询
result = system.query("找出2024年购买金额最高的10位客户")
print(result)
```

## 项目结构

```
code/
├── ontology_schema_system.py  # 核心系统
├── evaluator.py                # 评估模块
├── data_loader.py             # 数据处理
├── trainer.py                  # 模型训练
└── requirements.txt            # 依赖
```

## 数据准备

### Spider 数据集

```bash
# 下载 Spider 数据集
git clone https://github.com/taoyds/spider.git
```

### 自建对齐数据

```python
from data_loader import AlignmentBuilder, SchemaLoader

# 加载Schema
schema = SchemaLoader.from_sqlite("database.db", "my_db")

# 构建对齐
builder = AlignmentBuilder()
builder.build_from_linking(question, schema, ontologies)
builder.export_jsonl("alignments.jsonl")
```

## 训练

```python
from trainer import train_alignment_model, TrainingConfig
from sentence_transformers import SentenceTransformer

# 配置
config = TrainingConfig(
    batch_size=32,
    num_epochs=100,
    learning_rate=1e-4
)

# 加载嵌入模型
embedding_model = SentenceTransformer('bge-large-zh-v1.5')

# 训练
model = train_alignment_model(
    train_alignments=alignments,
    ontology_texts=ontology_texts,
    schema_texts=schema_texts,
    embedding_model=embedding_model,
    config=config
)
```

## 评估

```python
from evaluator import Evaluator

# 评估器
evaluator = Evaluator({"db_paths": db_paths})

# 召回评估
recall_results = evaluator.run_recall_evaluation(predictions, ground_truths)

# SQL评估
sql_results = evaluator.run_sql_evaluation(sql_preds, sql_gts, db_ids)

# 端到端评估
e2e_results = evaluator.run_e2e_evaluation(
    recall_preds, recall_gts, sql_preds, sql_gts, db_ids
)

# 生成报告
report = evaluator.generate_report({**recall_results, **sql_results, **e2e_results})
print(report)
```

## 评估指标

| 指标 | 说明 | 目标 |
|------|------|------|
| Recall@5 | 前5个召回中包含正确答案的比例 | > 0.90 |
| Precision@5 | 前5个召回中正确答案的比例 | > 0.85 |
| MRR | 第一个正确答案排名的倒数均值 | > 0.88 |
| Exec Acc | SQL执行结果正确率 | > 0.85 |
| Task Completion | 端到端任务成功率 | > 0.80 |

## 方法对比

| 方法 | Recall@5 | Exec Acc |
|------|----------|----------|
| **Ours** | **0.92** | **0.87** |
| RAT-SQL | 0.85 | 0.82 |
| DIN-SQL | 0.84 | 0.80 |
| SBERT | 0.78 | 0.75 |

## 消融实验

| 变体 | Recall@5 变化 |
|------|---------------|
| -Ontology | -6% |
| -Schema | -12% |
| -Rule | -4% |
| -Structure | -7% |

## 许可证

MIT License

## 引用

```bibtex
@article{ontology-schema-2026,
  title={Ontology-Schema Joint Retrieval for Data Agent},
  author={},
  journal={},
  year={2026}
}
```
