import re
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
HEADING_LINE_RE = re.compile(r"^#{1,6}\s.*$", re.MULTILINE)


def _has_substantive_content(text: str, min_chars: int = 20) -> bool:
    """Reject fragments with too little text after removing headings, images, and links."""
    stripped = HEADING_LINE_RE.sub("", text)
    stripped = IMAGE_RE.sub("", stripped)
    stripped = LINK_RE.sub("", stripped)
    return len(stripped.strip()) >= min_chars


def chunk_document(content: str) -> list[dict]:
    """Split Markdown into overlapping chunks with heading metadata, skipping sparse fragments."""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )
    header_splits = header_splitter.split_text(content)

    size_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    splits = size_splitter.split_documents(header_splits)

    return [
        {"content": doc.page_content, "metadata": doc.metadata}
        for doc in splits
        if _has_substantive_content(doc.page_content)
    ]
