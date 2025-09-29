import pprint
import urllib.parse
import json5
import os
import re
import time
from dotenv import load_dotenv
from typing import List, Sequence, Dict, Any
from typing_extensions import Any  # 确保Any类型可用
from openai import OpenAI
import numpy as np
import streamlit as st

# 设置页面配置
st.set_page_config(
    page_title="AI智能搜索助手",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
from elasticsearch import Elasticsearch

# 自定义CSS样式
def load_css():
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 1rem;
        font-weight: 700;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #424242;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stTextInput>div>div>input {
        border-radius: 10px;
    }
    .stButton>button {
        border-radius: 10px;
        background-color: #1E88E5;
        color: white;
        font-weight: 500;
    }
    .user-message {
        background-color: #E3F2FD;
        color: #333;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        border-left: 5px solid #1E88E5;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .assistant-message {
        background-color: #F0F7FF;
        color: #333;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        border-left: 5px solid #4CAF50;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .search-result {
        background-color: #FFF8E1;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        border: 1px solid #FFD54F;
    }
    .footer {
        text-align: center;
        margin-top: 2rem;
        color: #9E9E9E;
        font-size: 0.8rem;
    }
    /* 右侧聊天容器样式 - 固定高度并允许内部滚动 */
    .chat-container {
        height: 70vh;
        overflow-y: auto;
        padding: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# 文档分块工具
class TextSplitter:
    """文本分块工具，将长文本分割成指定大小的块"""
    
    def __init__(self, chunk_size=500, chunk_overlap=50):
        """
        初始化文本分块器
        
        Args:
            chunk_size: 每个块的最大字符数
            chunk_overlap: 相邻块之间的重叠字符数
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def split_text(self, text):
        """
        将文本分割成块
        
        Args:
            text: 要分割的文本
            
        Returns:
            分割后的文本块列表
        """
        # 如果文本长度小于chunk_size，直接返回
        if len(text) <= self.chunk_size:
            return [text]
        
        # 按段落分割
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = []
        current_size = 0
        
        for paragraph in paragraphs:
            # 如果段落本身超过chunk_size，进一步分割
            if len(paragraph) > self.chunk_size:
                # 添加当前累积的chunk
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_size = 0
                
                # 分割长段落
                sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                temp_chunk = []
                temp_size = 0
                
                for sentence in sentences:
                    if temp_size + len(sentence) <= self.chunk_size:
                        temp_chunk.append(sentence)
                        temp_size += len(sentence) + 1  # +1 for space
                    else:
                        if temp_chunk:
                            chunks.append(' '.join(temp_chunk))
                        temp_chunk = [sentence]
                        temp_size = len(sentence)
                
                if temp_chunk:
                    chunks.append(' '.join(temp_chunk))
            
            # 正常处理段落
            elif current_size + len(paragraph) <= self.chunk_size:
                current_chunk.append(paragraph)
                current_size += len(paragraph) + 2  # +2 for '\n\n'
            else:
                # 当前chunk已满，保存并开始新chunk
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [paragraph]
                current_size = len(paragraph)
        
        # 添加最后一个chunk
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        # 处理重叠
        if self.chunk_overlap > 0 and len(chunks) > 1:
            overlapped_chunks = []
            for i in range(len(chunks)):
                if i == 0:
                    overlapped_chunks.append(chunks[i])
                else:
                    # 从前一个chunk的末尾取chunk_overlap个字符
                    prev_chunk = chunks[i-1]
                    overlap_text = prev_chunk[-self.chunk_overlap:] if len(prev_chunk) > self.chunk_overlap else prev_chunk
                    overlapped_chunks.append(overlap_text + chunks[i])
            
            return overlapped_chunks
        
        return chunks

# 注册向量搜索工具 - 使用唯一名称避免冲突
@register_tool('streamlit_es_vector_search', allow_overwrite=True)
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
        self.text_splitter = TextSplitter(
            chunk_size=int(os.getenv('CHUNK_SIZE', '500')),
            chunk_overlap=int(os.getenv('CHUNK_OVERLAP', '50'))
        )
        
    def index_documents(self, documents):
        """索引文档到Elasticsearch
        
        Args:
            documents: 文档列表，每个文档包含content和metadata
            
        Returns:
            成功索引的文档数量
        """
        try:
            from elasticsearch.helpers import bulk
            
            # 批量索引文档
            actions = []
            indexed_count = 0
            
            for doc in documents:
                if 'content' not in doc:
                    continue
                    
                # 将文档分割成chunks
                chunks = self.text_splitter.split_text(doc['content'])
                print(f"文档 '{doc.get('path', 'unknown')}' 被分割为 {len(chunks)} 个块")
                
                # 为每个chunk生成embedding并创建索引
                for i, chunk_text in enumerate(chunks):
                    # 每处理10个块打印一次进度日志
                    if i > 0 and i % 10 == 0:
                        print(f"正在处理文档 '{os.path.basename(doc.get('path', 'unknown'))}' - 已完成 {i}/{len(chunks)} 个块 ({i/len(chunks)*100:.1f}%)")
                    
                    # 生成embedding
                    embedding = get_embedding(self.embedding_client, chunk_text)
                    
                    # 准备元数据
                    metadata = doc.get('metadata', {}).copy()
                    metadata.update({
                        'chunk_index': i,
                        'total_chunks': len(chunks),
                        'original_path': doc.get('path', ''),
                        'original_url': doc.get('url', '')
                    })
                    
                    # 创建索引动作
                    actions.append({
                        "_index": self.index_name,
                        "_source": {
                            "content": chunk_text,
                            "metadata": metadata,
                            "path": doc.get('path', ''),
                            "url": doc.get('url', ''),
                            "embedding": embedding,
                            "chunk_id": f"{os.path.basename(doc.get('path', 'doc'))}_chunk_{i}"
                        }
                    })
                    indexed_count += 1
            
            # 执行批量索引
            if actions:
                success, _ = bulk(self.es, actions)
                print(f"成功索引 {success} 个文档块")
                return indexed_count
            return 0
            
        except Exception as e:
            print(f"文档索引失败: {str(e)}")
            return 0

    def call(self, params: dict, **kwargs) -> list:
        """执行向量搜索
        
        Args:
            params: 包含查询参数的字典
            
        Returns:
            检索到的文档列表
        """
        query = params['query']
        try:
            print(f"生成query embedding: {query[:50]}...")
            embedding = get_embedding(self.embedding_client, query)
            
            # 构建向量搜索查询
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
                "size": 10,  # 增加检索数量，因为现在是chunk级别
                "_source": ["content", "metadata", "path", "url", "chunk_id"]
            }
            
            print(f"执行向量搜索，top_k=10")
            result = self.es.search(
                index=self.index_name,
                body=query_body
            )
            
            # 打印召回结果
            print("向量召回结果：")
            for i, hit in enumerate(result['hits']['hits'][:5]):  # 只显示前5个结果
                score = hit['_score'] - 1.0  # 还原cosine相似度
                content_preview = hit['_source']['content'][:100].replace('\n', ' ')
                chunk_id = hit['_source'].get('chunk_id', 'unknown')
                print(f"#{i+1} 评分: {score:.4f} | Chunk: {chunk_id} | 内容: {content_preview}...")
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
                    'content': hit['_source'].get('content', ''),
                    'chunk_id': hit['_source'].get('chunk_id', '')
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

@register_tool('streamlit_image_gen', allow_overwrite=True)
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
        
        # 添加chunk信息
        chunk_id = doc.get('chunk_id', '')
        if chunk_id:
            source = f"{source} (块ID: {chunk_id})"
        
        return source, content

def parse_files_to_docs(file_paths):
    """本地文件解析函数
    
    Args:
        file_paths: 文件路径列表
        
    Returns:
        解析后的文档列表
    """
    docs = []
    for file_path in file_paths:
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # 根据文件类型选择不同的解析方法
            if file_ext == '.pdf':
                # 使用PyPDF2解析PDF文件
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(file_path)
                    content = ""
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            content += page_text + "\n"
                except ImportError:
                    print("请安装PyPDF2库以解析PDF文件: pip install PyPDF2")
                    content = f"[PDF文件 {os.path.basename(file_path)} 需要安装PyPDF2库才能解析]"
            else:
                # 对于文本文件，尝试不同的编码
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
                content = None
                
                for encoding in encodings:
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            content = f.read()
                            break  # 如果成功读取，跳出循环
                    except UnicodeDecodeError:
                        continue
                
                if content is None:
                    # 如果所有编码都失败，尝试二进制读取
                    with open(file_path, 'rb') as f:
                        content = f.read().decode('utf-8', errors='replace')
            
            # 添加到文档列表
            docs.append({
                'content': content,
                'path': file_path,
                'url': f"file://{file_path}",
                'metadata': {
                    'filename': os.path.basename(file_path),
                    'filetype': os.path.splitext(file_path)[1][1:],
                    'created_at': os.path.getctime(file_path)
                }
            })
        except Exception as e:
            print(f"解析文件 {file_path} 失败: {str(e)}")
    return docs

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
    tools= [
        {
            "mcpServers": {
                "tavily-mcp": {
                    "command": "npx",
                    "args": ["-y", "tavily-mcp@0.1.4"],
                    "env": {
                        "TAVILY_API_KEY": os.getenv('TAVILY_API_KEY')
                    },
                    "disabled": False,
                    "autoApprove": []
                }
            }
        },'streamlit_image_gen', 'code_interpreter']
    
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
        'parser_page_size': 500,  # 与chunk_size保持一致
        'rag_keygen_strategy': 'SplitQueryThenGenKeyword',
        'es_config': es_config,
        'index_name': os.getenv('ES_INDEX_NAME', 'qwen_agent_docs_vector')
    }

    # 根据检索模式配置
    if use_embedding:
        rag_cfg['rag_searchers'] = ['streamlit_es_vector_search']  # 使用新的工具名称
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
                            "url": {"type": "keyword"},
                            "chunk_id": {"type": "keyword"}
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
                            },
                            "chunk_id": {"type": "keyword"}
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
        es_vector = ESVectorSearch()
        docs = parse_files_to_docs(files)
        indexed_count = es_vector.index_documents(docs)
        print(f"索引 {rag_cfg['index_name']} 已存在 {indexed_count} 个文档块，跳过索引步骤")
    
    print("AI助手初始化完成")  # 调试日志
    
    return bot

# Streamlit UI 实现
def streamlit_ui():
    # 加载CSS样式
    load_css()
    
    # 创建左右布局 (1:3比例)
    col_sidebar, col_main = st.columns([1, 3], gap="small")
    
    # 侧边栏内容
    with col_sidebar:
        st.markdown('<div class="sidebar">', unsafe_allow_html=True)
        st.markdown('<h1 class="main-header">🔍 AI智能搜索</h1>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">基于向量检索的智能问答系统</p>', unsafe_allow_html=True)
        
        # 用户输入区域 - 放在logo和快捷问题之间
        with st.container():
            user_input = st.text_input(
                "请输入您的问题:",
                key="user_query",
                placeholder="例如: 雇主责任险的保障范围是什么？"
            )
            send_button = st.button("发送", key="send_button", use_container_width=True)
        
        # 快捷问题建议
        st.markdown("### 💡 快捷问题")
        quick_questions = [
            "雇主责任险的保障范围是什么？",
            "平安企业团体综合意外险有哪些保障？",
            "财产一切险的免赔额是多少？"
        ]
        
        # 为每个问题创建独立回调
        for i, question in enumerate(quick_questions):
            def make_callback(q):
                def callback():
                    st.session_state.preset_question = q
                    st.session_state.input_key = str(time.time())
                    # 触发问答流程 - 将问题添加到消息历史并触发处理
                    if 'messages' not in st.session_state:
                        st.session_state.messages = []
                    st.session_state.messages.append({"role": "user", "content": q})
                    st.session_state.current_response = ""
                    st.session_state.processing_response = True
                return callback
                
            st.button(question, 
                     key=f"quick_{i}",
                     on_click=make_callback(question),
                     use_container_width=True)
        
        # 初始化输入状态
        if 'preset_question' not in st.session_state:
            st.session_state.preset_question = ""
            st.session_state.input_key = "main_input_0"
        
        # 显示搜索结果（如果有）
        if 'search_results' in st.session_state and st.session_state.search_results:
            st.markdown("### 📚 相关文档")
            for i, doc in enumerate(st.session_state.search_results[:3]):
                st.markdown(f"""
                <div class="search-result">
                    <strong>文档 {i+1}:</strong> {os.path.basename(doc.get('path', '未知'))}
                    <br><strong>内容:</strong> {doc.get('content', '')[:100]}...
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # 主内容区 - 聊天对话（右侧只显示聊天内容）
    with col_main:
        # 初始化会话状态
        if 'bot' not in st.session_state:
            with st.spinner('正在初始化AI助手...'):
                st.session_state.bot = init_agent_service(use_es=True, use_embedding=True)
        
        if 'messages' not in st.session_state:
            st.session_state.messages = []
        
        # 聊天容器 - 只显示消息历史，设置自适应高度并允许滚动
        # st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        
        # 显示历史消息 - 所有消息都必须在.chat-container内
        for message in st.session_state.messages:
            if message['role'] == 'user':
                st.markdown(f'<div class="user-message"><strong>用户:</strong> {message["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="assistant-message"><strong>AI助手:</strong> {message["content"]}</div>', unsafe_allow_html=True)
        
        # 如果正在处理AI响应，不显示静态的"正在思考中"文本
        # AI响应将在处理过程中动态显示
        
        st.markdown('</div>', unsafe_allow_html=True)
        
    # 处理预置问题填充
    if 'preset_question' in st.session_state and st.session_state.preset_question:
        # 将预设问题填入输入框
        st.markdown(f"""
        <script>
            setTimeout(() => {{
                const input = document.querySelector('input[aria-label="请输入您的问题:"]');
                if (input) {{
                    input.value = "{st.session_state.preset_question}";
                    input.focus();
                    input.select();
                }}
            }}, 100);
        </script>
        """, unsafe_allow_html=True)
        st.session_state.preset_question = ""
    
    # 处理用户输入
    if send_button and user_input:
        # 添加用户消息到会话状态
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        # 初始化响应内容
        st.session_state.current_response = ""
        st.session_state.processing_response = True
    
    # 如果有正在处理的响应 - 实现流式显示（参考 demo_streaming.py 的方式）
    if 'processing_response' in st.session_state and st.session_state.processing_response and len(st.session_state.messages) > 0:
        # 在右侧主内容区显示loading和流式输出
        with col_main:
            # 重新显示当前的聊天历史
            # st.markdown('<div class="chat-container">', unsafe_allow_html=True)
            
            # 显示历史消息（除了最后一条）
            for message in st.session_state.messages[:-1]:
                if message['role'] == 'user':
                    st.markdown(f'<div class="user-message"><strong>用户:</strong> {message["content"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="assistant-message"><strong>AI助手:</strong> {message["content"]}</div>', unsafe_allow_html=True)
            
            # 显示"正在思考中"状态
            with st.spinner("AI助手正在思考..."):
                # 为AI响应创建一个占位符，用于流式更新（类似 demo_streaming.py 的方式）
                ai_response_placeholder = st.empty()
                
                # 在占位符中先显示"正在思考中"
                with ai_response_placeholder:
                    st.markdown(f'<div class="assistant-message"><strong>AI助手:</strong> 正在思考中...</div>', unsafe_allow_html=True)
                
                # 获取最后一条用户消息
                last_user_message = st.session_state.messages[-1]['content']
                
                # 调用AI助手
                messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
                
                # 流式获取AI响应
                full_response = ""
                
                for response_chunk in st.session_state.bot.run(messages=messages):
                    if response_chunk and response_chunk[0]['role'] == 'assistant':
                        assistant_message = response_chunk[0]
                        new_content = assistant_message.get('content', '')
                        if new_content != full_response:
                            full_response = new_content
                            
                            # 在占位符中更新AI响应内容，覆盖"正在思考中"
                            with ai_response_placeholder:
                                st.markdown(f'<div class="assistant-message"><strong>AI助手:</strong> {full_response}</div>', unsafe_allow_html=True)
            
            # 在响应完成后，添加完整的消息到会话状态
            st.session_state.messages = st.session_state.messages[:-1]  # 移除最后的用户消息
            st.session_state.messages.append({"role": "user", "content": last_user_message})  # 重新添加用户消息
            st.session_state.messages.append({"role": "assistant", "content": full_response})  # 添加AI消息
            
            # 标记处理完成
            st.session_state.processing_response = False
            
            # 获取搜索结果
            if hasattr(st.session_state.bot, 'memory') and st.session_state.bot.memory:
                if hasattr(st.session_state.bot.memory, 'function_map'):
                    if 'streamlit_es_vector_search' in st.session_state.bot.memory.function_map:
                        retrieved_docs = st.session_state.bot.memory.function_map['streamlit_es_vector_search'].call({'query': last_user_message})
                        if retrieved_docs:
                            st.session_state.search_results = retrieved_docs
            
            # 重新运行以显示最终结果
            st.rerun()


if __name__ == '__main__':
    print("正在启动Streamlit应用...")
    print("启动AI智能搜索助手...")
    print("Streamlit应用已启动，请在浏览器中访问")
    streamlit_ui()