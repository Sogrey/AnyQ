import streamlit as st
import time
import random

# 模拟大模型的流式输出
def generate_streaming_response(prompt: str):
    # 这里只是模拟，实际应用中会调用你的大模型API
    responses = [
        "我正在思考如何回答你的问题...",
        "根据你提供的信息，我分析如下：",
        "首先，这个问题涉及到几个关键点：",
        "第一，我们需要考虑上下文环境；",
        "第二，要分析各种可能的解决方案；",
        "第三，权衡利弊后选择最佳方案；",
        "综合来看，我认为最佳答案是：",
        "保持开放心态，持续学习，不断迭代。"
    ]
    
    for text in responses:
        yield text
        time.sleep(random.uniform(0.3, 0.8))

# 主程序
def main():
    st.set_page_config(page_title="大模型流式输出演示", layout="wide")
    st.title("大模型流式输出演示")
    
    # 用户输入
    prompt = st.text_input("请输入你的问题：", "你能帮我解释一下人工智能吗？")
    
    # 生成按钮
    if st.button("生成回答"):
        # 显示流式输出
        st.write("### 模型正在生成回答：")
        
        # 使用空占位符来动态更新内容
        placeholder = st.empty()
        full_response = ""
        
        for chunk in generate_streaming_response(prompt):
            full_response += chunk + " "
            placeholder.markdown(full_response)
            
        st.success("回答生成完成！")

if __name__ == "__main__":
    main()