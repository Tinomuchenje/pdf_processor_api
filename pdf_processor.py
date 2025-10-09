"""
PDF Processor with LLM-based intelligent location extraction.
Optimized for large PDFs (250+ pages) with batch processing.
"""

import re
import os
import json
from collections import defaultdict

from PyPDF2 import PdfReader, PdfWriter
from openai import OpenAI
from dotenv import load_dotenv
import pytesseract
from pdf2image import convert_from_path

load_dotenv()

# Configuration
FREE_LLM_MODEL = 'google/gemini-2.0-flash-exp:free'
BATCH_SIZE = 50  # Pages per batch
PAGE_CONTEXT_CHARS = 3000  # Characters to send to LLM per page
TEXT_QUALITY_THRESHOLD = 50  # Min chars/page for good extraction
LARGE_PDF_THRESHOLD = 100  # Pages threshold for optimization

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_llm_client():
    """Get configured OpenRouter LLM client."""
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found. Get one at https://openrouter.ai/keys")
    
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

def parse_llm_json_response(response_text):
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = response_text.strip()
    
    # Remove markdown code blocks if present
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
        text = text.strip()
    
    return json.loads(text)

def call_llm(prompt, max_tokens=500):
    """Call LLM with prompt and return parsed JSON response."""
    try:
        client = get_llm_client()
        model = os.getenv('OPENROUTER_MODEL', FREE_LLM_MODEL)
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=max_tokens
        )
        
        result_text = response.choices[0].message.content.strip()
        return parse_llm_json_response(result_text)
    
    except json.JSONDecodeError as e:
        print(f"Failed to parse LLM JSON: {e}")
        return None
    except Exception as e:
        print(f"LLM call failed: {e}")
        return None


# ============================================================================
# TEXT EXTRACTION
# ============================================================================

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using PyPDF2."""
    reader = PdfReader(pdf_path)
    return [page.extract_text() for page in reader.pages]

def extract_text_with_ocr(pdf_path):
    """Extract text using OCR for scanned PDFs."""
    try:
        images = convert_from_path(pdf_path)
        return [pytesseract.image_to_string(img) for img in images]
    except Exception as e:
        print(f"OCR failed: {e}")
        return []

def get_pdf_text(pdf_path, use_ocr_fallback=True):
    """Get text from PDF with automatic OCR fallback for scanned documents."""
    pages_text = extract_text_from_pdf(pdf_path)
    
    if not use_ocr_fallback:
        return pages_text
    
    # Check text quality
    avg_chars = sum(len(text) for text in pages_text) / len(pages_text) if pages_text else 0
    
    if avg_chars < TEXT_QUALITY_THRESHOLD:
        print(f"Low text quality ({avg_chars:.1f} chars/page), trying OCR...")
        ocr_text = extract_text_with_ocr(pdf_path)
        if ocr_text:
            ocr_avg = sum(len(text) for text in ocr_text) / len(ocr_text)
            if ocr_avg > avg_chars:
                print("Using OCR results")
                return ocr_text
    
    return pages_text


# ============================================================================
# BUILDING/LOCATION EXTRACTION
# ============================================================================

def extract_buildings_from_page(page_text):
    """Extract building/location names from page using LLM."""
    prompt = f"""Extract ALL building/location names from this invoice page.

Return ONLY a JSON array of unique names. Example: ["48 Douglas Road", "Main Street"]
If none found, return: []

Invoice text:
---
{page_text[:4000]}
---

JSON array:"""

    result = call_llm(prompt, max_tokens=500)
    
    if result and isinstance(result, list):
        # Clean and validate
        return [b.strip() for b in result if isinstance(b, str) and len(b.strip()) > 2]
    
    # Fallback to regex if LLM fails
    return extract_buildings_regex(page_text)

def extract_building_column_data(page_text):
    """Extract data specifically from the Building column of invoice line items table."""
    prompt = f"""Extract ONLY the "Building" column data from the invoice line items table.

Invoice text:
---
{page_text[:PAGE_CONTEXT_CHARS]}
---

IMPORTANT:
- Find the line items table with columns like "Invoice Date", "Description", "Building", "Suite", etc.
- Extract ONLY the entries from the "Building" column
- Ignore all other text (headers, customer info, totals, etc.)
- Return each Building entry as a separate item

Return ONLY a JSON array of Building column entries.
Example: ["HILLSIDE BULAWAYO", "OK MART BULAWAYO"]
If no Building column found, return: []

JSON array:"""

    result = call_llm(prompt, max_tokens=300)
    
    if result and isinstance(result, list):
        return [b.strip() for b in result if isinstance(b, str) and len(b.strip()) > 1]
    
    # Fallback regex to find Building column data
    return extract_building_column_regex(page_text)

def extract_building_column_regex(page_text):
    """Fallback regex to extract Building column data from invoice table."""
    # Look for table patterns that might indicate Building column
    patterns = [
        # Pattern for Building column in table rows
        r'(?:Building|BUILDING)[\s\|]*([^\n\|]+)',
        # Pattern for table rows with multiple columns
        r'(\d{2}/\d{2}/\d{4})[\s\|]+[^\|]*[\s\|]+([A-Z][A-Z\s]+(?:BULAWAYO|HARARE|GWERU))',
    ]
    
    buildings = set()
    
    for pattern in patterns:
        for match in re.findall(pattern, page_text, re.IGNORECASE | re.MULTILINE):
            if isinstance(match, tuple):
                # Take the building part from tuple match
                building = match[1] if len(match) > 1 else match[0]
            else:
                building = match
                
            building = building.strip()
            if len(building) > 3 and not any(word in building.upper() for word in ['INVOICE', 'TOTAL', 'AMOUNT']):
                buildings.add(building)
    
    return list(buildings)[:10]

def extract_buildings_regex(page_text):
    """Fallback regex extraction when LLM fails."""
    patterns = [
        r'\b(\d+\s+[A-Za-z\s]+(?:Road|Street|Avenue|Drive|Lane|Close|Way|Place|Rd|St|Ave))\b',
        r'\b([A-Z][A-Z\.\s]{2,}[A-Z]{2,}(?:\s+[A-Z]+)*)\b',
    ]
    
    buildings = set()
    exclude_words = ['CUSTOMER', 'INVOICE', 'TOTAL', 'AMOUNT']
    
    for pattern in patterns:
        for match in re.findall(pattern, page_text):
            match = match.strip()
            if len(match) > 3 and not any(word in match.upper() for word in exclude_words):
                buildings.add(match)
    
    return list(buildings)[:10]


# ============================================================================
# LOCATION MATCHING
# ============================================================================

def find_locations_on_page(page_text, expected_locations):
    """Find which expected locations appear in the Building column of invoice table using LLM."""
    prompt = f"""Find locations ONLY in the "Building" column of the invoice line items table.

Expected locations to find: {json.dumps(expected_locations)}

Invoice text:
---
{page_text[:PAGE_CONTEXT_CHARS]}
---

IMPORTANT: 
- Look ONLY at the line items table with columns like "Invoice Date", "Description", "Building", "Suite", etc.
- Search ONLY in the "Building" column entries
- Ignore any other text on the page (headers, customer info, totals, etc.)
- Consider partial matches (e.g., "HILLSIDE" matches "HILLSIDE BULAWAYO")

Return ONLY a JSON array of matching location names from the expected list.
If none found in the Building column, return: []

JSON array:"""

    result = call_llm(prompt, max_tokens=200)
    
    if result and isinstance(result, list):
        return [loc for loc in result if loc in expected_locations]
    
    # Fallback: Extract Building column data first, then search
    building_data = extract_building_column_data(page_text)
    if building_data:
        return [loc for loc in expected_locations 
                if any(loc.lower() in building.lower() for building in building_data)]
    
    # Final fallback to string matching on entire page
    return [loc for loc in expected_locations if loc.lower() in page_text.lower()]

def find_locations_in_all_pages(pages_text, expected_locations):
    """
    Match locations to pages using LLM batch processing.
    Optimized for large PDFs (250+ pages).
    """
    total_pages = len(pages_text)
    print(f"📄 Processing {total_pages} pages...")
    
    location_pages = defaultdict(list)
    
    # Process in batches
    for batch_start in range(0, total_pages, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_pages)
        print(f"  🔍 Analyzing pages {batch_start + 1}-{batch_end}...")
        
        for i in range(batch_start, batch_end):
            page_num = i + 1
            found = find_locations_on_page(pages_text[i], expected_locations)
            
            for location in found:
                location_pages[location].append(page_num)
    
    print(f"✅ Completed {total_pages} pages")
    
    # Return sorted results for all expected locations
    return {loc: sorted(location_pages.get(loc, [])) for loc in expected_locations}

def find_locations_simple(pages_text, expected_locations):
    """Fallback simple string matching in Building column (used when LLM disabled)."""
    location_pages = defaultdict(list)
    
    for i, page_text in enumerate(pages_text):
        # Try to extract Building column data first
        building_data = extract_building_column_data(page_text)
        
            for location in expected_locations:
            # Search in Building column data if available
            if building_data:
                if any(location.lower() in building.lower() for building in building_data):
                        location_pages[location].append(i + 1)
        else:
                # Fallback to full page search
                if location.lower() in page_text.lower():
                    location_pages[location].append(i + 1)
    
    return {loc: location_pages.get(loc, []) for loc in expected_locations}


# ============================================================================
# BUILDING INFO EXTRACTION (for transparency)
# ============================================================================

def extract_building_info(pages_text, location_pages):
    """Extract building info from pages (optimized for large PDFs)."""
    building_info = {}
    total_pages = len(pages_text)
    
    if total_pages > LARGE_PDF_THRESHOLD:
        # Large PDF: only extract from matched pages
        print(f"📋 Large PDF ({total_pages} pages) - extracting from matched pages only...")
        matched_pages = set()
        for pages in location_pages.values():
            matched_pages.update(pages)
        
        for page_num in sorted(matched_pages):
            page_text = pages_text[page_num - 1]
            building_info[f"page_{page_num}"] = extract_building_column_data(page_text)
    else:
        # Small PDF: extract from all pages
        for i, page_text in enumerate(pages_text):
            building_info[f"page_{i+1}"] = extract_building_column_data(page_text)
    
    return building_info


# ============================================================================
# PDF SPLITTING
# ============================================================================

def create_split_pdfs(reader, location_pages, filename):
    """Create separate PDF files for each location."""
    result_files = []
    
    for location, page_numbers in location_pages.items():
        if not page_numbers:
            continue
        
        writer = PdfWriter()
        for page_num in page_numbers:
            writer.add_page(reader.pages[page_num - 1])
        
        # Create clean filename
        clean_name = re.sub(r'[^\w\s-]', '', location).strip()
        clean_name = re.sub(r'\s+', '_', clean_name)
        output_file = f"{clean_name}_{filename}"
        output_path = os.path.join('uploads', output_file)
        
        with open(output_path, "wb") as f:
            writer.write(f)
        
        result_files.append(output_file)
    
    return result_files


# ============================================================================
# MAIN PROCESSING FUNCTION
# ============================================================================

def process_pdf(input_pdf, expected_locations, filename, use_llm=True, use_ocr=True):
    """
    Process PDF to find and split pages by location using LLM.
    
    Args:
        input_pdf: PDF file path
        expected_locations: List of location names to find
        filename: Original filename for output naming
        use_llm: Use LLM for intelligent matching (default: True, RECOMMENDED)
        use_ocr: Use OCR fallback for scanned PDFs (default: True)
    
    Returns:
        (result_files, location_pages, building_info)
    """
    # Extract text from PDF
    pages_text = get_pdf_text(input_pdf, use_ocr)
    
    # Find which pages contain which locations (searching Building column only)
    if use_llm:
        print("🤖 Using FREE LLM to search Building column for maximum accuracy...")
        location_pages = find_locations_in_all_pages(pages_text, expected_locations)
    else:
        print("⚠️  Using simple string matching in Building column (lower accuracy)")
        location_pages = find_locations_simple(pages_text, expected_locations)
    
    # Extract building info for transparency
    building_info = extract_building_info(pages_text, location_pages)
    
    # Create split PDF files
    reader = PdfReader(input_pdf)
    result_files = create_split_pdfs(reader, location_pages, filename)
    
    return result_files, location_pages, building_info