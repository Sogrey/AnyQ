import pprint
import urllib.parse
import json5
import os
from dotenv import load_dotenv
from typing import List, Sequence

# 加载.env文件
load_dotenv()

# 导入本地qwen-agent模块
from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool
from qwen_agent.gui import WebUI
from qwen_agent.memory.es_memory import ESMemory


# 步骤 1（可选）：添加一个名为 `my_image_gen` 的自定义工具。
@register_tool('my_image_gen')
class MyImageGen(BaseTool):
    # `description` 用于告诉智能体该工具的功能。
    description = 'AI 绘画（图像生成）服务，输入文本描述，返回基于文本信息绘制的图像 URL。'
    # `parameters` 告诉智能体该工具有哪些输入参数。
    parameters = [{
        'name': 'prompt',
        'type': 'string',
        'description': '期望的图像内容的详细描述',
        'required': True
    }]

    def call(self, params: str, **kwargs) -> str:
        # `params` 是由 LLM 智能体生成的参数。
        prompt = json5.loads(params)['prompt']
        prompt = urllib.parse.quote(prompt)
        return json5.dumps(
            {'image_url': f'https://image.pollinations.ai/prompt/{prompt}'},
            ensure_ascii=False)


def init_agent_service(use_es=True):
    """初始化助手服务
    
    Args:
        use_es: 是否使用Elasticsearch进行文档检索
    """
    # 步骤 2：配置您所使用的 LLM。
    llm_cfg = {
        # 使用 DashScope 提供的模型服务：
        'model': 'qwen-max',
        'model_server': 'dashscope',
        'api_key': os.getenv('DASHSCOPE_API_KEY'),  # 从环境变量获取API Key
        'generate_cfg': {
            'top_p': 0.8
        }
    }

    # 步骤 3：创建一个智能体。这里我们以 `Assistant` 智能体为例，它能够使用工具并读取文件。
    system_instruction = '''你是一个乐于助人的AI助手。
在收到用户的请求后，你应该：
- 首先绘制一幅图像，得到图像的url，
- 然后运行代码`request.get`以下载该图像的url，
- 最后从给定的文档中选择一个图像操作进行图像处理。
用 `plt.show()` 展示图像。
你总是用中文回复用户。'''
    tools: Sequence[str] = ['my_image_gen', 'code_interpreter']  # `code_interpreter` 是框架自带的工具，用于执行代码。
    
    # 获取文件夹下所有文件
    file_dir = os.path.join(os.path.dirname(__file__), os.getenv('DOCS_DIR', 'docs'))
    files = []
    if os.path.exists(file_dir):
        # 遍历目录下的所有文件
        for file in os.listdir(file_dir):
            file_path = os.path.join(file_dir, file)
            if os.path.isfile(file_path):  # 确保是文件而不是目录
                files.append(file_path)
    print('files=', files)

    # Elasticsearch配置
    es_config = {
        'hosts': [os.getenv('ES_HOST', 'https://localhost:9200')],
        'basic_auth': (os.getenv('ES_USER', 'elastic'), os.getenv('ES_PASSWORD', '7dOzcb0RXmlXWza7VkRV')),
        'verify_certs': False,
        'request_timeout': 30
    }
    
    # 确保ES工具已注册
    try:
        from qwen_agent.tools.es_retrieval import ESRetrieval
    except ImportError as e:
        print(f"无法导入ESRetrieval: {str(e)}")
        use_es = False
    
    # RAG配置
    rag_cfg = {
        'max_ref_token': 4000,
        'parser_page_size': 500,
        'rag_keygen_strategy': 'SplitQueryThenGenKeyword',
        'rag_searchers': ['es_retrieval'] if use_es else ['keyword_search', 'front_page_search'],
        'es_config': es_config,
        'index_name': os.getenv('ES_INDEX_NAME', 'qwen_agent_docs')
    }

    # 统一使用Assistant初始化，通过rag_cfg配置ES功能
    bot = Assistant(
        llm=llm_cfg,
        system_message=system_instruction,
        function_list=tools,
        files=files,
        rag_cfg=rag_cfg
    )
    
    # 如果不想使用ES，可以在rag_cfg中配置其他检索方式
    # rag_cfg['rag_searchers'] = ['keyword_search', 'front_page_search']
    
    return bot


def app_tui():
    """终端交互模式
    
    提供命令行交互界面，支持：
    - 连续对话
    - 文件输入
    - 实时响应
    """
    try:
        # 初始化助手
        bot = init_agent_service(use_es=True)

        # 对话历史
        messages = []
        while True:
            try:
                # 获取用户输入
                query = input('user question: ')
                
                # 输入验证
                if not query:
                    print('user question cannot be empty！')
                    continue
                    
                # 构建消息
                messages.append({'role': 'user', 'content': query})

                print("正在处理您的请求...")
                # 运行助手并处理响应
                response = []
                current_index = 0
                first_chunk = True
                for response_chunk in bot.run(messages=messages):
                    if first_chunk:
                        # 尝试获取并打印召回的文档内容
                        if hasattr(bot, 'memory') and bot.memory:
                            print("\n===== 召回的文档内容 =====")
                            # 这里我们使用memory中的es_retrieval工具
                            if hasattr(bot.memory, 'function_map') and 'es_retrieval' in bot.memory.function_map:
                                retrieved_docs = bot.memory.function_map['es_retrieval'].call({'query': query})
                                if retrieved_docs:
                                    for i, doc in enumerate(retrieved_docs):
                                        print(f"\n文档片段 {i+1}:")
                                        print(f"内容: {doc.get('page_content', '')}")
                                        print(f"元数据: {doc.get('metadata', {})}")
                                else:
                                    print("没有召回任何文档内容")
                            else:
                                print("ES检索工具不可用，使用标准检索")
                                if hasattr(bot, 'retriever') and bot.retriever:
                                    retrieved_docs = bot.retriever.retrieve(query)
                                    if retrieved_docs:
                                        for i, doc in enumerate(retrieved_docs):
                                            print(f"\n文档片段 {i+1}:")
                                            print(f"内容: {doc.page_content}")
                                            print(f"元数据: {doc.metadata}")
                                    else:
                                        print("没有召回任何文档内容")
                            print("===========================\n")
                        first_chunk = False

                    # The response is a list of messages. We are interested in the assistant's message.
                    if response_chunk and response_chunk[0]['role'] == 'assistant':
                        assistant_message = response_chunk[0]
                        new_content = assistant_message.get('content', '')
                        print(new_content[current_index:], end='', flush=True)
                        current_index = len(new_content)
                    
                    response = response_chunk
                
                print() # New line after streaming.

                messages.extend(response)
            except Exception as e:
                print(f"处理请求时出错: {str(e)}")
                print("请重试或输入新的问题")
    except Exception as e:
        print(f"启动终端模式失败: {str(e)}")


def app_gui():
    """图形界面模式，提供 Web 图形界面"""
    try:
        print("正在启动 Web 界面...")
        # 初始化助手，使用ES检索
        bot = init_agent_service(use_es=True)
        # 配置聊天界面，列举3个典型门票查询问题
        chatbot_config = {
            'prompt.suggestions': [
                '画一只在写代码的猫',
                '介绍下雇主责任险',
                '帮我画一个宇宙飞船，然后把它变成黑白的'
            ]
        }
        print("Web 界面准备就绪，正在启动服务...")
        # 启动 Web 界面
        WebUI(
            bot,
            chatbot_config=chatbot_config
        ).run()
    except Exception as e:
        print(f"启动 Web 界面失败: {str(e)}")
        print("请检查网络连接和 API Key 配置")


if __name__ == '__main__':
    # 运行模式选择
    app_gui()          # 图形界面模式（默认）
    # app_tui()         # 终端交互模式