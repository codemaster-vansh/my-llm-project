# main.py
"""
Main FastAPI application for LLM deployment system.

This orchestrates:
- Receiving deployment webhook requests
- Validating requests with Pydantic
- Generating code with LLM
- Deploying to GitHub Pages
- Sending notifications to evaluation API
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from models import (
    Deployment,
    EvaluationResponse,
    WebhookResponse,
    ErrorResponse
)
from services import GitHubService, NotificationService
from services.llm_service_aipipe import LLMServiceAIPipe
from utils import validate_secret, sanitize_repo_name, format_commit_message

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Global services (initialized on startup)
llm_service = None
github_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.
    Initializes services on startup and cleans up on shutdown.
    """
    global llm_service, github_service
    
    logger.info("🚀 Starting LLM Deployment System...")
    
    try:
        # Initialize services
        llm_service = LLMServiceAIPipe()
        github_service = GitHubService()
        logger.info("✓ All services initialized successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    finally:
        logger.info("🛑 Shutting down LLM Deployment System...")


# Create FastAPI app
app = FastAPI(
    title="LLM Deployment System",
    description="Automated code generation and GitHub Pages deployment",
    version="1.0.0",
    lifespan=lifespan
)


async def process_deployment(request: Deployment):
    """
    Background task to process deployment request.
    
    This runs asynchronously after returning HTTP 200 to the client.
    Handles all the heavy lifting: code generation, GitHub deployment, notification.
    
    Args:
        request: Validated deployment request
    """
    logger.info(f"🔄 Processing deployment for task: {request.task}")
    
    try:
        # Step 1: Generate code
        logger.info("Step 1/4: Generating application code...")
        code_files = llm_service.generate_app_code(
            request.brief,
            request.checks,
            request.attachments
        )
        logger.info(f"✓ Generated {len(code_files)} file(s)")
        
        # Step 2: Generate README
        logger.info("Step 2/4: Generating README...")
        readme = llm_service.generate_readme(
            request.task,
            request.brief,
            request.checks
        )
        logger.info("✓ README generated")
        
        # Step 3: Deploy to GitHub
        logger.info("Step 3/4: Deploying to GitHub...")
        
        # Sanitize repository name
        repo_name = sanitize_repo_name(request.task)
        
        if request.round == 1:
            # Round 1: Create new repository
            github_service.create_repository(
                repo_name,
                f"Automated deployment for {request.task}"
            )
            
            # Add LICENSE
            github_service.add_license(repo_name)
            
            # Push all files
            all_files = {**code_files, "README.md": readme}
            commit_message = format_commit_message(request.round, request.task)
            commit_sha = github_service.push_files(
                repo_name,
                all_files,
                commit_message
            )
            
            # Enable GitHub Pages
            pages_url = github_service.enable_github_pages(repo_name)
            
        else:
            # Round 2: Update existing repository
            # Get existing code
            existing_repo = github_service.user.get_repo(repo_name)
            existing_html = existing_repo.get_contents("index.html").decoded_content.decode()
            existing_readme = existing_repo.get_contents("README.md").decoded_content.decode()
            
            # Update code based on revision request
            updated_code = llm_service.update_code_for_revision(
                existing_html,
                request.brief,
                request.brief  # Original brief (in real scenario, store this)
            )
            
            # Update README
            updated_readme = llm_service.update_readme_for_revision(
                existing_readme,
                request.brief
            )
            
            # Push updated files
            updated_files = {**updated_code, "README.md": updated_readme}
            commit_message = format_commit_message(request.round, request.task)
            commit_sha = github_service.push_files(
                repo_name,
                updated_files,
                commit_message
            )
            
            pages_url = github_service.get_pages_url(repo_name)
        
        repo_url = github_service.get_repository_url(repo_name)
        
        logger.info(f"✓ Deployed to: {repo_url}")
        logger.info(f"✓ Pages URL: {pages_url}")
        
        # Step 4: Notify evaluation API
        logger.info("Step 4/4: Sending notification to evaluation API...")
        
        evaluation_data = EvaluationResponse(
            email=request.email,
            task=request.task,
            round=request.round,
            nonce=request.nonce,
            repo_url=repo_url,
            commit_sha=commit_sha,
            pages_url=pages_url
        )
        
        # Send notification asynchronously
        async with NotificationService() as notif_service:
            success = await notif_service._notify_evaluation(
                request.evaluation_url,
                evaluation_data.model_dump(mode='json'),
                max_retries=5
            )
        
        if success:
            logger.info(f"✓ Notification sent successfully for {request.task}")
        else:
            logger.error(f"✗ Failed to notify evaluation API for {request.task}")
        
        logger.info(f"🎉 Deployment complete for task: {request.task}")
        
    except Exception as e:
        logger.error(f"💥 Deployment failed for {request.task}: {e}")
        logger.exception("Full traceback:")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "running",
        "service": "LLM Deployment System",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """
    Detailed health check with service status.
    """
    return {
        "status": "healthy",
        "services": {
            "llm": llm_service is not None,
            "github": github_service is not None
        }
    }


@app.post("/deploy", response_model=WebhookResponse)
async def deploy_endpoint(
    request: Deployment,
    background_tasks: BackgroundTasks
):
    """
    Main deployment webhook endpoint.
    
    Receives deployment requests, validates them, and processes asynchronously.
    Returns immediately with HTTP 200 while processing continues in background.
    
    Args:
        request: Deployment request (validated by Pydantic)
        background_tasks: FastAPI background tasks
    
    Returns:
        WebhookResponse with acceptance confirmation
    
    Raises:
        HTTPException: If validation or authentication fails
    """
    logger.info(f"📥 Received deployment request: {request.task} (Round {request.round})")
    
    # Validate secret
    import os
    expected_secret = os.getenv("SHARED_SECRET")
    
    if not expected_secret:
        logger.error("SHARED_SECRET not configured")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error"
        )
    
    if not validate_secret(request.secret, expected_secret):
        logger.warning(f"Invalid secret provided for task: {request.task}")
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication secret"
        )
    
    # Add deployment task to background
    background_tasks.add_task(process_deployment, request)
    
    # Return immediate response
    response = WebhookResponse(
        status="accepted",
        message="Request queued for processing",
        task=request.task
    )
    
    logger.info(f"✓ Request accepted: {request.task}")
    
    return response


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """
    Custom handler for Pydantic validation errors.
    
    Returns user-friendly error messages for invalid requests.
    """
    logger.warning(f"Validation error: {exc}")
    
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            status="error",
            message="Invalid request data",
            detail=str(exc)
        ).model_dump()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Custom handler for HTTP exceptions.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            status="error",
            message=exc.detail
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler for unexpected errors.
    """
    logger.error(f"Unexpected error: {exc}")
    logger.exception("Full traceback:")
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            status="error",
            message="Internal server error",
            detail="An unexpected error occurred"
        ).model_dump()
    )


if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.getenv("PORT", 8000))  # Render provides PORT env var
    
    print("\n" + "="*60)
    print("🚀 Starting LLM Deployment System")
    print("="*60)
    print(f"\nPort: {port}")
    print("\nEndpoints:")
    print("  • GET  /          - Health check")
    print("  • GET  /health    - Detailed health")
    print("  • POST /deploy    - Deployment webhook")
    print("\n" + "="*60 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"

    )
