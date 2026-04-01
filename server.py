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
#         KEEP-ALIVE (CRON JOB)
# ==========================================
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "alive", "message": "☁️ CloudNest is running!"})

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "ok", "service": "CloudNest API", "version": "2.0"})

# ==========================================
#         DEVELOPER AUTH
# ==========================================
@app.route('/api/dev/register', methods=['POST', 'GET'])
def dev_register():
    if request.method == 'GET': return jsonify({"error": "Use POST method"})
    data = request.json or {}
    name, email, password = data.get('name', '').strip(), data.get('email', '').strip().lower(), data.get('password', '').strip()
    if not name or not email or not password: return jsonify({"status": "error", "message": "সব ফিল্ড পূরণ করুন।"})
    
    devs = load_devs()
    if email in devs: return jsonify({"status": "error", "message": "এই ইমেইল আগেই রেজিস্টার্ড।"})
    
    api_key = generate_api_key(email)
    devs[email] = {"name": name, "email": email, "password": password, "api_key": api_key}
    save_devs(devs)
    return jsonify({"status": "success", "message": "রেজিস্ট্রেশন সফল!", "api_key": api_key, "name": name, "email": email})

@app.route('/api/dev/login', methods=['POST', 'GET'])
def dev_login():
    if request.method == 'GET': return jsonify({"error": "Use POST method"})
    data = request.json or {}
    email, password = data.get('email', '').strip().lower(), data.get('password', '').strip()
    devs = load_devs()
    if email in devs and devs[email]['password'] == password:
        return jsonify({"status": "success", "api_key": devs[email]['api_key'], "name": devs[email]['name'], "email": email})
    return jsonify({"status": "error", "message": "ইমেইল বা পাসওয়ার্ড ভুল।"})

# ==========================================
#         REALTIME DATABASE API
# ==========================================
@app.route('/api/db', methods=['POST', 'GET'])
def api_db():
    if request.method == 'GET': return jsonify({"error": "Method Not Allowed. Use POST with api_key and action."})
    data = request.json or {}
    api_key, action, key, payload = data.get('api_key'), data.get('action'), data.get('key', 'default'), data.get('data', '')
    
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id: return jsonify({"status": "error", "message": "Invalid API Key."})

    db_file = os.path.join(DATA_DIR, f"{api_key}_db.json")
    db_data = json.load(open(db_file)) if os.path.exists(db_file) else {}

    if action == 'save':
        db_data[key] = payload
        with open(db_file, "w") as f: json.dump(db_data, f, indent=2)
        return jsonify({"status": "success", "message": "Data saved!"})
    elif action == 'all': return jsonify({"status": "success", "data": db_data})
    elif action == 'delete':
        if key in db_data: del db_data[key]
        with open(db_file, "w") as f: json.dump(db_data, f, indent=2)
        return jsonify({"status": "success", "message": "Deleted."})
    return jsonify({"status": "error", "message": "Invalid action."})

# ==========================================
#         AUTHENTICATION API
# ==========================================
@app.route('/api/auth', methods=['POST', 'GET'])
def api_auth():
    if request.method == 'GET': return jsonify({"error": "Use POST method"})
    data = request.json or {}
    api_key, action, username, password = data.get('api_key'), data.get('action'), data.get('username', ''), data.get('password', '')
    
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id: return jsonify({"status": "error", "message": "Invalid API Key."})

    auth_file = os.path.join(DATA_DIR, f"{api_key}_auth.json")
    auth_data = json.load(open(auth_file)) if os.path.exists(auth_file) else {}

    if action == 'register':
        if username in auth_data: return jsonify({"status": "error", "message": "User exists!"})
        auth_data[username] = {"password": password, "uid": str(uuid.uuid4())}
        with open(auth_file, "w") as f: json.dump(auth_data, f, indent=2)
        return jsonify({"status": "success", "message": "Registered!"})
    elif action == 'all': return jsonify({"status": "success", "data": auth_data})
    elif action == 'delete':
        if username in auth_data: del auth_data[username]
        with open(auth_file, "w") as f: json.dump(auth_data, f, indent=2)
        return jsonify({"status": "success", "message": "User deleted."})
    elif action == 'edit':
        if username in auth_data and data.get('new_password'):
            auth_data[username]['password'] = data.get('new_password')
            with open(auth_file, "w") as f: json.dump(auth_data, f, indent=2)
            return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Invalid action."})

# ==========================================
#         USAGE & RULES API
# ==========================================
@app.route('/api/usage', methods=['POST'])
def usage():
    api_key = request.json.get('api_key')
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id: return jsonify({"status": "error"})
    
    storage_bytes = sum(os.path.getsize(os.path.join(UPLOAD_FOLDER, f)) for f in os.listdir(UPLOAD_FOLDER) if f.startswith(api_key))
    db_file, auth_file = os.path.join(DATA_DIR, f"{api_key}_db.json"), os.path.join(DATA_DIR, f"{api_key}_auth.json")
    db_bytes = os.path.getsize(db_file) if os.path.exists(db_file) else 0
    auth_bytes = os.path.getsize(auth_file) if os.path.exists(auth_file) else 0
    
    return jsonify({"status": "success", "storage": format_bytes(storage_bytes), "database": format_bytes(db_bytes), "total": format_bytes(storage_bytes+db_bytes+auth_bytes)})

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

# ==========================================
#         STORAGE API
# ==========================================
@app.route('/api/storage/list', methods=['POST'])
def list_files():
    api_key = request.json.get('api_key')
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id: return jsonify({"status": "error"})
    files = [{"filename": f, "url": f"{get_host_url()}/uploads/{f}", "size_str": format_bytes(os.path.getsize(os.path.join(UPLOAD_FOLDER, f)))} for f in os.listdir(UPLOAD_FOLDER) if f.startswith(api_key)]
    return jsonify({"status": "success", "files": files})

@app.route('/api/storage/delete', methods=['POST'])
def delete_file_api():
    api_key, filename = request.json.get('api_key'), request.json.get('filename', '')
    if filename.startswith(api_key): os.remove(os.path.join(UPLOAD_FOLDER, filename))
    return jsonify({"status": "success"})

@app.route('/uploads/<filename>')
def serve_file(filename): return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
