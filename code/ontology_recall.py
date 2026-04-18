#!/usr/bin/env python3
"""
Ontology-Schema 联合召回算法

5步流程:
  Step 1: 问题理解 (LLM)
  Step 2: L1 Ontology 召回 (向量相似度)
  Step 3: L2 Schema 映射 (映射表)
  Step 4: 元路径约束验证
  Step 5: 最小完备集提取 (MCS)

输出: MCS = {tables*, columns*, knowledge*}
"""

import json
import re
import logging
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    import faiss
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class RecallResult:
    """联合召回结果"""
    tables: list[str] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)  # {table, column}
    join_paths: list[list[str]] = field(default_factory=list)
    knowledge: list[str] = field(default_factory=list)  # business rules, formulas
    confidence: float = 1.0
    steps_log: list[dict] = field(default_factory=list)


class OntologyRecall:
    """Ontology-Schema 联合召回引擎"""

    def __init__(self, ontology_path: str, model_name: str = "all-MiniLM-L6-v2",
                 llm_model: str = "qwen3.5-plus",
                 llm_api_key: str = "sk-sp-fcf1d94d2cce41eb87155babef8bfa6e",
                 llm_base_url: str = "https://coding.dashscope.aliyuncs.com/v1"):
        self.ontology = self._load_ontology(ontology_path)
        self.model_name = model_name
        self._embedder = None
        self._faiss_index = None
        self._index_keys = []
        self.llm_model = llm_model
        self.llm_client = None
        if OPENAI_AVAILABLE and llm_api_key:
            self.llm_client = OpenAI(api_key=llm_api_key, base_url=llm_base_url)

    def _load_ontology(self, path: str) -> dict:
        with open(path) as f:
            return json.load(f)

    def _get_embedder(self):
        if self._embedder is None:
            if not EMBEDDING_AVAILABLE:
                raise RuntimeError("sentence-transformers not installed")
            self._embedder = SentenceTransformer(self.model_name)
        return self._embedder

    def _build_index(self):
        """构建 FAISS 索引（首次调用时延迟构建）"""
        if self._faiss_index is not None:
            return

        embedder = self._get_embedder()
        keys = []

        # 索引概念
        for c in self.ontology.get("concepts", []):
            name = c.get("table_name", c.get("name", ""))
            desc = c.get("description", name)
            keys.append({"type": "concept", "data": c, "text": f"{name} {desc}"})
            for alias in c.get("aliases", []):
                keys.append({"type": "concept", "data": c, "text": alias})

        # 索引属性
        for a in self.ontology.get("attributes", []):
            name = a.get("column_name", a.get("name", ""))
            desc = a.get("description", name)
            keys.append({"type": "attribute", "data": a, "text": f"{name} {desc}"})
            for alias in a.get("aliases", []):
                keys.append({"type": "attribute", "data": a, "text": alias})

        # 索引术语
        for t in self.ontology.get("term_dictionary", []):
            term = t.get("term", t.get("name", ""))
            mapping = t.get("mapping", t.get("description", ""))
            keys.append({"type": "term", "data": t, "text": f"{term} {mapping}"})

        # 索引业务规则
        for br in self.ontology.get("business_rules", []):
            name = br.get("name", br.get("description", ""))
            desc = br.get("description", "")
            keys.append({"type": "rule", "data": br, "text": f"{name} {desc}"})

        if not keys:
            return

        texts = [k["text"] for k in keys]
        embeddings = embedder.encode(texts, normalize_embeddings=True)
        dim = embeddings.shape[1]

        self._faiss_index = faiss.IndexFlatIP(dim)
        self._faiss_index.add(embeddings.astype(np.float32))
        self._index_keys = keys

    # ── Step 1: 问题理解 ──────────────────────────────────

    def understand_question(self, question: str) -> dict:
        """Step 1: LLM 提取问题中的实体、属性、条件、意图"""
        # 构建概念列表给 LLM 参考
        concept_list = []
        for c in self.ontology.get("concepts", []):
            name = c.get("table_name", c.get("name", ""))
            desc = c.get("description", "")
            aliases = c.get("aliases", [])
            concept_list.append(f"- {name}: {desc} (aliases: {', '.join(aliases)})")
        
        term_list = []
        for t in self.ontology.get("term_dictionary", []):
            term = t.get("term", t.get("name", ""))
            mapping = t.get("mapping", t.get("description", ""))
            term_list.append(f"- {term} → {mapping}")
        
        rule_list = []
        for br in self.ontology.get("business_rules", []):
            rule_list.append(f"- {br.get('name', br.get('description', ''))}")
        
        prompt = f"""Given a natural language question about a database, extract structured information.

Available database concepts (tables):
{chr(10).join(concept_list)}

Business terms:
{chr(10).join(term_list)}

Business rules:
{chr(10).join(rule_list)}

Question: {question}

Extract and return JSON:
{{
  "tables": [list of relevant table names from the concepts above],
  "columns": [list of specific column names mentioned or implied],
  "conditions": [list of WHERE conditions implied],
  "intent": "query|aggregate|compare|existence",
  "entities": [business entities mentioned, e.g. "sales representative", "customer"]
}}

Return ONLY the JSON, no explanation."""

        if self.llm_client:
            try:
                resp = self.llm_client.chat.completions.create(
                    model=self.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=512,
                )
                text = resp.choices[0].message.content.strip()
                # Extract JSON from response
                if text.startswith("```"):
                    text = re.sub(r'^```\w*\n?', '', text)
                    text = re.sub(r'\n?```$', '', text)
                parsed = json.loads(text)
                parsed["_source"] = "llm"
                return parsed
            except Exception as e:
                logger.warning(f"LLM question understanding failed: {e}")
        
        # Fallback: keyword-based
        return self._keyword_understand(question)

    def _keyword_understand(self, question: str) -> dict:
        """Fallback: keyword-based question understanding"""
        # 关键词提取（无需 LLM 的简化版）
        entities = []
        attributes = []
        conditions = []
        intent = "query"  # query | aggregate | compare | existence

        # 聚合意图检测
        agg_patterns = {
            "aggregate": [r"how many", r"count", r"total", r"sum", r"average", r"avg", r"最大", r"最小", r"最高", r"lowest", r"highest", r"most"],
            "compare": [r"difference", r"compare", r"vs", r"between.*and"],
            "existence": [r"whether", r"if there", r"does.*exist", r"is there"],
        }
        for intent_type, patterns in agg_patterns.items():
            for p in patterns:
                if re.search(p, question.lower()):
                    intent = intent_type
                    break

        # 从 Ontology 术语匹配实体
        for term in self.ontology.get("term_dictionary", []):
            t = term.get("term", term.get("name", "")).lower()
            if t in question.lower():
                entities.append(term)

        # 从业务规则匹配条件
        for rule in self.ontology.get("business_rules", []):
            keywords = rule.get("keywords", rule.get("name", "").lower().split())
            if isinstance(keywords, str):
                keywords = [keywords]
            for kw in keywords:
                if kw.lower() in question.lower():
                    conditions.append(rule)
                    break

        return {
            "question": question,
            "entities": entities,
            "attributes": attributes,
            "conditions": conditions,
            "intent": intent,
        }

    # ── Step 2: L1 Ontology 召回 ───────────────────────────

    def recall_ontology(self, question: str, top_k: int = 20, threshold: float = 0.3) -> dict:
        """Step 2: 关键词匹配 + 向量相似度双路召回"""
        results = {"concepts": [], "attributes": [], "terms": [], "rules": []}
        seen = set()
        q_lower = question.lower()

        # ── 路径1: 关键词/子串匹配（精确、可靠）──

        def _add(target_list, data, key_type, score, match_type):
            dedup = f"{key_type}:{data.get('id', data.get('name', data.get('term', '')))}"
            if dedup not in seen:
                seen.add(dedup)
                target_list.append({**data, "score": score, "match": match_type})

        for c in self.ontology.get("concepts", []):
            name = c.get("table_name", c.get("name", ""))
            # 检查表名、别名、映射表、描述
            candidates = [name] + c.get("aliases", []) + c.get("mapped_tables", [])
            desc = c.get("description", "")
            candidates.append(desc)
            
            for cand in candidates:
                if cand and cand.lower() in q_lower:
                    _add(results["concepts"], c, "concept", 1.0, "keyword")
                    break
            else:
                # 分词匹配：问题中的词是否出现在候选中
                q_words = set(re.findall(r'\w+', q_lower))
                cand_words = set(re.findall(r'\w+', ' '.join(c.lower() for c in candidates if c)))
                overlap = q_words & cand_words
                if overlap and len(overlap) >= 1:
                    # 只在有实质性重叠时才添加
                    meaningful = [w for w in overlap if len(w) > 2]
                    if meaningful:
                        _add(results["concepts"], c, "concept", 0.7, "partial")

        for a in self.ontology.get("attributes", []):
            col = a.get("column_name", a.get("name", ""))
            candidates = [col] + a.get("aliases", [])
            for cand in candidates:
                if cand and cand.lower() in q_lower:
                    _add(results["attributes"], a, "attribute", 1.0, "keyword")
                    break

        for t in self.ontology.get("term_dictionary", []):
            term = t.get("term", t.get("name", ""))
            if term and term.lower() in q_lower:
                _add(results["terms"], t, "term", 1.0, "keyword")

        for br in self.ontology.get("business_rules", []):
            name = br.get("name", br.get("description", ""))
            keywords = br.get("keywords", name.split())
            if isinstance(keywords, str):
                keywords = [keywords]
            if any(kw.lower() in q_lower for kw in keywords):
                _add(results["rules"], br, "rule", 0.9, "keyword")

        # ── 路径2: 向量相似度（补充召回）──
        try:
            self._build_index()
            if self._faiss_index is not None and len(self._index_keys) > 0:
                embedder = self._get_embedder()
                q_emb = embedder.encode([question], normalize_embeddings=True).astype(np.float32)
                scores, indices = self._faiss_index.search(q_emb, min(top_k * 3, len(self._index_keys)))

                for score, idx in zip(scores[0], indices[0]):
                    if score < 0.35:
                        continue
                    key = self._index_keys[idx]
                    key_type = key["type"]
                    data = key["data"]
                    dedup_key = f"{key_type}:{data.get('id', data.get('name', str(idx)))}"
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    entry = {**data, "score": float(score), "match": "vector"}
                    if key_type == "concept":
                        results["concepts"].append(entry)
                    elif key_type == "attribute":
                        results["attributes"].append(entry)
                    elif key_type == "term":
                        results["terms"].append(entry)
                    elif key_type == "rule":
                        results["rules"].append(entry)
        except Exception as e:
            logger.warning(f"Vector recall failed: {e}")

        return results

    # ── Step 3: L2 Schema 映射 ──────────────────────────────

    def map_to_schema(self, ontology_results: dict) -> dict:
        """Step 3: Ontology 元素 → Schema 表/列"""
        schema_mapping = self.ontology.get("schema_mapping", {})
        fk_map = {f"{fk['from']}": fk["to"] for fk in schema_mapping.get("foreign_keys", [])}

        tables = set()
        columns = []
        knowledge = []

        # 概念 → 表
        for concept in ontology_results.get("concepts", []):
            table = concept.get("table_name", concept.get("name", ""))
            if table:
                tables.add(table)

        # 属性 → 列
        for attr in ontology_results.get("attributes", []):
            col = attr.get("column_name", attr.get("name", ""))
            tbl = attr.get("table_name", "")
            if col:
                columns.append({"table": tbl, "column": col})
                if tbl:
                    tables.add(tbl)

        # 术语 → 展开
        for term in ontology_results.get("terms", []):
            mapping = term.get("mapping", term.get("mapped_columns", []))
            if isinstance(mapping, list):
                for m in mapping:
                    if "." in m:
                        t, c = m.rsplit(".", 1)
                        tables.add(t)
                        columns.append({"table": t, "column": c})

        # 业务规则 → knowledge
        for rule in ontology_results.get("rules", []):
            knowledge.append(rule.get("sql_condition", rule.get("description", "")))

        return {
            "tables": sorted(tables),
            "columns": columns,
            "knowledge": knowledge,
        }

    # ── Step 4: 元路径约束验证 ───────────────────────────────

    def validate_paths(self, schema_result: dict) -> list[list[str]]:
        """Step 4: 验证表间 JOIN 路径连通性，自动补全中间表"""
        tables = set(schema_result["tables"])

        adj = self._build_full_adjacency()

        # Step 4.1: 对每张已识别表，将其1跳邻居也加入候选
        # 这捕获 LLM 遗漏的 JOIN 中间表
        expanded_tables = set(tables)
        for t in list(tables):
            for neighbor in adj.get(t, []):
                expanded_tables.add(neighbor)

        if len(expanded_tables) <= 1:
            return [list(expanded_tables)]

        # Step 4.2: BFS 找最短路径连接所有原始表
        # 在扩展后的图上找，这样可以发现中间表
        tables_list = list(tables)
        all_paths = []

        connected = {tables_list[0]}
        remaining = set(tables_list[1:])

        while remaining:
            best_path = None
            best_len = float("inf")

            for src in connected:
                for tgt in remaining:
                    path = self._bfs(adj, src, tgt)
                    if path and len(path) < best_len:
                        best_len = len(path)
                        best_path = path

            if best_path is None:
                isolated = min(remaining)
                all_paths.append([isolated])
                connected.add(isolated)
                remaining.discard(isolated)
            else:
                all_paths.append(best_path)
                for node in best_path:
                    connected.add(node)
                    remaining.discard(node)

        return all_paths

    def _build_full_adjacency(self) -> dict:
        """构建全库外键邻接图"""
        adj = {}
        schema_mapping = self.ontology.get("schema_mapping", {})
        fks = schema_mapping.get("foreign_keys", [])
        relations = self.ontology.get("relations", [])

        for fk in fks:
            t_from = fk["from"].split(".")[0]
            t_to = fk["to"].split(".")[0]
            adj.setdefault(t_from, set()).add(t_to)
            adj.setdefault(t_to, set()).add(t_from)

        for r in relations:
            t_from = r.get("from_table", r.get("source", ""))
            t_to = r.get("to_table", r.get("target", ""))
            if t_from and t_to:
                adj.setdefault(t_from, set()).add(t_to)
                adj.setdefault(t_to, set()).add(t_from)

        return adj

    def _bfs(self, adj: dict, start: str, end: str) -> Optional[list[str]]:
        from collections import deque
        queue = deque([(start, [start])])
        visited = {start}
        while queue:
            node, path = queue.popleft()
            if node == end:
                return path
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    # ── Step 5: 最小完备集提取 ──────────────────────────────

    def extract_mcs(self, schema_result: dict, join_paths: list[list[str]]) -> RecallResult:
        """Step 5: 从候选集中提取最小完备集"""
        # 所有必需表 = 问题直接引用 + JOIN 连接表
        all_tables = set()
        for path in join_paths:
            all_tables.update(path)

        # 列去重
        seen_cols = set()
        unique_cols = []
        for col_entry in schema_result["columns"]:
            key = f"{col_entry['table']}.{col_entry['column']}"
            if key not in seen_cols:
                seen_cols.add(key)
                unique_cols.append(col_entry)

        # 移除不在必需表中的列（保留可能有用的）
        mcs_cols = [c for c in unique_cols if c["table"] in all_tables]

        return RecallResult(
            tables=sorted(all_tables),
            columns=mcs_cols,
            join_paths=join_paths,
            knowledge=schema_result.get("knowledge", []),
            confidence=1.0,
        )

    # ── 完整流程 ─────────────────────────────────────────────

    def recall(self, question: str, top_k: int = 20, threshold: float = 0.3) -> RecallResult:
        """完整 5 步联合召回"""
        steps_log = []

        # Step 1: LLM 问题理解
        q_analysis = self.understand_question(question)
        steps_log.append({"step": 1, "name": "问题理解", "source": q_analysis.get("_source", "unknown"),
                          "output": {k: v for k, v in q_analysis.items() if not k.startswith("_")}})

        # Step 2: L1 Ontology 召回
        ont_results = self.recall_ontology(question, top_k, threshold)
        
        # Merge LLM-extracted tables into ontology results
        llm_tables = set(t.lower() for t in q_analysis.get("tables", []))
        ont_tables = set()
        for c in ont_results["concepts"]:
            name = c.get("table_name", c.get("name", "")).lower()
            for mt in c.get("mapped_tables", [name]):
                ont_tables.add(mt.lower())
        
        # Add LLM tables not already in ontology results
        all_concepts = {c.get("table_name", c.get("name", "")).lower(): c 
                        for c in self.ontology.get("concepts", [])}
        for t in llm_tables:
            if t not in ont_tables and t in all_concepts:
                ont_results["concepts"].append({**all_concepts[t], "score": 0.95, "match": "llm"})
            elif t not in ont_tables:
                # LLM found a table not in ontology - add as raw
                ont_results["concepts"].append({"table_name": t, "name": t, "score": 0.9, "match": "llm_raw"})
        
        steps_log.append({
            "step": 2, "name": "L1 Ontology 召回",
            "output": {k: len(v) for k, v in ont_results.items()},
        })

        # Step 3: L2 Schema 映射
        schema_result = self.map_to_schema(ont_results)
        
        # Also add LLM-extracted columns
        for col_name in q_analysis.get("columns", []):
            col_lower = col_name.lower()
            existing_cols = {(c["column"]).lower() for c in schema_result["columns"]}
            if col_lower not in existing_cols:
                # Try to find which table this column belongs to
                for a in self.ontology.get("attributes", []):
                    if a.get("column_name", a.get("name", "")).lower() == col_lower:
                        schema_result["columns"].append({"table": a.get("table_name", ""), "column": col_name})
                        break
        
        steps_log.append({
            "step": 3, "name": "L2 Schema 映射",
            "output": {k: len(v) for k, v in schema_result.items()},
        })

        # Step 4: 元路径约束
        join_paths = self.validate_paths(schema_result)
        steps_log.append({
            "step": 4, "name": "元路径约束",
            "output": {"paths": join_paths},
        })

        # Step 5: 最小完备集提取
        result = self.extract_mcs(schema_result, join_paths)
        result.steps_log = steps_log
        steps_log.append({
            "step": 5, "name": "最小完备集提取",
            "output": {"tables": result.tables, "columns": len(result.columns)},
        })

        return result


def evaluate_recall(result: RecallResult, ground_truth_sql: str) -> dict:
    """评估召回结果 vs ground truth SQL"""
    # 从 SQL 提取表和列
    sql_lower = ground_truth_sql.lower()

    # 提取表
    gt_tables = set(t.lower() for t in re.findall(r'(?:from|join)\s+`?(\w+)`?', sql_lower))

    # 提取列 (alias.column 和 直接引用)
    gt_cols = set()
    for col in re.findall(r'(?:t\d+)\.(\w+)', sql_lower):
        gt_cols.add(col.lower())
    for t, c in re.findall(r'(\w+)\.(\w+)', sql_lower):
        if not re.match(r't\d+$', t):
            gt_cols.add(c.lower())

    # 比对
    result_tables = set(t.lower() for t in result.tables)
    result_cols = set(c["column"].lower() for c in result.columns)

    table_hit = len(gt_tables & result_tables)
    col_hit = len(gt_cols & result_cols)

    return {
        "table_recall": f"{table_hit}/{len(gt_tables)}" if gt_tables else "N/A",
        "table_recall_pct": round(100 * table_hit / len(gt_tables), 1) if gt_tables else None,
        "column_recall": f"{col_hit}/{len(gt_cols)}" if gt_cols else "N/A",
        "column_recall_pct": round(100 * col_hit / len(gt_cols), 1) if gt_cols else None,
        "gt_tables": sorted(gt_tables),
        "result_tables": sorted(result_tables),
        "missed_tables": sorted(gt_tables - result_tables),
    }


if __name__ == "__main__":
    import sys

    db_dir = Path(__file__).parent.parent / "data" / "ontologies"
    data_path = Path(__file__).parent.parent / "data" / "bird_full" / "data" / "train-00000-of-00001-4b532b7deeb3f011.parquet"

    import pandas as pd
    df = pd.read_parquet(data_path)

    # 测试的数据库
    test_dbs = ["car_retails", "public_review_platform", "works_cycles", "mondial_geo"]

    for db in test_dbs:
        ont_path = db_dir / f"{db}.json"
        if not ont_path.exists():
            print(f"⚠️  {db}: ontology not found")
            continue

        engine = OntologyRecall(str(ont_path))
        queries = df[df["db_id"] == db]

        print(f"\n{'='*60}")
        print(f"📊 {db} ({len(queries)} queries)")
        print(f"{'='*60}")

        for _, row in queries.iterrows():
            result = engine.recall(row["question"])
            eval_r = evaluate_recall(result, row["SQL"])
            t_pct = eval_r["table_recall_pct"] or 0
            c_pct = eval_r["column_recall_pct"] or 0
            missed = eval_r["missed_tables"]
            flag = "✅" if t_pct >= 80 else "⚠️"
            print(f"  {flag} Q: {row['question'][:60]:<60s} | 表:{t_pct:>5.0f}% 列:{c_pct:>5.0f}% | MCS:{len(result.tables)}表 {len(result.columns)}列" + (f" | 缺:{missed}" if missed else ""))
