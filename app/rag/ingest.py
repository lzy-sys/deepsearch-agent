"""知识库摄取 CLI

用法：
    uv run python -m app.rag.ingest --all            # 同步全部知识库
    uv run python -m app.rag.ingest --kb 电商行业     # 同步指定知识库
    uv run python -m app.rag.ingest --dir <路径>      # 同步指定目录
    uv run python -m app.rag.ingest --all --rebuild   # 强制重建
"""

import argparse
from pathlib import Path

from app.rag.indexer import sync_all_knowledge_bases, sync_knowledge_base_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="自研知识库 RAG 索引摄取")
    parser.add_argument("--kb", help="指定知识库名（docs/knowledge_base 下的子目录名）")
    parser.add_argument("--dir", help="指定知识库目录（直接对目录建索引）")
    parser.add_argument("--rebuild", action="store_true", help="强制重建（忽略内容哈希）")
    parser.add_argument("--all", action="store_true", help="同步全部知识库")
    args = parser.parse_args()

    if args.dir:
        kb_dir = Path(args.dir).resolve()
        if not kb_dir.is_dir():
            raise SystemExit(f"[error] 目录不存在: {kb_dir}")
        result = sync_knowledge_base_dir(kb_dir, force=args.rebuild)
        print(f"[ok] {result['kb_name']}: {result}")
        return

    if args.kb:
        from app.rag.kb_registry import get_kb_path

        kb_dir = get_kb_path(args.kb)
        if not kb_dir:
            raise SystemExit(f"[error] 知识库不存在: {args.kb}（可用 --all 查看）")
        result = sync_knowledge_base_dir(kb_dir, force=args.rebuild)
        print(f"[ok] {result['kb_name']}: {result}")
        return

    if args.all:
        results = sync_all_knowledge_bases(force=args.rebuild)
        for result in results:
            print(f"[ok] {result['kb_name']}: {result}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
