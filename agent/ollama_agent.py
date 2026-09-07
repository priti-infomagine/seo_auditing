from langchain.agents import create_agent
from langchain.tools import tool
from pydantic import BaseModel
# state_schema=MyState


@tool
def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"

agent = create_agent(model="ollama:north-mini-code-1.0", tools=tool,system_prompt="""  you are a mentor for a psychlogy student . 
                     your work is to explain the concepts of psychology in a simple way and provide examples to help the student understand the concepts better.
                     you should also provide a summary of the concepts and explain them in a way that is easy to understand.""",
                     #state_schema=MyState,
                     )


class Answer(BaseModel):
    summary: str
    confidence: float
    
result = agent.invoke({"messages": [{"role": "user", "content": "Summarize AI trends"}]})
result["structured_response"] 