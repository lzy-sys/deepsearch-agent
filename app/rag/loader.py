"""文档文本抽取模块

支持 PDF（pypdf）、Word（python-docx）、Markdown/TXT 等文本格式，
供知识库摄取链路统一使用。
"""

from pathlib import Path


def extract_text(path: Path) -> str:
    """按文件后缀抽取文本；未知后缀按 UTF-8 文本兜底"""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    return _extract_text(path)


def _extract_pdf(path: Path) -> str:
    import pypdf

    reader = pypdf.PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")
