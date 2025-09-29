# Elasticsearch 关键词搜索工具

## 功能概述
- 基于 Elasticsearch 的关键词搜索系统
- 支持对文档目录中的文件建立全文索引
- 提供多字段匹配搜索功能

## 主要功能
1. **连接 Elasticsearch**：支持多节点连接和重试机制
2. **创建索引**：定义 title, content, file_type, path 字段
3. **文档索引**：
   - 自动处理 UTF-8 和 GBK 编码
   - 支持批量索引文档
4. **关键词搜索**：
   - 支持 title 和 content 多字段匹配
   - 提供搜索结果高亮显示

## 使用说明
1. 安装依赖：
```bash
pip install elasticsearch tqdm
```

2. 配置 Elasticsearch 连接信息：
```python
es_hosts = ["https://localhost:9200"]
es_user = "elastic"
es_password = "your_password"
```

3. 运行程序：
```bash
python test_ai_search_by_ES.py
```

## 文件结构要求
- 文档应存放在程序同目录下的 `docs` 文件夹中
- 支持文本文件和 PDF 等格式（需确保内容可提取）

## 搜索结果展示
- 显示文档标题、路径和相关度评分
- 高亮显示匹配内容片段