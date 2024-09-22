import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pdfplumber
import re
import os
import tempfile

app = Flask(__name__)
CORS(app, resources={r"/search": {"origins": "*"}})

# Create a directory to store the PDFs
PDF_STORAGE_DIR = os.path.join(os.getcwd(), "static", "pdfs")
os.makedirs(PDF_STORAGE_DIR, exist_ok=True)

def sanitize_filename(filename):
    """Sanitize the filename by removing or replacing invalid characters."""
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def extract_text_from_pdf(pdf_path):
    """Extract text from a single PDF file."""
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return None

def search_term_in_text(term, text):
    """Search for the term in the text and extract the value following it."""
    term_lower = term.lower()

    # Check if the term is found in the text
    if term_lower in text.lower():
        if term_lower == "test results":
            # Extract everything under "Test Results" until the next double newline or end of text
            pattern = rf"{term}:\s*(.*?)(?:\n\n|\Z)"
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()  # Return the section under Test Results
        else:
            # For single terms (like "Hemoglobin"), capture the specific value
            pattern = rf"{term}\s*[:=]?\s*([\d.]+)"
            match = re.search(pattern, text, re.IGNORECASE)

            if match:
                return match.group(1)  # Return the captured value

    return None



def download_pdf_from_url(url):
    """Download a PDF from a URL and save it both locally and as a temp file."""
    try:
        print(f"Attempting to download PDF from: {url}")
        response = requests.get(url)
        print(f"Response status: {response.status_code}")
        response.raise_for_status()

        # Extract and sanitize the filename from the URL
        original_filename = url.split('/')[-1]
        sanitized_filename = sanitize_filename(original_filename)

        # Create the local file path
        local_pdf_path = os.path.join(PDF_STORAGE_DIR, sanitized_filename)
        
        # Save the PDF to a temporary file for processing
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_file.write(response.content)
        temp_file.close()

        # Also save the PDF locally for future downloads
        with open(local_pdf_path, 'wb') as local_file:
            local_file.write(response.content)
        
        return temp_file.name, local_pdf_path  # Return both temp and saved paths
    except Exception as e:
        print(f"Failed to download PDF from {url}: {str(e)}")
        return None, None

def process_pdf_urls(pdf_urls, term):
    """Process PDF URLs, download them, search for the term, and extract values."""
    results = {}
    found_in_any_pdf = False
    pdf_counter = 1  # Counter for naming files as pdf1, pdf2, etc.

    for pdf_url in pdf_urls:
        try:
            # Download the PDF from the URL
            temp_pdf_path, local_pdf_path = download_pdf_from_url(pdf_url)
            if not temp_pdf_path:
                continue  # Skip the file if there was an error downloading

            # Extract text from the downloaded PDF
            extracted_text = extract_text_from_pdf(temp_pdf_path)
            os.remove(temp_pdf_path)  # Clean up the temp file after processing

            if extracted_text is None:
                continue  # Skip if there was an error reading the file

            # Search for the term in the extracted text
            term_value = search_term_in_text(term, extracted_text)

            if term_value:
                found_in_any_pdf = True
                results[f'pdf{pdf_counter}'] = term_value  # Name the file as pdf1, pdf2, etc.
                pdf_counter += 1  # Increment counter for the next file
        except Exception as e:
            continue  # Skip the file in case of any exception

    if not found_in_any_pdf:
        return {"error": f"The term '{term}' was not found in any of the provided PDFs."}

    return results


@app.route('/search', methods=['POST'])
def search_term_in_pdfs():
    """API endpoint to search for a term in multiple PDF URLs."""
    try:
        data = request.get_json()
        search_term = data.get('term')
        pdf_urls = data.get('pdfUrls', [])

        if not search_term:
            return jsonify({"error": "Search term not provided"}), 400

        if not pdf_urls or len(pdf_urls) == 0:
            return jsonify({"error": "No PDF URLs provided"}), 400

        # Process the PDFs by URLs and search for the term
        results = process_pdf_urls(pdf_urls, search_term)

        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>', methods=['GET'])
def download_pdf(filename):
    """Route to download the stored PDFs."""
    try:
        return send_from_directory(PDF_STORAGE_DIR, filename)
    except Exception as e:
        return jsonify({"error": f"Failed to download file: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)
 