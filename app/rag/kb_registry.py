"""知识库注册表模块

负责发现 RAG_KB_DIR 下的知识库：每个子目录 = 一个知识库，
目录名 = 知识库名，可选 kb.yaml 提供 name / description。
"""

from pathlib import Path
from typing import Optional

import yaml

from app.rag.config import get_kb_root_path
from app.rag.models import KnowledgeBase


def get_kb_root() -> Path:
    return Path(get_kb_root_path())


def load_kb_meta(kb_dir: Path) -> dict:
    """读取 kb.yaml（可选），返回 {name, description}"""
    meta = {"name": kb_dir.name, "description": ""}
    yaml_path = kb_dir / "kb.yaml"
    if yaml_path.exists():
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            meta["name"] = str(data.get("name", kb_dir.name))
            meta["description"] = str(data.get("description", ""))
        except Exception:  # noqa: BLE001
            pass
    return meta


def list_knowledge_bases() -> list[KnowledgeBase]:
    """列出全部知识库（目录级信息，不含索引统计）"""
    root = get_kb_root()
    if not root.exists():
        return []
    kbs: list[KnowledgeBase] = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            meta = load_kb_meta(child)
            kbs.append(
                KnowledgeBase(
                    name=meta["name"],
                    description=meta["description"],
                    path=str(child),
                )
            )
    return kbs


def get_kb_path(name: str) -> Optional[Path]:
    """按知识库名（或目录名）查找知识库目录"""
    for kb in list_knowledge_bases():
        if kb.name == name or Path(kb.path).name == name:
            return Path(kb.path)
    return None
