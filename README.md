
# PDF Processing and Splitting API

This project provides a Flask-based API for processing and splitting PDF files based on specified locations. It allows users to upload PDF files, process them according to given criteria, and download the resulting split PDFs.

## Overview

The application consists of several key components:

1. A Flask web server (`app.py`)
2. A PDF processing module (`pdf_processor.py`)
3. Docker configuration for containerization
4. Dependencies management

## Key Features

- Upload and process PDF files
- Split PDFs based on specified locations
- Download processed PDF files
- API documentation with Swagger UI
- CORS support for cross-origin requests
- Docker containerization for easy deployment

## API Endpoints

### 1. Process PDF (`/process`)

**Input:**
- PDF file (multipart/form-data)
- List of locations (form data)

**Output:**
- List of generated PDF files
- Dictionary of locations and their corresponding page numbers

### 2. Download File (`/download/<filename>`)

**Input:**
- Filename (URL parameter)

**Output:**
- Processed PDF file

### 3. Health Check (`/hc`)

**Output:**
- API health status

## PDF Processing

The `pdf_processor.py` module handles the core functionality of PDF processing:

1. Extracts text from the input PDF
2. Searches for specified locations within the PDF text
3. Creates new PDFs for each location, containing relevant pages

## Local run

## Docker Configuration

The project includes a Dockerfile for containerization, which:

- Uses Python 3.9 slim as the base image
- Sets up the working directory
- Copies the application files
- Installs dependencies from `requirements.txt`
- Exposes port 5001
- Sets environment variables for Flask
- Defines the command to run the Flask application

## Security and Error Handling

- File upload size limit (16MB)
- Secure filename handling
- Custom error handlers for 403 and 500 errors
- Exception handling in API endpoints

## Usage

1. Build the Docker image
2. Run the container
3. Access the Swagger UI for API documentation and testing
4. Use the `/process` endpoint to upload and process PDFs
5. Download split PDFs using the `/download/<filename>` endpoint

This application provides a robust solution for PDF processing and splitting, with a focus on ease of use and deployment through Docker containerization.


## OCR Model Options
Text Detection Models:

# Available architectures: 'db_resnet50', 'db_mobilenet_v3_large', 'linknet_resnet18', 'linknet_resnet34', 'linknet_resnet50'
det_model = detection_predictor('db_resnet50', pretrained=True)

Text Recognition Models:
# Available architectures: 'crnn_vgg16_bn', 'crnn_mobilenet_v3_small', 'crnn_mobilenet_v3_large', 'sar_resnet31', 'master'
reco_model = recognition_predictor('crnn_vgg16_bn', pretrained=True)


End-to-End OCR Models:
# You can specify both detection and recognition architectures
ocr_model = ocr_predictor(
    det_arch='db_resnet50',
    reco_arch='crnn_vgg16_bn',
    pretrained=True
)

4. Key Information Extraction (KIE) Models:
# Available architectures: 'db_resnet50', 'crnn_vgg16_bn'
kie_model = kie_predictor(
    det_arch='db_resnet50',
    reco_arch='crnn_vgg16_bn',
    pretrained=True
)

KIE models not only perform OCR but also classify the extracted text into predefined categories, which can be useful for more structured document processing tasks.