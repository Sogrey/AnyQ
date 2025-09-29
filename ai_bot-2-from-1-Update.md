# ai_bot-2-from-1-Update.md

## 版本升级说明
从 `ai_bot-1.py` 升级到 `ai_bot-2.py`

### 核心变更

1. **新增功能模块**
   - 新增AI绘画工具`my_image_gen`
   ```python
   @register_tool('my_image_gen')
   class MyImageGen(BaseTool):
       description = 'AI绘画服务...'
   ```
   - 添加图像处理流程（生成→下载→处理→展示）
   - 实现文档目录自动扫描
   ```python
   file_dir = os.path.join(os.path.dirname(__file__), 'docs')
   ```

2. **架构优化**
   - 重构工具注册机制（使用`@register_tool`装饰器）
   - 分离交互模式（GUI/TUI）
   ```python
   def app_gui(): ...
   def app_tui(): ...
   ```
   - 增强错误处理（try-catch块）

3. **配置改进**
   - 环境变量管理
   ```python
   os.getenv('DASHSCOPE_API_KEY')
   ```
   - LLM参数可配置化
   ```python
   llm_cfg = {
       'model': 'qwen-max',
       'generate_cfg': {'top_p': 0.8}
   }
   ```

### 升级步骤

1. **环境准备**
   ```bash
   pip install qwen-agent urllib3 json5
   ```

2. **文件调整**
   - 创建`docs`目录存放待处理文档
   - 配置`.env`文件：
   ```
   DASHSCOPE_API_KEY=your_api_key
   ```

3. **验证测试**
   - 运行GUI模式：`python ai_bot-2.py`
   - 测试终端模式：取消注释`app_tui()`

### 注意事项
1. 确保`docs`目录存在且可读
2. API Key需有足够权限
3. 图像生成服务可能需要VPN访问