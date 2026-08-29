"""自研知识库 RAG 数据模型

知识库 / 分块 / 检索结果的结构化定义，供索引器、检索器与工具层复用。
"""

from pydantic import BaseModel


class KnowledgeBase(BaseModel):
    """一个知识库（对应 RAG_KB_DIR 下的一个子目录）"""

    name: str
    description: str = ""
    path: str = ""
    doc_count: int = 0
    chunk_count: int = 0


class Chunk(BaseModel):
    """检索命中的文本分块"""

    kb_name: str
    doc_name: str
    chunk_index: int
    text: str
    score: float = 0.0


class QueryResult(BaseModel):
    """一次知识库问答的结果"""

    kb_name: str
    question: str
    answer: str
    sources: list[Chunk] = []
