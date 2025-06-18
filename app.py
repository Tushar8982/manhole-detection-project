import os
import logging
from flask import Flask, render_template, request, url_for
from inference_sdk import InferenceHTTPClient
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Create Flask app
app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = "static/uploads"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize Roboflow client
try:
    CLIENT = InferenceHTTPClient(
        api_url="https://detect.roboflow.com",
        api_key="9HopKUn5y13R8AhwnhrQ"
    )
    logging.info("Roboflow client initialized successfully")
except Exception as e:
    logging.error(f"Failed to initialize Roboflow client: {e}")
    CLIENT = None

@app.route('/')
def home():
    """Render the home page with file upload form"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    """Handle file upload and manhole detection"""
    # Check if Roboflow client is initialized
    if not CLIENT:
        logging.error("Roboflow client not initialized")
        return render_template('result.html', 
                               message="Detection service is currently unavailable. Please try again later.")
    
    try:
        # Validate file upload
        if 'file' not in request.files:
            logging.error("No file part in the request")
            return render_template('result.html', message="No file uploaded. Please select a file.")
        
        file = request.files['file']
        if file.filename == '':
            logging.error("No selected file")
            return render_template('result.html', message="No file selected. Please choose an image file.")
        
        # Check if file type is allowed
        if not allowed_file(file.filename):
            logging.error(f"Invalid file type: {file.filename}")
            return render_template('result.html', 
                                   message="Invalid file type. Please upload an image file (PNG, JPG, JPEG, GIF, BMP, WEBP).")
        
        # Secure filename to prevent potential security issues
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the file
        try:
            file.save(filepath)
            logging.info(f"File saved successfully: {filepath}")
        except Exception as save_error:
            logging.error(f"Error saving file: {save_error}")
            return render_template('result.html', message="Error saving uploaded file. Please try again.")
        
        # Convert filepath to URL for template
        image_url = url_for('static', filename=f'uploads/{filename}')
        
        # Perform inference
        try:
            logging.info(f"Starting inference for: {filepath}")
            result = CLIENT.infer(filepath, model_id="data-lwv3a/1")
            
            # Log raw inference result for debugging
            logging.info(f"Raw inference result: {result}")
            
            predictions = result.get('predictions', [])
            
            if not predictions:
                logging.warning("No predictions found in the image")
                return render_template('result.html', 
                                       image=image_url, 
                                       message="No manhole detected in the image. Please try with a clearer image.")
            
            # Find the best prediction based on confidence
            best_prediction = max(predictions, key=lambda x: x.get('confidence', 0))
            label = best_prediction.get('class', '').lower()
            confidence = best_prediction.get('confidence', 0) * 100
            
            logging.info(f"Best prediction - Label: {label}, Confidence: {confidence:.2f}%")
            
            # Set confidence threshold for reliable predictions
            confidence_threshold = 40  # Lowered threshold for testing
            
            if confidence < confidence_threshold:
                return render_template('result.html', 
                                       image=image_url, 
                                       message=f"Uncertain detection (Confidence: {confidence:.2f}%). Please check manually or try with a clearer image.")
            
            # Process different label variations
            if 'open' in label or label == 'open_manhole':
                return render_template('result.html', 
                                       image=image_url, 
                                       message=f"⚠️ DANGER: Manhole is OPEN! (Confidence: {confidence:.2f}%)")
            elif 'closed' in label or 'covered' in label or label == 'closed_manhole':
                return render_template('result.html', 
                                       image=image_url, 
                                       message=f"✅ Safe: Manhole is closed/covered (Confidence: {confidence:.2f}%)")
            else:
                logging.warning(f"Unexpected label detected: {label}")
                return render_template('result.html', 
                                       image=image_url, 
                                       message=f"Detected: {label} (Confidence: {confidence:.2f}%). Please verify manually.")
        
        except Exception as inference_error:
            logging.error(f"Inference error: {inference_error}")
            return render_template('result.html', 
                                   image=image_url,
                                   message=f"Error during analysis: {str(inference_error)}. Please try again.")
    
    except Exception as upload_error:
        logging.error(f"Upload error: {upload_error}")
        return render_template('result.html', 
                               message=f"Error processing upload: {str(upload_error)}. Please try again.")

@app.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    return render_template('result.html', 
                           message="File too large. Please upload an image smaller than 16MB."), 413

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return render_template('result.html', message="Page not found."), 404

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors"""
    logging.error(f"Server error: {e}")
    return render_template('result.html', message="Internal server error. Please try again later."), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)