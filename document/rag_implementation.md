# Qwen-Agent RAG 实现分析

## 1. 核心组件

### 1.1 DocParser (`local_packages/qwen_agent/tools/doc_parser.py`)
- 功能：文档解析和分块
- 主要方法：
  - `parse_doc_to_chunk()`: 将文档分割成固定大小的块
  - `_load_doc()`: 加载文档内容
  - `_chunk_doc()`: 执行分块操作

### 1.2 SimpleDocParser (`local_packages/qwen_agent/tools/simple_doc_parser.py`)
- 轻量级文档解析器
- 支持的文件类型：PDF, DOCX, PPTX, TXT, HTML
- 使用段落分割符号(`PARAGRAPH_SPLIT_SYMBOL`)进行分块

### 1.3 Retrieval (`local_packages/qwen_agent/tools/retrieval.py`)
- 整合文档解析和搜索功能
- 配置参数：
  - `max_ref_token`: 最大引用token数
  - `parser_page_size`: 分块大小

## 2. 文档处理流程

### 2.1 文档解析
1. 检查文档是否已缓存
2. 未缓存则调用`SimpleDocParser`解析原始文档
3. 计算每个块的token数

### 2.2 分块策略
```python
DEFAULT_PARSER_PAGE_SIZE = 4000  # 默认分块大小
if total_token <= max_ref_token:
    # 整个文档作为一个块
    content = [{
        'content': full_text,
        'token': total_token,
        'metadata': {'source': url, 'title': title}
    }]
else:
    # 按固定大小分块
    chunks = [full_text[i:i+parser_page_size] 
             for i in range(0, len(full_text), parser_page_size)]
```

### 2.3 存储实现
- 使用SHA256哈希文档URL作为缓存键
- 存储路径结构：
  ```
  workspace/tools/
    ├── doc_parser/
    │   ├── [hash1]_[page_size]
    │   ├── [hash2]_[page_size]
    │   └── ...
    └── simple_doc_parser/
        ├── [hash1]_ori
        ├── [hash2]_ori
        └── ...
  ```

## 3. 检索功能

### 3.1 搜索类型
| 类型 | 实现文件 | 算法 |
|------|---------|------|
| 向量搜索 | `vector_search.py` | FAISS + 文本嵌入 |
| 关键词搜索 | `keyword_search.py` | BM25算法 |
| 混合搜索 | `hybrid_search.py` | 结合多种算法 |

### 3.2 检索流程
1. 加载所有文档块
2. 根据查询类型选择搜索算法
3. 计算相关性分数
4. 返回top-k相关块

## 4. 性能优化

1. **缓存机制**：
   - 解析后的文档会被缓存
   - 避免重复解析相同文档

2. **并行处理**：
   - 使用多线程处理多个文档

3. **token计算**：
   - 精确计算每个块的token数
   - 确保不超过模型上下文限制

## 5. 自定义配置

可通过修改以下参数调整RAG行为：
```python
# 在Retrieval初始化时配置
cfg = {
    'max_ref_token': 4000,  # 最大引用token数
    'parser_page_size': 2000,  # 分块大小
    'search_type': 'hybrid'  # 搜索类型
}