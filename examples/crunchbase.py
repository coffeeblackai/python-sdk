"""
Crunchbase HTML extraction using the CoffeeBlack SDK

This script demonstrates how to:
1. Navigate to a Crunchbase URL
2. Extract the complete HTML of each page
3. Extract structured investor data using the HTML extraction endpoint
4. Save the data as CSV
"""

import asyncio
import os
import time
from datetime import datetime
import pyautogui
import pyperclip
import csv
from coffeeblack import Argus
from typing import List

async def extract_current_page_html(sdk, page_number):
    """Helper function to extract HTML from current page"""
    try:
        # Open developer console
        print("Opening developer console...")
        pyautogui.hotkey('option', 'command', 'c')
        await asyncio.sleep(2)  # Increased delay after opening console

        # JavaScript to get complete HTML
        js_get_html = "copy(document.documentElement.outerHTML);"
        
        # Paste and execute the JavaScript
        print(f"Getting page {page_number} HTML...")
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
        print(f"Error extracting HTML from page {page_number}: {str(e)}")
        print("Full error details:")
        import traceback
        traceback.print_exc()
        return None

async def extract_investor_data(sdk, html_content):
    """Extract structured investor data from HTML using the extraction endpoint"""
    try:
        if not html_content:
            print("Warning: Empty HTML content received")
            return []

        # Define the schema for investor data
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "investments": {"type": "number"},
                    "exits": {"type": "number"},
                    "location": {"type": "string"}
                }
            }
        }

        print("Sending HTML to extraction endpoint...")
        # Extract data using the HTML extraction endpoint
        result = await sdk.extract_html(
            html=html_content,
            query="Extract all investors from the table, including their name, investor type (e.g. Individual/Angel), number of investments, number of exits, and location. Each row in the table represents one investor.",
            output_format="json",
            schema=schema
        )

        print("Received response from extraction endpoint")
        print(f"Response type: {type(result)}")
        
        # Parse the response which follows the standard format:
        # { data: any, metadata: { stats: {...}, format: string } }
        try:
            # First get the raw response data
            response_data = result.data if hasattr(result, 'data') else result.json()
            print(f"Raw response data type: {type(response_data)}")
            
            # Extract the actual data from the response
            if isinstance(response_data, dict):
                print("Processing response with metadata structure")
                print(f"Response keys: {list(response_data.keys())}")
                
                if 'data' not in response_data:
                    print("Warning: Response missing 'data' field")
                    return []
                    
                # Get the format from metadata if available
                format_type = response_data.get('metadata', {}).get('format', 'unknown')
                print(f"Response format: {format_type}")
                
                # Debug metadata if available
                if 'metadata' in response_data:
                    print("Metadata:", response_data['metadata'])
                
                extracted_data = response_data['data']
                print(f"Extracted data type: {type(extracted_data)}")
                if isinstance(extracted_data, str):
                    print(f"First 500 chars of extracted data: {extracted_data[:500]}")
            else:
                print(f"Warning: Unexpected response format. Got type: {type(response_data)}")
                print(f"First 500 chars of response: {str(response_data)[:500]}")
                return []

            # Handle different format types
            if isinstance(extracted_data, str):
                print("Data is in string format, attempting to parse...")
                if format_type == 'csv':
                    print("Parsing as CSV...")
                    # Parse CSV string into list of dictionaries
                    import io
                    csv_file = io.StringIO(extracted_data)
                    csv_reader = csv.DictReader(csv_file)
                    extracted_data = list(csv_reader)
                else:
                    # Try parsing as JSON
                    print("Attempting to parse as JSON...")
                    import json
                    try:
                        extracted_data = json.loads(extracted_data)
                        print("Successfully parsed JSON")
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse string data as JSON: {str(e)}")
                        print("JSON parse error location:", e.pos)
                        print("JSON error line:", e.lineno)
                        print("JSON error column:", e.colno)
                        if e.pos < len(extracted_data):
                            print(f"Context around error (20 chars before and after):")
                            start = max(0, e.pos - 20)
                            end = min(len(extracted_data), e.pos + 20)
                            print(extracted_data[start:end])
                        return []

            # Ensure we have a list of dictionaries
            if not isinstance(extracted_data, list):
                print(f"Warning: Expected list of investors, got {type(extracted_data)}")
                if isinstance(extracted_data, dict):
                    print(f"Dictionary keys: {list(extracted_data.keys())}")
                return []

            # Convert any numeric strings to numbers
            processed_data = []
            for investor in extracted_data:
                if not isinstance(investor, dict):
                    print(f"Warning: Expected dict for investor, got {type(investor)}")
                    continue
                    
                processed_investor = {}
                for key, value in investor.items():
                    print(f"Processing field {key}: {value} (type: {type(value)})")
                    if key in ['investments', 'exits']:
                        try:
                            processed_investor[key] = int(value) if value else 0
                        except (ValueError, TypeError):
                            print(f"Failed to convert {key}={value} to int")
                            processed_investor[key] = 0
                    else:
                        processed_investor[key] = str(value) if value else ""
                processed_data.append(processed_investor)

            print(f"Successfully extracted {len(processed_data)} investors")
            if processed_data:
                print("Sample of first investor:", processed_data[0])
            return processed_data

        except Exception as e:
            print(f"Error processing response: {str(e)}")
            print("Full error details:")
            import traceback
            traceback.print_exc()
            return []

    except Exception as e:
        print(f"Error in extract_investor_data: {str(e)}")
        print("Full error details:")
        import traceback
        traceback.print_exc()
        return []

async def merge_csv_files(run_dir: str, csv_headers: List[str]) -> str:
    """
    Merge all CSV files in the run directory into a single file.
    Returns the path to the merged file.
    """
    # Create merged CSV filename
    merged_csv = os.path.join(run_dir, "merged_investors.csv")
    
    # Write headers to merged file
    with open(merged_csv, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=csv_headers)
        writer.writeheader()
        
        # Find all CSV files in the directory
        csv_files = [f for f in os.listdir(run_dir) if f.endswith('.csv') and f != 'merged_investors.csv']
        
        # Read each CSV file and append to merged file
        for csv_file in csv_files:
            file_path = os.path.join(run_dir, csv_file)
            with open(file_path, 'r', newline='', encoding='utf-8') as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    writer.writerow(row)
    
    print(f"\nMerged {len(csv_files)} CSV files into: {merged_csv}")
    return merged_csv

async def main():
    """
    Main function that extracts and processes Crunchbase investor data.
    
    Environment variables:
    - COFFEEBLACK_API_KEY: Your CoffeeBlack API key
    - BROWSER: Browser to use (defaults to Safari if not set)
    - CRUNCHBASE_URL: URL to extract HTML from
    """
    # Initialize the SDK with API key for authentication
    api_key = os.environ.get("COFFEEBLACK_API_KEY")
    if not api_key:
        print("Warning: COFFEEBLACK_API_KEY environment variable not set. Some features may be limited.")
    
    # Initialize SDK
    sdk = Argus(
        api_key=api_key,
        verbose=True,
        debug_enabled=True,
        model="ui-detect"
    )
    
    try:
        # Create data directory if it doesn't exist
        data_dir = "crunchbase_data"
        os.makedirs(data_dir, exist_ok=True)
        
        # Create a subdirectory with timestamp for this run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = os.path.join(data_dir, timestamp)
        os.makedirs(run_dir, exist_ok=True)

        # Create CSV file for investor data
        csv_file = os.path.join(run_dir, "investors.csv")
        csv_headers = ["Name", "Type", "Investments", "Exits", "Location"]
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=csv_headers)
            writer.writeheader()
        
        # Define the browser to use - can be configured via environment variable
        browser_name = os.environ.get("BROWSER", "Safari")
        print(f"Using browser: {browser_name}")
        
        # Open and attach to the browser
        print("Opening browser...")
        await sdk.open_and_attach_to_app(browser_name, wait_time=2.0)

        # Get the URL from environment variable
        url = os.environ.get("CRUNCHBASE_URL", "https://www.crunchbase.com/discover/principal.investors/6b3605a30e042af7ccf6658fbdef3f50")
        if not url:
            print("Error: Please provide a Crunchbase URL through the CRUNCHBASE_URL environment variable")
            return

        # Navigate to Crunchbase URL
        print(f"Navigating to Crunchbase URL: {url}")
        await sdk.execute_action(f"Type '{url}' into the url bar", detection_sensitivity=0.5)
        await sdk.press_key("enter")

        # Wait for initial page to load
        print("Waiting for Crunchbase page to load...")
        await asyncio.sleep(5)

        page_number = 1
        total_pages = 20  # Cap at 1,000 results (50 investors per page * 20 pages)
        
        while page_number <= total_pages:
            try:
                # Verify we're on a page with table data
                print(f"\nVerifying page {page_number} loaded correctly...")
                see_result = await sdk.see(
                    description="Crunchbase table with company data",
                    wait=True,
                    timeout=10.0,
                    interval=0.5
                )
                
                if not see_result.get('matches', False):
                    print(f"Failed to find table on page {page_number}. Stopping.")
                    break

                # Extract HTML from current page
                html_content = await extract_current_page_html(sdk, page_number)
                if not html_content:
                    print(f"Failed to extract HTML from page {page_number}. Retrying...")
                    continue

                # Save raw HTML to file
                html_filename = os.path.join(run_dir, f"crunchbase_page_{page_number:04d}.html")
                print(f"Saving HTML to {html_filename}")
                with open(html_filename, 'w', encoding='utf-8') as f:
                    f.write(html_content)

                # Extract structured investor data
                print(f"Extracting investor data from page {page_number}...")
                investors = await extract_investor_data(sdk, html_content)

                # Save to CSV
                if investors:
                    csv_filename = os.path.join(run_dir, f"investors_page_{page_number:04d}.csv")
                    with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=csv_headers)
                        writer.writeheader()
                        for investor in investors:
                            writer.writerow({
                                "Name": investor.get("name", ""),
                                "Type": investor.get("type", ""),
                                "Investments": investor.get("investments", ""),
                                "Exits": investor.get("exits", ""),
                                "Location": investor.get("location", "")
                            })
                    print(f"Saved {len(investors)} investors from page {page_number} to {csv_filename}")
                else:
                    print(f"No investors found on page {page_number}")

                # Click Next button if not on last page
                if page_number < total_pages:
                    print("Clicking Next button...")
                    next_result = await sdk.execute_action(
                        "Click the Next link",
                        detection_sensitivity=0.3
                    )
                    
                    if not next_result.chosen_action:
                        print("Could not find Next button. Stopping.")
                        break
                    
                    # Wait for next page to load
                    await asyncio.sleep(5)
                
                page_number += 1

            except KeyboardInterrupt:
                print("\nScript interrupted by user. Saving progress...")
                break
            except Exception as e:
                print(f"Error processing page {page_number}: {str(e)}")
                print("Waiting 10 seconds before retrying...")
                await asyncio.sleep(10)
                continue

        print("\nData extraction completed! 🎉")
        print(f"Processed {page_number - 1} pages")
        print(f"Data saved in: {run_dir}")
        
        # Merge all CSV files
        merged_csv = await merge_csv_files(run_dir, csv_headers)
        print(f"Final merged CSV file: {merged_csv}")
        
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Cleaning up...")
        # Add any cleanup code here if needed

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript terminated by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc() 