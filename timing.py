import os
import fitz  # PyMuPDF
import google.generativeai as genai
import json
import re

# --- Configuration ---
# IMPORTANT: Replace with your actual Google API Key
# You can get a key from https://aistudio.google.com/app/apikey
API_KEY = "AIzaSyA72DwZCcdIVd3vJedIj62QKuFCA08biYk"

# --- Main Application Logic ---

def get_image_descriptions(page):
    """
    Extracts a summary of images on a page.
    Instead of sending image data, we describe the images to the LLM.
    """
    image_list = page.get_images(full=True)
    if not image_list:
        return "No images on this slide."

    image_descriptions = []
    # Analyze the images to create a description
    # This is a simplified analysis. More complex logic could analyze image size, position, etc.
    if len(image_list) == 1:
        img_info = page.get_image_info()[0]
        width, height = img_info['width'], img_info['height']
        if width > page.rect.width * 0.7 or height > page.rect.height * 0.7:
             image_descriptions.append("a single, large, dominant image")
        else:
             image_descriptions.append("a single, small-to-medium-sized image")
    else:
        image_descriptions.append(f"{len(image_list)} images of varying sizes")

    # You could add more sophisticated analysis here, e.g., trying to guess if an image
    # is a chart or a photograph based on its properties.
    # For now, we'll keep it general.

    return f"The slide contains {', '.join(image_descriptions)}."


def analyze_slide_timing(slide_number, text_content, image_description, model):
    """
    Sends the slide content to the Gemini API and returns the estimated time.
    """
    # Clean up text by removing excessive newlines and spaces
    cleaned_text = re.sub(r'\s+', ' ', text_content).strip()

    prompt = f"""
    You are an expert presentation coach. Your task is to estimate the presentation time for the following slide in minutes.

    **Slide Number:** {slide_number}

    **Slide Content:**
    * **Text:** "{cleaned_text}"
    * **Visuals:** "{image_description}"

    **Instructions for Estimation:**
    Analyze the provided text and visual description to estimate the time required to present this slide effectively. Consider the following factors:
    1.  **Text Volume and Complexity:** Word count, density of information, and use of technical jargon.
    2.  **Number of Points:** How many distinct ideas, bullet points, or concepts are presented?
    3.  **Visual Element Explanation:** Time needed to describe or refer to images, charts, or diagrams. A simple decorative image might need 5-10 seconds. A complex data chart or flowchart could require 60-90 seconds.
    4.  **Cognitive Load:** How much mental effort is required for the audience to understand the slide? Is it dense and data-heavy or light and simple?

    **Output Format:**
    Return your response as a JSON object with two keys:
    1.  "estimated_time": A floating-point number representing the estimated time in minutes (e.g., 2.5).
    2.  "reasoning": A brief, one-sentence explanation for your time estimate.

    **Example Response:**
    {{
        "estimated_time": 1.5,
        "reasoning": "The slide contains a moderate amount of text across three bullet points and a single supporting image, requiring a concise explanation."
    }}
    """

    try:
        response = model.generate_content(prompt)
        # The API response might have ```json ... ``` markers, remove them
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(cleaned_response)
        return result
    except (json.JSONDecodeError, AttributeError, ValueError) as e:
        print(f"Error processing API response for slide {slide_number}: {e}")
        print(f"Raw response was: {response.text}")
        return {"estimated_time": 0.0, "reasoning": "Failed to parse API response."}
    except Exception as e:
        print(f"An unexpected API error occurred for slide {slide_number}: {e}")
        return {"estimated_time": 0.0, "reasoning": "An unexpected API error occurred."}


def main():
    """
    Main function to run the presentation timing analysis.
    """
    print("--- Presentation Time Estimator ---")

    # --- API Key Check ---
    if API_KEY == "YOUR_API_KEY" or not API_KEY:
        print("\nERROR: Please replace 'YOUR_API_KEY' with your actual Google API key.")
        return

    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-1.5-pro')
    except Exception as e:
        print(f"Error configuring the AI model: {e}")
        print("Please ensure your API key is valid.")
        return

    # --- PDF File Input ---
    pdf_path = input("Enter the full path to your PDF file: ").strip()

    if not os.path.exists(pdf_path):
        print(f"\nError: The file '{pdf_path}' was not found.")
        return

    if not pdf_path.lower().endswith('.pdf'):
        print("\nError: The specified file is not a PDF.")
        return

    # --- PDF Processing ---
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening or parsing the PDF file: {e}")
        return

    total_estimated_time = 0.0
    print("\nAnalyzing slides... please wait.\n")

    print("-" * 50)
    print(f"{'Slide #':<10} | {'Est. Time (min)':<20} | {'Reasoning':<50}")
    print("-" * 50)

    for i, page in enumerate(doc):
        slide_number = i + 1
        text = page.get_text("text")
        images_desc = get_image_descriptions(page)

        # Skip analysis if the slide is essentially blank
        if not text.strip() and "No images" in images_desc:
            print(f"{slide_number:<10} | {'0.0':<20} | {'Slide is blank.'}")
            continue

        analysis = analyze_slide_timing(slide_number, text, images_desc, model)
        time = analysis.get("estimated_time", 0.0)
        reason = analysis.get("reasoning", "No reasoning provided.")

        print(f"{slide_number:<10} | {time:<20.2f} | {reason}")
        total_estimated_time += time

    print("-" * 50)
    print(f"\nTotal Estimated Presentation Time: {total_estimated_time:.2f} minutes")
    print(f"Total Number of Slides: {len(doc)}")


if __name__ == "__main__":
    main()
