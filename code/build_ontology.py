#!/usr/bin/env python3
"""
Ontology 半自动构建器 v2
从 BIRD 数据集的 DDL + Knowledge Evidence 生成 Ontology JSON

用法:
    cd ~/agent-work/research/ontology-schema/code
    .venv/bin/python3 build_ontology.py --db_id car_retails --output ../data/ontologies/
    .venv/bin/python3 build_ontology.py --top 5 --output ../data/ontologies/
    .venv/bin/python3 build_ontology.py --all --output ../data/ontologies/
"""

import json
import os
import re
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional


def parse_ddl(ddl_text: str) -> Dict:
    """解析 DDL 文本，提取表、列、外键。用平衡括号匹配 CREATE TABLE body。"""
    tables = {}
    foreign_keys = []

    # Normalize: collapse newlines
    ddl_norm = re.sub(r'\n\s*', ' ', ddl_text)

    # Find CREATE TABLE statements using balanced parentheses
    create_re = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\[]?(\w+)[`"\]]?\s*\(',
        re.IGNORECASE
    )

    for m in create_re.finditer(ddl_norm):
        table_name = m.group(1)
        start = m.end()
        # Find matching closing paren
        depth = 1
        pos = start
        while pos < len(ddl_norm) and depth > 0:
            if ddl_norm[pos] == '(':
                depth += 1
            elif ddl_norm[pos] == ')':
                depth -= 1
            pos += 1
        body = ddl_norm[start:pos - 1]

        columns = []
        primary_key = []

        # Split body by commas (careful with nested parens)
        parts = _split_body(body)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # FOREIGN KEY
            if re.match(r'(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY', part, re.IGNORECASE):
                fk_m = re.search(
                    r'FOREIGN\s+KEY\s*\(\s*(\w+)\s*\)\s*REFERENCES\s*(\w+)\s*\(\s*(\w+)\s*\)',
                    part, re.IGNORECASE
                )
                if fk_m:
                    foreign_keys.append({
                        "from_table": table_name,
                        "from_column": fk_m.group(1),
                        "to_table": fk_m.group(2),
                        "to_column": fk_m.group(3)
                    })
                continue

            # PRIMARY KEY (standalone)
            pk_m = re.match(r'PRIMARY\s+KEY\s*\((.+?)\)', part, re.IGNORECASE)
            if pk_m:
                primary_key = [c.strip().strip('"').strip('`') for c in pk_m.group(1).split(',')]
                continue

            # Skip other constraints
            if re.match(r'(?:CONSTRAINT|UNIQUE|CHECK|INDEX|KEY)\b', part, re.IGNORECASE):
                continue

            # Column definition: name type [constraints...]
            col_m = re.match(r'[`"\[]?(\w+)[`"\]]?\s+(\S+)', part, re.IGNORECASE)
            if col_m:
                col_name = col_m.group(1)
                col_type = col_m.group(2)
                if col_name.upper() in ('PRIMARY', 'FOREIGN', 'CONSTRAINT', 'UNIQUE', 'CHECK'):
                    continue
                columns.append({
                    "name": col_name,
                    "type": col_type,
                    "is_primary_key": 'primary key' in part.lower() or col_name in primary_key,
                    "nullable": 'not null' not in part.lower()
                })

        tables[table_name] = {"columns": columns, "primary_key": primary_key}

    return {"tables": tables, "foreign_keys": foreign_keys}


def _split_body(body: str) -> List[str]:
    """Split CREATE TABLE body by commas, respecting parenthesized expressions."""
    parts = []
    depth = 0
    current = []
    for ch in body:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
            continue
        current.append(ch)
    if current:
        parts.append(''.join(current))
    return parts


def parse_evidence(evidence_text: str) -> List[Dict]:
    """解析 BIRD knowledge evidence，提取术语→Schema映射"""
    mappings = []
    if not evidence_text:
        return mappings

    for match in re.finditer(r'(.+?)\s+refers?\s+to\s+(.+?)(?:;|$)', evidence_text, re.IGNORECASE):
        term = match.group(1).strip()
        definition = match.group(2).strip()
        mappings.append({"term": term, "definition": definition, "type": _classify(term, definition)})

    if not mappings:
        for match in re.finditer(r'(.+?)\s*=\s*(.+?)(?:;|$)', evidence_text):
            term, defn = match.group(1).strip(), match.group(2).strip()
            if len(term) > 1 and len(defn) > 1:
                mappings.append({"term": term, "definition": defn, "type": _classify(term, defn)})

    if not mappings and evidence_text.strip():
        mappings.append({"term": evidence_text.strip(), "definition": "", "type": "context"})

    return mappings


def _classify(term: str, definition: str) -> str:
    if re.search(r'[<>=!]+|COUNT|SUM|AVG|MAX|MIN|BETWEEN|LIKE|IN\s*\(', definition, re.IGNORECASE):
        return "condition"
    if '.' in definition:
        return "column_ref"
    if ',' in definition:
        return "multi_column"
    if re.match(r'^\w+$', definition.strip()):
        return "alias"
    return "semantic"


class OntologyBuilder:
    def __init__(self, db_id: str):
        self.db_id = db_id
        self.concepts = []
        self.attributes = []
        self.relations = []
        self.business_rules = []
        self.term_dictionary = []
        self.schema_mapping = {"tables": {}, "foreign_keys": []}
        self._counter = {"c": 0, "a": 0, "r": 0, "br": 0, "td": 0}

    def _next_id(self, prefix: str) -> str:
        self._counter[prefix] += 1
        return f"{prefix}_{self._counter[prefix]:03d}"

    def build_from_ddl(self, parsed: Dict):
        for table_name, info in parsed["tables"].items():
            cid = self._next_id("c")
            human = table_name.replace("_", " ").title()
            self.concepts.append({
                "id": cid, "name": human, "name_en": human,
                "type": "entity", "description": f"数据表: {table_name}",
                "aliases": [table_name, human.lower()],
                "mapped_tables": [table_name], "confidence": 1.0
            })
            for col in info["columns"]:
                aid = self._next_id("a")
                col_human = col["name"].replace("_", " ")
                self.attributes.append({
                    "id": aid, "concept_id": cid,
                    "name": col_human, "name_en": col_human,
                    "description": f"{table_name}.{col['name']} ({col['type']})",
                    "aliases": [col["name"], col_human],
                    "mapped_columns": [f"{table_name}.{col['name']}"],
                    "value_mapping": {}, "data_type": col["type"],
                    "is_primary_key": col["is_primary_key"], "confidence": 1.0
                })
            self.schema_mapping["tables"][table_name] = {
                "concept_id": cid,
                "description": f"表: {table_name}",
                "key_columns": [c["name"] for c in info["columns"] if c["is_primary_key"]]
            }

        for fk in parsed["foreign_keys"]:
            src = self._find_concept(fk["from_table"])
            tgt = self._find_concept(fk["to_table"])
            if src and tgt:
                rid = self._next_id("r")
                self.relations.append({
                    "id": rid,
                    "name": f"{src['name']} → {tgt['name']}",
                    "source_concept_id": src["id"],
                    "target_concept_id": tgt["id"],
                    "description": f"FK: {fk['from_table']}.{fk['from_column']} → {fk['to_table']}.{fk['to_column']}",
                    "mapped_joins": [f"{fk['from_table']}.{fk['from_column']} = {fk['to_table']}.{fk['to_column']}"],
                    "confidence": 1.0
                })
                self.schema_mapping["foreign_keys"].append({
                    "from": f"{fk['from_table']}.{fk['from_column']}",
                    "to": f"{fk['to_table']}.{fk['to_column']}",
                    "relation_id": rid
                })

    def build_from_evidence(self, evidence_mappings: List[Dict]):
        for ev in evidence_mappings:
            if ev["type"] == "condition":
                self.business_rules.append({
                    "id": self._next_id("br"),
                    "name": ev["term"],
                    "pattern": re.escape(ev["term"]),
                    "sql_template": ev["definition"],
                    "description": f"Evidence: {ev['term']} → {ev['definition']}",
                    "source": "knowledge_evidence", "confidence": 0.9
                })
            else:
                self.term_dictionary.append({
                    "id": self._next_id("td"),
                    "term": ev["term"],
                    "definition": ev["definition"],
                    "sql_expression": ev["definition"] if ev["type"] in ("condition", "alias", "column_ref") else "",
                    "mapped_concept_ids": self._find_relevant(ev["term"] + " " + ev["definition"]),
                    "source": "knowledge_evidence"
                })

    def _find_concept(self, table_name: str) -> Optional[Dict]:
        for c in self.concepts:
            if table_name in c.get("mapped_tables", []):
                return c
        return None

    def _find_relevant(self, text: str) -> List[str]:
        text_lower = text.lower()
        return [c["id"] for c in self.concepts
                if any(a.lower() in text_lower for a in c.get("aliases", []))]

    def to_dict(self) -> Dict:
        return {
            "_meta": {
                "version": "1.0",
                "db_id": self.db_id,
                "created_by": "auto",
                "stats": {
                    "concepts": len(self.concepts),
                    "attributes": len(self.attributes),
                    "relations": len(self.relations),
                    "business_rules": len(self.business_rules),
                    "term_dictionary": len(self.term_dictionary)
                }
            },
            "concepts": self.concepts,
            "attributes": self.attributes,
            "relations": self.relations,
            "business_rules": self.business_rules,
            "term_dictionary": self.term_dictionary,
            "schema_mapping": self.schema_mapping
        }


def load_bird_data(data_dir: str) -> Dict:
    import pyarrow.parquet as pq
    parquet = Path(data_dir) / "bird_full" / "data" / "train-00000-of-00001-4b532b7deeb3f011.parquet"
    table = pq.read_table(str(parquet))
    data = table.to_pydict()
    db_data = defaultdict(lambda: {"queries": [], "evidences": [], "schemas": [], "sqls": []})
    for i in range(len(data["db_id"])):
        db_id = data["db_id"][i]
        db_data[db_id]["queries"].append(data["question"][i])
        db_data[db_id]["evidences"].append(data["evidence"][i])
        db_data[db_id]["schemas"].append(data["schema"][i])
        db_data[db_id]["sqls"].append(data["SQL"][i])
    return dict(db_data)


def build_ontology_for_db(db_id: str, db_data: Dict) -> Dict:
    builder = OntologyBuilder(db_id)
    parsed = parse_ddl(db_data["schemas"][0])
    builder.build_from_ddl(parsed)

    seen = set()
    unique = []
    for ev in db_data["evidences"]:
        for m in parse_evidence(ev):
            if m["term"] not in seen:
                seen.add(m["term"])
                unique.append(m)
    builder.build_from_evidence(unique)
    return builder.to_dict()


def main():
    parser = argparse.ArgumentParser(description="BIRD Ontology Builder")
    parser.add_argument("--db_id", type=str, help="指定数据库ID")
    parser.add_argument("--all", action="store_true", help="构建所有数据库")
    parser.add_argument("--top", type=int, default=5, help="构建前N个数据库")
    parser.add_argument("--output", type=str, default="../data/ontologies/")
    parser.add_argument("--data_dir", type=str, default="../data/")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("📂 加载 BIRD 数据...")
    db_data = load_bird_data(args.data_dir)
    print(f"✅ 共 {len(db_data)} 个数据库")

    if args.db_id:
        targets = [args.db_id] if args.db_id in db_data else []
        if not targets:
            print(f"❌ {args.db_id} 不存在")
            return
    elif args.all:
        targets = sorted(db_data.keys())
    else:
        targets = sorted(db_data.keys(),
                         key=lambda x: len(db_data[x]["queries"]), reverse=True)[:args.top]

    print(f"\n🔨 构建 {len(targets)} 个 Ontology...\n")
    for db_id in targets:
        ont = build_ontology_for_db(db_id, db_data[db_id])
        out = output_dir / f"{db_id}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(ont, f, ensure_ascii=False, indent=2)
        s = ont["_meta"]["stats"]
        print(f"  ✅ {db_id}: {s['concepts']}C {s['attributes']}A {s['relations']}R "
              f"{s['business_rules']}BR {s['term_dictionary']}TD")

    print(f"\n✅ 完成！输出: {output_dir}")


if __name__ == "__main__":
    main()
