"""
数据处理模块
- 数据加载
- Schema处理
- Ontology处理
- 对齐数据构建
"""

import json
import sqlite3
from typing import List, Dict, Tuple, Set, Optional
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
import os


# ================== 数据模型 ==================

@dataclass
class DatabaseSchema:
    """数据库Schema"""
    db_id: str
    name: str
    tables: List[str] = field(default_factory=list)
    columns: Dict[str, List[str]] = field(default_factory=dict)
    foreign_keys: List[Dict[str, str]] = field(default_factory=list)
    primary_keys: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class SpiderExample:
    """Spider数据集示例"""
    query_id: str
    question: str
    question_toks: List[str]
    db_id: str
    sql: str
    query_type: str
    difficulty: str
    

# ================== Schema加载 ==================

class SchemaLoader:
    """Schema加载器"""
    
    @staticmethod
    def from_sqlite(db_path: str, db_id: str = "") -> DatabaseSchema:
        """从SQLite数据库加载Schema"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        schema = DatabaseSchema(db_id=db_id, name=db_id)
        
        # 获取所有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        schema.tables = tables
        
        # 获取每个表的列
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            schema.columns[table] = columns
            
            # 主键
            pk_cols = [row[1] for row in cursor.fetchall() if row[5] > 0]
            if pk_cols:
                schema.primary_keys[table] = pk_cols
                
        # 获取外键
        for table in tables:
            cursor.execute(f"PRAGMA foreign_key_list({table})")
            for row in cursor.fetchall():
                schema.foreign_keys.append({
                    "table": table,
                    "from": row[3],
                    "to": row[2],
                    "to_table": row[2]
                })
                
        conn.close()
        return schema
    
    @staticmethod
    def from_dict(data: Dict) -> DatabaseSchema:
        """从字典加载"""
        return DatabaseSchema(
            db_id=data.get("db_id", ""),
            name=data.get("name", ""),
            tables=data.get("tables", []),
            columns=data.get("columns", {}),
            foreign_keys=data.get("foreign_keys", []),
            primary_keys=data.get("primary_keys", {})
        )
    
    @staticmethod
    def to_dict(schema: DatabaseSchema) -> Dict:
        """转换为字典"""
        return {
            "db_id": schema.db_id,
            "name": schema.name,
            "tables": schema.tables,
            "columns": schema.columns,
            "foreign_keys": schema.foreign_keys,
            "primary_keys": schema.primary_keys
        }


# ================== Spider数据加载 ==================

class SpiderLoader:
    """Spider数据集加载器"""
    
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        
    def load_train(self) -> List[SpiderExample]:
        """加载训练集"""
        return self._load_split("train")
    
    def load_val(self) -> List[SpiderExample]:
        """加载验证集"""
        return self._load_split("val")
    
    def load_test(self) -> List[SpiderExample]:
        """加载测试集"""
        return self._load_split("test")
    
    def _load_split(self, split: str) -> List[SpiderExample]:
        """加载指定分割"""
        examples = []
        
        # 加载JSON
        json_path = self.data_dir / f"{split}.json"
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            for item in data:
                example = SpiderExample(
                    query_id=item.get("query_id", ""),
                    question=item.get("question", ""),
                    question_toks=item.get("question_toks", []),
                    db_id=item.get("db_id", ""),
                    sql=item.get("sql", ""),
                    query_type=item.get("query_type", ""),
                    difficulty=item.get("difficulty", "")
                )
                examples.append(example)
                
        return examples
    
    def load_schemas(self) -> Dict[str, DatabaseSchema]:
        """加载所有数据库Schema"""
        schemas = {}
        
        # 查找数据库目录
        db_dir = self.data_dir / "databases"
        if not db_dir.exists():
            return schemas
            
        for db_path in db_dir.glob("*.sqlite"):
            db_id = db_path.stem
            schemas[db_id] = SchemaLoader.from_sqlite(str(db_path), db_id)
            
        return schemas


# ================== Ontology处理 ==================

class OntologyProcessor:
    """Ontology处理器"""
    
    def __init__(self):
        self.entities: Dict[str, Dict] = {}
        self.relations: Dict[str, List[str]] = defaultdict(list)
        self.alignments: Dict[str, Tuple[str, str]] = {}
        
    def add_entity(
        self,
        entity_id: str,
        name: str,
        description: str,
        entity_type: str = "entity",
        properties: Dict = None
    ):
        """添加实体"""
        self.entities[entity_id] = {
            "id": entity_id,
            "name": name,
            "description": description,
            "type": entity_type,
            "properties": properties or {}
        }
        
    def add_relation(self, from_id: str, to_id: str, relation_type: str):
        """添加关系"""
        self.relations[from_id].append({
            "to": to_id,
            "type": relation_type
        })
        
    def add_alignment(self, ont_id: str, schema_id: str, align_type: str):
        """添加对齐"""
        self.alignments[ont_id] = (schema_id, align_type)
        
    def generate_from_schema(self, schema: DatabaseSchema) -> "OntologyProcessor":
        """从Schema自动生成基础Ontology"""
        # 为每个表创建实体
        for table in schema.tables:
            self.add_entity(
                entity_id=f"ont_{table}",
                name=table.replace("_", " "),
                description=f"表: {table}",
                entity_type="table"
            )
            
        # 为列创建属性
        for table, columns in schema.columns.items():
            for col in columns:
                self.add_entity(
                    entity_id=f"ont_{table}_{col}",
                    name=col.replace("_", " "),
                    description=f"{table}.{col}",
                    entity_type="column",
                    properties={"table": table}
                )
                
        # 从外键创建关系
        for fk in schema.foreign_keys:
            self.add_relation(
                f"ont_{fk['table']}",
                f"ont_{fk['to_table']}",
                "has_foreign_key"
            )
            
        return self
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "entities": self.entities,
            "relations": dict(self.relations),
            "alignments": self.alignments
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "OntologyProcessor":
        """从字典加载"""
        processor = cls()
        processor.entities = data.get("entities", {})
        processor.relations = defaultdict(list, data.get("relations", {}))
        processor.alignments = data.get("alignments", {})
        return processor


# ================== 业务规则处理 ==================

class BusinessRuleProcessor:
    """业务规则处理器"""
    
    def __init__(self):
        self.rules: Dict[str, Dict] = {}
        
    def add_rule(
        self,
        rule_id: str,
        name: str,
        pattern: str,
        transformation: str,
        examples: List[str] = None
    ):
        """添加规则"""
        self.rules[rule_id] = {
            "id": rule_id,
            "name": name,
            "pattern": pattern,
            "transformation": transformation,
            "examples": examples or []
        }
        
    def add_time_rule(
        self,
        rule_id: str,
        time_expr: str,
        sql_expr: str
    ):
        """添加时间规则"""
        self.add_rule(
            rule_id=rule_id,
            name=f"时间规则: {time_expr}",
            pattern=time_expr,
            transformation=sql_expr,
            examples=[f"查询{time_expr}的数据"]
        )
        
    def add_aggregate_rule(
        self,
        rule_id: str,
        concept: str,
        sql_expr: str
    ):
        """添加聚合规则"""
        self.add_rule(
            rule_id=rule_id,
            name=f"聚合规则: {concept}",
            pattern=concept,
            transformation=sql_expr,
            examples=[f"计算{concept}"]
        )
        
    def match(self, text: str) -> List[Dict]:
        """匹配文本中的规则"""
        matched = []
        text_lower = text.lower()
        
        for rule_id, rule in self.rules.items():
            pattern = rule["pattern"].lower()
            if pattern in text_lower:
                matched.append(rule)
                
        return matched
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {"rules": self.rules}
    
    @classmethod
    def from_dict(cls, data: Dict) -> "BusinessRuleProcessor":
        """从字典加载"""
        processor = cls()
        processor.rules = data.get("rules", {})
        return processor


# ================== 对齐数据构建 ==================

class AlignmentBuilder:
    """对齐数据构建器"""
    
    def __init__(self):
        self.alignments: List[Dict] = []
        
    def add_alignment(
        self,
        ont_id: str,
        schema_id: str,
        align_type: str,
        confidence: float = 1.0,
        source: str = "manual"
    ):
        """添加对齐"""
        self.alignments.append({
            "ontology_id": ont_id,
            "schema_id": schema_id,
            "alignment_type": align_type,
            "confidence": confidence,
            "source": source
        })
        
    def build_from_linking(
        self,
        question: str,
        schema: DatabaseSchema,
        ontologies: List[str]
    ) -> List[Dict]:
        """基于问题文本的自动链接"""
        # 简单的关键词匹配
        question_lower = question.lower()
        question_words = set(question_lower.split())
        
        # 匹配表名
        for table in schema.tables:
            table_words = set(table.replace("_", " ").split())
            if table_words & question_words:
                # 查找对应的Ontology
                for ont in ontologies:
                    if any(w in ont.lower() for w in table_words):
                        self.add_alignment(
                            ont_id=ont,
                            schema_id=table,
                            align_type="entity-table",
                            confidence=0.8,
                            source="keyword"
                        )
                        
        return self.alignments
    
    def export_jsonl(self, path: str):
        """导出为JSONL格式"""
        with open(path, 'w', encoding='utf-8') as f:
            for alignment in self.alignments:
                f.write(json.dumps(alignment, ensure_ascii=False) + "\n")
                
    def to_list(self) -> List[Dict]:
        """转换为列表"""
        return self.alignments


# ================== 数据集构建 ==================

class DatasetBuilder:
    """数据集构建器"""
    
    def __init__(self):
        self.examples = []
        
    def add_example(
        self,
        query_id: str,
        question: str,
        db_id: str,
        gold_sql: str,
        recalled_tables: List[str] = None,
        recalled_columns: List[str] = None,
        ontology: Dict = None,
        business_rules: List[str] = None,
        difficulty: str = "medium",
        query_type: str = ""
    ):
        """添加示例"""
        self.examples.append({
            "query_id": query_id,
            "question": question,
            "db_id": db_id,
            "gold_sql": gold_sql,
            "recalled_tables": recalled_tables or [],
            "recalled_columns": recalled_columns or [],
            "ontology": ontology or {},
            "business_rules": business_rules or [],
            "difficulty": difficulty,
            "query_type": query_type
        })
        
    def save(self, path: str):
        """保存为JSON"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.examples, f, ensure_ascii=False, indent=2)
            
    def save_jsonl(self, path: str):
        """保存为JSONL"""
        with open(path, 'w', encoding='utf-8') as f:
            for example in self.examples:
                f.write(json.dumps(example, ensure_ascii=False) + "\n")
                
    def split(
        self, 
        train_ratio: float = 0.7, 
        val_ratio: float = 0.15
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """分割数据集"""
        n = len(self.examples)
        train_size = int(n * train_ratio)
        val_size = int(n * val_ratio)
        
        train = self.examples[:train_size]
        val = self.examples[train_size:train_size + val_size]
        test = self.examples[train_size + val_size:]
        
        return train, val, test


# ================== 主入口 ==================

if __name__ == "__main__":
    # 示例使用
    
    # 1. 加载Schema
    schema = SchemaLoader.from_dict({
        "db_id": "test",
        "name": "test",
        "tables": ["customers", "orders"],
        "columns": {
            "customers": ["id", "name", "email"],
            "orders": ["id", "customer_id", "amount", "created_at"]
        },
        "foreign_keys": [
            {"table": "orders", "from": "customer_id", "to": "id", "to_table": "customers"}
        ],
        "primary_keys": {
            "customers": ["id"],
            "orders": ["id"]
        }
    })
    
    print("Schema:", json.dumps(SchemaLoader.to_dict(schema), indent=2))
    
    # 2. 生成Ontology
    ont_processor = OntologyProcessor()
    ont_processor.generate_from_schema(schema)
    print("\nOntology:", json.dumps(ont_processor.to_dict(), indent=2))
    
    # 3. 添加业务规则
    rule_processor = BusinessRuleProcessor()
    rule_processor.add_time_rule("time_last_year", "去年", "WHERE year = 2024")
    rule_processor.add_aggregate_rule("agg_total", "总金额", "SUM(amount)")
    
    matched = rule_processor.match("查询去年的总金额")
    print("\nMatched rules:", matched)
    
    # 4. 构建数据集
    builder = DatasetBuilder()
    builder.add_example(
        query_id="1",
        question="找出去年的前10位客户",
        db_id="test",
        gold_sql="SELECT customer_name FROM orders WHERE year = 2024 GROUP BY customer_id ORDER BY SUM(amount) DESC LIMIT 10",
        difficulty="medium",
        query_type="ranking"
    )
    
    print("\nDataset examples:", builder.examples)
