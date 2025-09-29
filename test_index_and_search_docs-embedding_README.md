# 基于 Embedding 的向量搜索工具 (升级版)

## 版本升级说明
本版本是基于 `test_ai_search_by_ES.py` 的升级版本，主要改进如下：

| 功能 | 原版 | 升级版 |
|------|------|--------|
| 搜索方式 | 关键词匹配 | 向量相似度 |
| 核心技术 | Elasticsearch 全文索引 | text-embedding-v4 + 向量搜索 |
| 索引结构 | 普通字段 | 增加 embedding 向量字段 |
| 搜索质量 | 关键词匹配 | 语义理解 |
| 扩展性 | 有限 | 支持多模态扩展 |

## 新增功能
1. **向量索引**：
   - 使用 text-embedding-v4 生成 1024 维向量
   - 支持余弦相似度计算

2. **混合搜索**：
   - 纯向量搜索
   - 可扩展为关键词+向量的混合搜索

3. **API 集成**：
   - 集成 DashScope 的 Embedding API

## 使用说明
1. 额外安装依赖：
```bash
pip install openai numpy
```

2. 设置环境变量：
```bash
export DASHSCOPE_API_KEY=your_api_key
```

3. 运行程序：
```bash
python test_index_and_search_docs-embedding.py
```

## 性能建议
1. 对大文档建议分块处理
2. 可调整 embedding 生成的内容长度
3. 可调整返回结果数量

## 典型应用场景
- 语义搜索
- 问答系统
- 内容推荐
- 相似文档查找

## 升级优势
- 更准确的语义理解
- 支持长尾查询
- 更好的多语言支持
- 可扩展性强