import os
import sys
from unittest.mock import MagicMock, patch
import pytest

# Add backend to path so we can import modules
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if backend_path not in sys.path:
    sys.path.append(backend_path)

from lambdas.shared.document_processing import DocumentProcessingService

class TestTextractFallback:
    
    @pytest.fixture
    def mock_env(self, monkeypatch):
        monkeypatch.setenv("KB_BUCKET_NAME", "test-bucket")

    @patch("lambdas.shared.document_processing.boto3.client")
    @patch("lambdas.shared.document_processing.PdfReader")
    def test_text_heavy_pdf_bypasses_textract(self, mock_reader, mock_boto_client, mock_env):
        """Test that a PDF with sufficient text does NOT trigger Textract."""
        
        # Setup Boto3 Mock
        mock_s3 = MagicMock()
        mock_textract = MagicMock()
        def get_client(service_name):
            if service_name == "s3": return mock_s3
            if service_name == "textract": return mock_textract
            return MagicMock()
        mock_boto_client.side_effect = get_client
        
        # Setup PDF Logic (High text content)
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is a detailed sentence with enough characters to pass the threshold." * 10
        mock_reader.return_value.pages = [mock_page]
        
        service = DocumentProcessingService()
        result, method = service._extract_pdf("dummy.pdf", s3_key="test.pdf")
        
        # Verify result structure
        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert method == "standard"
        
        # Verify Textract NOT called
        mock_textract.start_document_text_detection.assert_not_called()

    @patch("lambdas.shared.document_processing.boto3.client")
    @patch("lambdas.shared.document_processing.PdfReader")
    def test_scanned_pdf_triggers_textract(self, mock_reader, mock_boto_client, mock_env):
        """Test that a PDF with low/no text triggers Textract."""

        # Setup Boto3 Mock
        mock_s3 = MagicMock()
        mock_textract = MagicMock()
        def get_client(service_name):
            if service_name == "s3": return mock_s3
            if service_name == "textract": return mock_textract
            return MagicMock()
        mock_boto_client.side_effect = get_client
        
        # Setup Textract Response
        mock_textract.start_document_text_detection.return_value = {"JobId": "job-123"}
        mock_textract.get_document_text_detection.side_effect = [
            {"JobStatus": "IN_PROGRESS"},
            {"JobStatus": "SUCCEEDED"}, # Polling loop successful
            {"JobStatus": "SUCCEEDED", "Blocks": [ # Result retrieval loop
                {"BlockType": "PAGE"},
                {"BlockType": "LINE", "Text": "This text was extracted by Textract!"}
            ]}
        ]

        # Setup PDF Logic (Empty/Low text)
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "" # No text
        mock_reader.return_value.pages = [mock_page]
        
        service = DocumentProcessingService()
        result, method = service._extract_pdf("dummy.pdf", s3_key="test.pdf")
        
        # Verify result content
        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert "This text was extracted by Textract!" in result[0]["content"]
        assert method == "textract"
        
        # Verify Textract WAS called
        mock_textract.start_document_text_detection.assert_called_once()
