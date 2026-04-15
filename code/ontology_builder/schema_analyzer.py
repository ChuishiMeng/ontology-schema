"""Schema Analyzer - 解析 DDL，提取表/列/外键，生成 Ontology 草案"""

import re
from typing import Dict, List, Any


class SchemaAnalyzer:
    """解析数据库 DDL，提取 Schema 信息"""

    def parse_ddl(self, ddl_text: str) -> Dict[str, Any]:
        """
        解析 DDL 文本，提取表、列、外键信息

        Args:
            ddl_text: CREATE TABLE 等DDL语句

        Returns:
            {
                'tables': [{'name': str, 'columns': [...], 'primary_key': str}],
                'foreign_keys': [{'from_table': str, 'from_col': str, 'to_table': str, 'to_col': str}]
            }
        """
        tables = []
        foreign_keys = []

        # 提取 CREATE TABLE 语句
        create_pattern = r'CREATE TABLE\s+(\w+)\s*\((.*?)\)'
        matches = re.findall(create_pattern, ddl_text, re.IGNORECASE | re.DOTALL)

        for table_name, columns_text in matches:
            columns = []
            primary_key = None

            # 解析列定义
            lines = columns_text.split(',')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # PRIMARY KEY
                if 'PRIMARY KEY' in line.upper():
                    pk_match = re.search(r'PRIMARY KEY\s*\((\w+)\)', line)
                    if pk_match:
                        primary_key = pk_match.group(1)
                    continue

                # FOREIGN KEY
                if 'FOREIGN KEY' in line.upper() or 'REFERENCES' in line.upper():
                    # 独立 FOREIGN KEY 约束
                    fk_match = re.search(
                        r'FOREIGN KEY\s*\((\w+)\)\s*REFERENCES\s*(\w+)\s*\((\w+)\)',
                        line
                    )
                    if fk_match:
                        foreign_keys.append({
                            'from_table': table_name,
                            'from_col': fk_match.group(1),
                            'to_table': fk_match.group(2),
                            'to_col': fk_match.group(3)
                        })
                    continue

                # 普通列定义
                col_match = re.match(r'(\w+)\s+(\w+)', line)
                if col_match:
                    columns.append({
                        'name': col_match.group(1),
                        'type': col_match.group(2)
                    })

            tables.append({
                'name': table_name,
                'columns': columns,
                'primary_key': primary_key
            })

        return {
            'tables': tables,
            'foreign_keys': foreign_keys
        }

    def to_ontology_draft(self, schema_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        从 Schema 信息生成 Ontology 草案

        Args:
            schema_info: parse_ddl 的输出

        Returns:
            {
                'concepts': [{'name': str, 'attributes': [...]}],
                'relations': [{'from': str, 'to': str, 'type': 'foreign_key'}],
                'mappings': [{'concept': str, 'table': str, 'attribute': str, 'column': str}]
            }
        """
        concepts = []
        relations = []
        mappings = []

        # 表 → 概念
        for table in schema_info['tables']:
            concept_name = self._to_concept_name(table['name'])
            attributes = []

            for col in table['columns']:
                attr_name = self._to_attribute_name(col['name'])
                attributes.append(attr_name)
                mappings.append({
                    'concept': concept_name,
                    'attribute': attr_name,
                    'table': table['name'],
                    'column': col['name']
                })

            concepts.append({
                'name': concept_name,
                'attributes': attributes,
                'source_table': table['name']
            })

        # 外键 → 关系
        for fk in schema_info['foreign_keys']:
            from_concept = self._to_concept_name(fk['from_table'])
            to_concept = self._to_concept_name(fk['to_table'])
            relations.append({
                'from': from_concept,
                'to': to_concept,
                'type': 'foreign_key',
                'via': {
                    'from_column': fk['from_col'],
                    'to_column': fk['to_col']
                }
            })

        return {
            'concepts': concepts,
            'relations': relations,
            'mappings': mappings,
            'terms': []  # 业务术语待 LLM 增强
        }

    def _to_concept_name(self, table_name: str) -> str:
        """表名转概念名（驼峰化）"""
        # employees → Employee, orders → Order
        return table_name.capitalize().rstrip('s')

    def _to_attribute_name(self, column_name: str) -> str:
        """列名转属性名"""
        # member_id → memberId, total_amount → totalAmount
        parts = column_name.split('_')
        return parts[0] + ''.join(p.capitalize() for p in parts[1:])