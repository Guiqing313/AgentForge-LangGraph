# 微调与LoRA知识

## 什么是LoRA？
LoRA（低秩适配）是一种参数高效微调方法，通过在预训练模型中插入低秩分解矩阵来减少需要训练的参数数量。只训练两个很小的低秩矩阵 A、B来模拟全量微调效果。
- 只训练<1%的参数，现存和算力开销大幅降低
- 类比：整栋楼不动，只微调几个关键零件

## 什么是QLoRA？为什么8GB显存能跑7B模型？
三招：
1. 4bit量化（NF4）：把16bit权重压到4bit，7B模型从14GB降到3.5GB
2. 只训练低秩矩阵：省掉14GB的梯度
3. 分页优化器：显存不够是暂存到内存，防OOM

## SFT/DPO/RLHF区别
- SFT：监督微调，用标注数据教模型模仿
- DPO：直接偏好优化，用偏好对训练
- RLHF：强化学习+人类反馈，先用PPO训练，再用人类反馈


## 微调数据格式（alpaca）
instruction /input /output 三字段

## 工具链
LLaMA-Factory：可视化微调平台 训练→ 导出 LoRA adapter → Ollama Modelfile（FROM + ADAPTER）导入











