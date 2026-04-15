"""Ontology Generator - LLM 增强 Ontology"""

import json
from typing import Dict, Any, Optional


class OntologyGenerator:
    """使用 LLM 增强 Ontology"""

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM API 客户端（如 OpenAI, Qwen 等）
        """
        self.llm = llm_client
        self.schema_analyzer = None  # 注入或内部创建

    def generate_ontology(self, ddl: str,
                          business_docs: Optional[str] = None) -> Dict[str, Any]:
        """
        完整 Ontology 生成流程

        Args:
            ddl: 数据库 DDL
            business_docs: 业务文档（可选）

        Returns:
            Ontology 字典
        """
        from .schema_analyzer import SchemaAnalyzer

        # Step 1: Schema 分析
        analyzer = SchemaAnalyzer()
        schema_info = analyzer.parse_ddl(ddl)
        ontology_draft = analyzer.to_ontology_draft(schema_info)

        # Step 2: 业务文档增强（如果有）
        if business_docs and self.llm:
            ontology_draft = self._enhance_with_llm(ontology_draft, business_docs)

        return ontology_draft

    def _enhance_with_llm(self, ontology: Dict[str, Any],
                          docs: str) -> Dict[str, Any]:
        """
        使用 LLM 从业务文档提取术语和规则

        Args:
            ontology: Ontology 草案
            docs: 业务文档文本

        Returns:
            增强后的 Ontology
        """
        prompt = self._build_enhancement_prompt(ontology, docs)

        # 调用 LLM（假设 llm_client 有 chat 方法）
        response = self.llm.chat(prompt)

        # 解析 LLM 返回的术语和规则
        enhancements = self._parse_llm_response(response)

        # 合并到 Ontology
        ontology['terms'].extend(enhancements.get('terms', []))
        ontology['rules'].extend(enhancements.get('rules', []))

        return ontology

    def _build_enhancement_prompt(self, ontology: Dict, docs: str) -> str:
        """构建 LLM 提示词"""
        concepts_str = json.dumps(ontology['concepts'], indent=2)

        return f"""
分析以下业务文档，提取与数据库相关的业务术语和计算规则。

当前 Ontology 概念：
{concepts_str}

业务文档：
{docs}

请提取：
1. 业务术语：如"高价值客户"、"金牌会员"等，及其定义
2. 计算规则：如"流失率 = 30天未登录用户数 / 总用户数"
3. 术语到数据库字段的映射建议

以 JSON 格式返回：
{
  "terms": [
    {"name": "术语名", "definition": "定义", "mapped_to": "概念/属性"}
  ],
  "rules": [
    {"name": "规则名", "formula": "计算公式", "description": "描述"}
  ]
}
"""

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 返回"""
        try:
            # 尝试提取 JSON
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except:
            pass
        return {'terms': [], 'rules': []}