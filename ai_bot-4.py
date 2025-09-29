import pprint
import urllib.parse
import json5
import os
from dotenv import load_dotenv
from typing import List, Sequence, Dict, Any
from typing_extensions import Any  # 确保Any类型可用
from openai import OpenAI
import numpy as np

# 加载.env文件（强制覆盖现有变量）
load_dotenv(override=True)

# 验证必需环境变量
required_env_vars = ['DASHSCOPE_API_KEY', 'ES_HOST', 'ES_USER', 'ES_PASSWORD']
for var in required_env_vars:
    if not os.getenv(var):
        raise ValueError(f"Missing required environment variable: {var}")

# 导入本地qwen-agent模块
from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool
from qwen_agent.gui import WebUI
from qwen_agent.memory.es_memory import ESMemory
from elasticsearch import Elasticsearch

# 注册向量搜索工具
@register_tool('es_vector_search')
class ESVectorSearch(BaseTool):
    description = 'Elasticsearch向量检索服务'
    parameters = [{
        'name': 'query', 
        'type': 'string',
        'required': True
    }]

    def __init__(self, cfg=None):
        super().__init__(cfg)
        # 独立配置，不依赖外部传入
        self.es = Elasticsearch(
            hosts=[os.getenv('ES_HOST')],
            basic_auth=(os.getenv('ES_USER'), os.getenv('ES_PASSWORD')),
            verify_certs=False,
            request_timeout=30
        )
        self.embedding_client = init_embedding_client()
        self.index_name = os.getenv('ES_INDEX_NAME', 'qwen_agent_docs_vector')
        
    def index_documents(self, documents):
        """索引文档到Elasticsearch"""
        try:
            from elasticsearch.helpers import bulk
            # 批量索引文档
            actions = []
            for doc in documents:
                # 生成embedding
                if 'content' in doc:
                    embedding = get_embedding(self.embedding_client, doc['content'])
                    actions.append({
                        "_index": self.index_name,
                        "_source": {
                            "content": doc['content'],
                            "metadata": doc.get('metadata', {}),
                            "path": doc.get('path', ''),
                            "url": doc.get('url', ''),
                            "embedding": embedding
                        }
                    })
            
            # 执行批量索引
            success, _ = bulk(self.es, actions)
            return success
        except Exception as e:
            print(f"文档索引失败: {str(e)}")
            return 0

    def call(self, params: dict, **kwargs) -> list:
        query = params['query']
        try:
            print(f"生成query embedding: {query[:50]}...")
            embedding = get_embedding(self.embedding_client, query)
            
            query_body = {
                "query": {
                    "script_score": {
                        "query": {"match_all": {}},
                        "script": {
                            "source": """
                                if (!doc.containsKey('embedding') || doc['embedding'].size() == 0) {
                                    return 0
                                }
                                return cosineSimilarity(params.query_vector, 'embedding') + 1.0
                            """,
                            "params": {"query_vector": embedding}
                        }
                    }
                },
                "size": 5,
                "_source": ["content", "metadata", "path", "url"]
            }
            
            print(f"执行向量搜索，top_k=5")
            result = self.es.search(
                index=self.index_name,
                body=query_body
            )
            
            # 打印召回结果
            print("向量召回结果：")
            for i, hit in enumerate(result['hits']['hits'][:3]):
                score = hit['_score'] - 1.0  # 还原cosine相似度
                content_preview = hit['_source']['content'][:100].replace('\n', ' ')
                print(f"#{i+1} 评分: {score:.4f} | 内容: {content_preview}...")
                print(f"来源: {hit['_source'].get('path', hit['_source'].get('url', ''))}")
            # 标准化返回文档结构
            docs = []
            for hit in result['hits']['hits']:
                doc = {
                    'page_content': hit['_source'].get('content', ''),
                    'metadata': hit['_source'].get('metadata', {}),
                    'path': hit['_source'].get('path', ''),
                    'url': hit['_source'].get('url', ''),
                    'source': hit['_source'].get('path', hit['_source'].get('url', '')),
                    'text': hit['_source'].get('content', ''),
                    'content': hit['_source'].get('content', '')
                }
                # 确保至少有一个标识字段
                if not doc['path'] and not doc['url']:
                    doc['source'] = '未知来源'
                docs.append(doc)
            return docs
            
        except Exception as e:
            print(f"向量搜索失败: {str(e)}")
            return []

# 初始化embedding客户端
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

@register_tool('my_image_gen')
class MyImageGen(BaseTool):
    description = 'AI 绘画（图像生成）服务，输入文本描述，返回基于文本信息绘制的图像 URL。'
    parameters = [{
        'name': 'prompt',
        'type': 'string',
        'description': '期望的图像内容的详细描述',
        'required': True
    }]

    def call(self, params: str | Dict[str, str], **kwargs) -> str:
        if isinstance(params, str):
            params = json5.loads(params)
        prompt = str(params.get('prompt', ''))  # 安全获取prompt参数
        prompt = urllib.parse.quote(prompt)
        return json5.dumps(
            {'image_url': f'https://image.pollinations.ai/prompt/{prompt}'},
            ensure_ascii=False)

    def format_knowledge_to_source_and_content(self, doc):
        """将知识文档格式化为(来源, 内容)元组"""
        # 安全获取字段，提供默认值
        source = doc.get('path', doc.get('url', doc.get('source', '未知来源')))
        content = doc.get('page_content', doc.get('text', doc.get('content', '')))
        
        # 如果是本地文件路径，提取文件名作为简洁来源
        if isinstance(source, str):
            # 排除URL
            if not (source.startswith('http://') or source.startswith('https://')):
                # 使用os.path检测有效路径
                path_sep = os.path.sep
                alt_sep = os.path.altsep or path_sep
                if path_sep in source or alt_sep in source:
                    source = os.path.basename(source)
        
        return source, content

def init_agent_service(use_es=True, use_embedding=True):
    """初始化助手服务
    
    Args:
        use_es: 是否使用Elasticsearch进行文档检索
        use_embedding: 是否使用embedding向量检索
    """
    llm_cfg = {
        'model': 'qwen-max',
        'model_server': 'dashscope',
        'api_key': os.getenv('DASHSCOPE_API_KEY'),
        'generate_cfg': {
            'top_p': 0.8
        }
    }

    system_instruction = '''你是一个乐于助人的AI助手。
在收到用户的请求后，你应该：
- 首先绘制一幅图像，得到图像的url，
- 然后运行代码`request.get`以下载该图像的url，
- 最后从给定的文档中选择一个图像操作进行图像处理。
用 `plt.show()` 展示图像。
你总是用中文回复用户。'''
    tools: Sequence[str | BaseTool] = ['my_image_gen', 'code_interpreter']
    
    # 获取文件夹下所有文件
    file_dir = os.path.join(os.path.dirname(__file__), os.getenv('DOCS_DIR', 'docs'))
    files = []
    if os.path.exists(file_dir):
        for file in os.listdir(file_dir):
            file_path = os.path.join(file_dir, file)
            if os.path.isfile(file_path):
                files.append(file_path)
    print('files=', files)

    # Elasticsearch配置（严格模式）
    es_config = {
        'hosts': [os.getenv('ES_HOST')],
        'basic_auth': (os.getenv('ES_USER'), os.getenv('ES_PASSWORD')),
        'verify_certs': False,
        'request_timeout': 30
    }
    print(f"ES配置加载成功：{es_config['hosts'][0]}")  # 调试日志
    
    # RAG配置
    rag_cfg: dict[str, object] = {
        'max_ref_token': 4000,
        'parser_page_size': 500,
        'rag_keygen_strategy': 'SplitQueryThenGenKeyword',
        'es_config': es_config,
        'index_name': os.getenv('ES_INDEX_NAME', 'qwen_agent_docs_vector')
    }

    # 根据检索模式配置
    if use_embedding:
        rag_cfg['rag_searchers'] = ['es_vector_search']
        # 初始化embedding客户端
        rag_cfg['embedding_client'] = init_embedding_client()
        
        # 检查索引是否存在，不存在则创建
        es = Elasticsearch(
            hosts=[os.getenv('ES_HOST')],
            basic_auth=(os.getenv('ES_USER'), os.getenv('ES_PASSWORD')),
            verify_certs=False
        )
        
        if not es.indices.exists(index=rag_cfg['index_name']):
            # 创建带有embedding字段映射的索引
            es.indices.create(
                index=rag_cfg['index_name'],
                body={
                    "mappings": {
                        "properties": {
                            "embedding": {
                                "type": "dense_vector",
                                "dims": 1024,
                                "index": True,
                                "similarity": "cosine"
                            },
                            "content": {"type": "text"},
                            "metadata": {"type": "object"},
                            "path": {"type": "keyword"},
                            "url": {"type": "keyword"}
                        }
                    }
                }
            )
        else:
            # 索引存在，检查映射
            mapping = es.indices.get_mapping(index=rag_cfg['index_name'])
            if 'embedding' not in mapping[rag_cfg['index_name']]['mappings']['properties']:
                # 添加embedding字段映射
                es.indices.put_mapping(
                    index=rag_cfg['index_name'],
                    body={
                        "properties": {
                            "embedding": {
                                "type": "dense_vector",
                                "dims": 1024,
                                "index": True,
                                "similarity": "cosine"
                            }
                        }
                    }
                )
    else:
        rag_cfg['rag_searchers'] = ['es_retrieval'] if use_es else ['keyword_search', 'front_page_search']

    # 简化初始化流程
    bot = Assistant(
        llm=llm_cfg,
        system_message=system_instruction,
        function_list=tools,
        files=files,
        rag_cfg=rag_cfg
    )
    
    # 索引文档到向量索引
    if use_embedding and files:
        def parse_files_to_docs(file_paths):
            """本地文件解析函数"""
            docs = []
            for file_path in file_paths:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        docs.append({
                            'content': content,
                            'path': file_path,
                            'url': f"file://{file_path}"
                        })
                except Exception as e:
                    print(f"解析文件 {file_path} 失败: {str(e)}")
            return docs
            
        es_vector = ESVectorSearch()
        docs = parse_files_to_docs(files)
        indexed_count = es_vector.index_documents(docs)
        print(f"成功索引 {indexed_count} 个文档到向量索引 {rag_cfg['index_name']}")
    
    print("AI助手初始化完成")  # 调试日志
    
    return bot

def app_tui():
    try:
        bot = init_agent_service(use_es=True, use_embedding=True)
        messages = []
        while True:
            try:
                query = input('user question: ')
                if not query:
                    print('user question cannot be empty！')
                    continue
                    
                messages.append({'role': 'user', 'content': query})
                print("正在处理您的请求...")
                
                response = []
                current_index = 0
                first_chunk = True
                for response_chunk in bot.run(messages=messages):
                    if first_chunk:
                        if hasattr(bot, 'memory') and bot.memory:
                            print("\n===== 召回的文档内容 =====")
                            if hasattr(bot.memory, 'function_map'):
                                if 'es_vector_search' in bot.memory.function_map:
                                    retrieved_docs = bot.memory.function_map['es_vector_search'].call({'query': query})
                                elif 'es_retrieval' in bot.memory.function_map:
                                    retrieved_docs = bot.memory.function_map['es_retrieval'].call({'query': query})
                                
                                if retrieved_docs:
                                    for i, doc in enumerate(retrieved_docs):
                                        print(f"\n文档片段 {i+1}:")
                                        print(f"内容: {doc.get('page_content', '')}")
                                        print(f"元数据: {doc.get('metadata', {})}")
                                else:
                                    print("没有召回任何文档内容")
                            print("===========================\n")
                        first_chunk = False

                    if response_chunk and response_chunk[0]['role'] == 'assistant':
                        assistant_message = response_chunk[0]
                        new_content = assistant_message.get('content', '')
                        print(new_content[current_index:], end='', flush=True)
                        current_index = len(new_content)
                    
                    response = response_chunk
                
                print()
                messages.extend(response)
            except Exception as e:
                print(f"处理请求时出错: {str(e)}")
    except Exception as e:
        print(f"启动终端模式失败: {str(e)}")

def app_gui():
    try:
        print("正在启动 Web 界面...")
        bot = init_agent_service(use_es=True, use_embedding=True)
        chatbot_config = {
            'prompt.suggestions': [
                '画一只在写代码的猫',
                '介绍下雇主责任险',
                '帮我画一个宇宙飞船，然后把它变成黑白的'
            ]
        }
        print("Web 界面准备就绪，正在启动服务...")
        WebUI(bot, chatbot_config=chatbot_config).run()
    except Exception as e:
        print(f"启动 Web 界面失败: {str(e)}")

if __name__ == '__main__':
    app_gui()