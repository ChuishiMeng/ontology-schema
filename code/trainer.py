"""
模型训练模块
- 对比学习训练
- 编码器训练
- 重排序模型训练
"""

import json
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass
import numpy as np
from tqdm import tqdm
import random


# ================== 配置 ==================

@dataclass
class TrainingConfig:
    """训练配置"""
    # 模型配置
    embedding_dim: int = 256
    hidden_dim: int = 256
    num_layers: int = 3
    dropout: float = 0.1
    
    # 训练配置
    batch_size: int = 32
    learning_rate: float = 1e-4
    weight_decay: float = 1e-5
    num_epochs: int = 100
    warmup_steps: int = 1000
    
    # 对比学习配置
    temperature: float = 0.07
    margin: float = 0.5
    
    # 其他
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    save_dir: str = "./checkpoints"
    log_interval: int = 100


# ================== 数据集 ==================

class AlignmentDataset(Dataset):
    """对齐数据集"""
    
    def __init__(
        self,
        alignments: List[Dict],
        ontology_embeddings: Dict[str, np.ndarray],
        schema_embeddings: Dict[str, np.ndarray]
    ):
        self.alignments = alignments
        self.ontology_embeddings = ontology_embeddings
        self.schema_embeddings = schema_embeddings
        
    def __len__(self):
        return len(self.alignments)
    
    def __getitem__(self, idx):
        alignment = self.alignments[idx]
        
        ont_id = alignment["ontology_id"]
        schema_id = alignment["schema_id"]
        
        ont_emb = self.ontology_embeddings.get(ont_id)
        schema_emb = self.schema_embeddings.get(schema_id)
        
        if ont_emb is None or schema_emb is None:
            # 返回零向量作为fallback
            ont_emb = np.zeros(256)
            schema_emb = np.zeros(256)
        
        return {
            "ont_id": ont_id,
            "schema_id": schema_id,
            "ont_embedding": torch.from_numpy(ont_emb).float(),
            "schema_embedding": torch.from_numpy(schema_emb).float(),
            "label": 1.0 if alignment.get("confidence", 1.0) > 0.5 else 0.0
        }


class ContrastiveDataset(Dataset):
    """对比学习数据集"""
    
    def __init__(
        self,
        ontology_data: List[Tuple[str, str]],  # (id, text)
        schema_data: List[Tuple[str, str]],     # (id, text)
        alignments: List[Tuple[str, str]]       # (ont_id, schema_id) positive pairs
    ):
        self.ontology_data = ontology_data
        self.schema_data = schema_data
        self.alignments = alignments
        
        # 构建正样本映射
        self.positive_map: Dict[str, Set[str]] = {}
        for ont_id, schema_id in alignments:
            if ont_id not in self.positive_map:
                self.positive_map[ont_id] = set()
            self.positive_map[ont_id].add(schema_id)
            
    def __len__(self):
        return len(self.alignments) * 2  # 两倍数据以平衡正负样本
        
    def __getitem__(self, idx):
        is_ontology = idx % 2 == 0
        
        if is_ontology:
            # 从Ontology侧采样
            ont_idx = idx // 2 % len(self.ontology_data)
            ont_id, ont_text = self.ontology_data[ont_idx]
            
            # 正样本
            pos_schema_ids = list(self.positive_map.get(ont_id, set()))
            if pos_schema_ids:
                pos_schema_id = random.choice(pos_schema_ids)
                pos_idx = next(i for i, (sid, _) in enumerate(self.schema_data) if sid == pos_schema_id)
                _, pos_text = self.schema_data[pos_idx]
            else:
                pos_text = ""
                
            # 负样本
            neg_idx = random.randint(0, len(self.schema_data) - 1)
            _, neg_text = self.schema_data[neg_idx]
            
            return {
                "anchor_text": ont_text,
                "positive_text": pos_text,
                "negative_text": neg_text,
                "anchor_type": "ontology"
            }
        else:
            # 从Schema侧采样
            schema_idx = idx // 2 % len(self.schema_data)
            schema_id, schema_text = self.schema_data[schema_idx]
            
            # 正样本
            if schema_id in self.positive_map:
                pos_ont_ids = list(self.positive_map[schema_id])
                pos_ont_id = random.choice(pos_ont_ids)
                pos_idx = next(i for i, (oid, _) in enumerate(self.ontology_data) if oid == pos_ont_id)
                _, pos_text = self.ontology_data[pos_idx]
            else:
                pos_text = ""
                
            # 负样本
            neg_idx = random.randint(0, len(self.ontology_data) - 1)
            _, neg_text = self.ontology_data[neg_idx]
            
            return {
                "anchor_text": schema_text,
                "positive_text": pos_text,
                "negative_text": neg_text,
                "anchor_type": "schema"
            }


# ================== 模型 ==================

class AlignmentEncoder(nn.Module):
    """对齐编码器"""
    
    def __init__(self, config: TrainingConfig):
        super().__init__()
        self.config = config
        
        # 共享编码层
        self.encoder = nn.Sequential(
            nn.Linear(config.embedding_dim, config.hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim, config.hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout)
        )
        
    def forward(self, x):
        return self.encoder(x)


class ContrastiveLoss(nn.Module):
    """对比学习损失"""
    
    def __init__(self, temperature: float = 0.07):
        super().__init__()
        self.temperature = temperature
        
    def forward(self, anchor, positive, negative):
        # 归一化
        anchor = F.normalize(anchor, dim=-1)
        positive = F.normalize(positive, dim=-1)
        negative = F.normalize(negative, dim=-1)
        
        # 计算相似度
        pos_sim = torch.sum(anchor * positive, dim=-1) / self.temperature
        neg_sim = torch.sum(anchor * negative, dim=-1) / self.temperature
        
        # 计算损失
        loss = -torch.logsumexp(torch.stack([pos_sim, neg_sim]), dim=0)
        
        return loss.mean()


class AlignmentLoss(nn.Module):
    """对齐损失 - 结合对比学习和分类"""
    
    def __init__(self, config: TrainingConfig):
        super().__init__()
        self.config = config
        
        self.contrastive_loss = ContrastiveLoss(config.temperature)
        
        # 分类头
        self.classifier = nn.Sequential(
            nn.Linear(config.hidden_dim * 2, config.hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim, 1)
        )
        
    def forward(self, ont_emb, schema_emb, labels=None):
        # 对比损失
        pos_sim = F.cosine_similarity(ont_emb, schema_emb, dim=-1)
        neg_sim = torch.randn_like(pos_sim)  # 简化的负样本
        
        cont_loss = self.contrastive_loss(ont_emb, schema_emb, schema_emb.mean(dim=0, keepdim=True).expand_as(schema_emb))
        
        # 分类损失
        combined = torch.cat([ont_emb, schema_emb], dim=-1)
        logits = self.classifier(combined)
        
        if labels is not None:
            cls_loss = F.binary_cross_entropy_with_logits(
                logits.squeeze(-1), 
                labels
            )
            total_loss = cont_loss + cls_loss
        else:
            total_loss = cont_loss
            
        return total_loss, cont_loss, cls_loss if labels is not None else None


# ================== 训练器 ==================

class Trainer:
    """训练器"""
    
    def __init__(
        self,
        model: nn.Module,
        config: TrainingConfig,
        train_dataset: Dataset,
        val_dataset: Dataset = None
    ):
        self.model = model
        self.config = config
        self.train_dataset = train_dataset
        self.val_dataset = val_dataset
        
        # 设备
        self.device = torch.device(config.device)
        self.model.to(self.device)
        
        # 优化器
        self.optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay
        )
        
        # 学习率调度器
        self.scheduler = torch.optim.lr_scheduler.LinearLR(
            self.optimizer,
            start_factor=0.1,
            end_factor=1.0,
            total_iters=config.warmup_steps
        )
        
        # 损失函数
        self.criterion = AlignmentLoss(config)
        
        # 检查点目录
        self.save_dir = Path(config.save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
    def train_epoch(self, dataloader: DataLoader) -> Dict[str, float]:
        """训练一个epoch"""
        self.model.train()
        total_loss = 0
        total_cont_loss = 0
        total_cls_loss = 0
        num_batches = 0
        
        for batch in tqdm(dataloader, desc="Training"):
            # 移动到设备
            ont_emb = batch["ont_embedding"].to(self.device)
            schema_emb = batch["schema_embedding"].to(self.device)
            labels = batch["label"].to(self.device)
            
            # 前向传播
            self.optimizer.zero_grad()
            
            ont_enc = self.model(ont_emb)
            schema_enc = self.model(schema_emb)
            
            loss, cont_loss, cls_loss = self.criterion(
                ont_enc, schema_enc, labels
            )
            
            # 反向传播
            loss.backward()
            self.optimizer.step()
            self.scheduler.step()
            
            total_loss += loss.item()
            total_cont_loss += cont_loss.item()
            if cls_loss is not None:
                total_cls_loss += cls_loss.item()
            num_batches += 1
            
        return {
            "loss": total_loss / num_batches,
            "contrastive_loss": total_cont_loss / num_batches,
            "classification_loss": total_cls_loss / num_batches if num_batches > 0 else 0
        }
    
    @torch.no_grad()
    def evaluate(self, dataloader: DataLoader) -> Dict[str, float]:
        """评估"""
        self.model.eval()
        total_loss = 0
        correct = 0
        total = 0
        
        for batch in tqdm(dataloader, desc="Evaluating"):
            ont_emb = batch["ont_embedding"].to(self.device)
            schema_emb = batch["schema_embedding"].to(self.device)
            labels = batch["label"].to(self.device)
            
            ont_enc = self.model(ont_emb)
            schema_enc = self.model(schema_emb)
            
            # 计算对齐分数
            scores = F.cosine_similarity(ont_enc, schema_enc, dim=-1)
            preds = (scores > 0.5).float()
            
            correct += (preds == labels).sum().item()
            total += labels.size(0)
            
        accuracy = correct / total if total > 0 else 0
        
        return {"accuracy": accuracy}
    
    def train(self, num_epochs: int = None):
        """训练"""
        num_epochs = num_epochs or self.config.num_epochs
        
        # 创建DataLoader
        train_loader = DataLoader(
            self.train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True,
            num_workers=0
        )
        
        val_loader = None
        if self.val_dataset:
            val_loader = DataLoader(
                self.val_dataset,
                batch_size=self.config.batch_size,
                shuffle=False,
                num_workers=0
            )
        
        best_val_acc = 0
        
        for epoch in range(num_epochs):
            # 训练
            train_metrics = self.train_epoch(train_loader)
            
            print(f"Epoch {epoch+1}/{num_epochs}")
            print(f"  Train Loss: {train_metrics['loss']:.4f}")
            print(f"  Train Cont Loss: {train_metrics['contrastive_loss']:.4f}")
            
            # 验证
            if val_loader:
                val_metrics = self.evaluate(val_loader)
                print(f"  Val Accuracy: {val_metrics['accuracy']:.4f}")
                
                # 保存最佳模型
                if val_metrics['accuracy'] > best_val_acc:
                    best_val_acc = val_metrics['accuracy']
                    self.save_checkpoint("best_model.pt")
                    
            # 定期保存
            if (epoch + 1) % 10 == 0:
                self.save_checkpoint(f"checkpoint_epoch_{epoch+1}.pt")
                
        return best_val_acc
    
    def save_checkpoint(self, filename: str):
        """保存检查点"""
        path = self.save_dir / filename
        torch.save({
            "model_state_dict": self.model.state_dict(),
            "config": self.config
        }, path)
        print(f"  Saved checkpoint: {path}")
        
    def load_checkpoint(self, path: str):
        """加载检查点"""
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        print(f"Loaded checkpoint: {path}")


# ================== 对齐训练流程 ==================

def train_alignment_model(
    train_alignments: List[Dict],
    ontology_texts: Dict[str, str],
    schema_texts: Dict[str, str],
    embedding_model,  # sentence-transformers模型
    config: TrainingConfig
) -> AlignmentEncoder:
    """
    训练对齐模型
    
    Args:
        train_alignments: 训练对齐数据
        ontology_texts: Ontology文本 {id: text}
        schema_texts: Schema文本 {id: text}
        embedding_model: 句子嵌入模型
        config: 训练配置
        
    Returns:
        训练好的编码器
    """
    # 1. 编码所有文本
    print("Encoding texts...")
    ont_ids = list(ontology_texts.keys())
    ont_texts = [ontology_texts[id] for id in ont_ids]
    ont_embeddings = embedding_model.encode(ont_texts, convert_to_numpy=True)
    ontology_emb_dict = {id: emb for id, emb in zip(ont_ids, ont_embeddings)}
    
    schema_ids = list(schema_texts.keys())
    schema_texts_list = [schema_texts[id] for id in schema_ids]
    schema_embeddings = embedding_model.encode(schema_texts_list, convert_to_numpy=True)
    schema_emb_dict = {id: emb for id, emb in zip(schema_ids, schema_embeddings)}
    
    # 2. 创建数据集
    dataset = AlignmentDataset(
        alignments=train_alignments,
        ontology_embeddings=ontology_emb_dict,
        schema_embeddings=schema_emb_dict
    )
    
    # 3. 创建模型
    config.embedding_dim = ont_embeddings.shape[1]
    model = AlignmentEncoder(config)
    
    # 4. 训练
    trainer = Trainer(model, config, dataset)
    trainer.train()
    
    return model


# ================== 重排序模型 ==================

class Reranker(nn.Module):
    """重排序模型"""
    
    def __init__(self, config: TrainingConfig):
        super().__init__()
        
        # 双塔编码
        self.query_encoder = nn.Sequential(
            nn.Linear(config.embedding_dim, config.hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout)
        )
        
        self.doc_encoder = nn.Sequential(
            nn.Linear(config.embedding_dim, config.hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout)
        )
        
        # 交互层
        self.interaction = nn.Sequential(
            nn.Linear(config.hidden_dim * 3, config.hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim, 1)
        )
        
    def forward(self, query_emb, doc_emb):
        # 编码
        query_enc = self.query_encoder(query_emb)
        doc_enc = self.doc_encoder(doc_emb)
        
        # 交互特征
        combined = torch.cat([
            query_enc,
            doc_enc,
            query_enc * doc_enc  # 逐元素乘积
        ], dim=-1)
        
        score = self.interaction(combined)
        return score.squeeze(-1)


# ================== 主入口 ==================

if __name__ == "__main__":
    # 示例使用
    
    # 1. 配置
    config = TrainingConfig(
        batch_size=16,
        num_epochs=10,
        learning_rate=1e-4
    )
    
    # 2. 模拟数据
    ontology_data = [
        ("ont_1", "客户信息"),
        ("ont_2", "订单数据"),
        ("ont_3", "产品目录")
    ]
    
    schema_data = [
        ("customers", "客户表"),
        ("orders", "订单表"),
        ("products", "产品表")
    ]
    
    alignments = [
        ("ont_1", "customers"),
        ("ont_2", "orders"),
        ("ont_3", "products")
    ]
    
    # 3. 创建数据集
    dataset = ContrastiveDataset(
        ontology_data=ontology_data,
        schema_data=schema_data,
        alignments=alignments
    )
    
    print(f"Dataset size: {len(dataset)}")
    sample = dataset[0]
    print(f"Sample: {sample}")
    
    # 4. 创建模型
    config.embedding_dim = 256
    model = AlignmentEncoder(config)
    print(f"\nModel: {model}")
    
    # 5. 创建训练器
    # trainer = Trainer(model, config, dataset)
    # trainer.train()
