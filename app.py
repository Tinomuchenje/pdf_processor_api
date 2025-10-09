"""
PDF Processor API - LLM-powered PDF location extraction and splitting.
Handles PDFs of any size (even 1000+ pages) with intelligent batch processing.
"""

import os
import traceback
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from flasgger import Swagger, swag_from
from pdf_processor import process_pdf

# Configuration
UPLOAD_FOLDER = 'uploads'
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16 MB

# Initialize Flask app
app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Initialize Swagger UI with minimal config
swagger_config = {
    "specs": [{"endpoint": 'apispec', "route": '/apispec.json'}],
    "swagger_ui": True,
    "specs_route": "/",
    "headers": [],
    "static_url_path": "/flasgger_static",
    "swagger_ui_bundle_js": "//unpkg.com/swagger-ui-dist@3/swagger-ui-bundle.js",
    "swagger_ui_standalone_preset_js": "//unpkg.com/swagger-ui-dist@3/swagger-ui-standalone-preset.js",
    "swagger_ui_css": "//unpkg.com/swagger-ui-dist@3/swagger-ui.css"
}

Swagger(app, config=swagger_config)

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_pdf(filename):
    """Check if file is a PDF."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/', methods=['GET'])
def home():
    """API home page - redirects to Swagger UI."""
    return jsonify({
        'message': 'PDF Processor API - LLM-powered location extraction',
        'version': '2.0.0',
        'docs': '/',
        'health': '/hc',
        'process': '/process',
        'download': '/download/<filename>'
    }), 200

@app.route('/process', methods=['POST'])
@swag_from({
    'tags': ['PDF Processing'],
    'summary': 'Process PDF with AI-powered location extraction',
    'description': 'Upload PDF and extract pages by location using FREE LLM (Google Gemini). Supports 250+ page PDFs with intelligent batch processing. Includes OCR for scanned documents.',
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
            'description': 'Locations to find in Building column (e.g., ["HILLSIDE", "OK MART"])'
        }
    ],
    'responses': {
        200: {
            'description': 'Success',
            'schema': {
                'type': 'object',
                'properties': {
                    'files': {'type': 'array', 'items': {'type': 'string'}},
                    'location_pages': {'type': 'object'},
                    'building_info': {'type': 'object'}
                }
            }
        },
        400: {'description': 'Bad request'},
        500: {'description': 'Server error'}
    }
})
def process():
    """Process PDF and split by locations."""
    try:
        # Validate file upload
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if not file.filename:
            return jsonify({'error': 'No file selected'}), 400
        
        if not is_pdf(file.filename):
            return jsonify({'error': 'Only PDF files allowed'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        # Get locations parameter
        locations = request.form.getlist('locations')
        
        # Process PDF with optimal settings (always use LLM + OCR)
        result_files, location_pages, building_info = process_pdf(
            file_path, locations, filename
        )
        
        # Return results
        return jsonify({
            'files': result_files,
            'location_pages': location_pages,
            'building_info': building_info
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/download/<filename>', methods=['GET'])
@swag_from({
    'tags': ['File Download'],
    'summary': 'Download processed file',
    'parameters': [{
        'name': 'filename',
        'in': 'path',
        'type': 'string',
        'required': True,
        'description': 'Filename to download'
    }],
    'responses': {
        200: {'description': 'File sent'},
        404: {'description': 'File not found'}
    }
})
def download_file(filename):
    """Download a processed PDF file."""
    try:
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        return jsonify({'error': f'File not found: {str(e)}'}), 404

@app.route('/hc', methods=['GET'])
@swag_from({
    'tags': ['Health Check'],
    'summary': 'Health check',
    'responses': {200: {'description': 'Healthy'}}
})
def health():
    """Health check endpoint."""
    return 'Healthy', 200


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(403)
def forbidden(error):
    return jsonify({'error': 'Forbidden', 'message': str(error)}), 403

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Server error', 'message': str(error)}), 500


# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == '__main__':
    # Get port from environment variable (Render sets PORT)
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(host='0.0.0.0', port=port, debug=debug)