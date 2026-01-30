import pytest
from unittest.mock import MagicMock, patch
import os
import sys

# Ensure we can import from lambdas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from lambdas.handlers.start_handler import handle_start
from lambdas.handlers.project_handler import handle_project_selection

class TestProjectSelection:

    @pytest.fixture
    def mock_dependencies(self):
        with patch('lambdas.handlers.start_handler.S3Client') as MockS3, \
             patch('lambdas.handlers.start_handler.BedrockClient') as MockBedrock, \
             patch('lambdas.handlers.start_handler.ConversationState') as MockState, \
             patch('lambdas.handlers.start_handler.ConfigManager') as MockConfig, \
             patch('lambdas.handlers.start_handler.UserProjectManager') as MockUserProject:
            
            # Setup common mocks
            s3 = MockS3.return_value
            s3.upload_image.return_value = {
                "s3Key": "test-key", 
                "s3Url": "s3://test/key", 
                "httpsUrl": "http://test/key"
            }
            s3.download_image.return_value = b"fake-image-data"
            
            bedrock = MockBedrock.return_value
            bedrock.caption_image.return_value = "A worker on a ladder"
            bedrock.classify_observation_type.return_value = "Unsafe Act"
            bedrock.classify_hazard_type.return_value = ["Working at Height"]
            
            state = MockState.return_value
            
            config = MockConfig.return_value
            config.get_options.return_value = ["Project A", "Project B"]
            
            user_project = MockUserProject.return_value
            
            yield {
                "s3": s3,
                "bedrock": bedrock,
                "state": state,
                "config": config,
                "user_project": user_project
            }

    def test_start_new_user_no_project(self, mock_dependencies):
        """Test Start flow for a user with no previous project selected."""
        deps = mock_dependencies
        deps["user_project"].get_last_project.return_value = None
        
        user_input = {"imageUrl": "http://example.com/photo.jpg"}
        phone = "+1234567890"
        
        response = handle_start(user_input, phone, deps["state"])
        
        # Expect List Message
        assert "interactive" in response
        assert response["interactive"]["type"] == "list"
        assert response["interactive"]["body_text"] == "Choose from the active projects below:"
        
        # Verify state transition
        deps["state"].start_conversation.assert_called_once()
        args, kwargs = deps["state"].start_conversation.call_args
        assert kwargs["start_state"] == "WAITING_FOR_PROJECT"
        assert "projectId" not in kwargs["draft_data"]

    def test_start_returning_user_with_project(self, mock_dependencies):
        """Test Start flow for a user with a saved project."""
        deps = mock_dependencies
        deps["user_project"].get_last_project.return_value = "Project A"
        
        user_input = {"imageUrl": "http://example.com/photo.jpg"}
        phone = "+1234567890"
        
        response = handle_start(user_input, phone, deps["state"])
        
        # Expect Confirmation Button (Standard flow)
        assert "interactive" in response
        assert response["interactive"]["type"] == "button"
        assert "Project: *Project A*" in response["text"]
        
        # Verify state transition
        deps["state"].start_conversation.assert_called_once()
        args, kwargs = deps["state"].start_conversation.call_args
        assert kwargs["start_state"] == "WAITING_FOR_CONFIRMATION"
        assert kwargs["draft_data"]["projectId"] == "Project A"

    def test_project_selection_handler(self):
        """Test the handler that processes the project selection."""
        with patch('lambdas.handlers.project_handler.UserProjectManager') as MockUserProj:
            
            mock_user_proj = MockUserProj.return_value
            mock_state_manager = MagicMock()
            
            # Setup Draft Data simulation
            mock_state_item = {
                "draftData": {
                    "observationType": "Unsafe Act",
                    "classification": "Falls"
                }
            }
            
            response = handle_project_selection(
                user_input="Project B",
                phone_number="+1234567890",
                state_manager=mock_state_manager,
                state_item=mock_state_item
            )
            
            # Verify Persistence
            mock_user_proj.set_last_project.assert_called_with("+1234567890", "Project B")
            
            # Verify State Update
            mock_state_manager.update_state.assert_called_with(
                phone_number="+1234567890",
                new_state="WAITING_FOR_CONFIRMATION",
                curr_data={"projectId": "Project B"}
            )
            
            # Verify Response
            assert "interactive" in response
            assert "Project set to *Project B*" in response["text"]
            assert "Unsafe Act" in response["text"]
