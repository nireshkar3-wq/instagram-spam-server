import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import threading
import time
import os
import logging
import json
import shutil
import zipfile
import io
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from insta_bot import InstagramCommentBot

PROFILES_FILE = 'profiles.json'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'insta-secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

def load_profiles():
    if os.path.exists(PROFILES_FILE):
        with open(PROFILES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_profiles(profiles):
    with open(PROFILES_FILE, 'w') as f:
        json.dump(profiles, f, indent=4)

# Store the current bot instances and their status
# Format: { 'profile_name': { 'running': bool, 'current_task': str, 'thread': Thread } }
active_bots = {}

@socketio.on('join')
def on_join(data):
    profile = data.get('profile')
    if profile:
        eventlet.sleep(0) # Yield for eventlet
        join_room(profile)
        logging.info(f"Client joined room: {profile}")

@socketio.on('leave')
def on_leave(data):
    profile = data.get('profile')
    if profile:
        leave_room(profile)
        logging.info(f"Client left room: {profile}")

@app.route('/profiles', methods=['GET'])
def get_profiles():
    return jsonify(load_profiles())

@app.route('/profiles', methods=['POST'])
def add_profile():
    data = request.json
    name = data.get('name')
    username = data.get('username')
    password = data.get('password')
    
    if not name or not username or not password:
        return jsonify({'error': 'All fields are required'}), 400
        
    profiles = load_profiles()
    profiles[name] = {
        'username': username,
        'password': password
    }
    save_profiles(profiles)
    return jsonify({'message': f'Profile {name} saved successfully'})

@app.route('/profiles/<name>', methods=['DELETE'])
def delete_profile(name):
    profiles = load_profiles()
    if name in profiles:
        # Delete from JSON
        del profiles[name]
        save_profiles(profiles)
        
        # Delete session directory if it exists
        session_dir = os.path.join('Instagram_session', name)
        if os.path.exists(session_dir):
            try:
                shutil.rmtree(session_dir)
                return jsonify({'message': f'Profile {name} and its session data deleted'})
            except Exception as e:
                return jsonify({'message': f'Profile {name} credentials deleted, but failed to remove session folder: {str(e)}'}), 200
        
        return jsonify({'message': f'Profile {name} credentials deleted'})
    return jsonify({'error': 'Profile not found'}), 404

def bot_log_callback(profile_name, message, level):
    """Callback function for the bot to send logs to the frontend via rooms."""
    level_str = "INFO"
    if level == logging.ERROR: level_str = "ERROR"
    elif level == logging.WARNING: level_str = "WARNING"
    
    timestamp = time.strftime('%H:%M:%S')
    socketio.emit('bot_log', {
        'message': message,
        'level': level_str,
        'timestamp': timestamp,
        'profile': profile_name
    }, room=profile_name)


def run_bot_task(post_url, comment, count, headless, profile_name, username, password):
    active_bots[profile_name]['running'] = True
    try:
        bot = InstagramCommentBot(
            headless=headless, 
            log_callback=lambda msg, lvl: bot_log_callback(profile_name, msg, lvl),
            profile_name=profile_name,
            username=username,
            password=password
        )
        active_bots[profile_name]['bot'] = bot
        success = bot.run(post_url, comment, count)
        
        if success:
            bot_log_callback(profile_name, "✅ Bot task completed successfully!", logging.INFO)
        else:
            bot_log_callback(profile_name, "❌ Bot task failed. Check logs for details.", logging.ERROR)
            
    except Exception as e:
        bot_log_callback(profile_name, f"Critical error: {str(e)}", logging.ERROR)
    finally:
        active_bots[profile_name]['running'] = False
        active_bots[profile_name]['current_task'] = None
        socketio.emit('bot_finished', {'success': True, 'profile': profile_name}, room=profile_name)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/run', methods=['POST'])
def run_bot():
    data = request.json
    post_url = data.get('post_url')
    comment = data.get('comment')
    count = int(data.get('count', 1))
    headless = data.get('headless', False)
    profile_name = data.get('profile_name')
    
    # Require a valid profile
    profiles = load_profiles()
    if not profile_name or profile_name not in profiles:
        return jsonify({'error': 'A valid profile is required to run the bot'}), 400
        
    if profile_name in active_bots and active_bots[profile_name]['running']:
        return jsonify({'error': f'Bot is already running for profile {profile_name}'}), 400

    username = profiles[profile_name]['username']
    password = profiles[profile_name]['password']
    bot_log_callback(profile_name, f"Using saved credentials for profile: {profile_name}", logging.INFO)
    
    if not post_url or not comment:
        return jsonify({'error': 'Missing required parameters'}), 400
        
    active_bots[profile_name] = {
        'running': True,
        'current_task': 'Initializing...',
    }

    thread = threading.Thread(
        target=run_bot_task, 
        args=(post_url, comment, count, headless, profile_name, username, password)
    )
    thread.daemon = True
    thread.start()
    active_bots[profile_name]['thread'] = thread
    
    return jsonify({'message': 'Bot started successfully'})

@app.route('/status')
@app.route('/status/<profile_name>')
def get_status(profile_name=None):
    if profile_name:
        status = active_bots.get(profile_name, {'running': False, 'current_task': None})
        # Don't return the Thread object
        return jsonify({
            'running': status.get('running', False),
            'current_task': status.get('current_task')
        })
    
    # Return brief status for all (for overall UI awareness if needed)
    return jsonify({name: {'running': info['running'], 'task': info['current_task']} for name, info in active_bots.items()})

@app.route('/export_session/<profile_name>')
def export_session(profile_name):
    if profile_name in active_bots and active_bots[profile_name]['running']:
        return jsonify({'error': 'Cannot export session while the bot is running for this profile'}), 400

    session_path = os.path.join('Instagram_session', profile_name)
    if not os.path.exists(session_path):
        return jsonify({'error': 'Session data not found for this profile'}), 404
    
    # Create zip in memory
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(session_path):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, session_path)
                zf.write(abs_path, rel_path)
    
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'insta_session_{profile_name}.zip'
    )

@app.route('/import_session', methods=['POST'])
def import_session():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    profile_name = request.form.get('profile_name')
    
    if file.filename == '' or not profile_name:
        return jsonify({'error': 'No file or profile name selected'}), 400
    
    if not file.filename.endswith('.zip'):
        return jsonify({'error': 'Please upload a ZIP file'}), 400
        
    session_path = os.path.join('Instagram_session', profile_name)
    
    # Ensure base dir exists
    os.makedirs('Instagram_session', exist_ok=True)
    
    # Delete existing if any
    if os.path.exists(session_path):
        shutil.rmtree(session_path)
    
    os.makedirs(session_path)
    
    try:
        with zipfile.ZipFile(file, 'r') as zf:
            zf.extractall(session_path)
            
        # --- Auto-Flatten Logic ---
        # If the user zipped the profile folder (e.g. 'niresh'), we might have niresh/niresh/Default
        # We want everything in niresh/
        items = [i for i in os.listdir(session_path) if i != '__MACOSX'] # Ignore mac junk
        if len(items) == 1 and os.path.isdir(os.path.join(session_path, items[0])):
            # It's a nested folder (e.g. they zipped the 'niresh' folder)
            nested_path = os.path.join(session_path, items[0])
            for item in os.listdir(nested_path):
                shutil.move(os.path.join(nested_path, item), session_path)
            os.rmdir(nested_path)
            logging.info(f"Flattened nested folder for profile {profile_name}")
            
        return jsonify({'message': f'Session for {profile_name} imported successfully'})
    except Exception as e:
        return jsonify({'error': f'Failed to extract session: {str(e)}'}), 500

@app.route('/screenshot/<profile_name>')
def get_screenshot(profile_name):
    if profile_name not in active_bots or not active_bots[profile_name].get('bot'):
        return jsonify({'error': 'Bot not active for this profile'}), 404
        
    bot = active_bots[profile_name]['bot']
    screenshot_data = bot.get_screenshot_as_png()
    if not screenshot_data:
        return jsonify({'error': 'Could not capture screenshot'}), 500
        
    return send_file(
        io.BytesIO(screenshot_data),
        mimetype='image/png'
    )

if __name__ == '__main__':
    # Ensure templates and static directories exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    socketio.run(app, debug=True, port=5000, host='0.0.0.0')
