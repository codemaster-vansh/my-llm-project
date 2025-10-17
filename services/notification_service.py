# services/notification_service.py
"""
Notification Service for sending deployment results to evaluation endpoints.

This service handles:
- Sending POST requests to evaluation URLs
- Retry logic with exponential backoff
- Error handling and logging
"""

import asyncio
import logging
from typing import Dict, Optional
import httpx

# Configure logging
logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service for sending HTTP notifications with retry logic.
    """

    def __init__(self, timeout: float = 30.0):
        """
        Initialize the notification service.
        
        Args:
            timeout: Request timeout in seconds (default: 30.0)
        """

        self.timeout = timeout
        self.client = None

        logger.info(f"Notification Service initialized with {timeout}s timeout")

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()
    
    async def _notify_evaluation(self, url : str, data : Dict, max_retries : int = 5) -> bool:
        """
        Send notification to evaluation URL with exponential backoff retry.
        
        Implements retry strategy: 1s, 2s, 4s, 8s, 16s delays between attempts
        as specified in project requirements.
        
        Args:
            url: Evaluation endpoint URL
            data: JSON payload to send
            max_retries: Maximum number of retry attempts (default: 5)
        
        Returns:
            True if notification succeeded (HTTP 200), False otherwise
        """
        logger.info(f"Sending notification to {url}")
        logger.debug(f"Payload: {data}")

        delays = [1,2,4,8,16]

        for attempt in range(max_retries):
            try:

                if isinstance(data, dict):
                    for k, v in data.items():
                        if hasattr(v, '__class__') and v.__class__.__name__ == "HttpUrl":
                            data[k] = str(v)

                response = await self.client.post(
                    str(url), 
                    json=data,
                    headers = {
                        "Content-Type": "application/json",
                        "User-Agent": "LLM-Deployment-System/1.0"
                    }
                )

                if response.status_code == 200:
                    logger.info(f"✓ Notification successful (attempt {attempt + 1}/{max_retries})")
                    return True
                
                # Log non-200 responses
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries}: "
                    f"Got HTTP {response.status_code}"
                )

                # Logging responsesof debugging
                try:
                    error_body = response.text[:200]
                    logger.debug(f"Response body: {error_body}")
                except:
                    pass

            except httpx.TimeoutException as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries}: "
                    f"Request timed out - {e}"
                )

            except httpx.NetworkError as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries}: "
                    f"Network error - {e}"
                )
            
            except httpx.HTTPError as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries}: "
                    f"HTTP error - {e}"
                )

            except Exception as e:
                logger.error(
                    f"Attempt {attempt + 1}/{max_retries}: "
                    f"Unexpected error - {e}"
                )

            if attempt < max_retries - 1:
                delay = delays[attempt] if attempt < len(delays) else delays[-1]
                logger.info(f"Waiting {delay}s before retry...")
                await asyncio.sleep(delay)

        logger.error(f"✗ Failed to notify {url} after {max_retries} attempts")
        return False
    
    async def send_with_retry(self, url: str, payload: Dict, retries: int = 5) -> tuple[bool, Optional[str]]:
        """
        Send notification and return detailed result.
        
        Args:
            url: Target URL
            payload: JSON data to send
            retries: Number of retry attempts
        
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        success = await self._notify_evaluation(url, payload, retries)

        if success:
            return True, None
        else:
            return False, f"Failed after {retries} attempts"
        
    async def test_connection(self, url: str) -> bool:
        """
        Test if a URL is reachable with a simple GET request.
        
        Args:
            url: URL to test
        
        Returns:
            True if reachable, False otherwise
        """
        try:
            response = await self.client.get(url, timeout=5.0)
            logger.info(f"Test connection to {url}: HTTP {response.status_code}")
            return response.status_code < 500
        
        except Exception as e:
            logger.warning(f"Test connection to {url} failed: {e}")
            return False
        
# SYNC NOTI SERVICE FOR TESTING

class SyncNotificationService:
    """
    Synchronous wrapper around NotificationService for non-async contexts.
    """
    
    def __init__(self, timeout: float = 30.0):
        """Initialize sync notification service."""
        self.timeout = timeout
        self.async_service = NotificationService(timeout)

    def notify_evaluation(self, url: str, data: Dict, 
                         max_retries: int = 5) -> bool:
        """
        Synchronous notification method.
        
        Args:
            url: Evaluation endpoint URL
            data: JSON payload
            max_retries: Maximum retry attempts
        
        Returns:
            True if successful, False otherwise
        """
        async def _notify():
            async with self.async_service:
                return await self.async_service._notify_evaluation(
                    url, data, max_retries
                )
        
        return asyncio.run(_notify())
    
"""if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=== Testing Notification Service ===\n")
    
    async def run_tests():
        ""Run async tests.""
        
        # Test data
        test_payload = {
            "email": "test@example.com",
            "task": "test-task-123",
            "round": 1,
            "nonce": "abc123",
            "repo_url": "https://github.com/user/repo",
            "commit_sha": "abc123def456abc123def456abc123def456abc1",
            "pages_url": "https://user.github.io/repo/"
        }
        
        print("Test 1: Testing with httpbin.org (should succeed)...")
        async with NotificationService(timeout=10.0) as service:
            # httpbin.org/post echoes back POST data
            success = await service._notify_evaluation(
                "https://postman-echo.com/post",
                test_payload,
                max_retries=3
            )
            print(f"{'✓' if success else '✗'} Test with httpbin.org: {'SUCCESS' if success else 'FAILED'}\n")
        
        print("Test 2: Testing with invalid URL (should fail gracefully)...")
        async with NotificationService(timeout=5.0) as service:
            success = await service._notify_evaluation(
                "https://this-url-definitely-does-not-exist-12345.com/api",
                test_payload,
                max_retries=2  # Fewer retries for faster test
            )
            print(f"{'✓' if not success else '✗'} Test with invalid URL: {'FAILED as expected' if not success else 'Unexpected success'}\n")
        
        print("Test 3: Testing connection test...")
        async with NotificationService() as service:
            is_reachable = await service.test_connection("https://httpbin.org/get")
            print(f"{'✓' if is_reachable else '✗'} Connection test: {'SUCCESS' if is_reachable else 'FAILED'}\n")
        
        print("Test 4: Testing with detailed result...")
        async with NotificationService() as service:
            success, error = await service.send_with_retry(
                "https://httpbin.org/status/500",  # This returns 500 error
                test_payload,
                retries=2
            )
            print(f"{'✓' if not success else '✗'} Detailed result test: {'FAILED as expected' if not success else 'Unexpected'}")
            if error:
                print(f"  Error message: {error}\n")
        
        print("=" * 60)
        print("✓ All tests completed!")
        print("=" * 60)
    
    # Run async tests
    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n✗ Error during tests: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n--- Synchronous Wrapper Test ---\n")
    
    # Test synchronous wrapper
    try:
        print("Test 5: Testing synchronous wrapper...")
        sync_service = SyncNotificationService(timeout=10.0)
        
        test_data = {
            "test": "data",
            "timestamp": "2025-10-17T22:20:00Z"
        }
        
        result = sync_service.notify_evaluation(
            "https://postman-echo.com/post",
            test_data,
            max_retries=2
        )
        
        print(f"{'✓' if result else '✗'} Sync wrapper test: {'SUCCESS' if result else 'FAILED'}")
        
    except Exception as e:
        print(f"✗ Sync test error: {e}")"""

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    print("=== Testing Notification Service ===\n")

    async def run_tests():
        """Run async tests."""
        test_payload = {
            "email": "test@example.com",
            "task": "test-task-123",
            "round": 1,
            "nonce": "abc123",
            "repo_url": "https://github.com/user/repo",
            "commit_sha": "abc123def456abc123def456abc123def456abc1",
            "pages_url": "https://user.github.io/repo/"
        }

        # ✅ Test 1: Normal success case (POST)
        print("Test 1: Testing POST (should succeed)...")
        async with NotificationService(timeout=10.0) as service:
            success = await service._notify_evaluation(
                "https://postman-echo.com/post",
                test_payload,
                max_retries=3
            )
            print(f"{'✓' if success else '✗'} POST test: {'SUCCESS' if success else 'FAILED'}\n")

        # ✅ Test 2: Invalid URL (should fail gracefully)
        print("Test 2: Testing with invalid URL (should fail gracefully)...")
        async with NotificationService(timeout=5.0) as service:
            success = await service._notify_evaluation(
                "https://this-url-definitely-does-not-exist-12345.com/api",
                test_payload,
                max_retries=2
            )
            print(f"{'✓' if not success else '✗'} Invalid URL test: {'FAILED as expected' if not success else 'Unexpected success'}\n")

        # ✅ Test 3: GET connectivity test
        print("Test 3: Testing connection test (GET)...")
        async with NotificationService() as service:
            is_reachable = await service.test_connection("https://postman-echo.com/get")
            print(f"{'✓' if is_reachable else '✗'} Connection test: {'SUCCESS' if is_reachable else 'FAILED'}\n")

        # ✅ Test 4: Simulated 500 error (should fail and return error)
        print("Test 4: Testing with simulated server error (500)...")
        async with NotificationService() as service:
            success, error = await service.send_with_retry(
                "https://httpstat.us/500",
                test_payload,
                retries=2
            )
            print(f"{'✓' if not success else '✗'} 500 Error test: {'FAILED as expected' if not success else 'Unexpected success'}")
            if error:
                print(f"  Error message: {error}\n")

        # ✅ Test 5: Delayed response (simulate slow network using httpstat.us)
        print("Test 5: Testing delayed response (2 seconds)...")
        async with NotificationService(timeout=10.0) as service:
            success = await service._notify_evaluation(
                "https://deelay.me/2000/https://postman-echo.com/post",  # 2s delay then echo
                test_payload,
                max_retries=1
            )
            print(f"{'✓' if success else '✗'} Delay test: {'SUCCESS' if success else 'FAILED'}\n")
            
        print("=" * 60)
        print("✓ All async tests completed!")
        print("=" * 60)

    # Run async tests
    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n✗ Error during tests: {e}")
        import traceback
        traceback.print_exc()

    # ✅ Synchronous wrapper test
    print("\n--- Synchronous Wrapper Test ---\n")
    try:
        print("Test 6: Testing synchronous wrapper (POST)...")
        sync_service = SyncNotificationService(timeout=10.0)

        test_data = {
            "test": "data",
            "timestamp": "2025-10-17T22:20:00Z"
        }

        result = sync_service.notify_evaluation(
            "https://postman-echo.com/post",
            test_data,
            max_retries=2
        )

        print(f"{'✓' if result else '✗'} Sync wrapper test: {'SUCCESS' if result else 'FAILED'}")

    except Exception as e:
        print(f"✗ Sync test error: {e}")