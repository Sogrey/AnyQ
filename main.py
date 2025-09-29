#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
保险条款智能问答系统主程序入口
"""

import os
import sys
import argparse
from dotenv import load_dotenv

def main():
    """主程序入口函数"""
    parser = argparse.ArgumentParser(description='保险条款智能问答系统')
    parser.add_argument('--mode', type=str, default='web', choices=['web', 'cli'],
                        help='运行模式: web (Web界面) 或 cli (命令行界面)')
    parser.add_argument('--port', type=int, default=8501,
                        help='Web服务端口号 (默认: 8501)')
    parser.add_argument('--no-es', action='store_true',
                        help='禁用Elasticsearch检索')
    parser.add_argument('--no-embedding', action='store_true',
                        help='禁用向量嵌入检索')
    
    args = parser.parse_args()
    
    # 加载环境变量
    load_dotenv(override=True)
    
    # 检查必要的环境变量
    required_env_vars = ['DASHSCOPE_API_KEY', 'ES_HOST', 'ES_USER', 'ES_PASSWORD']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"错误: 缺少以下必需的环境变量: {', '.join(missing_vars)}")
        print("请在 .env 文件中设置这些变量")
        sys.exit(1)
    
    # 根据运行模式启动相应的界面
    if args.mode == 'web':
        # 使用Streamlit启动Web界面
        import subprocess
        cmd = [
            "streamlit", "run", "ai_bot-7.py",
            "--server.port", str(args.port),
            "--server.address", "localhost"
        ]
        
        print(f"正在启动Web界面，端口: {args.port}...")
        subprocess.run(cmd)
    else:
        # 命令行界面模式 - 导入CLI模块并运行
        try:
            # 从当前目录显式导入run_cli函数
            from .cli_interface import run_cli
            use_es = not args.no_es
            use_embedding = not args.no_embedding
            run_cli(use_es=use_es, use_embedding=use_embedding)
        except ImportError:
            print("错误: 命令行界面模块未找到。请确保 cli_interface.py 文件存在。")
            sys.exit(1)

if __name__ == "__main__":
    main()