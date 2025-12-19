"""Utilities for downloading and chunking documents."""

import os
import tempfile
from typing import Any, Dict, List

import boto3
from PyPDF2 import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken


class DocumentProcessingService:
    """Process documents stored in S3 into text chunks."""

    SUPPORTED_FILE_TYPES = {"pdf", "txt", "docx", "doc"}

    def __init__(self):
        self.s3_client = boto3.client("s3")
        self.bucket_name = os.environ.get("KB_BUCKET_NAME")
        if not self.bucket_name:
            raise ValueError("KB_BUCKET_NAME environment variable is required")

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,  # Increased for better semantic context
            chunk_overlap=200,  # Increased overlap
            length_function=self._count_tokens,
            separators=["\n\n", "\n", ". ", "! ", "? ", ", ", " ", ""],
        )

        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None

    @staticmethod
    def is_supported_file_type(file_type: str) -> bool:
        return file_type.lower() in DocumentProcessingService.SUPPORTED_FILE_TYPES

    @staticmethod
    def supported_file_types() -> List[str]:
        return sorted(DocumentProcessingService.SUPPORTED_FILE_TYPES)

    def _count_tokens(self, text: str) -> int:
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        return max(1, len(text) // 4)

    def _extract_pdf(self, file_path: str) -> str:
        reader = PdfReader(file_path)
        text = ""
        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                text += f"\n\n## Page {page_num} ##\n\n{page_text}"
        return text

    def _extract_docx(self, file_path: str) -> str:
        # Lazy import to avoid lxml import errors at module load time
        from docx import Document

        doc = Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            if not para.text.strip():
                continue

            # Heuristic for headers (style name usually contains Heading or is bold/large)
            if "Heading" in para.style.name:
                full_text.append(f"\n\n## {para.text} ##\n")
            else:
                full_text.append(para.text)

        return "\n\n".join(full_text)

    def _extract_txt(self, file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                return handle.read()
        except UnicodeDecodeError:
            # Fallback to latin-1
            print(f"UTF-8 decode failed for {file_path}, retrying with latin-1")
            with open(file_path, "r", encoding="latin-1", errors="ignore") as handle:
                return handle.read()

    def _extract_text(self, file_path: str, file_type: str) -> str:
        print(f"Extracting text from {file_path} (type: {file_type})")
        try:
            file_type_lower = file_type.lower()
            text = ""
            if file_type_lower == "pdf":
                text = self._extract_pdf(file_path)
            elif file_type_lower in {"docx", "doc"}:
                text = self._extract_docx(file_path)
            elif file_type_lower == "txt":
                text = self._extract_txt(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")

            if not text or not text.strip():
                print(f"WARNING: Extracted text is empty for {file_path}")
                return ""
            
            return text

        except Exception as e:
            print(f"Failed to extract text from {file_path}: {e}")
            raise e

    def _create_chunks(
        self, text: str, *, document_id: str, filename: str, kb_id: str
    ) -> List[Dict[str, Any]]:
        chunks = self.text_splitter.split_text(text)
        metadata: List[Dict[str, Any]] = []

        for index, chunk_text in enumerate(chunks):
            # Extract basic source location if possible (e.g., from PDF markers)
            page_num = "Unknown"
            if "## Page " in chunk_text:
                try:
                    # Simple extraction of first page marker in chunk
                    start = chunk_text.find("## Page ") + 8
                    end = chunk_text.find(" ##", start)
                    if end != -1:
                        page_num = chunk_text[start:end]
                except Exception:
                    pass

            metadata.append(
                {
                    "chunk_id": f"{document_id}_chunk_{index}",
                    "document_id": document_id,
                    "kb_id": kb_id,
                    "text": chunk_text,
                    "source": filename,
                    "page": page_num,
                    "chunk_index": index,
                    "total_chunks": len(chunks),
                    "token_count": self._count_tokens(chunk_text),
                }
            )
        return metadata

    def download_and_process(
        self,
        *,
        s3_key: str,
        document_id: str,
        filename: str,
        file_type: str,
        kb_id: str,
    ) -> List[Dict[str, Any]]:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_type}") as tmp:
            tmp_path = tmp.name
            self.s3_client.download_file(self.bucket_name, s3_key, tmp_path)

        try:
            text = self._extract_text(tmp_path, file_type)
            return self._create_chunks(
                text, document_id=document_id, filename=filename, kb_id=kb_id
            )
        finally:
            os.unlink(tmp_path)
