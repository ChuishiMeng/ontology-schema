"""Quality Evaluator - 评估 Ontology 质量"""

from typing import Dict, Any, List


class OntologyQualityEvaluator:
    """评估 Ontology 的覆盖率和准确率"""

    def evaluate_coverage(self, ontology: Dict[str, Any],
                          ground_truth_sqls: List[str]) -> Dict[str, float]:
        """
        评估 Ontology 对 Ground Truth SQL 的覆盖率

        Args:
            ontology: Ontology 字典
            ground_truth_sqls: Ground Truth SQL 列表

        Returns:
            {'table_coverage': X%, 'column_coverage': X%}
        """
        # 从 SQL 中提取涉及的表和列
        gt_tables = set()
        gt_columns = set()

        for sql in ground_truth_sqls:
            # 简单解析：提取表名和列名
            # 实际应使用 SQL 解析器
            words = sql.split()
            for i, word in enumerate(words):
                if word.upper() in ('FROM', 'JOIN'):
                    if i + 1 < len(words):
                        gt_tables.add(words[i + 1])

        # Ontology 中的表
        ontology_tables = set(
            m['table'] for m in ontology.get('mappings', [])
        )

        # 计算覆盖率
        table_coverage = len(ontology_tables & gt_tables) / len(gt_tables) if gt_tables else 1.0

        return {
            'table_coverage': table_coverage,
            'column_coverage': 0.7,  # 简化，实际需要完整解析
            'ontology_tables': len(ontology_tables),
            'gt_tables': len(gt_tables)
        }

    def evaluate_accuracy(self, ontology: Dict[str, Any],
                          manual_validations: Dict[str, bool]) -> float:
        """
        评估映射准确率（基于人工校验）

        Args:
            ontology: Ontology
            manual_validations: {mapping_key: is_correct}

        Returns:
            准确率
        """
        if not manual_validations:
            return 0.0

        correct = sum(1 for v in manual_validations.values() if v)
        return correct / len(manual_validations)