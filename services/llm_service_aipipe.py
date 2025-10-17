# services/llm_service.py
"""
LLM Service for code generation using AI Pipe API.

This service handles:
- Generating web applications from natural language briefs
- Creating professional README.md files
- Updating existing code based on revision requests
"""

import os
import logging
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Configure Logging
logger = logging.getLogger(__name__)

class LLMServiceAIPipe:
    """
    Service for interacting with AI Pipe API for code generation.
    """

    attachments_template = """\n\nATTACHMENTS PROVIDED: {length_attach} file(s)\nThese attachments should be used as examples or test data in your implementation.\nHandle similar file formats appropriately."""

    prompt_template = """You are a senior full-stack developer with 10+ years experience building production web applications.

PROJECT BRIEF:
{brief}

ACCEPTANCE CRITERIA (you MUST satisfy ALL of these):
{checks_text}
{attachments_text}

YOUR TASK:
Create a complete, production-grade single-page web application that can be deployed immediately to GitHub Pages.

TECHNICAL STACK & REQUIREMENTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HTML Structure:
✓ Use semantic HTML5 elements (header, main, section, article, footer)
✓ Include proper meta tags (charset, viewport, description)
✓ Add Open Graph tags for social sharing
✓ Use ARIA labels for accessibility (aria-label, role attributes)

CSS Design System:
✓ Use CSS custom properties (--primary-color, --spacing-unit, etc.)
✓ Implement mobile-first responsive design with breakpoints
✓ Use CSS Grid for page layout, Flexbox for components
✓ Add smooth transitions and hover effects
✓ Include dark mode support using prefers-color-scheme
✓ Use modern fonts (system font stack or Google Fonts CDN)
✓ Color palette: Use complementary colors, ensure WCAG AA contrast

JavaScript Architecture:
✓ Use ES6+ features (const/let, arrow functions, destructuring, async/await)
✓ Organize code into clear functions with single responsibilities
✓ Add JSDoc comments for complex functions
✓ Implement proper error handling with try-catch
✓ Use localStorage for state persistence if needed
✓ Add loading states and success/error feedback
✓ Parse URL query parameters with URLSearchParams if mentioned
✓ Validate all user inputs before processing

Code Quality Standards:
✓ DRY principle - no repeated code blocks
✓ Clear variable names (isLoading, not x; calculateTotal, not calc)
✓ Add comments explaining WHY, not WHAT
✓ Keep functions under 30 lines
✓ Use meaningful CSS class names (BEM methodology preferred)

User Experience:
✓ Show loading spinners during async operations
✓ Display clear error messages (not "Error 404")
✓ Add success confirmations for user actions
✓ Include keyboard shortcuts (Enter to submit, Esc to close)
✓ Focus management for accessibility
✓ Empty states with helpful messages

Performance:
✓ Minimize DOM queries (cache selectors)
✓ Use event delegation where appropriate
✓ Debounce search/filter inputs
✓ Lazy load images if any

STRICTLY FORBIDDEN:
✗ NO external dependencies requiring npm/build steps
✗ NO jQuery or other heavy libraries
✗ NO inline styles (except dynamic JS-generated)
✗ NO console.log in production code
✗ NO alert() or confirm() - use custom modals
✗ NO var keyword - only const/let

OUTPUT FORMAT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return ONLY the complete HTML file. Structure:

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="[SEO description]">
    <title>[Descriptive Title]</title>
    <style>
        /* CSS Custom Properties */
        :root {{
            --primary: #...;
            --secondary: #...;
            /* ... */
        }}
        
        /* Reset & Base Styles */
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        /* Your styles here */
    </style>
</head>
<body>
    <!-- Your HTML here -->
    
    <script>
        'use strict';
        
        // Your JavaScript here
        
        // Initialize on DOM ready
        document.addEventListener('DOMContentLoaded', () => {{
            // Main initialization
        }});
    </script>
</body>
</html>

CRITICAL:
• Start directly with <!DOCTYPE html>
• NO markdown code fences (```
-  NO explanatory text before or after
-  The file must work when saved as index.html
-  Test all interactive features in your head before outputting

Now generate the COMPLETE, PRODUCTION-READY application:"""


    def __init__(self):
        """
        Initialize the LLM service with AI Pipe API.
        
        Raises:
            ValueError: If AIPIPE_API_KEY is not found in environment variables
        """
        load_dotenv()
        
        self.api_key = os.getenv("AIPIPE_API_KEY")

        if not self.api_key:
            raise ValueError("AIPIPE_API_KEY not found in environment variables")
        
        self.api_url = "https://aipipe.org/openrouter/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Model configurations
        self.default_model = "openai/gpt-4o-mini"  # Fast model for general use
        self.advanced_model = "openai/gpt-4o"  # Better model for revisions
        
        #Retry Strategy

        retry_strat = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist= [429, 500, 502, 503, 504],
            allowed_methods=["POST"],
            raise_on_status=False
        )

        adapter = HTTPAdapter(max_retries=retry_strat)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Rate limiting
        self._last_request_time = 0
        self._min_request_interval = 0.1

        try:
            self._templates = self._load_all_templates()
            logger.info("LLM Service initialized successfully with cached templates")
        except FileNotFoundError as e:
            logger.error(f"Template loading failed: {e}")
            raise

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
            'readme': 'readme_prompt.txt',
            'revision': 'revision_prompt.txt',
            'readme_update': 'readme_update_prompt.txt',
            'fallback_html': 'fallback.html',
            'fallback_readme': 'fallback_readme.md'
        }

        for key, filename in template_files.items():
            template_path = os.path.join(os.path.dirname(__file__),'..','templates',filename)

            if not os.path.exists(template_path):
                raise FileNotFoundError(f"Template file not found: {filename} (expected at {template_path})")
            
            with open(template_path,'r',encoding='utf-8') as file:
                templates[key] = file.read()
                logger.debug(f"Loaded template: {filename}")
            
        return templates

    def _make_api_call(self, prompt: str, model: str = None, temperature: float = 0.2, max_tokens: int = 8192) -> str:
        """
        Make an API call to AI Pipe.
        
        Args:
            prompt: The prompt to send
            model: Model to use (defaults to self.default_model)
            temperature: Temperature setting (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            
        Returns:
            Response text from the API
            
        Raises:
            Exception: If API call fails
        """
        if model is None:
            model = self.default_model
            
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
    
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        try:
            response = self.session.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=120
            )
            self._last_request_time = time.time()

            response.raise_for_status()

            result = response.json()
            return result['choices'][0]['message']['content']
            
        except requests.exceptions.Timeout:
            logger.error("API request timed out after 120 seconds")
            raise Exception("Request timed out after 120 seconds")
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error occurred: {e}")
            raise Exception(f"HTTP error: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise Exception(f"API request failed: {e}")
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected API response format: {e}")
            raise Exception(f"Unexpected API response format: {e}")

    def generate_app_code(self, brief: str, checks: List[str], attachments: Optional[List[Dict]] = None) -> Dict[str, str]:
        """
        Generate complete web application code from a brief.
        
        Args:
            brief: Natural language description of what the app should do
            checks: List of evaluation criteria
            attachments: Optional list of attachments (e.g., sample images)
        
        Returns:
            Dictionary with filenames as keys and code as values
            Example: {"index.html": "<html>...</html>"}
        """
        logger.info(f"Generating app code for brief: {brief[:100]}...")

        prompt = self._build_app_generation_prompt(brief, checks, attachments)

        try:
            response_text = self._make_api_call(prompt, temperature=0.2, max_tokens=8192)
            html_code = self._clean_response(response_text)
            logger.info(f"Generated {len(html_code)} characters of HTML code")

            return {"index.html": html_code}
        
        except Exception as e:
            logger.error(f"Error generating app code: {e}")
            return self._generate_fallback_html(brief)
        
    def generate_readme(self, task: str, brief: str, checks: List[str]) -> str:
        """
        Generate a professional README.md file.
        
        Args:
            task: Task identifier
            brief: Project description
            checks: Evaluation criteria
        
        Returns:
            README.md content as string
        """
        logger.info(f"Generating README for task: {task}")

        prompt = self._build_readme_prompt(task, brief, checks)

        try:
            readme = self._make_api_call(prompt, temperature=0.3, max_tokens=4096)
            readme = readme.strip()
            logger.info(f"Generated README with {len(readme)} characters")
            return readme

        except Exception as e:
            logger.error(f"Error generating README: {e}")
            return self._generate_fallback_readme(task, brief)

    def update_code_for_revision(self, existing_code: str, revision_brief: str, original_brief: str) -> Dict[str, str]:
        """
        Modify existing code based on a revision request.
        
        Args:
            existing_code: Current HTML code
            revision_brief: What changes to make
            original_brief: Original requirements (for context)
        
        Returns:
            Dictionary with updated code
        """
        logger.info(f"Updating code for revision: {revision_brief[:100]}...")
        
        code_preview = existing_code[:6000] if len(existing_code) > 6000 else existing_code
        prompt = self._build_revision_prompt(code_preview, revision_brief, original_brief)
        
        try:
            response_text = self._make_api_call(
                prompt, 
                model=self.advanced_model, 
                temperature=0.2, 
                max_tokens=8192
            )
            updated_code = self._clean_response(response_text)
            logger.info(f"Generated updated code with {len(updated_code)} characters")
            
            return {"index.html": updated_code}
            
        except Exception as e:
            logger.error(f"Error updating code: {e}")
            return {"index.html": existing_code}

    def update_readme_for_revision(self, existing_readme: str, revision_brief: str) -> str:
        """
        Update README.md for a revision.
        
        Args:
            existing_readme: Current README content
            revision_brief: What changed in the revision
        
        Returns:
            Updated README content
        """
        logger.info("Updating README for revision")
        
        prompt = self._build_readme_update_prompt(existing_readme, revision_brief)
        
        try:
            response_text = self._make_api_call(
                prompt, 
                model=self.advanced_model, 
                temperature=0.3, 
                max_tokens=4096
            )
            return response_text.strip()
            
        except Exception as e:
            logger.error(f"Error updating README: {e}")
            return existing_readme        

    def _build_app_generation_prompt(self, briefs: str, checks: List[str], attachments: Optional[List[Dict]]) -> str:
        """Build prompt for app generation"""
        checks_texts = '\n'.join(f'{i + 1}. {check}' for i, check in enumerate(checks))
        
        attachments_texts = ""
        if attachments:
            attachments_texts = self.attachments_template.format(length_attach=len(attachments))

        return self.prompt_template.format(brief=briefs, checks_text=checks_texts, attachments_text=attachments_texts)
    
    def _build_readme_prompt(self, task: str, brief: str, checks: List[str]) -> str:
        """Build prompt for README generation."""
        prompt = self._templates['readme']
        
        checks_text = '\n'.join(f'- {check}' for check in checks)
        task_title = task.replace('-', ' ').title()
        
        prompt = prompt.format(
            task=task,
            brief=brief,
            checks_text=checks_text,
            task_title=task_title
        )
        
        return prompt
    
    def _build_revision_prompt(self, code_preview: str, revision_brief: str, original_brief: str) -> str:
        """Build prompt for code revision."""
        prompt = self._templates['revision']
        
        prompt = prompt.format(
            original_brief=original_brief,
            code_preview=code_preview,
            revision_brief=revision_brief
        )
        
        return prompt
    
    def _build_readme_update_prompt(self, existing_readme: str, revision_brief: str) -> str:
        """Build prompt for README update."""
        prompt = self._templates['readme_update']
        
        prompt = prompt.format(
            existing_readme=existing_readme,
            revision_brief=revision_brief
        )
        
        return prompt
    
    def _clean_response(self, response_text: str) -> str:
        """Remove markdown code fences and clean the response."""
        text = response_text.strip()

        # Remove markdown code fences if present
        if text.startswith("```html"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        # Ensure it starts with DOCTYPE or html tag
        if not text.startswith("<!DOCTYPE") and not text.startswith("<html"):
            doctype_pos = text.find("<!DOCTYPE")
            if doctype_pos > 0:
                text = text[doctype_pos:]

        return text
    
    def _generate_fallback_html(self, brief: str) -> Dict[str, str]:
        """Generate basic fallback HTML if API fails."""
        html = self._templates['fallback_html']
        html = html.format(brief=brief)

        return {"index.html": html}
    
    def _generate_fallback_readme(self, task: str, brief: str) -> str:
        """Generate basic fallback README if API fails."""
        readme = self._templates['fallback_readme']
        task_title = task.replace('-', ' ').title()
        readme = readme.format(
            task_title=task_title,
            brief=brief,
            task=task
        )
        
        return readme
    

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=== Testing LLM Service ===\n")
    
    try:
        print("Initializing service...")
        service = LLMServiceAIPipe()
        print("✓ Service initialized successfully\n")
        
        brief = "Create a simple calculator with add, subtract, multiply, divide"
        checks = ["Clean UI", "All four operations", "Clear results display"]
        
        print("Testing code generation...")
        code = service.generate_app_code(brief, checks)
        print(f"✓ Generated HTML: {len(code['index.html'])} chars")
        print(f"✓ Starts with: {code['index.html'][:50]}...")
        print(f"✓ Contains closing tag: {'</html>' in code['index.html']}\n")
        
        print("Testing README generation...")
        readme = service.generate_readme("calculator-app", brief, checks)
        print(f"✓ Generated README: {len(readme)} chars")
        print(f"✓ First line: {readme.split(chr(10))[0]}\n")
        
        print("=" * 50)
        print("✓ All tests completed successfully!")
        print("=" * 50)
        
    except ValueError as e:
        print(f"\n✗ Configuration Error: {e}")
        print("Make sure AIPIPE_API_KEY is set in your .env file")
    except FileNotFoundError as e:
        print(f"\n✗ Template Error: {e}")
        print("Make sure all template files exist in the templates/ directory")
    except requests.exceptions.RequestException as e:
        print(f"\n✗ Network Error: {e}")
        print("Check your internet connection and API endpoint")
    except Exception as e:
        print(f"\n✗ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
