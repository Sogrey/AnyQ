from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import os
import json
from tqdm import tqdm
from openai import OpenAI
import numpy as np

# 初始化OpenAI客户端
def init_embedding_client():
    return OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

# 生成文本embedding
def get_embedding(client, text):
    response = client.embeddings.create(
        model="text-embedding-v4",
        input=text,
        dimensions=1024,
        encoding_format="float"
    )
    return response.data[0].embedding

# 1. 连接到Elasticsearch
def connect_es():
    import time
    
    es_hosts = ["https://localhost:9200", "https://127.0.0.1:9200"]
    es_user = "elastic"
    es_password = "7dOzcb0RXmlXWza7VkRV"
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
    print("2. 服务启动后，检查是否输出elastic用户的密码")
    print("3. 确认config/elasticsearch.yml中的network.host设置正确")
    print("4. 确保9200端口未被防火墙阻止")
    exit(1)

# 2. 创建支持向量搜索的索引
def create_vector_index(es, index_name="insurance_docs_vector"):
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
    
    mapping = {
        "mappings": {
            "properties": {
                "title": {"type": "text", "analyzer": "standard"},
                "content": {"type": "text", "analyzer": "standard"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 1024,
                    "index": True,
                    "similarity": "cosine"
                },
                "file_type": {"type": "keyword"},
                "path": {"type": "keyword"}
            }
        }
    }
    es.indices.create(index=index_name, body=mapping)
    print(f"成功创建向量索引: {index_name}")
    return index_name

# 3. 索引文档并生成embedding
def index_documents_with_embedding(es, client, index_name):
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
                    try:
                        content = raw_data.decode('gbk')
                    except UnicodeDecodeError:
                        content = raw_data.decode('utf-8', errors='replace')
                
                # 生成embedding
                embedding = get_embedding(client, content[:1000])  # 只取前1000字符生成embedding
                
                doc = {
                    "_index": index_name,
                    "_source": {
                        "title": os.path.splitext(filename)[0],
                        "content": content,
                        "embedding": embedding,
                        "file_type": os.path.splitext(filename)[1][1:],
                        "path": file_path
                    }
                }
                actions.append(doc)
    
    # 批量索引文档
    success, _ = bulk(es, actions)
    print(f"成功索引 {success} 个文档(带embedding)")
    es.indices.refresh(index=index_name)

# 4. 执行向量搜索
def vector_search(es, client, index_name, query):
    # 生成查询文本的embedding
    query_embedding = get_embedding(client, query)
    
    script_query = {
        "script_score": {
            "query": {"match_all": {}},
            "script": {
                "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                "params": {"query_vector": query_embedding}
            }
        }
    }
    
    result = es.search(
        index=index_name,
        body={
            "query": script_query,
            "size": 5,
            "_source": ["title", "path", "content"]
        }
    )
    
    print(f"\n向量搜索 '{query}' 的结果 (共 {result['hits']['total']['value']} 条):")
    
    for hit in result["hits"]["hits"]:
        print(f"\n文档: {hit['_source']['title']}")
        print(f"路径: {hit['_source']['path']}")
        print(f"相关度: {hit['_score']:.2f}")
        print(f"内容片段: {hit['_source']['content'][:200]}...")

if __name__ == "__main__":
    try:
        # 初始化embedding客户端
        embedding_client = init_embedding_client()
        
        # 连接到ES
        es = connect_es()
        
        # 创建向量索引
        index_name = create_vector_index(es)
        
        # 索引文档(带embedding)
        index_documents_with_embedding(es, embedding_client, index_name)
        
        # 执行向量搜索
        search_query = "工伤保险和雇主险有什么区别？"
        vector_search(es, embedding_client, index_name, search_query)
        
    except Exception as e:
        print(f"发生错误: {str(e)}")