#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
保险条款智能问答系统的命令行界面模块
"""

import os
import sys
from typing import Optional, List, Dict, Any

# 明确导出的函数
__all__ = ['run_cli']

def run_cli(use_es: bool = True, use_embedding: bool = True) -> None:
    """
    运行命令行界面的问答系统
    
    Args:
        use_es: 是否使用Elasticsearch检索，默认为True
        use_embedding: 是否使用向量嵌入检索，默认为True
    """
    print("欢迎使用保险条款智能问答系统 (命令行版)")
    print(f"当前配置: Elasticsearch检索 {'启用' if use_es else '禁用'}, 向量嵌入检索 {'启用' if use_embedding else '禁用'}")
    
    # 导入必要的模块
    try:
        # 这里应该导入实际的问答处理模块
        # 例如: from qwen_agent.agents.doc_qa import DocQAAgent
        pass
    except ImportError as e:
        print(f"错误: 无法导入必要的模块: {e}")
        sys.exit(1)
    
    # 初始化问答系统
    # 这里应该初始化实际的问答系统
    # 例如: qa_agent = DocQAAgent(use_es=use_es, use_embedding=use_embedding)
    
    # 命令行交互循环
    while True:
        try:
            user_input = input("\n请输入您的问题 (输入'退出'或'exit'结束): ")
            
            if user_input.lower() in ['退出', 'exit', 'quit', 'q']:
                print("感谢使用，再见!")
                break
                
            if not user_input.strip():
                continue
                
            # 处理用户问题并获取回答
            # 这里应该调用实际的问答处理函数
            # 例如: answer = qa_agent.answer_question(user_input)
            
            # 临时模拟回答
            answer = f"您的问题是: {user_input}\n这是一个模拟回答。实际实现时，这里将返回基于保险条款的专业回答。"
            
            print("\n回答:")
            print(answer)
            
        except KeyboardInterrupt:
            print("\n操作被用户中断。感谢使用，再见!")
            break
        except Exception as e:
            print(f"\n处理问题时出错: {e}")

if __name__ == "__main__":
    # 直接运行此文件时的默认行为
    run_cli()