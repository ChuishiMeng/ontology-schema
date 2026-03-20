"""
评估模块
- 召回评估
- 生成评估
- 端到端评估
"""

import json
import sqlite3
from typing import List, Dict, Tuple, Set, Optional
from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict
import numpy as np
from tqdm import tqdm
import sqlglot
from sqlglot.errors import ParseError


# ================== 数据类型 ==================

@dataclass
class EvaluationResult:
    """评估结果"""
    metric: str
    value: float
    std: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None


@dataclass
class TestCase:
    """测试用例"""
    query_id: str
    question: str
    gold_sql: str
    db_id: str
    difficulty: str = "medium"
    query_type: str = ""
    ontology: Dict = None
    business_rules: List[str] = None


# ================== 召回评估 ==================

class RecallEvaluator:
    """召回评估器"""
    
    def __init__(self, k_values: List[int] = [1, 3, 5, 10]):
        self.k_values = k_values
        
    def evaluate(
        self, 
        predictions: List[List[str]], 
        ground_truth: List[List[str]]
    ) -> Dict[str, float]:
        """
        评估召回结果
        
        Args:
            predictions: 每查询的预测召回列表
            ground_truth: 每查询的真实相关列表
            
        Returns:
            指标字典
        """
        assert len(predictions) == len(ground_truth)
        
        results = {}
        
        # Recall@K
        for k in self.k_values:
            recall = self._recall_at_k(predictions, ground_truth, k)
            results[f"recall@{k}"] = recall
            
        # Precision@K
        for k in self.k_values:
            precision = self._precision_at_k(predictions, ground_truth, k)
            results[f"precision@{k}"] = precision
            
        # MRR
        results["mrr"] = self._mrr(predictions, ground_truth)
        
        # NDCG@K
        for k in self.k_values:
            ndcg = self._ndcg_at_k(predictions, ground_truth, k)
            results[f"ndcg@{k}"] = ndcg
            
        return results
    
    def _recall_at_k(self, preds: List[List[str]], gts: List[List[str]], k: int) -> float:
        """Recall@K"""
        total = 0.0
        for pred, gt in zip(preds, gts):
            pred_k = set(pred[:k])
            gt_set = set(gt)
            if len(gt_set) > 0:
                total += len(pred_k & gt_set) / len(gt_set)
        return total / len(preds)
    
    def _precision_at_k(self, preds: List[List[str]], gts: List[List[str]], k: int) -> float:
        """Precision@K"""
        total = 0.0
        for pred, gt in zip(preds, gts):
            pred_k = set(pred[:k])
            gt_set = set(gt)
            total += len(pred_k & gt_set) / k
        return total / len(preds)
    
    def _mrr(self, preds: List[List[str]], gts: List[List[str]]) -> float:
        """MRR"""
        total = 0.0
        for pred, gt in zip(preds, gts):
            gt_set = set(gt)
            for i, p in enumerate(pred, 1):
                if p in gt_set:
                    total += 1.0 / i
                    break
        return total / len(preds)
    
    def _ndcg_at_k(self, preds: List[List[str]], gts: List[List[str]], k: int) -> float:
        """NDCG@K"""
        total = 0.0
        for pred, gt in zip(preds, gts):
            gt_set = set(gt)
            dcg = 0.0
            for i, p in enumerate(pred[:k], 1):
                if p in gt_set:
                    dcg += 1.0 / np.log2(i + 1)
                    
            # IDCG
            idcg = sum(1.0 / np.log2(i + 1) for i in range(1, min(len(gt_set), k) + 1))
            
            total += dcg / idcg if idcg > 0 else 0.0
            
        return total / len(preds)


# ================== SQL评估 ==================

class SQLEvaluator:
    """SQL评估器"""
    
    def __init__(self, db_paths: Dict[str, str]):
        """
        初始化
        
        Args:
            db_paths: db_id -> sqlite路径
        """
        self.db_paths = db_paths
        self.dbs = {}
        
    def load_db(self, db_id: str):
        """加载数据库"""
        if db_id not in self.dbs:
            db_path = self.db_paths.get(db_id)
            if db_path and Path(db_path).exists():
                self.dbs[db_id] = sqlite3.connect(db_path)
        return self.dbs.get(db_id)
    
    def evaluate(
        self, 
        predictions: List[str], 
        ground_truths: List[str],
        db_ids: List[str]
    ) -> Dict[str, float]:
        """
        评估SQL生成结果
        
        Returns:
            包含 valid_rate, exec_acc, exact_match 等指标
        """
        assert len(predictions) == len(ground_truths) == len(db_ids)
        
        results = {
            "valid_rate": 0.0,
            "exec_acc": 0.0,
            "exact_match": 0.0,
            "syntax_error": 0,
            "execution_error": 0,
            "wrong_result": 0
        }
        
        valid_count = 0
        exec_correct = 0
        exact_match_count = 0
        
        for pred, gt, db_id in zip(predictions, ground_truths, db_ids):
            # 1. 语法验证
            is_valid, error = self.validate_syntax(pred)
            if not is_valid:
                results["syntax_error"] += 1
                continue
            valid_count += 1
            
            # 2. 执行验证
            exec_result, error = self.execute_sql(pred, db_id)
            if error:
                results["execution_error"] += 1
                continue
                
            # 3. 与Gold对比
            gold_result, gold_error = self.execute_sql(gt, db_id)
            if gold_error:
                continue
                
            # 执行正确
            if self.compare_results(exec_result, gold_result):
                exec_correct += 1
                
            # 精确匹配
            if pred.strip() == gt.strip():
                exact_match_count += 1
                
        total = len(predictions)
        results["valid_rate"] = valid_count / total if total > 0 else 0
        results["exec_acc"] = exec_correct / total if total > 0 else 0
        results["exact_match"] = exact_match_count / total if total > 0 else 0
        
        return results
    
    def validate_syntax(self, sql: str) -> Tuple[bool, Optional[str]]:
        """验证SQL语法"""
        try:
            sqlglot.parse(sql)
            return True, None
        except ParseError as e:
            return False, str(e)
    
    def execute_sql(self, sql: str, db_id: str) -> Tuple[Optional[List], Optional[str]]:
        """执行SQL"""
        conn = self.load_db(db_id)
        if not conn:
            return None, f"Database {db_id} not found"
            
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            results = cursor.fetchall()
            return results, None
        except Exception as e:
            return None, str(e)
    
    def compare_results(self, result1: List, result2: List) -> bool:
        """比较执行结果"""
        if result1 is None or result2 is None:
            return False
        return result1 == result2


# ================== 端到端评估 ==================

class EndToEndEvaluator:
    """端到端评估器"""
    
    def __init__(self, recall_evaluator: RecallEvaluator, sql_evaluator: SQLEvaluator):
        self.recall_evaluator = recall_evaluator
        self.sql_evaluator = sql_evaluator
        
    def evaluate(
        self,
        recall_preds: List[List[str]],
        recall_gts: List[List[str]],
        sql_preds: List[str],
        sql_gts: List[str],
        db_ids: List[str]
    ) -> Dict[str, float]:
        """
        端到端评估
        
        成功标准:
        1. 召回相关表/列 (Recall@3 >= 0.8)
        2. 生成有效SQL
        3. SQL执行无错误
        4. 返回非空结果
        """
        assert len(recall_preds) == len(recall_gts) == len(sql_preds) == len(sql_gts) == len(db_ids)
        
        # 召回评估
        recall_results = self.recall_evaluator.evaluate(recall_preds, recall_gts)
        
        # SQL评估
        sql_results = self.sql_evaluator.evaluate(sql_preds, sql_gts, db_ids)
        
        # 端到端成功率
        success_count = 0
        total = len(recall_preds)
        
        for i in range(total):
            # 1. 召回成功
            recall_at_3 = set(recall_preds[i][:3]) & set(recall_gts[i])
            recall_ok = len(recall_at_3) / len(set(recall_gts[i])) >= 0.8 if recall_gts[i] else True
            
            # 2. SQL有效且正确
            valid_sql, _ = self.sql_evaluator.validate_syntax(sql_preds[i])
            if not valid_sql:
                continue
                
            exec_result, exec_error = self.sql_evaluator.execute_sql(sql_preds[i], db_ids[i])
            if exec_error or exec_result is None:
                continue
                
            gold_result, _ = self.sql_evaluator.execute_sql(sql_gts[i], db_ids[i])
            result_match = self.sql_evaluator.compare_results(exec_result, gold_result)
            
            if recall_ok and result_match:
                success_count += 1
                
        results = {**recall_results, **sql_results}
        results["task_completion_rate"] = success_count / total if total > 0 else 0
        
        return results


# ================== 统计分析 ==================

def compute_confidence_interval(values: List[float], confidence: float = 0.95) -> Tuple[float, float]:
    """计算置信区间"""
    n = len(values)
    mean = np.mean(values)
    std = np.std(values, ddof=1)
    
    # t分布临界值
    from scipy import stats
    t_crit = stats.t.ppf((1 + confidence) / 2, n - 1)
    
    margin = t_crit * std / np.sqrt(n)
    return mean - margin, mean + margin


def paired_t_test(values1: List[float], values2: List[float]) -> Tuple[float, float]:
    """配对t检验"""
    from scipy import stats
    
    diff = [a - b for a, b in zip(values1, values2)]
    n = len(diff)
    mean_diff = np.mean(diff)
    std_diff = np.std(diff, ddof=1)
    
    t_stat = mean_diff / (std_diff / np.sqrt(n))
    p_value = 2 * (1 - stats.t.cdf(abs(t_stat), n - 1))
    
    return t_stat, p_value


# ================== 评估流程 ==================

class Evaluator:
    """综合评估器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.recall_evaluator = RecallEvaluator()
        self.sql_evaluator = SQLEvaluator(config.get("db_paths", {}))
        self.e2e_evaluator = EndToEndEvaluator(
            self.recall_evaluator, 
            self.sql_evaluator
        )
        
    def load_test_data(self, test_file: str) -> List[TestCase]:
        """加载测试数据"""
        test_cases = []
        with open(test_file, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                test_cases.append(TestCase(**data))
        return test_cases
    
    def run_recall_evaluation(
        self, 
        predictions: List[List[str]], 
        ground_truths: List[List[str]]
    ) -> Dict[str, float]:
        """运行召回评估"""
        return self.recall_evaluator.evaluate(predictions, ground_truths)
    
    def run_sql_evaluation(
        self,
        predictions: List[str],
        ground_truths: List[str],
        db_ids: List[str]
    ) -> Dict[str, float]:
        """运行SQL评估"""
        return self.sql_evaluator.evaluate(predictions, ground_truths, db_ids)
    
    def run_e2e_evaluation(
        self,
        recall_preds: List[List[str]],
        recall_gts: List[List[str]],
        sql_preds: List[str],
        sql_gts: List[str],
        db_ids: List[str]
    ) -> Dict[str, float]:
        """运行端到端评估"""
        return self.e2e_evaluator.evaluate(
            recall_preds, recall_gts, sql_preds, sql_gts, db_ids
        )
    
    def generate_report(self, results: Dict[str, float]) -> str:
        """生成评估报告"""
        report = "# 评估报告\n\n"
        
        report += "## 召回评估\n"
        for metric in ["recall@1", "recall@3", "recall@5", "mrr", "ndcg@5"]:
            if metric in results:
                report += f"- {metric}: {results[metric]:.4f}\n"
                
        report += "\n## SQL生成评估\n"
        for metric in ["valid_rate", "exec_acc", "exact_match"]:
            if metric in results:
                report += f"- {metric}: {results[metric]:.4f}\n"
                
        report += "\n## 端到端评估\n"
        if "task_completion_rate" in results:
            report += f"- Task Completion Rate: {results['task_completion_rate']:.4f}\n"
            
        return report


# ================== 主入口 ==================

if __name__ == "__main__":
    # 示例使用
    import tempfile
    
    # 创建临时数据库
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    cursor.execute("INSERT INTO customers VALUES (1, 'Alice'), (2, 'Bob')")
    conn.commit()
    conn.close()
    
    # 评估器
    config = {"db_paths": {"test": db_path}}
    evaluator = Evaluator(config)
    
    # 测试召回评估
    preds = [["table1", "table2"], ["table1"]]
    gts = [["table1", "table3"], ["table1", "table2"]]
    
    results = evaluator.run_recall_evaluation(preds, gts)
    print("Recall Results:", results)
    
    # 测试SQL评估
    sql_preds = ["SELECT * FROM customers", "SELECT name FROM customers"]
    sql_gts = ["SELECT * FROM customers", "SELECT name FROM customers"]
    db_ids = ["test", "test"]
    
    results = evaluator.run_sql_evaluation(sql_preds, sql_gts, db_ids)
    print("SQL Results:", results)
    
    # 清理
    import os
    os.unlink(db_path)
