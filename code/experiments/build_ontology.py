"""
Ontology 构建实验脚本

测试 LLM 半自动 Ontology 构建的效率和效果
"""

import time
import sys
sys.path.append('..')

from ontology_builder import SchemaAnalyzer, OntologyGenerator, OntologyQualityEvaluator


def run_experiment(ddl_text: str, db_name: str = "test_db"):
    """
    运行 Ontology 构建实验

    Args:
        ddl_text: 数据库 DDL
        db_name: 数据库名称
    """
    print(f"\n=== Ontology 构建实验: {db_name} ===\n")

    # 1. Schema 分析（Step 1）
    print("[Step 1] Schema 分析...")
    analyzer = SchemaAnalyzer()
    start_time = time.time()
    schema_info = analyzer.parse_ddl(ddl_text)
    ontology_draft = analyzer.to_ontology_draft(schema_info)
    step1_time = time.time() - start_time

    print(f"  - 提取表数: {len(schema_info['tables'])}")
    print(f"  - 外键数: {len(schema_info['foreign_keys'])}")
    print(f"  - 概念数: {len(ontology_draft['concepts'])}")
    print(f"  - 耗时: {step1_time:.2f}s")

    # 2. Ontology 生成（Step 2-3）
    # 注：Step 2 需要 LLM，这里先跳过
    print("\n[Step 2-3] Ontology 生成（仅 Step 1，无 LLM 增强）")
    ontology = ontology_draft

    # 3. 输出 Ontology
    print("\n[Output] Ontology 结构:")
    for concept in ontology['concepts'][:3]:  # 显示前3个概念
        print(f"  - 概念: {concept['name']}")
        print(f"    属性: {', '.join(concept['attributes'][:5])}...")

    print(f"\n总耗时: {step1_time:.2f}s")
    print(f"目标: ≤7200s (2小时)")

    return ontology, step1_time


# 测试 DDL
TEST_DDL = """
CREATE TABLE members (
    id INTEGER PRIMARY KEY,
    level VARCHAR(20),
    register_date DATE,
    total_spend FLOAT
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    member_id INTEGER,
    total_amount FLOAT,
    order_date DATE,
    FOREIGN KEY (member_id) REFERENCES members(id)
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100),
    category VARCHAR(50),
    price FLOAT
);
"""


if __name__ == "__main__":
    ontology, build_time = run_experiment(TEST_DDL, "test_ecommerce")

    # 保存 Ontology
    import json
    output_path = "../data/ontologies/test_ecommerce.json"
    with open(output_path, 'w') as f:
        json.dump(ontology, f, indent=2)
    print(f"\nOntology 已保存: {output_path}")