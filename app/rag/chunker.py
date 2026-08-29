"""文本分块模块

基于 LangChain RecursiveCharacterTextSplitter 按字符切块，
优先在段落、换行、句末标点等分隔符处断块，相邻块保留重叠。
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

# 中文友好分隔符：递归分块时优先在段落、换行、句号处断块
_CHINESE_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """把长文本切成若干分块

    :param text: 原始文本
    :param chunk_size: 单块最大字符数
    :param overlap: 相邻块重叠字符数
    :return: 非空分块列表
    """
    text = (text or "").strip()
    if not text or chunk_size <= 0:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=_CHINESE_SEPARATORS,
        length_function=len,
        strip_whitespace=True,
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]