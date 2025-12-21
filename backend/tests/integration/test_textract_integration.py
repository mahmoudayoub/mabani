import sys
import os
import boto3
import pytest

# Add backend to path so we can import modules
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if backend_path not in sys.path:
    sys.path.append(backend_path)

from lambdas.shared.document_processing import DocumentProcessingService

@pytest.mark.skip(reason="Requires real AWS credentials and S3 upload")
def test_real_textract_integration():
    """
    Integration test for Textract. 
    NOTE: This test requires a valid PDF in S3 and proper credentials.
    Env vars KB_BUCKET_NAME must be set.
    """
    print("--- REAL AWS TEXTRACT TEST ---")
    
    bucket_name = os.environ.get("KB_BUCKET_NAME", "taskflow-backend-dev-kb")
    os.environ["KB_BUCKET_NAME"] = bucket_name
    os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"
    
    # We assume the file exists/is uploaded for this test
    # Or we can create a dummy file. 
    # For now, relying on pre-existing setup from manual verify step
    s3_key = "test_textract_doc.pdf"
    local_path = "backend/scripts/Electrical Safety Guidelines.pdf" 
    
    if not os.path.exists(local_path):
        pytest.skip(f"Local test file not found at {local_path}")
    
    service = DocumentProcessingService()
    
    try:
        result = service._extract_pdf(local_path, s3_key=s3_key)
        
        assert len(result) > 0
        content = result[0]["content"]
        assert len(content) > 100
        print("\nSUCCESS: Text extracted.")
        
    except Exception as e:
        pytest.fail(f"Integration test failed: {e}")

if __name__ == "__main__":
    # Allow running as script too
    test_real_textract_integration()
