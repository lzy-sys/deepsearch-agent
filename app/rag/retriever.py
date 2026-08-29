"""检索模块（LangChain：向量 + BM25 混合检索）

get_retriever() 按 RAG_RETRIEVER 配置返回指定知识库的检索器：
- hybrid：EnsembleRetriever 加权融合向量检索与 BM25 检索
- bm25：仅关键词检索（jieba 分词）
- vector：仅向量语义检索
任一检索器不可用时自动降级，保证链路可用。
"""

import jieba
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.rag.config import RAG_RETRIEVER, RAG_TOP_K
from app.rag.indexer import _vectorstore, ensure_indexed, load_bm25_documents
from app.rag.models import Chunk


def _vector_retriever(kb_name: str, k: int) -> BaseRetriever:
    """按知识库过滤的向量检索器"""
    vectorstore = _vectorstore()
    return vectorstore.as_retriever(
        search_kwargs={"k": k, "filter": {"kb_name": kb_name}}
    )


def _bm25_retriever(kb_name: str, k: int) -> BM25Retriever | None:
    """基于 jieba 分词构建的知识库 BM25 检索器"""
    documents = load_bm25_documents(kb_name)
    if not documents:
        return None
    return BM25Retriever.from_documents(
        documents,
        preprocess_func=lambda text: list(jieba.cut(text)),
        k=k,
    )


# 检索器进程级缓存：同一次会话内多次提问复用同一构建结果，
# 避免每次都对全部文档重新做 jieba 分词与 BM25 构建
_retriever_cache: dict[tuple[str, str, int], BaseRetriever] = {}


def invalidate_retriever_cache(kb_name: str | None = None) -> None:
    """使检索器缓存失效（知识库重索引后由 indexer 调用；kb_name 为空时清空全部）"""
    global _retriever_cache
    if kb_name is None:
        _retriever_cache.clear()
    else:
        _retriever_cache = {k: v for k, v in _retriever_cache.items() if k[0] != kb_name}


def get_retriever(kb_name: str, top_k: int | None = None) -> BaseRetriever:
    """构建指定知识库的检索器（hybrid / bm25 / vector，向量不可用时自动降级）"""
    ensure_indexed(kb_name)
    k = top_k or RAG_TOP_K
    mode = RAG_RETRIEVER
    cache_key = (kb_name, mode, k)

    cached = _retriever_cache.get(cache_key)
    if cached is not None:
        return cached

    bm25 = _bm25_retriever(kb_name, k)

    if mode in ("hybrid", "vector"):
        try:
            vector = _vector_retriever(kb_name, k)
            if mode == "vector":
                _retriever_cache[cache_key] = vector
                return vector
            if bm25 is None:
                _retriever_cache[cache_key] = vector
                return vector
            retriever = EnsembleRetriever(retrievers=[vector, bm25], weights=[0.5, 0.5])
            _retriever_cache[cache_key] = retriever
            return retriever
        except Exception as exc:  # noqa: BLE001
            print(f"[RAG] 向量检索不可用，降级 BM25：{exc}")

    if bm25 is None:
        raise RuntimeError(f"知识库 '{kb_name}' 没有任何可用的检索器")
    _retriever_cache[cache_key] = bm25
    return bm25


def doc_to_chunk(doc: Document, kb_name: str, rank: int = 0) -> Chunk:
    """把 LangChain Document 转成工具层使用的 Chunk 模型

    similarity_score/score 是子检索器写入的真实相关度；EnsembleRetriever
    融合排序后不写分数，此时用融合排序位置的倒数作为展示分。
    """
    score = doc.metadata.get("similarity_score", doc.metadata.get("score"))
    if score is None:
        score = 1.0 / (rank + 1)
    return Chunk(
        kb_name=kb_name,
        doc_name=doc.metadata.get("doc_name", ""),
        chunk_index=doc.metadata.get("chunk_index", 0),
        text=doc.page_content,
        score=round(float(score), 4),
    )


def retrieve(kb_name: str, question: str, top_k: int | None = None) -> list[Chunk]:
    """检索知识库，返回 Top-K 分块（含来源文档与相关度）"""
    k = top_k or RAG_TOP_K
    # EnsembleRetriever 融合两个子检索器后块数可能超过 K，这里收敛到 Top-K
    documents = get_retriever(kb_name, k).invoke(question)[:k]
    return [doc_to_chunk(doc, kb_name, rank) for rank, doc in enumerate(documents)]