"""检索模块（BM25 + 向量，RRF 融合）

retrieve() 返回按相关度排序的 Top-K 分块：
- hybrid：BM25 与向量检索结果做 RRF（Reciprocal Rank Fusion）融合
- bm25：仅关键词检索（jieba 分词）
- vector：仅向量语义检索
任一检索器不可用时自动降级，保证链路可用。
"""

import jieba

from app.rag.config import RAG_RETRIEVER, RAG_RRF_K, RAG_TOP_K
from app.rag.indexer import _collection, _get_embedding_model, load_bm25
from app.rag.models import Chunk


def _rrf_score(bm25_rank, vector_rank) -> float:
    score = 0.0
    if bm25_rank is not None:
        score += 1.0 / (RAG_RRF_K + bm25_rank + 1)
    if vector_rank is not None:
        score += 1.0 / (RAG_RRF_K + vector_rank + 1)
    return round(score, 6)


def retrieve(kb_name: str, question: str, top_k: int | None = None) -> list[Chunk]:
    """检索知识库，返回 Top-K 分块（含来源文档与相关度）"""
    top_k = top_k or RAG_TOP_K
    mode = RAG_RETRIEVER
    candidates: dict[tuple, dict] = {}

    # 正文映射：(doc_name, chunk_index) -> text（向量检索只返回元数据，正文从 BM25 取）
    loaded = load_bm25(kb_name)
    text_by_key: dict[tuple, str] = {}
    if loaded is not None:
        for idx, meta in enumerate(loaded["metadatas"]):
            text_by_key[(meta.get("doc_name"), meta.get("chunk_index"))] = loaded["chunks"][idx]

    # ---------- 向量检索 ----------
    if mode in ("hybrid", "vector"):
        try:
            query_embedding = list(_get_embedding_model().embed([question]))[0]
            collection = _collection()
            n_results = max(top_k * 3, 10)
            result = collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=n_results,
                where={"kb_name": kb_name},
                include=["metadatas", "distances"],
            )
            metadatas = (result.get("metadatas") or [[]])[0]
            for rank, meta in enumerate(metadatas):
                key = (meta.get("doc_name"), meta.get("chunk_index"))
                if key not in text_by_key:
                    continue
                entry = candidates.setdefault(
                    key, {"text": text_by_key[key], "meta": meta, "bm25_rank": None, "vector_rank": None}
                )
                entry["vector_rank"] = rank
        except Exception as exc:  # noqa: BLE001
            print(f"[RAG] 向量检索不可用，降级 BM25：{exc}")
            if mode == "hybrid":
                mode = "bm25"

    # ---------- BM25 检索 ----------
    if mode in ("hybrid", "bm25"):
        if loaded is not None:
            chunks = loaded["chunks"]
            metadatas = loaded["metadatas"]
            bm25 = loaded["bm25"]
            tokenized_query = list(jieba.cut(question))
            scores = bm25.get_scores(tokenized_query)
            order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            for rank, idx in enumerate(order[: top_k * 3]):
                if scores[idx] <= 0:
                    break
                meta = metadatas[idx]
                key = (meta.get("doc_name"), meta.get("chunk_index"))
                entry = candidates.setdefault(
                    key,
                    {"text": chunks[idx], "meta": meta, "bm25_rank": None, "vector_rank": None},
                )
                entry["bm25_rank"] = rank

    if not candidates:
        return []

    # ---------- RRF 融合排序 ----------
    scored: list[Chunk] = []
    for key, entry in candidates.items():
        scored.append(
            Chunk(
                kb_name=kb_name,
                doc_name=key[0],
                chunk_index=key[1],
                text=entry["text"],
                score=_rrf_score(entry["bm25_rank"], entry["vector_rank"]),
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]
