"""
AI搜索问答应用 - 使用本地修改版的qwen-agent
"""

import sys
import os

# 添加本地包路径，确保优先使用本地版本的qwen-agent
sys.path.insert(0, './')

# 导入qwen-agent相关模块
try:
    import qwen_agent
    from qwen_agent import Agent, MultiAgentHub
    from qwen_agent.llm import get_chat_model
    from qwen_agent.tools import TOOL_REGISTRY, BaseTool
    from qwen_agent.tools import DocParser, SimpleDocParser
    
    print(f"成功导入本地版本的qwen-agent: {qwen_agent.__file__}")
    print(f"qwen-agent版本: {qwen_agent.__version__}")
except ImportError as e:
    print(f"导入qwen-agent失败: {e}")
    print("请确保已安装qwen-agent并运行了copy_qwen_agent_source.py脚本")
    sys.exit(1)

# 配置文档路径
DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")

def main():
    """主函数"""
    print("初始化AI搜索问答系统...")
    print(f"文档目录: {DOCS_DIR}")
    
    # 检查文档目录
    if not os.path.exists(DOCS_DIR):
        print(f"错误: 文档目录不存在: {DOCS_DIR}")
        return
    
    # 列出可用文档
    docs = [f for f in os.listdir(DOCS_DIR) if os.path.isfile(os.path.join(DOCS_DIR, f))]
    print(f"找到{len(docs)}个文档:")
    for doc in docs:
        print(f"  - {doc}")
    
    # 列出qwen-agent的主要模块
    print("\nqwen-agent主要模块:")
    modules = [name for name in os.listdir('./qwen_agent') 
               if os.path.isdir(os.path.join('./qwen_agent', name)) 
               and not name.startswith('__')]
    for module in modules:
        print(f"  - {module}")
    
    # 列出可用的工具
    print("\n可用的工具:")
    for tool_name in TOOL_REGISTRY:
        print(f"  - {tool_name}")
    
    print("\n系统准备就绪，可以开始问答...")
    print("您可以修改qwen_agent目录下的源码来自定义界面和功能")

if __name__ == "__main__":
    main()