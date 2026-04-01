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
CORS(app)

# Max upload size: 10 MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

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
        with open(DEV_DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_devs(devs):
    with open(DEV_DATA_FILE, "w") as f:
        json.dump(devs, f, indent=4)

def hash_password(password):
    """Hash password with SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def generate_api_key(email):
    """Deterministic API key from email — same key on every login"""
    return "cn_" + hashlib.sha256(email.encode()).hexdigest()[:32]

def get_dev_by_api_key(api_key):
    if not api_key:
        return None, None
    devs = load_devs()
    for email, info in devs.items():
        if info.get('api_key') == api_key:
            return email, info
    return None, None

def get_host_url():
    return os.environ.get("RENDER_EXTERNAL_URL", f"http://127.0.0.1:{PORT}").rstrip('/')

def format_bytes(b):
    if b < 1024: return f"{b} B"
    elif b < 1024**2: return f"{b/1024:.2f} KB"
    elif b < 1024**3: return f"{b/1024**2:.2f} MB"
    else: return f"{b/1024**3:.2f} GB"

# ==========================================
#         SERVE FRONTEND
# ==========================================
@app.route('/')
def home():
    """Serve the Cloud Nest console frontend"""
    # Try to serve index.html from the current directory
    if os.path.exists('index.html'):
        return send_from_directory('.', 'index.html')
    # Fallback if index.html not present
    return jsonify({"status": "ok", "service": "CloudNest API", "version": "2.0",
                    "note": "Place index.html in the same directory as server.py to serve the console."})

@app.route('/ping')
def ping():
    """Keep-alive endpoint — add this URL to cron-job.org to prevent Render sleep"""
    return jsonify({"status": "alive", "message": "☁️ CloudNest is running!"})

# ==========================================
#         FILE SIZE ERROR HANDLER
# ==========================================
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"status": "error", "message": "File too large. Maximum size is 10 MB."}), 413

# ==========================================
#         DEVELOPER AUTH
# ==========================================
@app.route('/api/dev/register', methods=['POST'])
def dev_register():
    data = request.json or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()

    if not name or not email or not password:
        return jsonify({"status": "error", "message": "All fields are required."})
    if len(password) < 6:
        return jsonify({"status": "error", "message": "Password must be at least 6 characters."})
    if '@' not in email:
        return jsonify({"status": "error", "message": "Please enter a valid email."})

    devs = load_devs()
    if email in devs:
        return jsonify({"status": "error", "message": "This email is already registered."})

    api_key = generate_api_key(email)
    devs[email] = {
        "name": name,
        "email": email,
        "password": hash_password(password),
        "api_key": api_key
    }
    save_devs(devs)
    return jsonify({"status": "success", "message": "Registration successful!", "api_key": api_key, "name": name, "email": email})

@app.route('/api/dev/login', methods=['POST'])
def dev_login():
    data = request.json or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()

    devs = load_devs()
    if email not in devs:
        return jsonify({"status": "error", "message": "Email or password is incorrect."})

    stored = devs[email]
    stored_pw = stored.get('password', '')

    # Support both hashed (new) and plaintext (legacy) passwords
    pw_match = (stored_pw == hash_password(password)) or (stored_pw == password)
    if not pw_match:
        return jsonify({"status": "error", "message": "Email or password is incorrect."})

    # Upgrade plaintext password to hashed on next login
    if stored_pw == password:
        devs[email]['password'] = hash_password(password)
        save_devs(devs)

    info = devs[email]
    return jsonify({"status": "success", "api_key": info['api_key'], "name": info['name'], "email": email})

# ==========================================
#         REALTIME DATABASE API
# ==========================================
@app.route('/api/db', methods=['POST'])
def api_db():
    data = request.json or {}
    api_key = data.get('api_key')
    action = data.get('action')
    key = str(data.get('key', 'default')).strip()
    payload = data.get('data', '')

    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id:
        return jsonify({"status": "error", "message": "Invalid API Key."})

    if not key:
        return jsonify({"status": "error", "message": "Key cannot be empty."})

    db_file = os.path.join(DATA_DIR, f"{api_key}_db.json")
    db_data = {}
    if os.path.exists(db_file):
        with open(db_file, "r") as f:
            db_data = json.load(f)

    if action == 'save':
        db_data[key] = payload
        with open(db_file, "w") as f: json.dump(db_data, f, indent=2)
        return jsonify({"status": "success", "message": "Data saved!"})

    elif action == 'load':
        return jsonify({"status": "success", "data": db_data.get(key, "")})

    elif action == 'all':
        return jsonify({"status": "success", "data": db_data})

    elif action == 'delete':
        if key in db_data:
            del db_data[key]
            with open(db_file, "w") as f: json.dump(db_data, f, indent=2)
        return jsonify({"status": "success", "message": "Deleted."})

    elif action == 'edit':
        new_data = data.get('new_data', '')
        db_data[key] = new_data
        with open(db_file, "w") as f: json.dump(db_data, f, indent=2)
        return jsonify({"status": "success", "message": "Updated."})

    return jsonify({"status": "error", "message": "Invalid action."})

# ==========================================
#         AUTHENTICATION API
# ==========================================
@app.route('/api/auth', methods=['POST'])
def api_auth():
    data = request.json or {}
    api_key = data.get('api_key')
    action = data.get('action')
    username = data.get('username', '').strip()
    password = data.get('password', '')

    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id:
        return jsonify({"status": "error", "message": "Invalid API Key."})

    auth_file = os.path.join(DATA_DIR, f"{api_key}_auth.json")
    auth_data = {}
    if os.path.exists(auth_file):
        with open(auth_file, "r") as f:
            auth_data = json.load(f)

    if action == 'register':
        if not username or not password:
            return jsonify({"status": "error", "message": "Username and password required."})
        if username in auth_data:
            return jsonify({"status": "error", "message": "User already exists!"})
        uid = str(uuid.uuid4())
        auth_data[username] = {"password": hash_password(password), "uid": uid}
        with open(auth_file, "w") as f: json.dump(auth_data, f, indent=2)
        return jsonify({"status": "success", "message": "Registered!", "uid": uid})

    elif action == 'login':
        if username not in auth_data:
            return jsonify({"status": "error", "message": "Wrong credentials."})
        stored_pw = auth_data[username].get('password', '')
        # Support both hashed and plaintext (legacy)
        pw_match = (stored_pw == hash_password(password)) or (stored_pw == password)
        if pw_match:
            # Upgrade plaintext to hashed
            if stored_pw == password:
                auth_data[username]['password'] = hash_password(password)
                with open(auth_file, "w") as f: json.dump(auth_data, f, indent=2)
            return jsonify({"status": "success", "message": "Logged in!", "uid": auth_data[username].get('uid', '')})
        return jsonify({"status": "error", "message": "Wrong credentials."})

    elif action == 'all':
        # Don't expose passwords
        safe_data = {u: {"uid": info.get("uid", ""), "username": u} for u, info in auth_data.items()}
        return jsonify({"status": "success", "data": safe_data})

    elif action == 'delete':
        if username in auth_data:
            del auth_data[username]
            with open(auth_file, "w") as f: json.dump(auth_data, f, indent=2)
        return jsonify({"status": "success", "message": "User deleted."})

    elif action == 'edit':
        new_password = data.get('new_password', '')
        if username in auth_data and new_password:
            auth_data[username]['password'] = hash_password(new_password)
            with open(auth_file, "w") as f: json.dump(auth_data, f, indent=2)
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "User not found."})

    return jsonify({"status": "error", "message": "Invalid action."})

# ==========================================
#         FILE STORAGE API
# ==========================================
@app.route('/api/upload', methods=['POST'])
def upload_file():
    api_key = request.form.get('api_key')
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id:
        return jsonify({"status": "error", "message": "Invalid API key"})

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"})
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Empty file"})

    filename = secure_filename(file.filename)
    unique_filename = f"{api_key}_{uuid.uuid4().hex[:8]}_{filename}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(filepath)
    size = os.path.getsize(filepath)
    file_url = f"{get_host_url()}/uploads/{unique_filename}"
    return jsonify({"status": "success", "url": file_url, "filename": unique_filename, "size": format_bytes(size)})

@app.route('/api/storage/list', methods=['POST'])
def list_files():
    data = request.json or {}
    api_key = data.get('api_key')
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id:
        return jsonify({"status": "error", "message": "Invalid API Key."})

    files = []
    for fname in os.listdir(UPLOAD_FOLDER):
        if fname.startswith(api_key + "_"):
            fpath = os.path.join(UPLOAD_FOLDER, fname)
            size = os.path.getsize(fpath)
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else 'file'
            display = fname.replace(f"{api_key}_", "", 1)
            # Remove the UUID prefix for nicer display
            parts = display.split('_', 1)
            display_name = parts[1] if len(parts) > 1 else display
            files.append({
                "filename": fname,
                "display_name": display_name,
                "url": f"{get_host_url()}/uploads/{fname}",
                "size": size,
                "size_str": format_bytes(size),
                "ext": ext
            })
    return jsonify({"status": "success", "files": files})

@app.route('/api/storage/delete', methods=['POST'])
def delete_file_api():
    data = request.json or {}
    api_key = data.get('api_key')
    filename = data.get('filename', '')
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id:
        return jsonify({"status": "error", "message": "Invalid API Key."})
    if not filename.startswith(api_key + "_"):
        return jsonify({"status": "error", "message": "Unauthorized."})
    fpath = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    return jsonify({"status": "success", "message": "File deleted."})

@app.route('/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ==========================================
#         USAGE API
# ==========================================
@app.route('/api/usage', methods=['POST'])
def usage():
    data = request.json or {}
    api_key = data.get('api_key')
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id:
        return jsonify({"status": "error", "message": "Invalid API Key."})

    storage_bytes = 0
    file_count = 0
    for fname in os.listdir(UPLOAD_FOLDER):
        if fname.startswith(api_key + "_"):
            storage_bytes += os.path.getsize(os.path.join(UPLOAD_FOLDER, fname))
            file_count += 1

    db_file = os.path.join(DATA_DIR, f"{api_key}_db.json")
    auth_file = os.path.join(DATA_DIR, f"{api_key}_auth.json")
    db_bytes = os.path.getsize(db_file) if os.path.exists(db_file) else 0
    auth_bytes = os.path.getsize(auth_file) if os.path.exists(auth_file) else 0
    total = storage_bytes + db_bytes + auth_bytes

    return jsonify({
        "status": "success",
        "storage": format_bytes(storage_bytes),
        "storage_bytes": storage_bytes,         # FIX: needed for usage bars
        "database": format_bytes(db_bytes),
        "db_bytes": db_bytes,                   # FIX: was missing, bars showed 0%
        "authentication": format_bytes(auth_bytes),
        "auth_bytes": auth_bytes,               # FIX: was missing, bars showed 0%
        "total": format_bytes(total),
        "total_bytes": total,
        "file_count": file_count
    })

# ==========================================
#         RULES API
# ==========================================
@app.route('/api/rules', methods=['POST'])
def rules_api():
    data = request.json or {}
    api_key = data.get('api_key')
    action = data.get('action', 'get')
    user_id, _ = get_dev_by_api_key(api_key)
    if not user_id:
        return jsonify({"status": "error", "message": "Invalid API Key."})

    rules_file = os.path.join(DATA_DIR, f"{api_key}_rules.json")
    default_rules = '{\n  "rules": {\n    ".read": "true",\n    ".write": "true"\n  }\n}'

    if action == 'get':
        if os.path.exists(rules_file):
            with open(rules_file) as f:
                return jsonify({"status": "success", "rules": f.read()})
        return jsonify({"status": "success", "rules": default_rules})

    elif action == 'update':
        rules_text = data.get('rules', default_rules)
        try:
            json.loads(rules_text)
        except Exception:
            return jsonify({"status": "error", "message": "Invalid JSON format."})
        with open(rules_file, 'w') as f:
            f.write(rules_text)
        return jsonify({"status": "success", "message": "Rules updated!"})

    return jsonify({"status": "error", "message": "Invalid action."})

# ==========================================
#         START SERVER
# ==========================================
if __name__ == '__main__':
    print("=" * 45)
    print("   ☁️  CloudNest API Server v2.1")
    print("=" * 45)
    print(f"🌐 Server : {get_host_url()}")
    print(f"📌 Port   : {PORT}")
    print(f"📂 Data   : {DATA_DIR}/")
    print(f"🖥️  Console: {get_host_url()}/")
    print("=" * 45)
    app.run(host='0.0.0.0', port=PORT, debug=False)
