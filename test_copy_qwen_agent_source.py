"""
将已安装的qwen-agent源码包拷贝到本地项目目录
用于后续自定义修改界面
"""

import os
import sys
import shutil
import site
import importlib.util

def find_package_path(package_name):
    """查找已安装包的路径"""
    try:
        spec = importlib.util.find_spec(package_name)
        if spec is None:
            return None
        return os.path.dirname(os.path.dirname(spec.origin))
    except (ImportError, AttributeError):
        return None

def copy_package_to_local(package_name, target_dir="./local_packages"):
    """将包复制到本地目录"""
    package_path = find_package_path(package_name)
    
    if not package_path:
        print(f"未找到包 {package_name}，请确保已安装")
        return False
    
    print(f"找到 {package_name} 在: {package_path}")
    
    # 创建目标目录
    os.makedirs(target_dir, exist_ok=True)
    
    # 目标路径
    target_path = os.path.join(target_dir, package_name)
    
    # 如果目标已存在，先删除
    if os.path.exists(target_path):
        shutil.rmtree(target_path)
    
    # 复制包目录
    source_package_dir = os.path.join(package_path, package_name)
    if os.path.exists(source_package_dir):
        print(f"复制 {source_package_dir} 到 {target_path}")
        shutil.copytree(source_package_dir, target_path)
        print(f"成功复制 {package_name} 到本地目录 {target_dir}")
        return True
    else:
        print(f"未找到包目录: {source_package_dir}")
        return False

if __name__ == "__main__":
    # 复制qwen-agent包到本地
    success = copy_package_to_local("qwen_agent", "./local_packages")
    
    if success:
        print("\n操作完成！")
        print("现在您可以修改本地的qwen_agent代码，并通过以下方式使用本地版本:")
        print("1. 在代码中使用 import sys; sys.path.insert(0, './local_packages') 来优先使用本地版本")
        print("2. 或者创建一个.pth文件添加到site-packages目录")
    else:
        print("\n操作失败！请确保已安装qwen-agent包")