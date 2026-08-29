"""文本分块模块

滑动窗口按字符切块，尽量在段落/句号处断块，相邻块保留重叠，
保证检索单元信息相对完整。
"""


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

    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)
        chunk = text[start:end]

        # 非末尾块：优先在换行或句号处断块，避免切碎句子
        if end < length:
            cut = max(chunk.rfind("\n"), chunk.rfind("。"), chunk.rfind("."))
            if cut > chunk_size * 0.5:
                chunk = chunk[: cut + 1]
                end = start + len(chunk)

        cleaned = chunk.strip()
        if cleaned:
            chunks.append(cleaned)

        if end >= length:
            break
        start = max(end - overlap, start + 1)

    return chunks
