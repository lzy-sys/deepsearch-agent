"""向量化模型模块

基于 LangChain 的 FastEmbedEmbeddings（fastembed / ONNX）懒加载单例。
向量模型首次使用需联网下载权重；不可用时不在此处抛错，
由索引/检索层捕获并自动降级为纯 BM25 检索。
"""

_embedding_model = None


def get_embedding_model():
    """懒加载并返回进程级复用的 embedding 模型实例"""
    global _embedding_model
    if _embedding_model is None:
        from langchain_community.embeddings import FastEmbedEmbeddings

        from app.rag.config import RAG_EMBEDDING_MODEL

        _embedding_model = FastEmbedEmbeddings(model_name=RAG_EMBEDDING_MODEL)
    return _embedding_model