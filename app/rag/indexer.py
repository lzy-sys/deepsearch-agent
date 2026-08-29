"""索引构建模块（LangChain：Chroma 向量 + BM25 + 增量索引）

设计要点：
- 文档统一为 LangChain Document（page_content + metadata: kb_name/doc_name/chunk_index/doc_hash）。
- 向量索引由 langchain-chroma 的 Chroma vectorstore 管理（单集合，cosine，禁用自动 embedding）。
- 增量索引使用 langchain_core.indexing.index() + SQLRecordManager（SQLite 记录文档 hash），
  只处理新增/变更/删除的文档，替代手写全量重建。
- BM25 语料以 Document 列表 pickle 持久化（每知识库一个文件），检索时重建 BM25Retriever。
- 向量模型不可用时自动降级为纯 BM25（不写向量索引）。
"""

import hashlib
import os
import pickle
from pathlib import Path

from langchain_community.indexes._sql_record_manager import SQLRecordManager
from langchain_core.documents import Document
from langchain_core.indexing import index

from app.rag.chunker import chunk_text
from app.rag.config import (
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
    RAG_RETRIEVER,
    get_index_root_path,
)
from app.rag.embeddings import get_embedding_model
from app.rag.kb_registry import get_kb_path, list_knowledge_bases
from app.rag.loader import extract_text

# Chroma 向量集合名（同一持久化目录下唯一）
RAG_COLLECTION_NAME = "kb_chunks"

_vectorstore_instance = None


def get_index_root() -> Path:
    return Path(get_index_root_path())


def get_chroma_path() -> Path:
    return get_index_root() / "chroma"


def get_bm25_dir() -> Path:
    return get_index_root() / "bm25"


def _collection():
    """返回底层 Chroma collection（供统计等直接查询元数据）"""
    return _vectorstore()._collection


def _vectorstore():
    """懒加载进程级 Chroma vectorstore 单例"""
    from langchain_chroma import Chroma

    global _vectorstore_instance
    if _vectorstore_instance is None:
        _vectorstore_instance = Chroma(
            collection_name=RAG_COLLECTION_NAME,
            persist_directory=str(get_chroma_path()),
            embedding_function=get_embedding_model(),
            collection_metadata={"hnsw:space": "cosine"},
        )
    return _vectorstore_instance


def _get_record_manager(kb_name: str) -> SQLRecordManager:
    """按知识库构建 SQLite 记录管理器（记录文档 hash，支撑增量索引）"""
    get_index_root().mkdir(parents=True, exist_ok=True)
    records_path = get_index_root() / "records.sqlite"
    record_manager = SQLRecordManager(
        namespace=f"kb/{kb_name}",
        db_url=f"sqlite:///{records_path.as_posix()}",
    )
    record_manager.create_schema()
    return record_manager


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
    """同步单个知识库索引（默认增量；force 时全量重建）

    :param kb_dir: 知识库目录
    :param force: 强制全量重建（cleanup=full + 强制更新全部文档）
    :return: 统计信息 {kb_name, docs, chunks, vectors}
    """
    kb_name = kb_dir.name

    # 1) 抽取 + 分块为 LangChain Document（正文与元数据统一在此表示）
    doc_files = _kb_doc_files(kb_dir)
    documents: list[Document] = []
    for doc_path in doc_files:
        text = extract_text(doc_path)
        digest = _file_hash(doc_path)
        for chunk_index, chunk in enumerate(
            chunk_text(text, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP)
        ):
            documents.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "kb_name": kb_name,
                        "doc_name": doc_path.name,
                        "chunk_index": chunk_index,
                        "doc_hash": digest,
                    },
                )
            )

    # 2) 向量索引（增量；空知识库/force 时用 full 清理已删除文档的残留；
    #    纯 BM25 模式跳过向量步骤，保证无向量环境下检索可降级）
    vectors_ok = False
    try:
        if RAG_RETRIEVER != "bm25":
            index(
                documents,
                _get_record_manager(kb_name),
                _vectorstore(),
                cleanup="full" if (force or not documents) else "incremental",
                source_id_key="doc_name",
                force_update=force,
                key_encoder="sha256",
                # 一次 batch 处理整个知识库：避免跨 batch 的增量清理边界效应
                # （同一文档的块被拆分到多个 batch 时，前序 batch 的 cleanup
                # 会误删尚未刷新时间戳的块并重复嵌入）
                batch_size=1000,
            )
        vectors_ok = True
    except Exception as exc:  # noqa: BLE001
        print(
            f"[RAG] 向量索引不可用（{exc}），知识库 '{kb_name}' 降级为纯 BM25 检索"
        )

    # 3) BM25 语料持久化：向量索引成功后才原子替换，
    #    避免"新 BM25 + 旧向量"的混合代次让已删除文档的块仍被检索到
    if vectors_ok:
        _save_bm25_documents(kb_name, documents)
    else:
        print(
            f"[RAG] 知识库 '{kb_name}' 向量索引失败，BM25 语料保持上一版本"
            "（可执行 --rebuild 尝试重建）"
        )

    # 4) 索引状态已变化，使该知识库的检索器缓存失效，避免检索到旧语料
    from app.rag.retriever import invalidate_retriever_cache

    invalidate_retriever_cache(kb_name)

    return {
        "kb_name": kb_name,
        "docs": len({d.metadata["doc_name"] for d in documents}),
        "chunks": len(documents),
        "vectors": vectors_ok,
    }


def sync_knowledge_base(kb_name: str, force: bool = False) -> dict:
    """按名称同步知识库"""
    kb_dir = get_kb_path(kb_name)
    if not kb_dir:
        raise ValueError(f"知识库不存在: {kb_name}")
    return sync_knowledge_base_dir(kb_dir, force=force)


def sync_all_knowledge_bases(
    force: bool = False, skip_existing: bool = False
) -> list[dict]:
    """同步全部知识库（服务启动时自动调用）

    :param force: 强制全量重建
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


def _save_bm25_documents(kb_name: str, documents: list[Document]) -> None:
    """原子持久化 BM25 语料（先写临时文件再替换，避免并发读方读到损坏的 pickle）"""
    get_bm25_dir().mkdir(parents=True, exist_ok=True)
    target = get_bm25_dir() / f"{kb_name}.pkl"
    tmp_path = target.with_suffix(".pkl.tmp")
    with tmp_path.open("wb") as f:
        pickle.dump(documents, f)
    os.replace(tmp_path, target)


def load_bm25_documents(kb_name: str) -> list[Document]:
    """加载 BM25 语料（分块 Document 列表，供检索时重建 BM25Retriever）"""
    path = get_bm25_dir() / f"{kb_name}.pkl"
    if not path.exists():
        return []
    with path.open("rb") as f:
        return pickle.load(f)


def ensure_indexed(kb_name: str) -> None:
    """若知识库尚未建立 BM25 索引则惰性同步一次（工具层调用）"""
    if (get_bm25_dir() / f"{kb_name}.pkl").exists():
        return
    sync_knowledge_base(kb_name)