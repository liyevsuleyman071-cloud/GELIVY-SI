"""Süni intellekt məntiqi (Groq + LangGraph). Başqa heç nə burada olmur."""

import os
import re
from typing import List, Optional, Union

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, MessagesState, StateGraph

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
MAX_HISTORY = 20  # modelə göndərilən son mesajların sayı

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY tapılmadı! Zəhmət olmasa .env faylına əlavə edin.")

DEFAULT_SYSTEM_PROMPT = (
    "Sən Gelivy AI köməkçisisən. İstifadəçiyə onun yazdığı dildə, aydın və dəqiq cavab ver. "
    "Lazım olduqda Markdown istifadə et."
)


class Bot:
    def __init__(self, model=None, system_prompt: str = DEFAULT_SYSTEM_PROMPT):
        self.model = model or ChatGroq(
            model=GROQ_MODEL,
            groq_api_key=GROQ_API_KEY,
            temperature=0.3,
            max_tokens=1000,
        )
        self.system_prompt = system_prompt
        self.graph = self._build_graph()  # bir dəfə yığılır, hər sorğuda yenidən yox

    def _call_model(self, state: MessagesState):
        response = self.model.invoke(state["messages"])
        return {"messages": [response]}

    def _build_graph(self):
        workflow = StateGraph(MessagesState)
        workflow.add_node("agent", self._call_model)
        workflow.set_entry_point("agent")
        workflow.add_edge("agent", END)
        return workflow.compile()

    def ask_ai(self, history: Union[str, List[dict]]) -> str:
        """history: [{"role": "human"|"ai", "content": "..."}] siyahısı (və ya tək mətn)."""
        if isinstance(history, str):
            history = [{"role": "human", "content": history}]

        messages = [SystemMessage(content=self.system_prompt)]
        for item in history[-MAX_HISTORY:]:
            message_class = HumanMessage if item.get("role") == "human" else AIMessage
            messages.append(message_class(content=item.get("content", "")))

        result = self.graph.invoke({"messages": messages})
        return self._clean(result["messages"][-1].content)

    @staticmethod
    def _clean(content) -> str:
        if isinstance(content, list):  # bəzi modellər hissələrlə qaytarır
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        # Qwen kimi modellər <think>...</think> daxili fikirlərini də qaytara bilir.
        content = re.sub(r"<think>.*?</think>", "", str(content), flags=re.DOTALL)
        return content.strip()


bot = Bot()
