import re
from PyPDF2 import PdfReader, PdfWriter
from collections import defaultdict
import os
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import tempfile

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using PyPDF2"""
    reader = PdfReader(pdf_path)
    pages_text = []
    for page in reader.pages:
        pages_text.append(page.extract_text())
    return pages_text

def extract_text_with_ocr(pdf_path):
    """Extract text using OCR as fallback for scanned PDFs"""
    try:
        # Convert PDF pages to images
        images = convert_from_path(pdf_path)
        pages_text = []
        
        for image in images:
            # Use OCR to extract text from image
            text = pytesseract.image_to_string(image)
            pages_text.append(text)
        
        return pages_text
    except Exception as e:
        print(f"OCR extraction failed: {e}")
        return []

def extract_building_column_from_text(page_text):
    """
    Extract building information from the invoice table structure.
    Looks specifically for the Building column in the invoice table.
    """
    buildings = []
    
    # Strategy 1: Look for table row data that contains dates (invoice rows)
    # and extract the building field from those rows
    invoice_rows = re.findall(r'(\d{2}/\d{2}/\d{4}.*)', page_text)
    
    for row in invoice_rows:
        # Split the row into columns (typically tab or multiple spaces separated)
        columns = re.split(r'\s{2,}|\t', row)
        
        # In typical invoice layout: Date, Description, Building, Suite, VAT, Unit, Price, Amount
        # Building is usually the 3rd column (index 2)
        if len(columns) >= 3:
            potential_building = columns[2].strip()
            
            # Validate this looks like a building/location name
            if (potential_building and 
                len(potential_building) > 2 and
                not re.match(r'^\d+\.?\d*$', potential_building) and  # Not just numbers
                not re.match(r'^[A-Z]\s+[A-Z]$', potential_building)):  # Not VAT codes
                buildings.append(potential_building)
    
    # Strategy 2: Direct pattern matching for known building formats
    building_patterns = [
        # Address patterns: "48 Douglas Road", "123 Main Street"
        r'\b(\d+\s+[A-Za-z\s]+(?:Road|Street|Avenue|Drive|Lane|Close|Way|Place|Rd|St|Ave))\b',
        
        # Location codes: "O.M HSE CHIREDZI", "ABC BUILDING NAME"
        r'\b([A-Z][A-Z\.\s]{2,}[A-Z]{2,}(?:\s+[A-Z]+)*)\b',
        
        # Mixed format: "O.M HSE CHIREDZI", "HSE BUILDING"
        r'\b([A-Z\.]+\s+HSE\s+[A-Z]+)\b',
    ]
    
    for pattern in building_patterns:
        matches = re.findall(pattern, page_text)
        for match in matches:
            match = match.strip()
            # Additional filtering
            if (match and 
                len(match) > 3 and
                'CUSTOMER' not in match.upper() and
                'INVOICE' not in match.upper() and
                'VAT' not in match.upper() and
                'AMOUNT' not in match.upper() and
                match not in buildings):
                buildings.append(match)
    
    # Strategy 3: Find building data in table structure context
    # Look for lines with "Building" header and extract the corresponding data
    lines = page_text.split('\n')
    building_header_found = False
    
    for i, line in enumerate(lines):
        # Find the table header
        if 'Building' in line and 'Description' in line:
            building_header_found = True
            continue
            
        # Process data rows after finding the header
        if building_header_found and line.strip():
            # Skip obvious header or separator lines
            if any(keyword in line.lower() for keyword in ['code', 'incl vat', '---', '===', 'amount before']):
                break
                
            # If this line contains a date pattern, it's likely a data row
            if re.search(r'\d{2}/\d{2}/\d{4}', line):
                # Try to extract building information from this line
                # Remove date and description parts, focus on building section
                parts = re.split(r'\s{3,}', line)  # Split on 3+ spaces
                
                for part in parts[1:4]:  # Skip first part (likely date/description), check next few
                    part = part.strip()
                    if (part and 
                        len(part) > 3 and
                        not re.match(r'^\d{2}/\d{2}/\d{4}', part) and  # Not a date
                        not re.match(r'^[\d\.,]+$', part) and  # Not just numbers/money
                        not re.match(r'^[A-Z]\s*[A-Z]$', part) and  # Not VAT codes
                        'SHOP' not in part.upper() or 'ROAD' in part.upper() or 'HSE' in part.upper()):
                        buildings.append(part)
                        break
                break  # Only process first data row
    
    # Clean and deduplicate results
    cleaned_buildings = []
    for building in buildings:
        building = building.strip()
        # Remove duplicates and overly generic terms
        if (building and 
            building not in cleaned_buildings and
            len(building) > 3 and
            not building.upper().startswith('CUSTOMER') and
            not building.upper().startswith('ATTENTION')):
            cleaned_buildings.append(building)
    
    return cleaned_buildings

def find_locations_in_pages(pages_text, expected_locations, use_building_column=True):
    """
    Find locations in pages with intelligent search strategy.
    Default: Building column search with automatic fallback for maximum compatibility.
    """
    location_pages = defaultdict(list)
    
    for i, page_text in enumerate(pages_text):
        if use_building_column:
            # Extract building information from this page
            building_info = extract_building_column_from_text(page_text)
            
            # Track which locations were found via building column search
            found_locations = set()
            
            # Search within building information first (improved accuracy)
            for location in expected_locations:
                for building in building_info:
                    if location.lower() in building.lower():
                        location_pages[location].append(i + 1)
                        found_locations.add(location)
                        break
            
            # For locations not found in building column, fallback to full-page search
            # This ensures existing integrations always get results
            unfound_locations = set(expected_locations) - found_locations
            if unfound_locations:
                for location in unfound_locations:
                    if location.lower() in page_text.lower():
                        location_pages[location].append(i + 1)
        else:
            # Original full-page search for explicit backward compatibility
            for location in expected_locations:
                if location.lower() in page_text.lower():
                    location_pages[location].append(i + 1)
    
    return location_pages

def process_pdf(input_pdf, expected_locations, filename, use_building_column=True, use_ocr_fallback=True):
    """
    Process PDF to find and extract pages containing specified locations.
    
    Args:
        input_pdf: Path to input PDF file
        expected_locations: List of locations to search for
        filename: Original filename for output naming
        use_building_column: If True, search only in Building column (default: True)
        use_ocr_fallback: If True, use OCR if regular text extraction fails (default: True)
    
    Returns:
        tuple: (result_files, location_pages, building_info)
    """
    reader = PdfReader(input_pdf)
    
    # Try regular text extraction first
    pages_text = extract_text_from_pdf(input_pdf)
    
    # Check if text extraction was successful (if pages have very little text, might be scanned)
    text_quality_threshold = 50  # Minimum characters per page to consider good extraction
    avg_text_length = sum(len(text) for text in pages_text) / len(pages_text) if pages_text else 0
    
    # If text extraction seems poor and OCR fallback is enabled, try OCR
    if use_ocr_fallback and avg_text_length < text_quality_threshold:
        print(f"Text extraction quality low (avg {avg_text_length:.1f} chars/page), trying OCR...")
        ocr_pages_text = extract_text_with_ocr(input_pdf)
        if ocr_pages_text:
            # Use OCR results if they contain more text
            ocr_avg_length = sum(len(text) for text in ocr_pages_text) / len(ocr_pages_text)
            if ocr_avg_length > avg_text_length:
                print("Using OCR results for better text extraction")
                pages_text = ocr_pages_text
    
    # Find locations using improved algorithm
    location_pages = find_locations_in_pages(pages_text, expected_locations, use_building_column)
    
    # Extract building information for debugging/transparency
    building_info = {}
    for i, page_text in enumerate(pages_text):
        building_info[f"page_{i+1}"] = extract_building_column_from_text(page_text)
    
    # Create split PDFs
    result_files = []
    for location, page_numbers in location_pages.items():
        if page_numbers:  # Only create file if pages were found
            writer = PdfWriter()
            
            for page_num in page_numbers:
                writer.add_page(reader.pages[page_num - 1])  # Convert to 0-indexed
            
            # Clean location name for filename
            clean_location = re.sub(r'[^\w\s-]', '', location).strip()
            clean_location = re.sub(r'\s+', '_', clean_location)
            output_pdf = f"{clean_location}_{filename}"
            output_path = os.path.join('uploads', output_pdf)
            
            with open(output_path, "wb") as output_file:
                writer.write(output_file)
            
            result_files.append(output_pdf)
    
    return result_files, location_pages, building_info