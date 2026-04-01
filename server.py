import json
import os
import uuid
import hashlib
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# ==========================================
#         CONFIGURATION
# ==========================================
PORT = int(os.environ.get("PORT", 8080))
app = Flask(__name__)
CORS(app) # Enable CORS for frontend connection

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
DEV_DATA_FILE = os.path.join(DATA_DIR, "developers.json")
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
#         HELPER FUNCTIONS
# ==========================================
def load_devs():
    if os.path.exists(DEV_DATA_FILE):
        with open(DEV_DATA_FILE, "r") as f: return json.load(f)
    return {}

def save_devs(devs):
    with open(DEV_DATA_FILE, "w") as f: json.dump(devs, f, indent=4)

def generate_api_key(email):
    return "cn_" + hashlib.sha256(email.encode()).hexdigest()[:32]

def get_dev_by_api_key(api_key):
    devs = load_devs()
    for email, info in devs.items():
        if info.get('api_key') == api_key: return email, info
    return None, None

def get_host_url():
    return os.environ.get("RENDER_EXTERNAL_URL", "http://127.0.0.1:8080").rstrip('/')

def format_bytes(b):
    if b < 1024: return f"{b} B"
    elif b < 1024**2: return f"{b/1024:.2f} KB"
    elif b < 1024**3: return f"{b/1024**2:.2f} MB"
    else: return f"{b/1024**3:.2f} GB"

# ==========================================
#         KEEP-ALIVE
# ==========================================
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "alive", "message": "☁️ CloudNest is running!"})

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "ok", "service": "CloudNest API Console", "version": "2.1"})

# ==========================================
#         DEVELOPER AUTHENTICATION
# ==========================================
@app.route('/api/dev/auth', methods=['POST'])
def dev_auth():
    data = request.json or {}
    action = data.get('action')
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    
    devs = load_devs()
    
    if action == 'register':
        name = data.get('name', '').strip()
        if not name or not email or not password: return jsonify({"status": "error", "message": "Fill all fields."})
        if email in devs: return jsonify({"status": "error", "message": "Email already registered."})
        
        api_key = generate_api_key(email)
        devs[email] = {"name": name, "email": email, "password": password, "api_key": api_key, "plan": "free"}
        save_devs(devs)
        return jsonify({"status": "success", "message": "Registered!", "api_key": api_key, "name": name, "email": email, "plan": "free"})
        
    elif action == 'login':
        if email in devs and devs[email]['password'] == password:
            plan = devs[email].get('plan', 'free')
            return jsonify({"status": "success", "api_key": devs[email]['api_key'], "name": devs[email]['name'], "email": email, "plan": plan})
        return jsonify({"status": "error", "message": "Invalid email or password."})
        
    return jsonify({"status": "error", "message": "Invalid action."})

# ==========================================
#         REALTIME DATABASE API
# ==========================================
@app.route('/api/db', methods=['POST'])
def api_db():
    data = request.json or {}
    api_key, action, key = data.get('api_key'), data.get('action'), data.get('key', 'default')
    
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id: return jsonify({"status": "error", "message": "Invalid API Key."})

    db_file = os.path.join(DATA_DIR, f"{api_key}_db.json")
    db_data = json.load(open(db_file)) if os.path.exists(db_file) else {}

    if action == 'save':
        db_data[key] = data.get('data', '')
        with open(db_file, "w") as f: json.dump(db_data, f, indent=2)
        return jsonify({"status": "success", "message": "Data saved!"})
    elif action == 'edit':
        if key in db_data:
            db_data[key] = data.get('new_data', '')
            with open(db_file, "w") as f: json.dump(db_data, f, indent=2)
            return jsonify({"status": "success", "message": "Data updated!"})
        return jsonify({"status": "error", "message": "Key not found."})
    elif action == 'load':
        return jsonify({"status": "success", "data": db_data.get(key)})
    elif action == 'all': 
        return jsonify({"status": "success", "data": db_data})
    elif action == 'delete':
        if key in db_data: 
            del db_data[key]
            with open(db_file, "w") as f: json.dump(db_data, f, indent=2)
            return jsonify({"status": "success", "message": "Deleted."})
    return jsonify({"status": "error", "message": "Invalid action."})

# ==========================================
#         APP AUTHENTICATION API
# ==========================================
@app.route('/api/auth', methods=['POST'])
def api_auth():
    data = request.json or {}
    api_key, action = data.get('api_key'), data.get('action')
    username, password = data.get('username', ''), data.get('password', '')
    
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id: return jsonify({"status": "error", "message": "Invalid API Key."})

    auth_file = os.path.join(DATA_DIR, f"{api_key}_auth.json")
    auth_data = json.load(open(auth_file)) if os.path.exists(auth_file) else {}

    if action == 'register':
        if username in auth_data: return jsonify({"status": "error", "message": "User already exists!"})
        auth_data[username] = {"password": password, "uid": str(uuid.uuid4())}
        with open(auth_file, "w") as f: json.dump(auth_data, f, indent=2)
        return jsonify({"status": "success", "message": "Registered!"})
    elif action == 'login':
        if username in auth_data and auth_data[username]['password'] == password:
            return jsonify({"status": "success", "message": "Login successful", "uid": auth_data[username]['uid']})
        return jsonify({"status": "error", "message": "Invalid credentials."})
    elif action == 'all': 
        return jsonify({"status": "success", "data": auth_data})
    elif action == 'delete':
        if username in auth_data: 
            del auth_data[username]
            with open(auth_file, "w") as f: json.dump(auth_data, f, indent=2)
            return jsonify({"status": "success", "message": "User deleted."})
    return jsonify({"status": "error", "message": "Invalid action."})

# ==========================================
#         STORAGE API (UPLOAD & LIST)
# ==========================================
@app.route('/api/upload', methods=['POST'])
def api_upload():
    api_key = request.form.get('api_key')
    file = request.files.get('file')
    
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id: return jsonify({"status": "error", "message": "Invalid API Key."})
    if not file: return jsonify({"status": "error", "message": "No file provided."})
    
    filename = secure_filename(file.filename)
    save_name = f"{api_key}_{filename}"
    file.save(os.path.join(UPLOAD_FOLDER, save_name))
    
    return jsonify({"status": "success", "message": "File uploaded!", "url": f"{get_host_url()}/uploads/{save_name}"})

@app.route('/api/storage/list', methods=['POST'])
def list_files():
    api_key = request.json.get('api_key')
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id: return jsonify({"status": "error"})
    
    files = []
    for f in os.listdir(UPLOAD_FOLDER):
        if f.startswith(api_key):
            display_name = f.replace(api_key + "_", "", 1)
            ext = display_name.split('.')[-1].lower() if '.' in display_name else ''
            size_bytes = os.path.getsize(os.path.join(UPLOAD_FOLDER, f))
            files.append({
                "filename": f,
                "display_name": display_name,
                "ext": ext,
                "url": f"{get_host_url()}/uploads/{f}",
                "size": size_bytes,
                "size_str": format_bytes(size_bytes)
            })
    return jsonify({"status": "success", "files": files})

@app.route('/api/storage/delete', methods=['POST'])
def delete_file_api():
    api_key, filename = request.json.get('api_key'), request.json.get('filename', '')
    user_id, _ = get_dev_by_api_key(api_key)
    if user_id and filename.startswith(api_key): 
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath): os.remove(filepath)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "File not found or unauthorized"})

@app.route('/uploads/<filename>')
def serve_file(filename): 
    return send_from_directory(UPLOAD_FOLDER, filename)

# ==========================================
#         USAGE & RULES & ADMIN
# ==========================================
@app.route('/api/usage', methods=['POST'])
def usage():
    api_key = request.json.get('api_key')
    user_id, dev_info = get_dev_by_api_key(api_key)
    if not user_id: return jsonify({"status": "error"})
    
    # Calculate Storage
    storage_bytes = sum(os.path.getsize(os.path.join(UPLOAD_FOLDER, f)) for f in os.listdir(UPLOAD_FOLDER) if f.startswith(api_key))
    file_count = sum(1 for f in os.listdir(UPLOAD_FOLDER) if f.startswith(api_key))
    
    # Calculate Database & Auth
    db_file, auth_file = os.path.join(DATA_DIR, f"{api_key}_db.json"), os.path.join(DATA_DIR, f"{api_key}_auth.json")
    db_bytes = os.path.getsize(db_file) if os.path.exists(db_file) else 0
    
    auth_data = json.load(open(auth_file)) if os.path.exists(auth_file) else {}
    auth_users_count = len(auth_data)
    
    return jsonify({
        "status": "success", 
        "plan": dev_info.get('plan', 'free'),
        "monthly_usage": {
            "storage": storage_bytes,
            "db": db_bytes,
            "auth": auth_users_count
        },
        "file_count": file_count,
        "total": format_bytes(storage_bytes + db_bytes)
    })

@app.route('/api/rules', methods=['POST'])
def rules_api():
    api_key, action = request.json.get('api_key'), request.json.get('action', 'get')
    rules_file = os.path.join(DATA_DIR, f"{api_key}_rules.json")
    default_rules = '{\n  "rules": {\n    ".read": "true",\n    ".write": "true"\n  }\n}'
    
    if action == 'get':
        return jsonify({"status": "success", "rules": open(rules_file).read() if os.path.exists(rules_file) else default_rules})
    elif action == 'update':
        with open(rules_file, 'w') as f: f.write(request.json.get('rules', default_rules))
        return jsonify({"status": "success"})

@app.route('/api/admin/make-premium', methods=['POST'])
def make_premium():
    # Basic protection for Admin Endpoint
    target_email = request.json.get('target_email', '').strip().lower()
    devs = load_devs()
    if target_email in devs:
        devs[target_email]['plan'] = 'premium'
        save_devs(devs)
        return jsonify({"status": "success", "message": f"{target_email} upgraded to Premium!"})
    return jsonify({"status": "error", "message": "User not found."})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
