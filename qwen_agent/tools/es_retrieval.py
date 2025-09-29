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
from typing import Dict, List, Optional, Union, Any
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from qwen_agent.log import logger
from qwen_agent.settings import DEFAULT_MAX_REF_TOKEN
from qwen_agent.tools.base import BaseTool, register_tool
from qwen_agent.tools.doc_parser import Record
from qwen_agent.utils.utils import hash_sha256


@register_tool('es_retrieval')
class ESRetrieval(BaseTool):
    description = "使用Elasticsearch从给定文件列表中检索出和问题相关的内容"
    parameters = {
        'type': 'object',
        'properties': {
            'query': {
                'description': '用户的查询问题，用于在文档中匹配相关内容',
                'type': 'string',
            },
            'files': {
                'description': '待解析的文件路径列表，支持本地文件路径或可下载的http(s)链接',
                'type': 'array',
                'items': {
                    'type': 'string'
                }
            },
            'top_k': {
                'description': '返回的最相关文档片段数量',
                'type': 'integer',
                'default': 5
            }
        },
        'required': ['query', 'files'],
    }

    def __init__(self, cfg: Optional[Dict] = None):
        super().__init__(cfg)
        self.max_ref_token: int = self.cfg.get('max_ref_token', DEFAULT_MAX_REF_TOKEN)
        self.es_config = self.cfg.get('es_config', {
            'hosts': ["https://localhost:9200"],
            'basic_auth': ("elastic", "7dOzcb0RXmlXWza7VkRV"),
            'verify_certs': False,
            'request_timeout': 30
        })
        self.index_name = self.cfg.get('index_name', 'qwen_agent_docs')
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

    def _create_index_if_not_exists(self):
        """创建索引（如果不存在）"""
        if not self.es_client:
            return False
            
        try:
            if not self.es_client.indices.exists(index=self.index_name):
                mapping = {
                    "mappings": {
                        "properties": {
                            "content": {"type": "text", "analyzer": "standard"},
                            "metadata": {
                                "properties": {
                                    "source": {"type": "keyword"},
                                    "page": {"type": "integer"},
                                    "file_type": {"type": "keyword"},
                                    "chunk_id": {"type": "keyword"}
                                }
                            }
                        }
                    }
                }
                self.es_client.indices.create(index=self.index_name, body=mapping)
                logger.info(f"成功创建索引: {self.index_name}")
            return True
        except Exception as e:
            logger.error(f"创建索引失败: {str(e)}")
            return False

    def _index_documents(self, records: List[Record]) -> bool:
        """将文档索引到Elasticsearch"""
        if not self.es_client:
            return False
            
        if not self._create_index_if_not_exists():
            return False
            
        try:
            actions = []
            for record in records:
                # 安全处理文档内容，确保content属性存在
                content = getattr(record, 'content', '')
                doc_id = hash_sha256(f"{record.url}_{content[:50]}" if content else record.url)
                actions.append({
                    "_index": self.index_name,
                    "_id": doc_id,
                    "_source": {
                        "content": content,
                        "metadata": {
                            "source": record.url,
                            "file_type": getattr(record, 'file_type', 'unknown'),
                            "chunk_id": doc_id
                        }
                    }
                })
            
            if actions:
                success, failed = bulk(self.es_client, actions, refresh=True)
                failed_count = len(failed) if isinstance(failed, (list, tuple)) else 0
                logger.info(f"成功索引 {success} 个文档片段，失败 {failed_count} 个")
                return True
            return False
        except Exception as e:
            logger.error(f"索引文档失败: {str(e)}")
            return False

    def _search_documents(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """在Elasticsearch中搜索相关文档"""
        if not self.es_client:
            return []
            
        try:
            search_body = {
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["content"],
                        "type": "best_fields"
                    }
                },
                "highlight": {
                    "fields": {
                        "content": {}
                    }
                },
                "size": top_k
            }
            
            result = self.es_client.search(index=self.index_name, body=search_body)
            
            docs = []
            for hit in result["hits"]["hits"]:
                source = hit["_source"]
                metadata = source.get("metadata", {})
                
                # 构建文档对象
                doc = {
                    "page_content": source.get("content", ""),
                    "metadata": {
                        "source": metadata.get("source", ""),
                        "page": metadata.get("page", 0),
                        "score": hit["_score"]
                    }
                }
                
                # 如果有高亮内容，添加到结果中
                if "highlight" in hit and "content" in hit["highlight"]:
                    doc["highlight"] = hit["highlight"]["content"]
                
                docs.append(doc)
            
            return docs
        except Exception as e:
            logger.error(f"搜索文档失败: {str(e)}")
            return []

    def call(self, params: Union[str, Dict[str, Any]], docs: Optional[List[Record]] = None, **kwargs) -> List[Dict[str, Any]]:
        """使用Elasticsearch检索相关内容
        
        Args:
            params: 包含查询和文件列表的参数
            docs: 可选的已解析文档列表
            
        Returns:
            检索到的相关文档列表
        """
        # 自动填充files参数
        if isinstance(params, dict) and docs:
            params['files'] = [doc.url for doc in docs]
            
        params = self._verify_json_format_args(params)
        query = params.get('query', '')
        top_k = params.get('top_k', 5)
        
        if not query:
            return []
            
        # 如果提供了已解析的文档，则索引这些文档
        if docs:
            self._index_documents(docs)
            
        # 执行搜索
        results = self._search_documents(query, top_k)
        return results