import asyncio
import json
import os
import shutil
import tempfile

import aiohttp
import yaml
from keynote_parser.file_utils import process

def extract_text_from_keynote(keynote_path: str) -> list[str]:
    """
    Extracts text content from each slide of a Keynote file using keynote-parser.
    This includes text from slide content and presenter notes.

    Args:
        keynote_path (str): The full path to the Keynote file.

    Returns:
        list[str]: A list of strings, where each string is the combined text content of a slide.
                   Returns an empty list if extraction fails.
    """
    if not os.path.exists(keynote_path):
        print(f"Error: Keynote file not found at {keynote_path}")
        return []

    temp_dir = tempfile.mkdtemp()
    print(f"Unpacking Keynote file to temporary directory: {temp_dir}...")

    try:
        process(keynote_path, temp_dir)

        slide_texts = []
        index_dir = os.path.join(temp_dir, "Index")
        if not os.path.isdir(index_dir):
            print("Error: Could not find 'Index' directory in unpacked Keynote file.")
            return []

        slide_files = sorted(
            [
                f
                for f in os.listdir(index_dir)
                if f.startswith("Slide-") and f.endswith(".iwa.yaml")
            ]
        )

        for slide_file in slide_files:
            slide_path = os.path.join(index_dir, slide_file)
            with open(slide_path, "r", encoding="utf-8") as f:
                slide_data = yaml.safe_load(f)

                if slide_data.get("skipped", False):
                    continue

                def find_text_recursively(data):
                    texts = []
                    if isinstance(data, dict):
                        for key, value in data.items():
                            if key == "text" and isinstance(value, str):
                                texts.append(value)
                            elif isinstance(value, (dict, list)):
                                texts.extend(find_text_recursively(value))
                    elif isinstance(data, list):
                        for item in data:
                            texts.extend(find_text_recursively(item))
                    return texts

                all_texts = find_text_recursively(slide_data)
                slide_texts.append(" ".join(all_texts))

        return slide_texts

    except Exception as e:
        print(f"An error occurred during text extraction with keynote-parser: {e}")
        return []
    finally:
        print(f"Cleaning up temporary directory: {temp_dir}")
        shutil.rmtree(temp_dir)

async def estimate_slide_duration(slide_text: str, slide_number: int) -> dict:
    """
    Estimates the presentation duration for a single slide's text (including presenter notes)
    using the Gemini API.

    Args:
        slide_text (str): The text content of the slide, combined with its presenter notes.
        slide_number (int): The sequential number of the slide.

    Returns:
        dict: A dictionary containing the slide number, estimated duration in seconds,
              and the original text content. Returns None if estimation fails.
    """
    # Base prompt for the LLM to estimate speaking time
    # The prompt now explicitly mentions considering presenter notes
    prompt = (
        f"Estimate the natural presentation duration in seconds for the following combined slide content "
        f"(including visible text and presenter notes). Consider a moderate, clear speaking pace. "
        f"Return the estimate as a JSON object with 'slide_number' (integer), 'estimated_duration_seconds' (integer), "
        f"and 'text_content' (string). The combined text content for slide {slide_number} is:\n\n"
        f"'{slide_text}'"
    )

    # Define the expected JSON schema for the LLM's response
    generation_config = {
        "responseMimeType": "application/json",
        "responseSchema": {
            "type": "OBJECT",
            "properties": {
                "slide_number": {"type": "INTEGER"},
                "estimated_duration_seconds": {"type": "INTEGER"},
                "text_content": {"type": "STRING"}
            },
            "propertyOrdering": ["slide_number", "estimated_duration_seconds", "text_content"]
        }
    }

    chat_history = []
    chat_history.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {
        "contents": chat_history,
        "generationConfig": generation_config
    }

    # API key is intentionally left empty as per instructions for Canvas environment
    api_key = "AIzaSyA72DwZCcdIVd3vJedIj62QKuFCA08biYk" 
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    print(f"Estimating duration for slide {slide_number}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload) as response:
                response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
                result = await response.json()

                if result.get("candidates") and result["candidates"][0].get("content") and \
                   result["candidates"][0]["content"].get("parts") and \
                   result["candidates"][0]["content"]["parts"][0].get("text"):
                    
                    json_str = result["candidates"][0]["content"]["parts"][0]["text"]
                    
                    # The API might return text with leading/trailing non-JSON characters.
                    # Attempt to find the actual JSON block.
                    start_index = json_str.find('{')
                    end_index = json_str.rfind('}')
                    
                    if start_index != -1 and end_index != -1 and end_index > start_index:
                        parsed_json = json.loads(json_str[start_index:end_index+1])
                        return parsed_json
                    else:
                        print(f"Warning: Could not parse JSON from LLM response for slide {slide_number}. Response: {json_str}")
                        return {
                            "slide_number": slide_number,
                            "estimated_duration_seconds": 0, # Default to 0 on parsing error
                            "text_content": slide_text,
                            "error": "JSON parsing failed"
                        }
                else:
                    print(f"Error: LLM response for slide {slide_number} was malformed or empty: {result}")
                    return {
                        "slide_number": slide_number,
                        "estimated_duration_seconds": 0, # Default to 0 on malformed response
                        "text_content": slide_text,
                        "error": "Malformed LLM response"
                    }
    except aiohttp.ClientError as e:
        print(f"Network or HTTP error for slide {slide_number}: {e}")
        return {
            "slide_number": slide_number,
            "estimated_duration_seconds": 0, # Default to 0 on network error
            "text_content": slide_text,
            "error": str(e)
        }
    except json.JSONDecodeError as e:
        print(f"JSON decode error for slide {slide_number}: {e}. Raw response text might have been malformed.")
        return {
            "slide_number": slide_number,
            "estimated_duration_seconds": 0, # Default to 0 on JSON decode error
            "text_content": slide_text,
            "error": "JSON decode error"
        }
    except Exception as e:
        print(f"An unexpected error occurred during AI estimation for slide {slide_number}: {e}")
        return {
            "slide_number": slide_number,
            "estimated_duration_seconds": 0, # Default to 0 on unexpected error
            "text_content": slide_text,
            "error": str(e)
        }

async def main():
    """
    Main function to run the Keynote slide duration estimation application.
    Prompts the user for a Keynote file path, extracts text, and estimates durations.
    """
    keynote_file_path = input("Enter the full path to your Keynote file (e.g., /Users/YourUser/Documents/MyPresentation.key): ")
    
    # Example for testing without user input (uncomment and modify for quick testing)
    # keynote_file_path = "/Users/paulb/Desktop/TestPresentation.key" 

    slide_texts = extract_text_from_keynote(keynote_file_path)

    if not slide_texts:
        print("No text extracted. Exiting.")
        return

    print(f"\nExtracted text from {len(slide_texts)} slides. Now estimating durations...")

    tasks = []
    for i, text in enumerate(slide_texts):
        # Only process slides with content
        if text.strip():
            tasks.append(estimate_slide_duration(text, i + 1))
        else:
            print(f"Skipping empty slide {i + 1}.")
            # Add a placeholder for empty slides
            tasks.append(asyncio.create_task(asyncio.sleep(0, result={
                "slide_number": i + 1,
                "estimated_duration_seconds": 0,
                "text_content": "[Empty Slide - No text detected]"
            })))

    estimated_durations = await asyncio.gather(*tasks)

    print("\n--- Estimated Slide Durations ---")
    total_duration_seconds = 0
    for result in estimated_durations:
        slide_num = result.get("slide_number", "N/A")
        duration_sec = result.get("estimated_duration_seconds", 0)
        text_content = result.get("text_content", "No content").replace('\n', ' ').strip()
        error_msg = result.get("error", "")

        if error_msg:
            print(f"Slide {slide_num}: Error - {error_msg}")
        else:
            print(f"Slide {slide_num}: {duration_sec} seconds")
            print(f"  Content preview: '{text_content[:70]}{'...' if len(text_content) > 70 else ''}'")
            total_duration_seconds += duration_sec
        print("-" * 30)

    total_minutes = total_duration_seconds // 60
    remaining_seconds = total_duration_seconds % 60
    print(f"\nTotal Estimated Presentation Duration: {total_minutes} minutes and {remaining_seconds} seconds")
    print("Note: This estimation is based purely on text content (including presenter notes) and a moderate speaking pace.")
    print("It does not account for images, videos, animations, audience interaction, or presenter pauses.")


if __name__ == "__main__":
    # Ensure this script is run on macOS as it relies on AppleScript and Keynote.
    if os.uname().sysname != 'Darwin':
        print("This application is designed to run on macOS only, as it requires Keynote and AppleScript.")
    else:
        # Run the main asynchronous function
        asyncio.run(main())

