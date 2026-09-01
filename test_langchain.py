from langchain_ollama import ChatOllama

model = ChatOllama(
    model="qwen3:1.7b"
)

response = model.invoke(
    "tell me the current situation of the social mindset in india"
)

print(response.content)