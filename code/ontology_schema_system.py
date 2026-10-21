"""
Ontology-Schema 联合召回系统
Data Agent 领域的 Ontology-Schema 联合召回

核心模块:
1. 统一知识图谱构建
2. 异构图神经网络编码
3. 多源联合召回
4. SQL生成与验证
"""

import os
import json
import yaml
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import HeteroData
from torch_geometric.nn import HeteroConv, Linear, SAGEConv
from sentence_transformers import SentenceTransformer
import faiss
import networkx as nx
from collections import defaultdict
import sqlparse
from sqlglot import parse, transpile


# ================== 配置类 ==================

@dataclass
class Config:
    """系统配置"""
    # 模型配置
    embedding_model: str = "bge-large-zh-v1.5"
    llm_model: str = "gpt-4"
    hidden_dim: int = 256
    num_layers: int = 3
    
    # 召回配置
    semantic_top_k: int = 50
    final_top_k: int = 10
    fusion_weights: Dict[str, float] = field(default_factory=lambda: {
        "semantic": 0.5,
        "structural": 0.3,
        "rule": 0.2
    })
    
    # 索引配置
    index_type: str = "IVF"
    nlist: int = 100
    
    # 路径配置
    data_dir: str = "./data"
    output_dir: str = "./outputs"
    model_dir: str = "./models"
    
    # 设备配置
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


# ================== 数据模型 ==================

@dataclass
class SchemaElement:
    """Schema元素基类"""
    id: str
    name: str
    type: str  # table, column
    description: str = ""
    data_type: str = ""
    

@dataclass 
class TableElement(SchemaElement):
    """表元素"""
    columns: List[str] = field(default_factory=list)
    primary_key: str = ""
    foreign_keys: Dict[str, str] = field(default_factory=dict)  # col -> ref_table
    
    
@dataclass
class ColumnElement(SchemaElement):
    """列元素"""
    table_id: str = ""
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: str = ""
    nullable: bool = True
    

@dataclass
class OntologyEntity:
    """Ontology实体"""
    id: str
    name: str
    description: str
    entity_type: str  # entity, attribute, concept
    parent_id: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)
    properties: Dict = field(default_factory=dict)


@dataclass
class BusinessRule:
    """业务规则"""
    id: str
    name: str
    pattern: str  # 匹配模式
    transformation: str  # SQL转换
    examples: List[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """召回结果"""
    element_id: str
    element_type: str  # table, column, ontology, rule
    score: float
    metadata: Dict = field(default_factory=dict)


# ================== 统一知识图谱 ==================

class UnifiedKnowledgeGraph:
    """统一知识图谱"""
    
    def __init__(self, config: Config):
        self.config = config
        self.tables: Dict[str, TableElement] = {}
        self.columns: Dict[str, ColumnElement] = {}
        self.ontology: Dict[str, OntologyEntity] = {}
        self.rules: Dict[str, BusinessRule] = {}
        self.alignments: Dict[str, Tuple[str, str]] = {}  # ont_id -> (table_id/col_id, type)
        self.graph = nx.MultiDiGraph()
        
    def add_table(self, table: TableElement):
        """添加表"""
        self.tables[table.id] = table
        self.graph.add_node(f"table:{table.id}", 
                           node_type="table", 
                           name=table.name,
                           description=table.description)
        
    def add_column(self, column: ColumnElement):
        """添加列"""
        self.columns[column.id] = column
        self.graph.add_node(f"column:{column.id}",
                           node_type="column",
                           name=column.name,
                           table=column.table_id,
                           data_type=column.data_type)
        
        # 添加表-列边
        self.graph.add_edge(f"table:{column.table_id}", 
                           f"column:{column.id}",
                           edge_type="has_column")
        
        # 外键关系
        if column.is_foreign_key:
            self.graph.add_edge(f"column:{column.id}",
                               f"column:{column.references}",
                               edge_type="references")
                                    
    def add_ontology(self, entity: OntologyEntity):
        """添加Ontology实体"""
        self.ontology[entity.id] = entity
        self.graph.add_node(f"ontology:{entity.id}",
                           node_type="ontology",
                           name=entity.name,
                           description=entity.description,
                           entity_type=entity.entity_type)
        
    def add_alignment(self, ont_id: str, schema_id: str, align_type: str):
        """添加对齐关系"""
        self.alignments[ont_id] = (schema_id, align_type)
        
        # 添加对齐边
        if schema_id in self.tables:
            self.graph.add_edge(f"ontology:{ont_id}",
                               f"table:{schema_id}",
                               edge_type="aligns_to")
        elif schema_id in self.columns:
            self.graph.add_edge(f"ontology:{ont_id}",
                               f"column:{schema_id}",
                               edge_type="aligns_to")
                               
    def add_business_rule(self, rule: BusinessRule):
        """添加业务规则"""
        self.rules[rule.id] = rule
        self.graph.add_node(f"rule:{rule.id}",
                           node_type="rule",
                           name=rule.name,
                           pattern=rule.pattern)
    
    def get_schema_by_ontology(self, ont_id: str) -> List[str]:
        """通过Ontology获取相关Schema"""
        if ont_id not in self.alignments:
            return []
        return [self.alignments[ont_id][0]]
    
    def get_neighbors(self, node_id: str, depth: int = 1) -> List[str]:
        """获取邻居节点"""
        if node_id in self.tables:
            node_id = f"table:{node_id}"
        elif node_id in self.columns:
            node_id = f"column:{node_id}"
        elif node_id in self.ontology:
            node_id = f"ontology:{node_id}"
            
        neighbors = []
        for i in range(depth):
            if i == 0:
                neighbors = list(self.graph.neighbors(node_id))
            else:
                new_neighbors = []
                for n in neighbors:
                    new_neighbors.extend(list(self.graph.neighbors(n)))
                neighbors.extend(new_neighbors)
        return neighbors
    
    def to_hetero_data(self) -> HeteroData:
        """转换为PyG异构图数据"""
        data = HeteroData()
        
        # 节点
        table_ids = [f"table:{t}" for t in self.tables.keys()]
        column_ids = [f"column:{c}" for c in self.columns.keys()]
        ontology_ids = [f"ontology:{o}" for o in self.ontology.keys()]
        
        # 边
        edge_list = list(self.graph.edges(data=True))
        
        return data
    
    def save(self, path: str):
        """保存图结构"""
        data = {
            "tables": {k: vars(v) for k, v in self.tables.items()},
            "columns": {k: vars(v) for k, v in self.columns.items()},
            "ontology": {k: vars(v) for k, v in self.ontology.items()},
            "rules": {k: vars(v) for k, v in self.rules.items()},
            "alignments": self.alignments
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    def load(self, path: str):
        """加载图结构"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 重建对象
        self.tables = {k: TableElement(**v) for k, v in data.get('tables', {}).items()}
        self.columns = {k: ColumnElement(**v) for k, v in data.get('columns', {}).items()}
        self.ontology = {k: OntologyEntity(**v) for k, v in data.get('ontology', {}).items()}
        self.rules = {k: BusinessRule(**v) for k, v in data.get('rules', {}).items()}
        self.alignments = {k: tuple(v) for k, v in data.get('alignments', {}).items()}


# ================== 异构图神经网络编码器 ==================

class HeteroSchemaGNN(nn.Module):
    """异构图神经网络编码器"""
    
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.hidden_dim = config.hidden_dim
        
        # 节点类型映射
        self.node_types = ['table', 'column', 'ontology']
        
        # 各类型的线性变换层
        self.node_embeddings = nn.ModuleDict({
            node_type: nn.Linear(self.hidden_dim, self.hidden_dim)
            for node_type in self.node_types
        })
        
        # 异构图卷积层
        self.conv1 = HeteroConv({
            ('table', 'has_column', 'column'): SAGEConv(self.hidden_dim, self.hidden_dim),
            ('column', 'rev_has_column', 'table'): SAGEConv(self.hidden_dim, self.hidden_dim),
            ('ontology', 'aligns_to', 'table'): SAGEConv(self.hidden_dim, self.hidden_dim),
            ('table', 'rev_aligns_to', 'ontology'): SAGEConv(self.hidden_dim, self.hidden_dim),
            ('ontology', 'aligns_to', 'column'): SAGEConv(self.hidden_dim, self.hidden_dim),
            ('column', 'rev_aligns_to', 'ontology'): SAGEConv(self.hidden_dim, self.hidden_dim),
            ('column', 'references', 'column'): SAGEConv(self.hidden_dim, self.hidden_dim),
        }, aggr='mean')
        
        self.conv2 = HeteroConv({
            ('table', 'has_column', 'column'): SAGEConv(self.hidden_dim, self.hidden_dim),
            ('column', 'rev_has_column', 'table'): SAGEConv(self.hidden_dim, self.hidden_dim),
            ('ontology', 'aligns_to', 'table'): SAGEConv(self.hidden_dim, self.hidden_dim),
            ('table', 'rev_aligns_to', 'ontology'): SAGEConv(self.hidden_dim, self.hidden_dim),
        }, aggr='mean')
        
        self.conv3 = HeteroConv({
            ('table', 'has_column', 'column'): SAGEConv(self.hidden_dim, self.hidden_dim),
            ('column', 'rev_has_column', 'table'): SAGEConv(self.hidden_dim, self.hidden_dim),
        }, aggr='mean')
        
        # 输出层
        self.classifier = nn.Sequential(
            nn.Linear(self.hidden_dim * 2, self.hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(self.hidden_dim, 1)
        )
        
    def forward(self, x_dict, edge_index_dict):
        """前向传播"""
        # 第一层卷积
        x_dict = self.conv1(x_dict, edge_index_dict)
        x_dict = {k: F.relu(v) for k, v in x_dict.items()}
        
        # 第二层卷积
        x_dict = self.conv2(x_dict, edge_index_dict)
        x_dict = {k: F.relu(v) for k, v in x_dict.items()}
        
        # 第三层卷积
        x_dict = self.conv3(x_dict, edge_index_dict)
        
        return x_dict
    
    def get_embeddings(self, x_dict) -> Dict[str, np.ndarray]:
        """获取各节点类型的嵌入"""
        embeddings = {}
        for node_type, x in x_dict.items():
            if isinstance(x, torch.Tensor):
                embeddings[node_type] = x.detach().cpu().numpy()
        return embeddings


# ================== 语义召回器 ==================

class SemanticRecaller:
    """语义召回器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.embedding_model = SentenceTransformer(config.embedding_model)
        self.index: Optional[faiss.Index] = None
        self.id_to_item: Dict[int, str] = {}
        self.item_to_id: Dict[str, int] = {}
        
    def build_index(self, items: List[Tuple[str, str, str]]):
        """
        构建向量索引
        items: [(id, text, type), ...]
        """
        self.id_to_item = {}
        self.item_to_id = {}
        
        texts = []
        for idx, (item_id, text, item_type) in enumerate(items):
            self.id_to_item[idx] = item_id
            self.item_to_id[item_id] = idx
            texts.append(text)
            
        # 编码
        embeddings = self.embedding_model.encode(texts, 
                                                  show_progress_bar=True,
                                                  convert_to_numpy=True)
        
        # 归一化
        faiss.normalize_L2(embeddings)
        
        # 构建索引
        dim = embeddings.shape[1]
        if self.config.index_type == "IVF":
            quantizer = faiss.IndexFlatIP(dim)
            self.index = faiss.IndexIVFFlat(quantizer, dim, self.config.nlist)
            self.index.train(embeddings)
        else:
            self.index = faiss.IndexFlatIP(dim)
            
        self.index.add(embeddings)
        
    def recall(self, query: str, top_k: int = 50) -> List[Tuple[str, float]]:
        """语义召回"""
        # 编码查询
        query_embedding = self.embedding_model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)
        
        # 检索
        distances, indices = self.index.search(query_embedding, top_k)
        
        # 转换为结果
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0:
                item_id = self.id_to_item[idx]
                results.append((item_id, float(dist)))
                
        return results
    
    def save_index(self, path: str):
        """保存索引"""
        faiss.write_index(self.index, f"{path}.index")
        with open(f"{path}_meta.json", 'w') as f:
            json.dump({
                'id_to_item': self.id_to_item,
                'item_to_id': self.item_to_id
            }, f)
            
    def load_index(self, path: str):
        """加载索引"""
        self.index = faiss.read_index(f"{path}.index")
        with open(f"{path}_meta.json", 'r') as f:
            meta = json.load(f)
            self.id_to_item = meta['id_to_item']
            self.item_to_id = meta['item_to_id']


# ================== 结构召回器 ==================

class StructuralRecaller:
    """结构召回器 - 基于图结构扩展"""
    
    def __init__(self, knowledge_graph: UnifiedKnowledgeGraph):
        self.kg = knowledge_graph
        
    def fk_propagation(self, table_ids: List[str], max_depth: int = 2) -> List[str]:
        """通过外键关系传播"""
        visited = set(table_ids)
        queue = list(table_ids)
        
        while queue:
            current = queue.pop(0)
            # 查找外键关联的表
            for col_id, col in self.kg.columns.items():
                if col.table_id == current and col.is_foreign_key:
                    ref_table = col.references.split('.')[0] if '.' in col.references else col.references
                    if ref_table not in visited:
                        visited.add(ref_table)
                        queue.append(ref_table)
                        
        return list(visited)
    
    def path_inference(self, from_id: str, to_id: str) -> List[str]:
        """路径推理 - 找从from到to的路径"""
        if from_id not in self.kg.tables:
            from_id = f"table:{from_id}"
        if to_id not in self.kg.tables:
            to_id = f"table:{to_id}"
            
        try:
            path = nx.shortest_path(self.kg.graph, from_id, to_id)
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
    
    def recall(self, 
               seed_tables: List[str], 
               seed_ontology: List[str] = None,
               max_depth: int = 2) -> Dict[str, List[str]]:
        """结构召回"""
        results = {
            "tables": set(),
            "columns": set()
        }
        
        # 从种子表出发
        tables = self.fk_propagation(seed_tables, max_depth)
        results["tables"].update(tables)
        
        # 获取相关列
        for table_id in tables:
            for col_id, col in self.kg.columns.items():
                if col.table_id == table_id:
                    results["columns"].add(col_id)
                    
        # 从Ontology出发
        if seed_ontology:
            for ont_id in seed_ontology:
                related = self.kg.get_schema_by_ontology(ont_id)
                results["tables"].update(related)
                
        return {
            "tables": list(results["tables"]),
            "columns": list(results["columns"])
        }


# ================== 规则召回器 ==================

class RuleRecaller:
    """规则召回器 - 业务规则匹配"""
    
    def __init__(self, knowledge_graph: UnifiedKnowledgeGraph):
        self.kg = knowledge_graph
        self.rule_patterns: Dict[str, List[BusinessRule]] = defaultdict(list)
        
    def add_rule(self, rule: BusinessRule):
        """添加规则"""
        self.kg.add_business_rule(rule)
        # 建立模式索引
        for keyword in rule.pattern.split():
            self.rule_patterns[keyword].append(rule)
            
    def match(self, query: str) -> List[BusinessRule]:
        """匹配查询中的规则"""
        matched_rules = []
        query_lower = query.lower()
        
        for keyword, rules in self.rule_patterns.items():
            if keyword.lower() in query_lower:
                matched_rules.extend(rules)
                
        # 去重
        seen = set()
        unique_rules = []
        for rule in matched_rules:
            if rule.id not in seen:
                seen.add(rule.id)
                unique_rules.append(rule)
                
        return unique_rules
    
    def transform(self, query: str, matched_rules: List[BusinessRule]) -> str:
        """应用规则转换"""
        transformed = query
        for rule in matched_rules:
            # 简单的占位符替换
            transformed = transformed.replace(rule.pattern, rule.transformation)
        return transformed
    
    def recall(self, query: str) -> List[Tuple[str, str, float]]:
        """规则召回"""
        matched_rules = self.match(query)
        
        results = []
        for rule in matched_rules:
            results.append((rule.id, "rule", 1.0))
            
        return results


# ================== 联合召回器 ==================

class JointRetriever:
    """联合召回器 - 多源融合"""
    
    def __init__(self, config: Config, knowledge_graph: UnifiedKnowledgeGraph):
        self.config = config
        self.kg = knowledge_graph
        
        # 各召回器
        self.semantic_recaller = SemanticRecaller(config)
        self.structural_recaller = StructuralRecaller(knowledge_graph)
        self.rule_recaller = RuleRecaller(knowledge_graph)
        
        # 权重
        self.weights = config.fusion_weights
        
    def build_indices(self):
        """构建索引"""
        # 构建语义索引
        items = []
        
        # 表
        for table_id, table in self.kg.tables.items():
            text = f"{table.name}: {table.description} columns: {', '.join(table.columns)}"
            items.append((table_id, text, "table"))
            
        # 列
        for col_id, col in self.kg.columns.items():
            text = f"{col.name}: {col.description} type: {col.data_type}"
            items.append((col_id, text, "column"))
            
        # Ontology
        for ont_id, ont in self.kg.ontology.items():
            text = f"{ont.name}: {ont.description}"
            items.append((ont_id, text, "ontology"))
            
        self.semantic_recaller.build_index(items)
        
    def retrieve(self, query: str, intent: Dict = None) -> List[RetrievalResult]:
        """联合召回"""
        results = []
        
        # Stage 1: 语义召回
        semantic_results = self.semantic_recaller.recall(
            query, 
            top_k=self.config.semantic_top_k
        )
        for item_id, score in semantic_results:
            results.append(RetrievalResult(
                element_id=item_id,
                element_type="semantic",
                score=score * self.weights["semantic"],
                metadata={"signal": "semantic"}
            ))
            
        # Stage 2: 结构扩展
        # 从语义结果中提取表
        seed_tables = [r.element_id for r in results[:10] 
                      if r.element_id in self.kg.tables]
        
        if seed_tables:
            seed_ontology = [r.element_id for r in results[:10]
                            if r.element_id in self.kg.ontology]
            
            struct_results = self.structural_recaller.recall(
                seed_tables,
                seed_ontology
            )
            
            # 添加结构得分
            for table_id in struct_results["tables"]:
                if table_id not in [r.element_id for r in results]:
                    results.append(RetrievalResult(
                        element_id=table_id,
                        element_type="table",
                        score=self.weights["structural"],
                        metadata={"signal": "structural"}
                    ))
                    
        # Stage 3: 规则增强
        rule_results = self.rule_recaller.recall(query)
        for rule_id, rule_type, score in rule_results:
            results.append(RetrievalResult(
                element_id=rule_id,
                element_type="rule",
                score=score * self.weights["rule"],
                metadata={"signal": "rule"}
            ))
            
        # 排序
        results.sort(key=lambda x: x.score, reverse=True)
        
        # 取Top-K
        return results[:self.config.final_top_k]


# ================== SQL生成器 ==================

class SQLGenerator:
    """SQL生成器"""
    
    def __init__(self, config: Config):
        self.config = config
        
    def build_prompt(self, 
                    query: str, 
                    recalled: List[RetrievalResult],
                    knowledge: str = "") -> str:
        """构建Prompt"""
        
        # 收集召回的表和列
        tables = []
        columns = []
        
        for r in recalled:
            if r.element_id in self.kg.tables:
                tables.append(self.kg.tables[r.element_id])
            elif r.element_id in self.kg.columns:
                columns.append(self.kg.columns[r.element_id])
                
        # 格式化Schema
        schema_text = "### 可用表:\n"
        for table in tables:
            schema_text += f"- {table.name}: {table.description}\n"
            for col in table.columns:
                schema_text += f"  - {col}\n"
                
        # 格式化业务规则
        rules_text = ""
        if knowledge:
            rules_text = f"\n### 业务规则:\n{knowledge}\n"
            
        prompt = f"""<instruction>
你是一个SQL专家。根据用户的问题生成有效的SQL查询。
只能使用下面提供的表和列。
</instruction>

<schema>
{schema_text}
</schema>

{rules_text}

<question>
{query}
</question>

<output_format>
只返回SQL语句，不要解释。
</output_format>"""
        
        return prompt
        
    def generate(self, prompt: str) -> str:
        """调用LLM生成SQL"""
        # 这里应该调用实际的LLM API
        # 简化实现
        raise NotImplementedError("需要实现LLM调用")
        
    def validate(self, sql: str, allowed_tables: List[str]) -> Tuple[bool, str]:
        """SQL验证"""
        try:
            # 语法解析
            parsed = sqlparse.parse(sql)
            if not parsed:
                return False, "语法错误"
                
            # 表引用检查
            for stmt in parsed:
                for token in stmt.tokens:
                    if token.ttype is None and token.value in allowed_tables:
                        pass  # 表存在
                        
            return True, "Valid"
            
        except Exception as e:
            return False, str(e)


# ================== 主系统 ==================

class OntologySchemaSystem:
    """Ontology-Schema联合召回系统"""
    
    def __init__(self, config: Config):
        self.config = config
        
        # 核心组件
        self.kg = UnifiedKnowledgeGraph(config)
        self.retriever: Optional[JointRetriever] = None
        self.generator = SQLGenerator(config)
        
    def initialize(self):
        """初始化系统"""
        self.retriever = JointRetriever(self.config, self.kg)
        self.retriever.build_indices()
        
    def add_schema(self, schema_path: str):
        """加载Schema"""
        # 简化的Schema加载
        pass
        
    def add_ontology(self, ontology_path: str):
        """加载Ontology"""
        # 简化的Ontology加载
        pass
        
    def query(self, user_query: str, intent: Dict = None) -> Dict:
        """处理查询"""
        # 1. 联合召回
        recalled = self.retriever.retrieve(user_query, intent)
        
        # 2. 收集业务知识
        knowledge = ""
        for r in recalled:
            if r.element_type == "rule":
                rule = self.kg.rules.get(r.element_id)
                if rule:
                    knowledge += f"- {rule.name}: {rule.transformation}\n"
                    
        # 3. 构建Prompt
        prompt = self.generator.build_prompt(user_query, recalled, knowledge)
        
        # 4. 生成SQL (实际应调用LLM)
        # sql = self.generator.generate(prompt)
        
        return {
            "query": user_query,
            "recalled": [
                {
                    "id": r.element_id,
                    "type": r.element_type,
                    "score": r.score,
                    "metadata": r.metadata
                }
                for r in recalled
            ],
            "knowledge": knowledge,
            "prompt": prompt
        }
        
    def save(self, path: str):
        """保存系统"""
        self.kg.save(f"{path}/knowledge_graph.json")
        self.retriever.semantic_recaller.save_index(f"{path}/semantic_index")
        
    def load(self, path: str):
        """加载系统"""
        self.kg.load(f"{path}/knowledge_graph.json")
        self.retriever = JointRetriever(self.config, self.kg)
        self.retriever.semantic_recaller.load_index(f"{path}/semantic_index")


# ================== 工具函数 ==================

def load_spider_dataset(path: str) -> List[Dict]:
    """加载Spider数据集"""
    data = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            data.append(json.loads(line))
    return data


def load_schema_from_db(db_path: str) -> Tuple[List[TableElement], List[ColumnElement]]:
    """从数据库加载Schema"""
    # 简化实现
    return [], []


def create_alignment(ontology: Dict, schema: Dict) -> Dict[str, Tuple[str, str]]:
    """创建Ontology-Schema对齐"""
    alignments = {}
    # 简化实现
    return alignments


# ================== 主入口 ==================

if __name__ == "__main__":
    # 示例使用
    config = Config()
    
    # 创建系统
    system = OntologySchemaSystem(config)
    
    # 添加示例Schema
    system.kg.add_table(TableElement(
        id="customers",
        name="customers",
        description="客户表",
        columns=["customer_id", "customer_name", "email", "created_at"]
    ))
    
    # 初始化
    system.initialize()
    
    # 查询
    result = system.query("找出2024年购买金额最高的10位客户")
    print(json.dumps(result, ensure_ascii=False, indent=2))
