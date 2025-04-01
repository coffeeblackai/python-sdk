"""
Investor Profile Enrichment Script

This script:
1. Reads investor data from merged_investors.csv
2. Uses SERP to find LinkedIn profile URLs
3. Uses Gemini to filter and validate profile URLs
4. Uses CoffeeBlack SDK to analyze LinkedIn profiles
5. Extracts and enriches profile information
6. Creates an enriched CSV with additional data
"""

import os
import json
import asyncio
import logging
import pandas as pd
import requests
import pyautogui
import pyperclip
from typing import Dict, List, Any, Optional
from datetime import datetime
from coffeeblack import Argus
from vertexai.preview.generative_models import GenerativeModel, Part
from google.cloud import aiplatform
import dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("InvestorEnrichment")

class InvestorEnricher:
    def __init__(self, 
                 output_folder: str = "enriched_investors",
                 coffeeblack_api_key: Optional[str] = None,
                 serp_api_key: Optional[str] = None,
                 serp_engine_id: Optional[str] = None,
                 project_id: Optional[str] = None,
                 location: str = "us-central1"):
        """
        Initialize the InvestorEnricher
        
        Args:
            output_folder: Folder to save enriched data
            coffeeblack_api_key: API key for CoffeeBlack SDK
            serp_api_key: API key for Google Custom Search API
            serp_engine_id: Engine ID for Google Custom Search API
            project_id: Google Cloud project ID
            location: Google Cloud location
        """
        self.output_folder = output_folder
        self.coffeeblack_api_key = coffeeblack_api_key or os.environ.get("COFFEEBLACK_API_KEY")
        self.serp_api_key = serp_api_key or os.environ.get("SERP_API_KEY")
        self.serp_engine_id = serp_engine_id or os.environ.get("SERP_ENGINE_ID")
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = location
        
        # Create output folder
        os.makedirs(self.output_folder, exist_ok=True)
        
        # Initialize CoffeeBlack SDK
        if self.coffeeblack_api_key:
            self.sdk = Argus(
                api_key=self.coffeeblack_api_key,
                verbose=True,
                debug_enabled=True,
                model="ui-detect"
            )
            logger.info("Initialized CoffeeBlack SDK")
        else:
            logger.warning("No CoffeeBlack API key provided!")
            self.sdk = None
            
        if not self.serp_api_key or not self.serp_engine_id:
            logger.warning("Missing SERP API key or Engine ID - some features may be limited")
            
        # Initialize Vertex AI
        if self.project_id:
            logger.info(f"Initializing Vertex AI with project: {self.project_id}")
            aiplatform.init(project=self.project_id, location=self.location)
            self.model = GenerativeModel("gemini-pro")
        else:
            logger.warning("No Google Cloud project ID provided!")
            self.model = None
        
        logger.info(f"InvestorEnricher initialized with output folder: {output_folder}")
    
    async def find_linkedin_profile(self, investor_name: str) -> Optional[str]:
        """
        Find LinkedIn profile URL using Google Custom Search API and Gemini
        
        Args:
            investor_name: Name of the investor to search for
            
        Returns:
            LinkedIn profile URL if found, None otherwise
        """
        try:
            if not self.serp_api_key or not self.serp_engine_id:
                logger.warning("SERP API not configured, skipping profile search")
                return None
                
            # Prepare search query
            params = {
                'key': self.serp_api_key,
                'cx': self.serp_engine_id,
                'q': f"{investor_name} linkedin profile",
                'num': 5,
                'siteSearch': 'linkedin.com',
                'siteSearchFilter': 'i'
            }
            
            # Make the request
            response = await asyncio.to_thread(
                requests.get,
                "https://www.googleapis.com/customsearch/v1", 
                params=params
            )
            
            if response.status_code != 200:
                logger.error(f"SERP API error: {response.status_code}")
                return None
            
            data = response.json()
            
            # Collect all potential LinkedIn profile URLs
            profile_urls = []
            if "items" in data:
                for item in data["items"]:
                    link = item.get("link", "")
                    if "linkedin.com/in/" in link:
                        profile_urls.append({
                            "url": link,
                            "title": item.get("title", ""),
                            "snippet": item.get("snippet", "")
                        })
            
            if not profile_urls:
                return None
                
            # Use Gemini to analyze and select the best profile URL
            if self.model:
                prompt = f"""
                Analyze these LinkedIn profile URLs for {investor_name} and select the most likely correct profile.
                Consider the title and snippet information provided.
                
                Profile options:
                {json.dumps(profile_urls, indent=2)}
                
                Return ONLY the URL of the most likely correct profile, or "none" if none are likely correct.
                """
                
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    prompt
                )
                
                selected_url = response.text.strip().strip('"')
                if selected_url.lower() != "none":
                    return selected_url
            
            # Fallback to first URL if Gemini analysis fails
            return profile_urls[0]["url"]
            
        except Exception as e:
            logger.error(f"Error finding LinkedIn profile: {str(e)}")
            return None
    
    async def extract_profile_html(self, profile_url: str) -> Optional[str]:
        """Helper function to extract HTML from LinkedIn profile"""
        try:
            # Open developer console
            print("Opening developer console...")
            pyautogui.hotkey('option', 'command', 'c')
            await asyncio.sleep(2)  # Increased delay after opening console

            # JavaScript to get complete HTML
            js_get_html = "copy(document.documentElement.outerHTML);"
            
            # Paste and execute the JavaScript
            print("Getting profile HTML...")
            pyperclip.copy(js_get_html)
            await asyncio.sleep(1)  # Added delay before typing
            pyautogui.hotkey('command', 'v')
            await asyncio.sleep(1)  # Added delay before pressing enter
            pyautogui.press('enter')
            await asyncio.sleep(3)  # Increased delay to ensure HTML is copied

            # Get the HTML from clipboard
            html_content = pyperclip.paste()
            
            # Close the console
            print("Closing developer console...")
            await asyncio.sleep(1)  # Added delay before closing console
            pyautogui.hotkey('option', 'command', 'i')
            await asyncio.sleep(2)  # Increased delay after closing console
            
            return html_content

        except Exception as e:
            print(f"Error extracting HTML from profile: {str(e)}")
            print("Full error details:")
            import traceback
            traceback.print_exc()
            return None
    
    async def analyze_profile(self, investor_name: str) -> Dict[str, Any]:
        """
        Analyze an investor's profile using CoffeeBlack SDK
        
        Args:
            investor_name: Name of the investor to analyze
            
        Returns:
            Dictionary containing extracted profile information
        """
        try:
            logger.info(f"Analyzing profile for: {investor_name}")
            
            if not self.sdk:
                return {"error": "Missing CoffeeBlack SDK"}
            
            # First find the LinkedIn profile URL
            profile_url = await self.find_linkedin_profile(investor_name)
            if not profile_url:
                return {"error": "Could not find LinkedIn profile URL"}
            
            # Open and attach to Safari
            logger.info("Opening Safari...")
            await self.sdk.open_and_attach_to_app("Safari", wait_time=2.0)
            
            try:
                # Navigate to the profile
                logger.info(f"Navigating to profile: {profile_url}")
                await self.sdk.execute_action(
                    f"Type '{profile_url}' into the url bar",
                    detection_sensitivity=0.5
                )
                await self.sdk.press_key("enter")
                
                # Wait for page to load
                await asyncio.sleep(5)
                
                # Extract HTML content using developer console
                html_content = await self.extract_profile_html(profile_url)
                if not html_content:
                    return {"error": "Could not extract profile HTML"}
                
                # Save raw HTML to file
                html_filename = os.path.join(self.output_folder, f"{investor_name.lower().replace(' ', '_')}_profile.html")
                with open(html_filename, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                # Define schema for profile data
                schema = {
                    "type": "object",
                    "properties": {
                        "current_company": {"type": "string"},
                        "current_role": {"type": "string"},
                        "previous_companies": {"type": "array", "items": {"type": "string"}},
                        "previous_roles": {"type": "array", "items": {"type": "string"}},
                        "education": {"type": "array", "items": {"type": "string"}},
                        "skills": {"type": "array", "items": {"type": "string"}},
                        "location": {"type": "string"},
                        "bio": {"type": "string"},
                        "connection_degree": {"type": "string"}
                    }
                }
                
                # Extract structured data using the HTML extraction endpoint
                result = await self.sdk.extract_html(
                    html=html_content,
                    query="Extract the following information from this LinkedIn profile: current company, current role, previous companies, previous roles, education, skills, location, bio, and connection degree.",
                    output_format="json",
                    schema=schema
                )
                
                if not result or not hasattr(result, 'data'):
                    return {"error": "No profile data found"}
                
                # Extract the data from the response
                profile_data = result.data if hasattr(result, 'data') else result.json()
                if isinstance(profile_data, dict) and 'data' in profile_data:
                    profile_data = profile_data['data']
                
                # If they are a second connection, get mutual connections
                if profile_data.get('connection_degree') == '2nd degree connection':
                    logger.info("Found 2nd connection, getting mutual connections...")
                    
                    # Click on mutual connections link
                    await self.sdk.execute_action(
                        "Click on the mutual connections link",
                        detection_sensitivity=0.5
                    )
                    
                    # Wait for page to load
                    await asyncio.sleep(5)
                    
                    # Extract mutual connections HTML
                    mutual_html = await self.extract_profile_html(profile_url)
                    if mutual_html:
                        # Save mutual connections HTML
                        mutual_filename = os.path.join(self.output_folder, f"{investor_name.lower().replace(' ', '_')}_mutual_connections.html")
                        with open(mutual_filename, 'w', encoding='utf-8') as f:
                            f.write(mutual_html)
                        
                        # Extract mutual connections data
                        mutual_schema = {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "title": {"type": "string"},
                                    "company": {"type": "string"}
                                }
                            }
                        }
                        
                        mutual_result = await self.sdk.extract_html(
                            html=mutual_html,
                            query="Extract the names, titles, and companies of all mutual connections listed.",
                            output_format="json",
                            schema=mutual_schema
                        )
                        
                        if mutual_result and hasattr(mutual_result, 'data'):
                            mutual_data = mutual_result.data if hasattr(mutual_result, 'data') else mutual_result.json()
                            if isinstance(mutual_data, dict) and 'data' in mutual_data:
                                profile_data['mutual_connections'] = mutual_data['data']
                
                return profile_data
                
            finally:
                # Close Safari with Cmd+Q
                logger.info("Closing Safari...")
                pyautogui.hotkey('command', 'q')
                await asyncio.sleep(2)  # Wait for Safari to close
            
        except Exception as e:
            logger.error(f"Error analyzing profile: {str(e)}")
            return {"error": str(e)}
    
    async def enrich_investors(self, input_csv: str, output_csv: str):
        """
        Enrich investor data with profile information
        
        Args:
            input_csv: Path to input CSV file
            output_csv: Path to output CSV file
        """
        try:
            # Read input CSV
            df = pd.read_csv(input_csv)
            
            # Add new columns for enriched data
            df['current_company'] = None
            df['current_role'] = None
            df['previous_companies'] = None
            df['previous_roles'] = None
            df['education'] = None
            df['skills'] = None
            df['profile_url'] = None
            df['connection_degree'] = None
            df['location'] = None
            df['bio'] = None
            df['mutual_connections'] = None  # New column for mutual connections
            
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_csv), exist_ok=True)
            
            # Process each investor
            for index, row in df.iterrows():
                investor_name = row['Name']
                logger.info(f"\nProcessing investor {index + 1}/{len(df)}: {investor_name}")
                
                try:
                    # Analyze profile
                    profile_info = await self.analyze_profile(investor_name)
                    
                    if "error" not in profile_info:
                        # Update DataFrame with profile info
                        for key in profile_info:
                            if key in df.columns:
                                df.at[index, key] = profile_info[key]
                        
                        # Save progress after each successful profile
                        df.to_csv(output_csv, index=False)
                        logger.info(f"Saved progress to {output_csv}")
                    
                    # Add delay to avoid rate limiting
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Error processing investor {investor_name}: {str(e)}")
                    # Save progress even if there's an error
                    df.to_csv(output_csv, index=False)
                    continue
            
            logger.info(f"\nCompleted processing all investors. Final data saved to: {output_csv}")
            
        except Exception as e:
            logger.error(f"Error enriching investors: {str(e)}")
            # Save progress even if there's an error
            df.to_csv(output_csv, index=False)

async def main_async():
    """Async main function"""
    input_csv = "crunchbase_data/20250324_225839/merged_investors.csv"
    output_csv = "enriched_investors/enriched_investors.csv"
    
    enricher = InvestorEnricher()
    await enricher.enrich_investors(input_csv, output_csv)

def main():
    """Main function"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main() 