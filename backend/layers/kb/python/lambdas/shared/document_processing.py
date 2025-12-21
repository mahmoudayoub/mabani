"""Utilities for downloading and chunking documents."""

import os
import tempfile
from typing import Any, Dict, List, Tuple

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

    def _extract_text_with_textract(self, s3_key: str) -> str:
        """Fallback to AWS Textract for scanned documents."""
        print(f"Triggering Textract for {s3_key}")
        textract_client = boto3.client("textract")
        
        try:
            response = textract_client.start_document_text_detection(
                DocumentLocation={
                    "S3Object": {"Bucket": self.bucket_name, "Name": s3_key}
                }
            )
            job_id = response["JobId"]
            
            print(f"Started Textract Job: {job_id}")
            
            # Poll for completion
            import time
            while True:
                response = textract_client.get_document_text_detection(JobId=job_id)
                status = response["JobStatus"]
                
                if status in ["SUCCEEDED", "FAILED", "PARTIAL_SUCCESS"]:
                    break
                time.sleep(2)
            
            if status == "SUCCEEDED":
                text = ""
                # Pagination
                next_token = None
                while True:
                    if next_token:
                        response = textract_client.get_document_text_detection(JobId=job_id, NextToken=next_token)
                    else:
                        response = textract_client.get_document_text_detection(JobId=job_id)
                        
                    for block in response["Blocks"]:
                        if block["BlockType"] == "LINE":
                            text += block["Text"] + "\n"
                        elif block["BlockType"] == "PAGE":
                            text += "\n\n## Page End ##\n\n"

                    next_token = response.get("NextToken")
                    if not next_token:
                        break
                return text
            else:
                print(f"Textract failed with status: {status}")
                return ""
                
        except Exception as e:
            print(f"Textract invocation failed: {e}")
            return ""

    def _extract_pdf(self, file_path: str, s3_key: str = None) -> Tuple[List[Dict[str, Any]], str]:
        reader = PdfReader(file_path)
        extracted_text = ""
        valid_text_count = 0
        extraction_method = "standard"
        
        content_items = []
        
        # 1. Attempt standard Text Extraction
        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                extracted_text += f"\n\n## Page {page_num} ##\n\n{page_text}"
                valid_text_count += len(page_text.strip())
        
        # 2. Check sufficiency (Average < 50 chars per page implies scan)
        avg_chars_per_page = valid_text_count / len(reader.pages) if reader.pages else 0
        
        if avg_chars_per_page < 50:
             print(f"Insufficient text extracted ({avg_chars_per_page} chars/page). Falling back to Textract.")
             if s3_key:
                 extracted_text = self._extract_text_with_textract(s3_key)
                 if extracted_text:
                     return [{"type": "text", "content": extracted_text, "page": "Unknown"}], "textract"

        # Return standard extracted text if successful or if Textract failed
        if extracted_text.strip():
             return [{"type": "text", "content": extracted_text, "page": "Unknown"}], extraction_method
        
        return [], "failed"

    def _extract_docx(self, file_path: str) -> List[Dict[str, Any]]:
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

        text_content = "\n\n".join(full_text)
        if text_content.strip():
             return [{"type": "text", "content": text_content, "page": "Unknown"}]
        return []

    def _extract_txt(self, file_path: str) -> List[Dict[str, Any]]:
        text = ""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
        except UnicodeDecodeError:
            # Fallback to latin-1
            print(f"UTF-8 decode failed for {file_path}, retrying with latin-1")
            with open(file_path, "r", encoding="latin-1", errors="ignore") as handle:
                text = handle.read()
        
        if text.strip():
            return [{"type": "text", "content": text, "page": "Unknown"}]
        return []

    def _extract_content(self, file_path: str, file_type: str, s3_key: str = None) -> Tuple[List[Dict[str, Any]], str]:
        """Extract content (text or image) from file."""
        print(f"Extracting content from {file_path} (type: {file_type})")
        try:
            file_type_lower = file_type.lower()
            if file_type_lower == "pdf":
                return self._extract_pdf(file_path, s3_key=s3_key)
            elif file_type_lower in {"docx", "doc"}:
                return self._extract_docx(file_path), "standard"
            elif file_type_lower == "txt":
                return self._extract_txt(file_path), "standard"
            else:
                print(f"Unsupported file type: {file_type}")
                return [], "failed"
        except Exception as e:
            print(f"Extraction failed: {e}")
            return [], "failed"

    def _create_chunks(
        self, content_items: List[Dict[str, Any]], *, document_id: str, filename: str, kb_id: str, start_index: int = 0
    ) -> List[Dict[str, Any]]:
        metadata: List[Dict[str, Any]] = []
        chunk_index = start_index

        for item in content_items:
            item_type = item["type"]
            content = item["content"]
            page_num = item.get("page", "Unknown")

            if item_type == "text":
                # Split text content into smaller chunks
                text_chunks = self.text_splitter.split_text(content)
                for chunk_text in text_chunks:
                    # Update page number if marker is found in this specific chunk
                    chunk_page = page_num
                    if "## Page " in chunk_text:
                        try:
                            start = chunk_text.find("## Page ") + 8
                            end = chunk_text.find(" ##", start)
                            if end != -1:
                                chunk_page = chunk_text[start:end]
                        except Exception:
                            pass

                    metadata.append({
                        "chunk_id": f"{document_id}_chunk_{chunk_index}",
                        "document_id": document_id,
                        "kb_id": kb_id,
                        "text": chunk_text, # Standard field for vector DB text representation
                        "type": "text",
                        "content": chunk_text, # Payload for embedding
                        "source": filename,
                        "page": chunk_page,
                        "chunk_index": chunk_index,
                        "token_count": self._count_tokens(chunk_text),
                    })
                    chunk_index += 1

        return metadata

    def download_and_process(
        self,
        *,
        s3_key: str,
        document_id: str,
        kb_id: str,
        filename: str,
        file_type: str,
        chunk_index_start: int = 0,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Download file and process into chunks."""
        tmp_path = os.path.join(tempfile.gettempdir(), f"doc_{document_id}.{file_type}")
        
        print(f"Downloading {s3_key} to {tmp_path}")
        if not s3_key:
             # Local testing override
             tmp_path = filename 
        else:
            self.s3_client.download_file(self.bucket_name, s3_key, tmp_path)

        try:
            content_items, extraction_method = self._extract_content(tmp_path, file_type, s3_key=s3_key)
            if not content_items:
                 msg = f"No content extracted from {tmp_path}."
                 if file_type.lower() == "pdf":
                     msg += " (PDF might be image-only and Textract fallback failed/disabled)"
                 raise ValueError(msg)

            chunks = self._create_chunks(
                content_items=content_items,
                document_id=document_id,
                kb_id=kb_id,
                filename=filename,
                start_index=chunk_index_start,
            )
            return chunks, extraction_method
        finally:
            if s3_key and os.path.exists(tmp_path):
                os.unlink(tmp_path)
