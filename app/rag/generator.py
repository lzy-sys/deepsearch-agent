"""回答生成模块

把检索到的分块拼成带来源的上下文，复用项目统一大模型生成回答，
并显式标注来源文档，减少幻觉。
"""

from app.agent.llm import model
from app.rag.models import Chunk

SYSTEM_PROMPT = (
    "你是一个严谨的企业内部知识库助手。你只能依据提供的检索内容回答问题，"
    "不得编造检索内容之外的细节；引用关键信息时标注来源文档名；"
    "若检索内容不足以回答，请明确说明缺少哪些信息。"
)


def build_context(chunks: list[Chunk]) -> str:
    """把检索分块拼成带来源的上下文文本"""
    parts = []
    for index, chunk in enumerate(chunks, start=1):
        parts.append(f"[来源{index}] 文档：{chunk.doc_name}\n{chunk.text}")
    return "\n\n".join(parts)


def generate_answer(kb_name: str, question: str, chunks: list[Chunk]) -> str:
    """基于检索内容生成回答（无命中时返回明确提示）"""
    if not chunks:
        return "未在知识库中检索到相关内容，请尝试换一个知识库或调整问题表述。"

    context = build_context(chunks)
    prompt = (
        f"知识库：{kb_name}\n\n"
        f"检索到的内容：\n{context}\n\n"
        f"用户问题：{question}\n\n"
        "要求：\n"
        "1. 依据检索内容回答，引用时标注来源文档名；\n"
        "2. 回答结构清晰、结论明确；\n"
        "3. 若检索内容不足，明确指出缺失部分。"
    )
    try:
        response = model.invoke([("system", SYSTEM_PROMPT), ("human", prompt)])
        return str(getattr(response, "content", "") or "").strip()
    except Exception as exc:  # noqa: BLE001
        return f"生成回答失败：{exc}"
