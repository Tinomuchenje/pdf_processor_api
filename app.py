from flask import Flask, request, jsonify, send_file, redirect
from flask_cors import CORS
from werkzeug.utils import secure_filename
from flasgger import Swagger, swag_from
import os
import traceback
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
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/process', methods=['POST'])
@swag_from({
    'tags': ['PDF Processing'],
    'summary': 'Process a PDF file with intelligent Building column search',
    'description': 'Upload a PDF file and specify locations to search for. Uses intelligent Building column detection for improved accuracy on invoice tables. Automatically falls back to full-page search if needed. Includes OCR support for scanned PDFs.',
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
            'description': 'List of locations to search for. System intelligently searches in Building column first for better accuracy.'
        },
        {
            'name': 'use_building_column',
            'in': 'formData',
            'type': 'boolean',
            'required': False,
            'description': 'Whether to use intelligent Building column search (default: true for improved accuracy)'
        },
        {
            'name': 'use_ocr_fallback',
            'in': 'formData',
            'type': 'boolean',
            'required': False,
            'description': 'Whether to use OCR fallback for scanned PDFs (default: true)'
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
                    },
                    'building_info': {
                        'type': 'object',
                        'description': 'Building information extracted from each page for transparency'
                    },
                    'search_method': {
                        'type': 'string',
                        'description': 'Search method used (building_column_with_fallback by default for improved accuracy)'
                    },
                    'improved_accuracy': {
                        'type': 'boolean',
                        'description': 'Whether improved building column search was used'
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
            # Always use building column search for improved accuracy (default: true)
            use_building_column = request.form.get('use_building_column', 'true').lower() == 'true'
            use_ocr_fallback = request.form.get('use_ocr_fallback', 'true').lower() == 'true'
            result_files, location_pages, building_info = process_pdf(
                file_path, locations, filename, use_building_column, use_ocr_fallback
            )
            # Determine actual search method used
            search_method = 'building_column_with_fallback' if use_building_column else 'full_page_search'
            
            return jsonify({
                'files': result_files,
                'location_pages': location_pages,
                'building_info': building_info,
                'search_method': search_method,
                'improved_accuracy': use_building_column
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

@app.errorhandler(403)
def forbidden_error(error):
    return jsonify({'error': 'Forbidden', 'message': str(error)}), 403

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal Server Error', 'message': str(error)}), 500

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

if __name__ == '__main__':
    app.run(debug=True)