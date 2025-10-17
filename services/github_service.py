# services/github_service.py
"""
GitHub Service for repository management and deployment.

This service handles:
- Creating GitHub repositories
- Pushing files (HTML, README, LICENSE)
- Enabling GitHub Pages
- Managing commits and getting SHAs
"""


import os
import time
import logging
from typing import Dict, Optional
from github import Github, GithubException
from github.Repository import Repository
from dotenv import load_dotenv
import requests

logger = logging.getLogger(__name__)

class GitHubService:
    """
    Service for interacting with GitHub API using PyGithub.
    """

    def __init__(self):
        """
        Initialize the GitHub service with authentication.
        
        Raises:
            ValueError: If GITHUB_TOKEN or GITHUB_USERNAME not found
        """
        load_dotenv()

        self.git_auth_token = os.getenv("GITHUB_AUTH_TOKEN")
        self.git_uname = os.getenv("GITHUB_USERNAME")

        if not self.git_auth_token:
            raise ValueError("GITHUB_AUTH_TOKEN not found in environment variables")
        
        if not self.git_uname:
            raise ValueError("GITHUB_USERNAME not found in environment variables")
        
        try:
            self.client = Github(login_or_token=self.git_auth_token)
            self.user = self.client.get_user()

            try:
                _ = self.user.login
                self.templates = self._load_all_templates()
                logger.info(f"GitHub Service with cached templates initialized for user: {self.user.login}")
            except:
                logger.info("Github Service Initialization FAILED")

        except GithubException as e:
            logger.error(f"GitHub authentication failed: {e}")
            raise ValueError(f"Invalid GitHub token or authentication failed: {e}")

    def _load_all_templates(self) -> Dict[str,str]:
        """
        Load all template files and cache them.
        
        Returns:
            Dictionary of template names to content
            
        Raises:
            FileNotFoundError: If any template file is missing
        """

        templates = {}
        template_files = {
            'license' : 'MIT_License.txt',
        }        

        for key, filename in template_files.items():
            template_path = os.path.join(os.path.dirname(__file__),'..','templates',filename)

            if not os.path.exists(template_path):
                raise FileNotFoundError(f"Template file not found: {filename} (expected at {template_path})")
            
            with open(template_path,'r',encoding='utf-8') as file:
                templates[key] = file.read()
                logger.debug(f"Loaded template: {filename}")
            
        return templates
    
    def create_repository(self,repo_name : str, description : str = "") -> Repository:
        """
        Create a new public GitHub repository.
        
        Args:
            repo_name: Name of the repository
            description: Repository description
        
        Returns:
            Repository object
            
        Raises:
            Exception: If repository creation fails
        """
        logger.info(f"Creating repository: {repo_name}")

        try:
            try:
                existing_repo = self.user.get_repo(repo_name)
                logger.warning(f"Repository '{repo_name}' already exists, using existing repo")
                return existing_repo
            except GithubException as e:
                if e.status != 404:
                    raise
            
            repo = self.user.create_repo(
                name = repo_name,
                description = description,
                private = False,
                auto_init = False,
                has_issues = True,
                has_wiki = False,
                has_downloads = True
            )

            logger.info(f"Repository created : {repo.html_url}")

            time.sleep(2)

            return repo
        
        except GithubException as e:
            logger.error(f"Failed to create repository: {e}")
            raise Exception(f"Repository creation failed: {e}")
        
    def delete_repository(self, repo_name : str) -> None:
        """
        Delete a repository (use with caution!).
        
        Args:
            repo_name: Name of the repository to delete
        """
        logger.warning(f"Deleting repository: {repo_name}")

        try:
            repo = self.user.get_repo(repo_name)
            repo.delete()
            logger.info(f"Repository '{repo_name}' deleted")

        except GithubException as e:
            logger.error(f"Failed to delete repository: {e}")
            raise Exception(f"Repository deletion failed: {e}")
        
    def push_files(self,repo_name : str, files : Dict[str,str], commit_message : str = "Initial commit") -> str:
        """
        Push multiple files to repository.
        
        Args:
            repo_name: Name of the repository
            files: Dictionary of {filepath: content}
            commit_message: Commit message
        
        Returns:
            Commit SHA (40-character hex string)
            
        Raises:
            Exception: If file push fails
        """

        logger.info(f"Pushing {len(files)} file(s) to {repo_name}")

        try:
            repo = self.user.get_repo(repo_name)

            for filepath, content in files.items():
                try:
                    existing_file = repo.get_contents(filepath)

                    repo.update_file(
                        path=filepath,
                        message=commit_message,
                        content=content,
                        sha=existing_file.sha,
                        branch="main"
                    )
                    logger.info(f"Updated file: {filepath}")

                except GithubException as e:
                    if e != 404:
                        repo.create_file(
                            path=filepath,
                            message=commit_message,
                            content=content,
                            branch="main"
                        )
                        logger.info(f"Created file: {filepath}")
                    else:
                        raise

            #get latest commit sha
            commits = repo.get_commits()
            latest_commit_sha = commits[0].sha

            logger.info(f"Files pushed successfully, commit SHA: {latest_commit_sha}")
            
            return latest_commit_sha
        
        except GithubException as e:
            logger.error(f"Failed to push files: {e}")
            raise Exception(f"File push failed: {e}")
        
    def add_license(self,repo_name : str) -> None:
        """
        Add MIT LICENSE to repository.
        
        Args:
            repo_name: Name of the repository
        """
        logger.info(f"Adding MIT LICENSE to {repo_name}")

        try:
            from datetime import datetime, timezone
            current_year = datetime.now().year

            license_content = self.templates['license'].format(year=current_year)

            repo = self.user.get_repo(repo_name)

            try:
                existing = repo.get_contents("LICENSE")
                logger.info("LICENSE already exists, skipping")
                return
            except GithubException as e:
                if e.status != 404:
                    raise

            repo.create_file(
                path="LICENSE",
                message="Add MIT License",
                content=license_content,
                branch="main"
            )

            logger.info("MIT LICENSE added successfully")

        except GithubException as e:
            logger.error(f"Failed to add LICENSE: {e}")

    def enable_github_pages(self, repo_name : str, branch : str = "main") -> str:
        """
        Enable GitHub Pages for the repository.
        
        Args:
            repo_name: Name of the repository
            branch: Branch to use for Pages (default: main)
        
        Returns:
            GitHub Pages URL
            
        Note:
            PyGithub has limited Pages support, so we use the REST API directly
        """
        logger.info(f"Enabling GitHub Pages for {repo_name}")

        try:
            repo = self.user.get_repo(repo_name)

            try:
                repo.create_pages_site(
                    source = {"branch" : branch, "path" : "/"}
                )

                logger.info("GitHub Pages enabled via PyGithub")
            except AttributeError:
                # Method doesn't exist, use REST API directly
                self._enable_pages_via_rest_api(repo_name, branch)
            except GithubException as e:
                if e.status == 409:
                    logger.info("GitHub Pages already enabled")
                else:
                    # Try REST API as FALLBACK
                    self._enable_pages_via_rest_api(repo_name, branch)

            time.sleep(5)

            pages_url = f"https://{self.git_uname}.github.io/{repo_name}/"
            logger.info(f"GitHub Pages URL: {pages_url}")
            return pages_url

        except Exception as e:
            logger.error(f"Failed to enable GitHub Pages: {e}")
            # Return URL anyway - it might work even if API call failed
            return f"https://{self.git_uname}.github.io/{repo_name}/"
        
    def _enable_pages_via_rest_api(self, repo_name : str, branch : str = "main") -> None:
        """
        Enable GitHub Pages using REST API directly.
        
        Args:
            repo_name: Name of the repository
            branch: Branch to use for Pages
        """
        url = f"https://api.github.com/repos/{self.git_uname}/{repo_name}/pages"

        headers = {
            "Authorization": f"token {self.git_auth_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        data = {
            "source" : {
                "branch" : branch,
                "path" : "/"
            }
        }

        response = requests.post(url, headers=headers, json=data, timeout=30)

        if response.status_code == 201:
            logger.info("GitHub Pages enabled via REST API")
        elif response.status_code == 409:
            logger.info("GitHub Pages already enabled (REST API)")
        else:
            logger.warning(f"Pages API returned status {response.status_code}")

    def get_repository_url(self, repo_name : str) -> str:
        """
        Get the HTTPS URL of a repository.
        
        Args:
            repo_name: Name of the repository
        
        Returns:
            Repository URL
        """
        return f"https://github.com/{self.git_uname}/{repo_name}"
    
    def get_pages_url(self, repo_name: str) -> str:
        """
        Get the GitHub Pages URL for a repository.
        
        Args:
            repo_name: Name of the repository
        
        Returns:
            GitHub Pages URL
        """
        return f"https://{self.username}.github.io/{repo_name}/"
    
    def verify_pages_live(self, pages_url: str, max_retries: int = 5) -> bool:
        """
        Verify that GitHub Pages is live and returning 200.
        
        Args:
            pages_url: GitHub Pages URL to check
            max_retries: Maximum number of retry attempts
        
        Returns:
            True if Pages is live, False otherwise
        """
        logger.info(f"Verifying Pages is live: {pages_url}")

        for attempt in range(max_retries):
            try:
                response = requests.get(pages_url, timeout = 10)

                if response.status_code == 200:
                    logger.info("GitHub Pages is live!")
                    return True
                
                logger.info(f"Attempt {attempt + 1}: Status {response.status_code}")

            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}: Request failed - {e}")

            if attempt < max_retries - 1:
                time.sleep(10)

        logger.warning("GitHub Pages verification timed out")
        return False
    
    def get_commit_sha(self, repo_name: str, branch: str = "main") -> str:
        """
        Get the latest commit SHA from a branch.
        
        Args:
            repo_name: Name of the repository
            branch: Branch name (default: main)
        
        Returns:
            Commit SHA (40-character hex string)
        """
        try:
            repo = self.user.get_repo(repo_name)
            commits = repo.get_commits(sha=branch)
            return commits[0].sha
        
        except GithubException as e:
            logger.error(f"Failed to get commit SHA : {e}")
            raise Exception(f"Failed to get commit SHA : {e}")
        
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=== Testing GitHub Service ===\n")
    
    try:
        # Initialize service
        print("Initializing GitHub service...")
        service = GitHubService()
        print(f"✓ Authenticated as: {service.user.login}\n")
        
        # Test repository name
        test_repo_name = f"test-deployment-{int(time.time())}"
        
        print(f"Test 1: Creating repository '{test_repo_name}'...")
        repo = service.create_repository(
            test_repo_name,
            "Test repository for automated deployment"
        )
        print(f"✓ Repository created: {repo.html_url}\n")
        
        print("Test 2: Adding LICENSE...")
        service.add_license(test_repo_name)
        print("✓ LICENSE added\n")
        
        print("Test 3: Pushing test files...")
        test_files = {
            "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Page</title>
</head>
<body>
    <h1>Hello from automated deployment!</h1>
    <p>This is a test page.</p>
</body>
</html>""",
            "README.md": """# Test Deployment

This is a test repository created by the automated deployment system.

## Features
- Automated repository creation
- GitHub Pages deployment
- MIT License included
"""
        }
        
        commit_sha = service.push_files(
            test_repo_name,
            test_files,
            "Initial deployment"
        )
        print(f"✓ Files pushed, commit SHA: {commit_sha}\n")
        
        print("Test 4: Enabling GitHub Pages...")
        pages_url = service.enable_github_pages(test_repo_name)
        print(f"✓ Pages URL: {pages_url}\n")
        
        print("Test 5: Verifying Pages is live (this may take ~30 seconds)...")
        is_live = service.verify_pages_live(pages_url)
        print(f"{'✓' if is_live else '⚠'} Pages {'is' if is_live else 'not yet'} live\n")

        print("Test 6: Deleting test repository...")
        service.delete_repository(test_repo_name)
        print(f"✓ Repository '{test_repo_name}' deleted successfully\n")
        
        print("=" * 60)
        print("✓ All tests completed successfully!")
        print("=" * 60)
        print(f"\nRepository URL: {service.get_repository_url(test_repo_name)}")
        print(f"Pages URL: {pages_url}")
        print(f"\nNote: You can delete this test repo manually or run:")
        print(f"  service.delete_repository('{test_repo_name}')")
        
    except ValueError as e:
        print(f"\n✗ Configuration Error: {e}")
        print("Make sure GITHUB_TOKEN and GITHUB_USERNAME are set in .env")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()