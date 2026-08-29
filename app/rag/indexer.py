"""索引构建模块（ChromaDB 向量 + BM25）

设计要点：
- ChromaDB 只存「向量 + 元数据」（kb_name / doc_name / chunk_index / doc_hash），
  正文统一存 BM25 pickle，避免 chromadb 自动 embedding 与双份存储。
- 每次同步对该知识库全量重建（先清空再写入），天然幂等、不会重复。
- 向量模型不可用时自动降级为纯 BM25（Chroma 不写向量，检索时走 BM25）。
"""

import hashlib
import pickle
from pathlib import Path
from typing import Optional

import jieba
from rank_bm25 import BM25Okapi

from app.rag.chunker import chunk_text
from app.rag.config import (
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
    RAG_EMBEDDING_MODEL,
    get_index_root_path,
)
from app.rag.kb_registry import get_kb_path, list_knowledge_bases
from app.rag.loader import extract_text

_embedding_model = None


def get_index_root() -> Path:
    return Path(get_index_root_path())


def get_chroma_path() -> Path:
    return get_index_root() / "chroma"


def get_bm25_dir() -> Path:
    return get_index_root() / "bm25"


class _RaiseEmbeddingFunction:
    """禁止 chromadb 自动 embedding：所有向量必须显式传入"""

    def name(self) -> str:
        return "raise-no-auto-embedding"

    def __call__(self, input):  # noqa: ANN001
        raise NotImplementedError("必须显式传入 embeddings")


def _get_embedding_model():
    """懒加载 fastembed 中文向量模型（首次调用会联网下载模型权重）"""
    global _embedding_model
    if _embedding_model is None:
        from fastembed import TextEmbedding

        _embedding_model = TextEmbedding(model_name=RAG_EMBEDDING_MODEL)
    return _embedding_model


def _collection():
    """懒加载 ChromaDB 持久化客户端与集合"""
    import chromadb

    client = chromadb.PersistentClient(
        path=str(get_chroma_path()),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name="kb_chunks",
        metadata={"hnsw:space": "cosine"},
        embedding_function=_RaiseEmbeddingFunction(),
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _kb_doc_files(kb_dir: Path) -> list[Path]:
    """知识库目录下的可索引文档（排除 kb.yaml 等元数据文件）"""
    return sorted(p for p in kb_dir.iterdir() if p.is_file() and p.name != "kb.yaml")


def sync_knowledge_base_dir(kb_dir: Path, force: bool = False) -> dict:
    """全量重建单个知识库的索引（幂等）

    :param kb_dir: 知识库目录
    :param force: 兼容参数（当前总是全量重建，天然幂等）
    :return: 统计信息 {kb_name, docs, chunks, vectors}
    """
    del force  # 全量重建模式，无需单独处理
    kb_name = kb_dir.name

    # 1) 抽取 + 分块
    docs = _kb_doc_files(kb_dir)
    all_chunks: list[tuple[str, dict]] = []
    for doc_path in docs:
        text = extract_text(doc_path)
        digest = _file_hash(doc_path)
        for index, chunk in enumerate(chunk_text(text, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP)):
            all_chunks.append(
                (
                    chunk,
                    {
                        "kb_name": kb_name,
                        "doc_name": doc_path.name,
                        "chunk_index": index,
                        "doc_hash": digest,
                    },
                )
            )

    # 2) 向量索引（模型不可用时降级为纯 BM25）
    vectors_ok = False
    if all_chunks:
        try:
            embeddings = [
                e.tolist()
                for e in _get_embedding_model().embed([c[0] for c in all_chunks])
            ]
            collection = _collection()
            collection.delete(where={"kb_name": kb_name})
            ids = [
                f"{kb_name}::{meta['doc_name']}::{meta['chunk_index']}"
                for _, meta in all_chunks
            ]
            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=[meta for _, meta in all_chunks],
            )
            vectors_ok = True
        except Exception as exc:  # noqa: BLE001
            print(
                f"[RAG] 向量模型不可用（{exc}），知识库 '{kb_name}' 降级为纯 BM25 检索"
            )

    # 3) BM25 索引（正文的唯一来源）
    _save_bm25(kb_name, all_chunks)

    return {
        "kb_name": kb_name,
        "docs": len(docs),
        "chunks": len(all_chunks),
        "vectors": vectors_ok,
    }


def sync_knowledge_base(kb_name: str, force: bool = False) -> dict:
    """按名称同步知识库"""
    kb_dir = get_kb_path(kb_name)
    if not kb_dir:
        raise ValueError(f"知识库不存在: {kb_name}")
    return sync_knowledge_base_dir(kb_dir, force=force)


def sync_all_knowledge_bases(force: bool = False, skip_existing: bool = False) -> list[dict]:
    """同步全部知识库（服务启动时自动调用）

    :param force: 强制重建
    :param skip_existing: 已建立 BM25 索引的知识库跳过（避免启动时重复下载向量模型）
    """
    results = []
    for kb in list_knowledge_bases():
        try:
            if skip_existing and (get_bm25_dir() / f"{kb.name}.pkl").exists():
                continue
            results.append(sync_knowledge_base_dir(Path(kb.path), force=force))
        except Exception as exc:  # noqa: BLE001
            print(f"[RAG] 知识库 '{kb.name}' 同步失败: {exc}")
    return results


def _save_bm25(kb_name: str, chunks: list[tuple[str, dict]]) -> None:
    corpus = [list(jieba.cut(text)) for text, _ in chunks]
    payload = {
        "chunks": [text for text, _ in chunks],
        "metadatas": [meta for _, meta in chunks],
        "corpus": corpus,
    }
    get_bm25_dir().mkdir(parents=True, exist_ok=True)
    with (get_bm25_dir() / f"{kb_name}.pkl").open("wb") as f:
        pickle.dump(payload, f)


def load_bm25(kb_name: str) -> Optional[dict]:
    """加载 BM25 索引（返回 chunks/metadatas/bm25）"""
    path = get_bm25_dir() / f"{kb_name}.pkl"
    if not path.exists():
        return None
    with path.open("rb") as f:
        payload = pickle.load(f)
    return {
        "chunks": payload.get("chunks", []),
        "metadatas": payload.get("metadatas", []),
        "bm25": BM25Okapi(payload.get("corpus", [])),
    }


def ensure_indexed(kb_name: str) -> None:
    """若知识库尚未建立 BM25 索引则惰性同步一次（工具层调用）"""
    if (get_bm25_dir() / f"{kb_name}.pkl").exists():
        return
    sync_knowledge_base(kb_name)
