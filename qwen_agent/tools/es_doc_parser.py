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

import os
import json
import time
from typing import Dict, List, Optional, Union, Any
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from qwen_agent.log import logger
from qwen_agent.settings import DEFAULT_MAX_REF_TOKEN, DEFAULT_PARSER_PAGE_SIZE
from qwen_agent.tools.base import BaseTool, register_tool
from qwen_agent.tools.simple_doc_parser import SimpleDocParser, PARSER_SUPPORTED_FILE_TYPES
from qwen_agent.utils.utils import hash_sha256


@register_tool('es_doc_parser')
class ESDocParser(BaseTool):
    description = f"使用Elasticsearch解析并索引文档内容，支持文件类型包括：{' / '.join(PARSER_SUPPORTED_FILE_TYPES)}"
    parameters = {
        'type': 'object',
        'properties': {
            'url': {
                'description': '待解析的文件的路径，可以是一个本地路径或可下载的http(s)链接',
                'type': 'string',
            },
            'index_name': {
                'description': 'Elasticsearch索引名称',
                'type': 'string',
                'default': 'qwen_agent_docs'
            }
        },
        'required': ['url'],
    }

    def __init__(self, cfg: Optional[Dict] = None):
        super().__init__(cfg)
        self.max_ref_token: int = self.cfg.get('max_ref_token', DEFAULT_MAX_REF_TOKEN)
        self.parser_page_size: int = self.cfg.get('parser_page_size', DEFAULT_PARSER_PAGE_SIZE)
        
        # 创建文档解析器
        self.doc_parser = SimpleDocParser({
            'max_ref_token': self.max_ref_token, 
            'parser_page_size': self.parser_page_size,
            'structured_doc': True  # 确保返回结构化文档
        })
        
        # 从环境变量获取Elasticsearch配置
        self.es_config = {
            'hosts': [os.getenv('ES_HOST', 'https://localhost:9200')],
            'basic_auth': (os.getenv('ES_USER', 'elastic'), os.getenv('ES_PASSWORD', '7dOzcb0RXmlXWza7VkRV')),
            'verify_certs': os.getenv('ES_VERIFY_CERTS', 'False').lower() == 'true',
            'request_timeout': int(os.getenv('ES_TIMEOUT', '30'))
        }
        # 如果cfg中有配置，则覆盖环境变量
        if 'es_config' in self.cfg:
            self.es_config.update(self.cfg['es_config'])
            
        self.default_index_name = os.getenv('ES_INDEX_NAME', self.cfg.get('index_name', 'qwen_agent_docs'))
        self.es_client = None
        self._connect_es()

    def _connect_es(self):
        """连接到Elasticsearch服务器"""
        try:
            self.es_client = Elasticsearch(**self.es_config)
            if self.es_client.ping():
                logger.info(f"成功连接到Elasticsearch: {self.es_client.info().body['version']['number']}")
            else:
                logger.error("无法连接到Elasticsearch服务")
                self.es_client = None
        except Exception as e:
            logger.error(f"连接Elasticsearch失败: {str(e)}")
            self.es_client = None

    def _create_index_if_not_exists(self, index_name: str):
        """创建索引（如果不存在）"""
        if not self.es_client:
            return False
            
        try:
            if not self.es_client.indices.exists(index=index_name):
                mapping = {
                    "mappings": {
                        "properties": {
                            "content": {"type": "text", "analyzer": "standard"},
                            "metadata": {
                                "properties": {
                                    "source": {"type": "keyword"},
                                    "page": {"type": "integer"},
                                    "file_type": {"type": "keyword"},
                                    "chunk_id": {"type": "keyword"},
                                    "content_type": {"type": "keyword"}
                                }
                            }
                        }
                    }
                }
                self.es_client.indices.create(index=index_name, body=mapping)
                logger.info(f"成功创建索引: {index_name}")
            return True
        except Exception as e:
            logger.error(f"创建索引失败: {str(e)}")
            return False

    def _index_document(self, doc: List[Dict], url: str, file_type: str, index_name: str) -> bool:
        """将解析后的文档索引到Elasticsearch"""
        if not self.es_client:
            return False
            
        if not self._create_index_if_not_exists(index_name):
            return False
            
        try:
            actions = []
            for page in doc:
                page_num = page.get('page_num', 0)
                for content_item in page.get('content', []):
                    # 处理文本内容
                    if 'text' in content_item:
                        text_content = content_item.get('text', '')
                        if text_content.strip():  # 确保内容不为空
                            doc_id = hash_sha256(f"{url}_{page_num}_{text_content[:50]}")
                            actions.append({
                                "_index": index_name,
                                "_id": doc_id,
                                "_source": {
                                    "content": text_content,
                                    "metadata": {
                                        "source": url,
                                        "page": page_num,
                                        "file_type": file_type,
                                        "chunk_id": doc_id,
                                        "content_type": "text"
                                    }
                                }
                            })
                    # 处理表格内容
                    elif 'table' in content_item:
                        table_content = content_item.get('table', '')
                        if table_content.strip():  # 确保内容不为空
                            doc_id = hash_sha256(f"{url}_{page_num}_{table_content[:50]}")
                            actions.append({
                                "_index": index_name,
                                "_id": doc_id,
                                "_source": {
                                    "content": table_content,
                                    "metadata": {
                                        "source": url,
                                        "page": page_num,
                                        "file_type": file_type,
                                        "chunk_id": doc_id,
                                        "content_type": "table"
                                    }
                                }
                            })
            
            if actions:
                success, failed = bulk(self.es_client, actions, refresh=True)
                logger.info(f"成功索引 {success} 个文档片段，失败 {len(failed) if failed else 0} 个")
                return True
            return False
        except Exception as e:
            logger.error(f"索引文档失败: {str(e)}")
            return False

    def call(self, params: Union[str, dict], **kwargs) -> Dict[str, Any]:
        """解析文档并索引到Elasticsearch
        
        Args:
            params: 包含文件URL和索引名称的参数
            
        Returns:
            包含索引结果的字典
        """
        params = self._verify_json_format_args(params)
        url = params.get('url', '')
        index_name = params.get('index_name', self.default_index_name)
        
        if not url:
            return {"success": False, "error": "未提供文件URL"}
            
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 解析文档
            logger.info(f"开始解析文档: {url}")
            parsed_doc = self.doc_parser.call({"url": url})
            
            # 确保解析结果是列表格式
            if not isinstance(parsed_doc, list):
                return {"success": False, "error": "文档解析失败，未返回结构化内容"}
                
            # 获取文件类型
            file_type = url.split('.')[-1].lower() if '.' in url else 'unknown'
            
            # 索引文档
            logger.info(f"开始索引文档到 {index_name}")
            index_success = self._index_document(parsed_doc, url, file_type, index_name)
            
            # 计算处理时间
            elapsed_time = time.time() - start_time
            
            # 返回结果
            if index_success:
                return {
                    "success": True,
                    "message": f"文档已成功解析并索引到 {index_name}",
                    "file": url,
                    "index": index_name,
                    "time_taken": f"{elapsed_time:.2f}秒"
                }
            else:
                return {
                    "success": False,
                    "error": "文档索引失败",
                    "file": url
                }
                
        except Exception as e:
            logger.error(f"处理文档时出错: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "file": url
            }