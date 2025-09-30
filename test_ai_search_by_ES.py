from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import os
import json
from tqdm import tqdm

# 1. 连接到Elasticsearch
def connect_es():
    import time
    
    # 配置参数
    es_hosts = [os.getenv('ES_HOST', 'https://localhost:9200')]
    es_user = os.getenv('ES_USER', 'elastic')
    es_password = os.getenv('ES_PASSWORD','')

    max_retries = 5
    retry_delay = 10  # 秒
    
    for attempt in range(1, max_retries + 1):
        try:
            es = Elasticsearch(
                es_hosts,
                basic_auth=(es_user, es_password),
                verify_certs=False,
                request_timeout=30
            )
            
            if es.ping():
                print(f"成功连接到Elasticsearch: {es.info().body['version']['number']}")
                return es
            else:
                print(f"尝试 {attempt}/{max_retries}: Elasticsearch服务未响应...")
                
        except Exception as e:
            print(f"尝试 {attempt}/{max_retries} 失败: {str(e)}")
            
        if attempt < max_retries:
            print(f"{retry_delay}秒后重试...")
            time.sleep(retry_delay)
    
    print("无法连接到Elasticsearch，请确认:")
    print("1. 已下载并启动Elasticsearch服务")
    print("   - 下载: https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.11.0-windows-x86_64.zip")
    print("   - 启动: 解压后运行 bin/elasticsearch.bat")
    print("2. 服务启动后，检查是否输出elastic用户的密码")
    print("3. 确认config/elasticsearch.yml中的network.host设置正确")
    print("4. 确保9200端口未被防火墙阻止")
    exit(1)

# 2. 创建索引
def create_index(es, index_name="insurance_docs"):
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
    
    mapping = {
        "mappings": {
            "properties": {
                "title": {"type": "text", "analyzer": "standard"},
                "content": {"type": "text", "analyzer": "standard"}, 
                "file_type": {"type": "keyword"},
                "path": {"type": "keyword"}
            }
        }
    }
    es.indices.create(index=index_name, body=mapping)
    print(f"成功创建索引: {index_name}")
    return index_name

# 3. 索引文档
def index_documents(es, index_name):
    docs_dir = os.path.join(os.path.dirname(__file__), "docs")
    actions = []
    
    for filename in tqdm(os.listdir(docs_dir), desc="处理文档"):
        file_path = os.path.join(docs_dir, filename)
        if os.path.isfile(file_path):
            with open(file_path, "rb") as f:
                raw_data = f.read()
                try:
                    content = raw_data.decode('utf-8')
                except UnicodeDecodeError:
                    # 尝试其他常见编码
                    try:
                        content = raw_data.decode('gbk')
                    except UnicodeDecodeError:
                        content = raw_data.decode('utf-8', errors='replace')  # 替换无法解码的字符
                
                doc = {
                    "_index": index_name,
                    "_source": {
                        "title": os.path.splitext(filename)[0],
                        "content": content,
                        "file_type": os.path.splitext(filename)[1][1:],
                        "path": file_path
                    }
                }
                actions.append(doc)
    
    # 批量索引文档
    success, _ = bulk(es, actions)
    print(f"成功索引 {success} 个文档")
    es.indices.refresh(index=index_name)

# 4. 执行搜索
def search_documents(es, index_name, query):
    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["title^2", "content"],
                "type": "best_fields"
            }
        },
        "highlight": {
            "fields": {
                "content": {}
            }
        }
    }
    
    result = es.search(index=index_name, body=body)
    print(f"\n搜索 '{query}' 的结果 (共 {result['hits']['total']['value']} 条):")
    
    for hit in result["hits"]["hits"]:
        print(f"\n文档: {hit['_source']['title']}")
        print(f"路径: {hit['_source']['path']}")
        print(f"相关度: {hit['_score']:.2f}")
        
        # 打印高亮片段
        if "highlight" in hit:
            for h in hit["highlight"]["content"][:3]:  # 最多显示3个片段
                print(f"- {h.replace('<em>', '').replace('</em>', '')}")

if __name__ == "__main__":
    try:
        # 连接到ES
        es = connect_es()
        
        # 创建索引
        index_name = create_index(es)
        
        # 索引文档
        index_documents(es, index_name)
        
        # 执行搜索
        search_query = "工伤保险和雇主险有什么区别？"
        search_documents(es, index_name, search_query)
        
    except Exception as e:
        print(f"发生错误: {str(e)}")