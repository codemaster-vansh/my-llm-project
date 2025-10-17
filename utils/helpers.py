#utils/helpers.py
"""
Utility functions for the LLM deployment system.

Contains helpers for:
- Secret validation (timing-safe comparison)
- Data URI parsing and decoding
- Repository name sanitization
- Logging utilities
"""

import base64,re,secrets
from typing import Tuple, Optional
from datetime import datetime, timezone
import logging

#Config of logger
logger = logging.getLogger(__name__)

def validate_secret(provided_secret : str, expected_secret : str) -> bool:
    """
    Validate a secret using constant-time comparison to prevent timing attacks.
    
    Args:
        provided_secret: Secret from the incoming request
        expected_secret: Expected secret from environment variables
    
    Returns:
        True if secrets match, False otherwise
    
    Security:
        Uses secrets.compare_digest() for timing-attack-safe comparison
    """

    if not provided_secret or not expected_secret:
        logger.warning("Empty secret provided for comparison")
        return False
    
    provided_secret_in_bytes = provided_secret.encode('utf-8')
    expected_secret_in_bytes = expected_secret.encode('utf-8')

    return secrets.compare_digest(provided_secret_in_bytes,expected_secret_in_bytes)

def decode_data_uri(data_uri : str) -> Tuple[str, bytes, str]:
    """
    Parse and decode a data URI into its components.
    
    Args:
        data_uri: Data URI string (e.g., 'data:image/png;base64,iVBORw...')
    
    Returns:
        Tuple of (mime_type, decoded_data, encoding)
        Example: ('image/png', b'\\x89PNG...', 'base64')
    
    Raises:
        ValueError: If the data URI format is invalid
    """
    # Regex pattern to parse data URI
    # Format: data:[<mediatype>][;base64],<data>
    pattern = r'^data:([^;,]+)?(;base64)?,(.+)$'
    match = re.match(pattern, data_uri)

    if not match:
        raise ValueError(f"Invalid data URI format: {data_uri[:50]}...")
    
    mime_type = match.group(1) or 'text/plain'
    encoding = 'base64' if match.group(2) else 'url'
    data_string = match.group(3)

    if encoding == 'base64':
        try:
            decoded_data = base64.b64decode(data_string)
        except Exception as e:
            raise ValueError(f"Failed to decode base64 data: {e}")
    else:
        #just encode the data to utf-8
        decoded_data = data_string.encode('utf-8')
    
    logger.info(f"Decoded Data URI: {mime_type}, {len(decoded_data)} bytes")
    return mime_type,decoded_data,encoding

def sanitize_repo_name(task_name : str) -> str:
    """
    Sanitize task name to create a valid GitHub repository name.
    
    GitHub repo name rules:
    - Only alphanumeric characters and hyphens
    - Cannot start or end with a hyphen
    - Maximum 100 characters
    - Lowercase recommended
    
    Args:
        task_name: Raw task identifier (e.g., 'Captcha Solver 2025!')
    
    Returns:
        Sanitized repo name (e.g., 'captcha-solver-2025')
    """
    #convert to lowercase
    name = task_name.lower()

    # Replace spaces and invalid characters with hyphens
    # Keep only alphanumeric and hyphens
    name = re.sub(r'[^a-z0-9-]','-',name)

    # Replace multiple consecutive hyphens with single hyphen
    name = re.sub(r'-+','-',name)

    # Remove trailing/leading hyphens
    name = name.strip('-')

    # Ensure not empty
    if not name:
        name = f"repo-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    # max chars is 100
    name = name[:100]

    # log and return 
    logger.info(f"Sanitized repo name: '{task_name}' -> '{name}'")
    return name

def format_commit_message(round_num: int, task: str) -> str:
    """
    Generate standardized commit message.
    
    Args:
        round_num: Round number (1 or 2)
        task: Task identifier
    
    Returns:
        Formatted commit message
    """
    if round_num == 1:
        return f"Initial deployment for {task}"
    else:
        return f"Revision update for {task} (Round {round_num})"
    
def save_attachment_to_file(decoded_data : bytes, filename : str, output_dir : str = ".") -> str:
    """
    Save decoded attachment data to a file.
    
    Args:
        decoded_data: Binary data to save
        filename: Target filename
        output_dir: Directory to save file (default: current directory)
    
    Returns:
        Full path to saved file
    """
    import os

    #sanitize
    safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    filepath = os.path.join(output_dir,safe_filename)

    # Write binary data
    with open(filepath,'wb') as file:
        file.write(decoded_data)

    logger.info(f"Saved attachment to: {filepath} ({len(decoded_data)} bytes)")
    return filepath

def extract_repo_owner_name(repo_url: str) -> Tuple[str, str]:
    """
    Extract owner and repo name from GitHub URL.
    
    Args:
        repo_url: GitHub repository URL
                  (e.g., 'https://github.com/username/repo-name')
    
    Returns:
        Tuple of (owner, repo_name)
        Example: ('username', 'repo-name')
    
    Raises:
        ValueError: If URL format is invalid
    """

    # Pattern matching
    pattern = r'github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$'
    match = re.search(pattern, repo_url)

    if not match:
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    owner = match.group(1)
    repo_name = match.group(2)

    return owner, repo_name

def create_timestamp() -> str:
    """
    Create ISO 8601 formatted timestamp.
    
    Returns:
        UTC timestamp string (e.g., '2025-10-14T00:50:00Z')
    """

    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def truncate_text(text: str, max_length: int = 100, 
                  suffix: str = "...") -> str:
    """
    Truncate text to specified length with suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncated
    
    Returns:
        Truncated text
    """

    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def validate_github_token(token: str) -> bool:
    """
    Basic validation for GitHub personal access token format.
    
    Args:
        token: GitHub PAT to validate
    
    Returns:
        True if format looks valid, False otherwise
    
    Note:
        This only checks format, not if token is actually valid
    """
    if not token:
        return False
    
    if token.startswith('ghp_') and len(token) == 40:
        return True
    if token.startswith('github_pat_') and len(token) >= 82:
        return True
    
    logger.warning("GitHub token format appears invalid")
    return False

# Example usage and tasks
if __name__ == "__main__":
    # Configure logging for testing
    logging.basicConfig(level=logging.INFO)
    
    print("=== Testing Utility Functions ===\n")
    
    # Test 1: Secret validation
    print("1. Secret Validation:")
    result = validate_secret("my-secret", "my-secret")
    print(f"   Matching secrets: {result}")
    result = validate_secret("wrong-secret", "my-secret")
    print(f"   Non-matching secrets: {result}\n")
    
    # Test 2: Data URI decoding
    print("2. Data URI Decoding:")
    test_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    mime, data, enc = decode_data_uri(test_uri)
    print(f"   MIME type: {mime}")
    print(f"   Data size: {len(data)} bytes")
    print(f"   Encoding: {enc}\n")
    
    # Test 3: Repo name sanitization
    print("3. Repository Name Sanitization:")
    test_names = [
        "Captcha Solver 2025!",
        "test___multiple---dashes",
        "UPPERCASE-Name",
        "special@#$chars"
    ]
    for name in test_names:
        sanitized = sanitize_repo_name(name)
        print(f"   '{name}' -> '{sanitized}'")
    print()
    
    # Test 4: Commit message formatting
    print("4. Commit Message Formatting:")
    msg1 = format_commit_message(1, "captcha-solver")
    msg2 = format_commit_message(2, "captcha-solver")
    print(f"   Round 1: {msg1}")
    print(f"   Round 2: {msg2}\n")
    
    # Test 5: GitHub URL parsing
    print("5. GitHub URL Parsing:")
    test_urls = [
        "https://github.com/user123/my-repo",
        "https://github.com/org-name/project-name.git"
    ]
    for url in test_urls:
        try:
            owner, repo = extract_repo_owner_name(url)
            print(f"   {url}")
            print(f"     Owner: {owner}, Repo: {repo}")
        except ValueError as e:
            print(f"   Error: {e}")
    print()
    
    # Test 6: Timestamp creation
    print("6. Timestamp Creation:")
    ts = create_timestamp()
    print(f"   Current timestamp: {ts}\n")
    
    # Test 7: Text truncation
    print("7. Text Truncation:")
    long_text = "This is a very long text that needs to be truncated for display purposes"
    truncated = truncate_text(long_text, max_length=30)
    print(f"   Original: {long_text}")
    print(f"   Truncated: {truncated}\n")
    
    print("=== All tests completed ===")
