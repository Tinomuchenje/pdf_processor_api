from flask import Flask, request, jsonify, send_file, redirect
from flask_cors import CORS
from werkzeug.utils import secure_filename
from flasgger import Swagger, swag_from
import os
import traceback
from doctr.io import DocumentFile
from doctr.models import ocr_predictor,kie_predictor
from PIL import Image
import io
from pdf_processor import process_pdf

app = Flask(__name__)
CORS(app)

# Swagger configuration
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/apispec.json',
            "rule_filter": lambda rule: True,  # all in
            "model_filter": lambda tag: True,  # all in
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/"
}

Swagger(app, config=swagger_config)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'tiff', 'bmp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/process', methods=['POST'])
@swag_from({
    'tags': ['PDF Processing'],
    'summary': 'Process a PDF file',
    'description': 'Upload a PDF file and specify locations to group pages',
    'parameters': [
        {
            'name': 'file',
            'in': 'formData',
            'type': 'file',
            'required': True,
            'description': 'PDF file to process'
        },
        {
            'name': 'locations',
            'in': 'formData',
            'type': 'array',
            'items': {'type': 'string'},
            'collectionFormat': 'multi',
            'required': True,
            'description': 'List of locations to search for in the PDF'
        }
    ],
    'responses': {
        200: {
            'description': 'Successful operation',
            'schema': {
                'type': 'object',
                'properties': {
                    'files': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    },
                    'location_pages': {
                        'type': 'object',
                        'additionalProperties': {
                            'type': 'array',
                            'items': {'type': 'integer'}
                        }
                    }
                }
            }
        },
        400: {
            'description': 'Bad request'
        },
        500: {
            'description': 'Internal server error'
        }
    }
})
def process():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            locations = request.form.getlist('locations')
            result_files, location_pages = process_pdf(file_path, locations, filename)
            return jsonify({
                'files': result_files,
                'location_pages': location_pages
            }), 200
        return jsonify({'error': 'Invalid file type'}), 400
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/download/<filename>', methods=['GET'])
@swag_from({
    'tags': ['File Download'],
    'summary': 'Download a processed file',
    'parameters': [
        {
            'name': 'filename',
            'in': 'path',
            'type': 'string',
            'required': True,
            'description': 'Name of the file to download'
        }
    ],
    'responses': {
        200: {
            'description': 'File downloaded successfully'
        },
        404: {
            'description': 'File not found'
        }
    }
})
def download_file(filename):
    try:
        return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 404
    
@app.route('/hc', methods=['GET'])
@swag_from({
    'tags': ['Health Check'],
    'summary': 'API health check',
    'responses': {
        200: {
            'description': 'API is healthy'
        }
    }
})
def health():
   return 'Healthy', 200

# Initialize the OCR model
ocr_model = ocr_predictor(
    det_arch='db_resnet50', 
    reco_arch='crnn_vgg16_bn',
    pretrained=True,
    assume_straight_pages=False,
    preserve_aspect_ratio=True,
    export_as_straight_boxes=False
)               

@app.route('/ocr', methods=['POST'])
@swag_from({
    'tags': ['Document Processing'],
    'summary': 'Perform OCR on a PDF or image file',
    'description': 'Upload a PDF or image file and perform OCR using Mindee DocTR',
    'parameters': [
        {
            'name': 'file',
            'in': 'formData',
            'type': 'file',
            'required': True,
            'description': 'PDF or image file to process'
        }
    ],
    'responses': {
        200: {
            'description': 'Successful operation',
            'schema': {
                'type': 'object',
                'properties': {
                    'text': {
                        'type': 'string',
                        'description': 'Extracted text from the document'
                    }
                }
            }
        },
        400: {
            'description': 'Bad request'
        },
        500: {
            'description': 'Internal server error'
        }
    }
})
def perform_ocr():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Determine file type and process accordingly
            file_extension = filename.rsplit('.', 1)[1].lower()
            if file_extension == 'pdf':
                doc = DocumentFile.from_pdf(file_path)
            else:  # Image file
                doc = DocumentFile.from_images(file_path)
            

            result = ocr_model(doc)
            
            # Extract text from the OCR result
            extracted_text = []
            for page in result.pages:
                page_text = []
                for block in page.blocks:
                    for line in block.lines:
                        line_text = ' '.join(word.value for word in line.words)
                        page_text.append(line_text)
                extracted_text.append('\n'.join(page_text))


            
            
            # Join all pages with double newlines
            full_text = '\n\n'.join(extracted_text)
            #logger.info(f"OCR completed successfully for file: {filename}")
            # Clean up: remove the temporary file
            os.remove(file_path)
            
            return jsonify({
                'text': full_text
            }), 200
        return jsonify({'error': 'Invalid file type'}), 400
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.errorhandler(403)
def forbidden_error(error):
    return jsonify({'error': 'Forbidden', 'message': str(error)}), 403

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal Server Error', 'message': str(error)}), 500

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

if __name__ == '__main__':
    app.run(debug=True)