"""自研知识库 RAG 配置模块

集中读取 RAG_* 环境变量，供摄取、索引、检索与生成模块复用。
与项目其他模块保持一致，使用 python-dotenv 向上查找 .env。
"""

import os
from typing import Optional

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# 知识库根目录：每个子目录 = 一个知识库
RAG_KB_DIR: str = os.getenv("RAG_KB_DIR", "docs/knowledge_base")

# 索引目录：ChromaDB 持久化目录 + BM25 pickle
RAG_INDEX_DIR: str = os.getenv("RAG_INDEX_DIR", "data/rag")

# 分块参数
RAG_CHUNK_SIZE: int = _get_int("RAG_CHUNK_SIZE", 512)
RAG_CHUNK_OVERLAP: int = _get_int("RAG_CHUNK_OVERLAP", 64)

# 检索参数
RAG_TOP_K: int = _get_int("RAG_TOP_K", 4)
RAG_RETRIEVER: str = os.getenv("RAG_RETRIEVER", "hybrid")  # hybrid | bm25 | vector

# 向量化模型（fastembed / ONNX，中文推荐 BAAI/bge-small-zh-v1.5）
RAG_EMBEDDING_MODEL: str = os.getenv(
    "RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"
)


def get_kb_root_path() -> "os.PathLike[str]":
    """返回知识库根目录（相对项目根解析）"""
    from pathlib import Path

    root = Path(RAG_KB_DIR)
    if not root.is_absolute():
        # app/rag/config.py -> parents[2] = 项目根目录
        root = Path(__file__).resolve().parents[2] / RAG_KB_DIR
    return root


def get_index_root_path() -> "os.PathLike[str]":
    """返回索引根目录（相对项目根解析）"""
    from pathlib import Path

    root = Path(RAG_INDEX_DIR)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / RAG_INDEX_DIR
    return root
