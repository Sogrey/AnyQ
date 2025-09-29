# text-embedding-v4：属于Qwen3-Embedding系列
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
completion = client.embeddings.create(
    model="text-embedding-v4",
    input="衣服的质量杠杠的，很漂亮，不枉我等了这么久啊，喜欢，以后还来这里买",
    dimensions=1024,  # 指定向量维度
    encoding_format="float"
)
print(completion.model_dump_json())