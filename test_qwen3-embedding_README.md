# Qwen3 Embedding 测试工具

## 功能说明
- 测试 text-embedding-v4 模型效果
- 生成文本向量表示
- 计算相似度矩阵

## 核心参数
| 参数 | 说明 | 默认值 |
|------|------|------|
| model | 模型版本 | text-embedding-v4 |
| dimensions | 向量维度 | 1024 |
| encoding_format | 编码格式 | float |

## 使用示例
```python
# 基本调用
embedding = get_embedding("测试文本")

# 批量处理
embeddings = batch_get_embedding(["文本1", "文本2"])
```

## 评估指标
1. 生成速度
2. 向量质量
3. 内存占用
4. 长文本处理能力

## 典型应用
- 语义搜索
- 文本聚类
- 问答系统
- 内容推荐