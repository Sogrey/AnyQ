# Copyright 2023 The Qwen team, Alibaba Group. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from typing import Dict, Iterator, List, Optional, Union

import json5

from qwen_agent.llm import BaseChatModel
from qwen_agent.llm.schema import ASSISTANT, USER, Message
from qwen_agent.log import logger
from qwen_agent.memory.memory import Memory
from qwen_agent.settings import DEFAULT_MAX_REF_TOKEN, DEFAULT_PARSER_PAGE_SIZE
from qwen_agent.tools import BaseTool
from qwen_agent.utils.utils import extract_text_from_message


class ESMemory(Memory):
    """使用Elasticsearch进行文档检索的Memory类
    
    这个类扩展了基础Memory类，使用Elasticsearch进行文档索引和检索，
    提供更高效的文档检索能力。
    """

    def __init__(self,
                 function_list: Optional[List[Union[str, Dict, BaseTool]]] = None,
                 llm: Optional[Union[Dict, BaseChatModel]] = None,
                 system_message: Optional[str] = None,
                 files: Optional[List[str]] = None,
                 rag_cfg: Optional[Dict] = None,
                 es_config: Optional[Dict] = None):
        """初始化ESMemory
        
        Args:
            function_list: 工具列表
            llm: 语言模型配置或实例
            system_message: 系统消息
            files: 文件列表
            rag_cfg: RAG配置
            es_config: Elasticsearch配置
        """
        self.es_config = es_config or {
            'hosts': ["https://localhost:9200"],
            'basic_auth': ("elastic", "7dOzcb0RXmlXWza7VkRV"),
            'verify_certs': False,
            'request_timeout': 30
        }
        
        # 设置默认RAG配置
        rag_cfg = rag_cfg or {}
        self.index_name = rag_cfg.get('index_name', 'qwen_agent_docs')
        
        # 确保配置中包含ES相关参数
        if 'es_config' not in rag_cfg:
            rag_cfg['es_config'] = self.es_config
        if 'index_name' not in rag_cfg:
            rag_cfg['index_name'] = self.index_name
            
        # 初始化父类
        function_list = function_list or []
        
        # 添加ES工具
        es_tools = [{
            'name': 'es_retrieval',
            'max_ref_token': rag_cfg.get('max_ref_token', DEFAULT_MAX_REF_TOKEN),
            'es_config': self.es_config,
            'index_name': self.index_name
        }, {
            'name': 'es_doc_parser',
            'max_ref_token': rag_cfg.get('max_ref_token', DEFAULT_MAX_REF_TOKEN),
            'parser_page_size': rag_cfg.get('parser_page_size', DEFAULT_PARSER_PAGE_SIZE),
            'es_config': self.es_config,
            'index_name': self.index_name
        }]
        
        super().__init__(
            function_list=es_tools + function_list,
            llm=llm,
            system_message=system_message,
            files=files,
            rag_cfg=rag_cfg
        )

    def _run(self, messages: List[Message], lang: str = 'en', **kwargs) -> Iterator[List[Message]]:
        """处理输入文件并使用Elasticsearch进行检索
        
        Args:
            messages: 消息列表
            lang: 语言
            
        Yields:
            检索到的文档消息
        """
        # 获取RAG文件
        rag_files = self.get_rag_files(messages)

        if not rag_files:
            yield [Message(role=ASSISTANT, content='', name='memory')]
        else:
            query = ''
            # 只根据最后一个用户查询进行检索
            if messages and messages[-1].role == USER:
                query = extract_text_from_message(messages[-1], add_upload_info=False)

            # 关键词生成（与父类相同）
            if query and self.rag_keygen_strategy.lower() != 'none':
                try:
                    from importlib import import_module
                    module_name = 'qwen_agent.agents.keygen_strategies'
                    module = import_module(module_name)
                    cls = getattr(module, self.rag_keygen_strategy)
                    keygen = cls(llm=self.llm)
                    response = keygen.run([Message(USER, query)], files=rag_files)
                    last = None
                    for last in response:
                        continue
                    if last:
                        keyword = last[-1].content.strip()
                    else:
                        keyword = ''

                    if keyword.startswith('```json'):
                        keyword = keyword[len('```json'):]
                    if keyword.endswith('```'):
                        keyword = keyword[:-3]
                    try:
                        keyword_dict = json5.loads(keyword)
                        if 'text' not in keyword_dict:
                            keyword_dict['text'] = query
                        query = json.dumps(keyword_dict, ensure_ascii=False)
                        logger.info(query)
                    except Exception:
                        query = query
                except Exception as e:
                    logger.warning(f"关键词生成失败: {str(e)}")

            # 使用ES检索工具
            try:
                # 首先确保所有文件都已索引
                for file in rag_files:
                    self.function_map['es_doc_parser'].call(
                        {
                            'url': file,
                            'index_name': self.index_name
                        },
                        **kwargs,
                    )
                
                # 然后执行检索
                content = self.function_map['es_retrieval'].call(
                    {
                        'query': query,
                        'top_k': 5  # 返回前5个最相关的结果
                    },
                    **kwargs,
                )
                
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False, indent=4)

                yield [Message(role=ASSISTANT, content=content, name='memory')]
            except Exception as e:
                logger.error(f"ES检索失败: {str(e)}")
                # 如果ES检索失败，回退到标准检索
                content = self.function_map['retrieval'].call(
                    {
                        'query': query,
                        'files': rag_files
                    },
                    **kwargs,
                )
                
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False, indent=4)

                yield [Message(role=ASSISTANT, content=content, name='memory')]