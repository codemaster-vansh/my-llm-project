#models.py
"""
Data models for the LLM Deployment System
Defines all request/response structures with validation.
"""

from pydantic import BaseModel, Field, field_validator, HttpUrl
from typing import List, Optional
from datetime import datetime, timezone

class Attachment(BaseModel):
    """
    Represents File Attachment encoded as data URI

    Attributes:
        name: FileName (e.g., 'sample.png')
        url: Base64 encoded data URI ('e.g., 'data:image/png;base64,iVBOR...')
    """

    name: str = Field(...,min_length=1, description="Attachment Filename")
    url: str = Field(...,min_length=10, description="Data URI with base64 content")

    @field_validator('url')
    @classmethod
    def validate_data_uri(cls, v:str) -> str:
        """Ensure URL is valid"""
        if not v.startswith("data:"):
            raise ValueError('Attachment URL must be a data URI starting with "data:"')
        return v
    

class Deployment(BaseModel):
    """
    Incoming webhook request from the evaluation system.
    
    This is what the instructor's system POSTs to your endpoint.
    """
    email: str = Field(..., description="Student email address")
    secret: str = Field(..., min_length=1, description="Shared authentication secret")
    task: str = Field(..., min_length=1, description="Unique task identifier")
    round: int = Field(..., ge=1, le=2, description="Round number (1 or 2)")
    nonce: str = Field(..., min_length=1, description="Unique nonce for this request")
    brief: str = Field(..., min_length=10, description="App requirements description")
    checks: List[str] = Field(..., min_items=1, description="Evaluation criteria")
    evaluation_url: HttpUrl = Field(..., description="URL to POST evaluation results")
    attachments: List[Attachment] = Field(default_factory=list, description="Optional file attachments")

    @field_validator('email')
    @classmethod
    def validate_email_format(cls,v:str) -> str:
        """Basic Email Validation"""
        if '@' not in v or '.' not in v.split('@')[-1]:
            raise ValueError('Invalid email format')
        return v.lower()
    
    #for documentation purposes
    class Config:
        json_schema_extra = {
            "example" : {
                "email": "student@example.com",
                "secret": "my-secret-key",
                "task": "captcha-solver-2025",
                "round": 1,
                "nonce": "ab12-xyz",
                "brief": "Create a captcha solver that handles ?url=...",
                "checks": [
                    "Repo has MIT license",
                    "README.md is professional",
                    "Page displays captcha"
                ],
                "evaluation_url": "https://example.com/notify",
                "attachments": []
            }
        }

class EvaluationResponse(BaseModel):
    """
    Response sent to the evaluation URL after deployment.
    
    This is what you POST back to the instructor's system.
    """
    email: str = Field(..., description="Student email address")
    #secret: str = Field(..., min_length=1, description="Shared authentication secret")
    task: str = Field(..., min_length=1, description="Unique task identifier")
    round: int = Field(..., ge=1, le=2, description="Round number (1 or 2)")
    nonce: str = Field(..., min_length=1, description="Unique nonce for this request")
    repo_url: HttpUrl = Field(..., description="GitHub repository URL")
    commit_sha: str = Field(..., min_length=40, max_length=40, description="Git commit SHA (40 chars)")
    pages_url: HttpUrl = Field(..., description="GitHub Pages deployment URL")
    
    @field_validator('email')
    @classmethod
    def validate_email_format(cls,v:str) -> str:
        """Basic Email Validation"""
        if '@' not in v or '.' not in v.split('@')[-1]:
            raise ValueError('Invalid email format')
        return v.lower()
    
    @field_validator('commit_sha')
    @classmethod
    def validate_sha_format(cls, v: str) -> str:
        """Ensure commit SHA is valid hexadecimal"""
        if not all(c in '0123456789abcdef' for c in v.lower()):
            raise ValueError('Commit SHA must be valid hexadecimal')
        return v.lower()
    
    @field_validator('repo_url', 'pages_url')
    @classmethod
    def validate_github_urls(cls, v: HttpUrl) -> HttpUrl:
        """Ensure URLs are GitHub-related"""
        if 'github' not in str(v).lower():
            raise ValueError('URL must be a GitHub URL')
        return v
    
    #for documentation purposes
    class Config:
        json_schema_extra = {
            "example": {
                "email": "student@example.com",
                "task": "captcha-solver-2025",
                "round": 1,
                "nonce": "ab12-xyz",
                "repo_url": "https://github.com/username/captcha-solver-2025",
                "commit_sha": "abc123def456abc123def456abc123def456abc1",
                "pages_url": "https://username.github.io/captcha-solver-2025/"
            }
        }

class WebhookResponse(BaseModel):
    """
    Immediate HTTP 200 response to webhook caller.
    
    Sent immediately to acknowledge receipt (before processing).
    """
    status: str = Field(default="accepted", description="Request status")
    message: str = Field(default="Request queued for processing", description="Status message")
    task: str = Field(..., description="Task ID being processed")
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc) , description="Timestamp of receipt")

    #for documentation purposes
    class Config:
        json_schema_extra = {
            "example": {
                "status": "accepted",
                "message": "Request queued for processing",
                "task": "captcha-solver-2025",
                "received_at": "2025-10-14T00:50:00Z"
            }
        }

class ErrorResponse(BaseModel):
    """
    Error response for validation failures or processing errors.
    """
    status: str = Field(default="error", description="Error status")
    message: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "error",
                "message": "Invalid secret provided",
                "detail": "Authentication failed"
            }
        }