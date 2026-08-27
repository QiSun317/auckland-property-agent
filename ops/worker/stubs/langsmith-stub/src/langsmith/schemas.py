"""LangChain 旧兼容导出所需的 LangSmith 枚举。"""

from __future__ import annotations

from enum import Enum


class RunTypeEnum(str, Enum):
    LLM = "llm"
    CHAIN = "chain"
    TOOL = "tool"
    RETRIEVER = "retriever"
    EMBEDDING = "embedding"
    PROMPT = "prompt"
    PARSER = "parser"


class FeedbackSourceType(str, Enum):
    MODEL = "model"
