"""
HTML extraction functionality for the CoffeeBlack SDK.
"""

import base64
import json
import logging
import time
import aiohttp
from typing import Dict, Any, Optional

from .types import ExtractResponse

logger = logging.getLogger(__name__)

class HTMLExtractor:
    """
    HTML extraction functionality for the CoffeeBlack SDK.
    Handles extracting structured data from HTML using natural language queries.
    """
    
    def __init__(self, base_url: str, api_key: Optional[str] = None, debug_enabled: bool = False, debug_dir: str = 'debug'):
        """
        Initialize the HTML extractor.
        
        Args:
            base_url: Base URL for the CoffeeBlack API
            api_key: Optional API key for authentication
            debug_enabled: Whether to enable debug logging
            debug_dir: Directory for debug logs
        """
        self.base_url = base_url
        self.api_key = api_key
        self.debug_enabled = debug_enabled
        self.debug_dir = debug_dir

    async def _make_api_request_with_retry(self, 
                                         session: aiohttp.ClientSession,
                                         url: str, 
                                         data: Dict[str, Any], 
                                         headers: Dict[str, str],
                                         max_retries: int = 2,
                                         retry_backoff: float = 0.5) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Make an API request with retry and exponential backoff for transient errors.
        """
        retries = 0
        last_exception = None
        timestamp = int(time.time())

        while retries <= max_retries:
            try:
                if retries > 0:
                    backoff_time = retry_backoff * (2 ** (retries - 1))
                    logger.info(f"Retrying API request (attempt {retries}/{max_retries}) after {backoff_time}s backoff")
                    await asyncio.sleep(backoff_time)

                async with session.post(url, json=data, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        error_message = f"API request failed with status {response.status}: {error_text}"
                        
                        # Don't retry on client errors except rate limits
                        if response.status < 500 and response.status != 429:
                            return False, None, error_message
                            
                        last_exception = RuntimeError(error_message)
                        retries += 1
                        continue

                    response_text = await response.text()
                    return True, response_text, None

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                retries += 1
            except Exception as e:
                error_message = f"Unexpected error during API request: {str(e)}"
                return False, None, error_message

        error_message = f"API request failed after {max_retries} retries. Last error: {str(last_exception)}"
        logger.warning(error_message)
        return False, None, error_message

    async def extract(self,
                     html: str,
                     query: str,
                     output_format: str = "json",
                     schema: Optional[Dict[str, Any]] = None) -> ExtractResponse:
        """
        Extract structured data from HTML based on a natural language query.
        The HTML content will be automatically base64 encoded before sending to the API.
        
        Args:
            html: The raw HTML content to extract data from
            query: Natural language query describing what data to extract
            output_format: Format for the output data ("json" or "csv")
            schema: Optional schema defining the expected structure of the output data
        
        Returns:
            ExtractResponse object that supports chaining format conversions
        
        Raises:
            ValueError: If output_format is invalid
            RuntimeError: If the API request fails
        """
        # Validate output format
        valid_formats = ["json", "csv"]
        if output_format not in valid_formats:
            raise ValueError(f"Invalid output format. Must be one of: {', '.join(valid_formats)}")
        
        # Base64 encode the HTML content
        encoded_html = base64.b64encode(html.encode()).decode()
        
        # Prepare request payload
        payload = {
            "html": encoded_html,
            "encoding": "base64",
            "query": query,
            "outputFormat": output_format
        }
        
        if schema:
            payload["schema"] = schema
        
        # Log request details if debug enabled
        if self.debug_enabled:
            logger.info(f"Extracting data from HTML with query: {query}")
            logger.info(f"Output format: {output_format}")
            if schema:
                logger.info(f"Using schema: {schema}")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Construct API URL
                url = f"{self.base_url}/api/extract/html"
                
                # Add headers including API key if provided
                headers = {
                    'Content-Type': 'application/json'
                }
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                # Make API request with retry
                success, response_text, error_message = await self._make_api_request_with_retry(
                    session=session,
                    url=url,
                    data=payload,
                    headers=headers
                )
                
                if not success:
                    raise RuntimeError(f"Failed to extract data: {error_message}")
                
                # Parse response
                try:
                    result = json.loads(response_text)
                except json.JSONDecodeError:
                    raise RuntimeError(f"Failed to parse response as JSON")
                
                # Log results if debug enabled
                if self.debug_enabled:
                    logger.info(f"Extraction completed in {result.get('processing_time', 0)}s")
                
                # Return ExtractResponse object
                return ExtractResponse(result)
                
        except Exception as e:
            raise RuntimeError(f"Failed to extract data from HTML: {e}") 