import re
from PyPDF2 import PdfReader, PdfWriter
from collections import defaultdict
import os

def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    pages_text = []
    for page in reader.pages:
        pages_text.append(page.extract_text())
    return pages_text

def find_locations_in_pages(pages_text, expected_locations):
    location_pages = defaultdict(list)
    for i, page_text in enumerate(pages_text):
        for location in expected_locations:
            if location.lower() in page_text.lower():
                location_pages[location].append(i + 1)  # Adding 1 to make page numbers 1-indexed
    return location_pages

def process_pdf(input_pdf, expected_locations, filename):
    reader = PdfReader(input_pdf)
    pages_text = extract_text_from_pdf(input_pdf)
    location_pages = find_locations_in_pages(pages_text, expected_locations)
    
    result_files = []
    for location, page_numbers in location_pages.items():
        writer = PdfWriter()
        
        for page_num in page_numbers:
            writer.add_page(reader.pages[page_num - 1])  # Subtracting 1 to convert back to 0-indexed
        
        output_pdf = f"{location.replace(' ', '_')}_{filename}.pdf"
        output_path = os.path.join('uploads', output_pdf)
        with open(output_path, "wb") as output_file:
            writer.write(output_file)
        
        result_files.append(output_pdf)
    
    return result_files, location_pages