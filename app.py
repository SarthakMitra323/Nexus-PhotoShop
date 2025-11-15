from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import uuid
from datetime import datetime
import base64
from io import BytesIO
from PIL import Image
import logging

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
app.config['MAX_IMAGES'] = 100  # Maximum number of images to store

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def allowed_file(filename):
    """Check if the file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def cleanup_old_images():
    """Remove old images if we exceed the maximum limit"""
    try:
        images = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if allowed_file(filename):
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                modified_time = os.path.getmtime(filepath)
                images.append((filepath, modified_time))
        
        # Sort by modification time (oldest first)
        images.sort(key=lambda x: x[1])
        
        # Remove oldest images if we exceed the limit
        if len(images) > app.config['MAX_IMAGES']:
            images_to_remove = len(images) - app.config['MAX_IMAGES']
            for i in range(images_to_remove):
                os.remove(images[i][0])
                logger.info(f"Removed old image: {os.path.basename(images[i][0])}")
    
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")

def save_image_locally(image_data, filename):
    """Save image to local storage"""
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # If image_data is base64, decode it
        if isinstance(image_data, str) and image_data.startswith('data:image'):
            # Remove data URL prefix
            image_data = image_data.split(',')[1]
        
        # Decode base64 data
        image_bytes = base64.b64decode(image_data)
        
        # Open image with PIL to validate and potentially convert
        image = Image.open(BytesIO(image_bytes))
        
        # Convert to RGB if necessary (for JPEG compatibility)
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')
        
        # Save the image as PNG (lossless)
        image.save(filepath, 'PNG', optimize=True)
        
        # Clean up old images
        cleanup_old_images()
        
        # Create a URL that can be used to access the image
        image_url = f"/image/{filename}"
        
        return {
            'success': True,
            'filename': filename,
            'url': image_url,
            'filepath': filepath,
            'size': os.path.getsize(filepath),
            'message': 'Image saved successfully!'
        }
    except Exception as e:
        logger.error(f"Error saving image: {str(e)}")
        return {
            'success': False,
            'error': f'Failed to save image: {str(e)}'
        }

def get_storage_info():
    """Get information about storage usage"""
    total_size = 0
    image_count = 0
    
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        if allowed_file(filename):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            total_size += os.path.getsize(filepath)
            image_count += 1
    
    return {
        'total_images': image_count,
        'total_size_bytes': total_size,
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'max_images': app.config['MAX_IMAGES'],
        'remaining_slots': max(0, app.config['MAX_IMAGES'] - image_count)
    }

@app.route('/')
def home():
    """Home endpoint"""
    storage_info = get_storage_info()
    return jsonify({
        'message': 'Nexus PhotoShop Backend API - FREE Version',
        'version': '1.0.0',
        'storage': 'Local Storage',
        'storage_info': storage_info,
        'endpoints': {
            'POST /save': 'Save an image',
            'GET /images': 'List all saved images',
            'GET /image/<filename>': 'Get a specific image',
            'DELETE /image/<filename>': 'Delete an image',
            'GET /storage': 'Get storage information'
        }
    })

@app.route('/save', methods=['POST'])
def save_image():
    """Save image endpoint - accepts both file upload and base64 data"""
    try:
        # Check storage limits
        storage_info = get_storage_info()
        if storage_info['total_images'] >= app.config['MAX_IMAGES']:
            return jsonify({
                'success': False,
                'error': f'Storage limit reached. Maximum {app.config["MAX_IMAGES"]} images allowed.'
            }), 400
        
        # Generate unique filename
        file_extension = 'png'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        filename = f"nexus_edit_{timestamp}_{unique_id}.{file_extension}"
        
        # Check if data is coming as base64
        if request.json and 'imageData' in request.json:
            image_data = request.json['imageData']
            result = save_image_locally(image_data, filename)
                
            if result['success']:
                return jsonify(result), 201
            else:
                return jsonify(result), 400
        
        # Check if data is coming as file upload
        elif 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                # Read file data
                image_data = file.read()
                
                # Convert to base64 for consistent handling
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                
                result = save_image_locally(image_base64, filename)
                    
                if result['success']:
                    return jsonify(result), 201
                else:
                    return jsonify(result), 400
            else:
                return jsonify({
                    'success': False,
                    'error': 'Invalid file type. Allowed types: png, jpg, jpeg, gif, bmp'
                }), 400
        
        else:
            return jsonify({
                'success': False,
                'error': 'No image data provided. Send as base64 in JSON or as file upload'
            }), 400
            
    except Exception as e:
        logger.error(f"Error in save_image: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/images', methods=['GET'])
def list_images():
    """List all saved images"""
    try:
        images = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if allowed_file(filename):
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_size = os.path.getsize(filepath)
                modified_time = os.path.getmtime(filepath)
                
                images.append({
                    'filename': filename,
                    'size_bytes': file_size,
                    'size_mb': round(file_size / (1024 * 1024), 2),
                    'modified': datetime.fromtimestamp(modified_time).isoformat(),
                    'url': f"/image/{filename}"
                })
        
        # Sort by modification time (newest first)
        images.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({
            'success': True,
            'images': images,
            'count': len(images)
        })
    
    except Exception as e:
        logger.error(f"Error listing images: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to list images: {str(e)}'
        }), 500

@app.route('/image/<filename>', methods=['GET'])
def get_image(filename):
    """Get a specific image by filename"""
    try:
        # Security check - prevent directory traversal
        if '..' in filename or filename.startswith('/'):
            return jsonify({
                'success': False,
                'error': 'Invalid filename'
            }), 400
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'error': 'Image not found'
            }), 404
        
        return send_file(filepath)
    
    except Exception as e:
        logger.error(f"Error retrieving image: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve image: {str(e)}'
        }), 500

@app.route('/image/<filename>', methods=['DELETE'])
def delete_image(filename):
    """Delete a specific image"""
    try:
        # Security check - prevent directory traversal
        if '..' in filename or filename.startswith('/'):
            return jsonify({
                'success': False,
                'error': 'Invalid filename'
            }), 400
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'error': 'Image not found'
            }), 404
        
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'message': f'Image {filename} deleted successfully'
        })
    
    except Exception as e:
        logger.error(f"Error deleting image: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to delete image: {str(e)}'
        }), 500

@app.route('/storage', methods=['GET'])
def storage_info():
    """Get storage information"""
    try:
        info = get_storage_info()
        return jsonify({
            'success': True,
            'storage_info': info
        })
    except Exception as e:
        logger.error(f"Error getting storage info: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to get storage info: {str(e)}'
        }), 500

@app.route('/cleanup', methods=['POST'])
def cleanup_images():
    """Manually trigger cleanup of old images"""
    try:
        cleanup_old_images()
        storage_info = get_storage_info()
        
        return jsonify({
            'success': True,
            'message': 'Cleanup completed',
            'storage_info': storage_info
        })
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Cleanup failed: {str(e)}'
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    storage_info = get_storage_info()
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'storage': 'local',
        'storage_info': storage_info
    })

if __name__ == '__main__':
    print("🚀 Nexus PhotoShop FREE Backend Starting...")
    print("💰 100% FREE - No paid services required!")
    print(f"📁 Local upload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"📊 Storage limit: {app.config['MAX_IMAGES']} images")
    print("🌐 Server running on http://localhost:5000")
    print("\n📋 Available endpoints:")
    print("   GET  /              - API information")
    print("   POST /save          - Save an image")
    print("   GET  /images        - List all images")
    print("   GET  /image/<name>  - Get specific image")
    print("   DELETE /image/<name>- Delete an image")
    print("   GET  /storage       - Storage information")
    
    # Initial storage info
    info = get_storage_info()
    print(f"\n💾 Current storage: {info['total_images']}/{app.config['MAX_IMAGES']} images ({info['total_size_mb']} MB)")
    
    app.run(debug=True, host='0.0.0.0', port=5000)