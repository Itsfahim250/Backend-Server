import os
import json
import uuid
import hashlib
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
PORT = int(os.environ.get("PORT", 8080))

# ==========================================
#         MASTER SYSTEM DB (Do not change)
# ==========================================
SYSTEM_DB = "https://strikexo-55b1d-default-rtdb.firebaseio.com"

# DEFAULT FALLBACKS (If Admin Panel is not configured yet)
DEFAULT_CONFIG = {
    "dbs": [
        "https://strikexo-55b1d-default-rtdb.firebaseio.com",
        "https://mango-tour-15f84-default-rtdb.firebaseio.com",
        "https://smartgpt-7ca90-default-rtdb.firebaseio.com"
    ],
    "imgbb_key": "",
    "cloudinary": {"cloud_name": "", "api_key": "", "api_secret": ""}
}

# ==========================================
#         HELPER FUNCTIONS
# ==========================================
def safe_email(email):
    return email.replace('.', ',')

def generate_api_key(email):
    return "cn_" + hashlib.sha256(email.encode()).hexdigest()[:32]

def get_request_data():
    if request.is_json: return request.json or {}
    try: return json.loads(request.data) if request.data else {}
    except: return dict(request.form)

def get_system_config():
    """Fetches live configuration set via Admin Panel"""
    res = requests.get(f"{SYSTEM_DB}/system/config.json")
    if res.status_code == 200 and res.json():
        return res.json()
    return DEFAULT_CONFIG

def assign_db_to_user(api_key):
    config = get_system_config()
    active_dbs = config.get("dbs", DEFAULT_CONFIG["dbs"])
    hash_val = int(hashlib.md5(api_key.encode()).hexdigest(), 16)
    return active_dbs[hash_val % len(active_dbs)]

def get_dev_info(api_key):
    res = requests.get(f"{SYSTEM_DB}/developers/{api_key}.json")
    return res.json() if res.status_code == 200 else None

# ==========================================
#         ADMIN PANEL API
# ==========================================
@app.route('/api/admin/config', methods=['GET', 'POST', 'OPTIONS'])
def admin_config():
    if request.method == 'OPTIONS': return jsonify({}), 200
    
    if request.method == 'GET':
        config = get_system_config()
        return jsonify({"status": "success", "config": config})
        
    if request.method == 'POST':
        data = get_request_data()
        requests.put(f"{SYSTEM_DB}/system/config.json", json=data)
        return jsonify({"status": "success", "message": "Global Configuration Saved!"})

# ==========================================
#         DEVELOPER AUTHENTICATION
# ==========================================
@app.route('/api/dev/auth', methods=['POST', 'OPTIONS'])
def dev_auth():
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = get_request_data()
    action = data.get('action')
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    encoded_email = safe_email(email)
    
    if action == 'register':
        name = data.get('name', '').strip()
        if not name or not email or not password: return jsonify({"status": "error", "message": "Fill all fields."})
        check = requests.get(f"{SYSTEM_DB}/emails/{encoded_email}.json").json()
        if check: return jsonify({"status": "error", "message": "Email already registered."})
        
        api_key = generate_api_key(email)
        assigned_db = assign_db_to_user(api_key)
        dev_data = {"name": name, "email": email, "password": password, "api_key": api_key, "plan": "free", "assigned_db": assigned_db}
        
        requests.put(f"{SYSTEM_DB}/developers/{api_key}.json", json=dev_data)
        requests.put(f"{SYSTEM_DB}/emails/{encoded_email}.json", json=api_key)
        return jsonify({"status": "success", "message": "Registered!", "api_key": api_key, "name": name, "email": email, "plan": "free"})
        
    elif action == 'login':
        api_key = requests.get(f"{SYSTEM_DB}/emails/{encoded_email}.json").json()
        if api_key:
            dev_data = requests.get(f"{SYSTEM_DB}/developers/{api_key}.json").json()
            if dev_data and dev_data.get('password') == password:
                return jsonify({"status": "success", "api_key": api_key, "name": dev_data['name'], "email": email, "plan": dev_data.get('plan', 'free')})
        return jsonify({"status": "error", "message": "Invalid credentials."})

# ==========================================
#         REALTIME DATABASE & APP AUTH
# ==========================================
# (Keep api_db and api_auth exactly as they were in previous codes. They connect to assigned_db securely.)
@app.route('/api/db', methods=['POST', 'OPTIONS'])
def api_db():
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = get_request_data()
    api_key, action, key = data.get('api_key'), data.get('action'), data.get('key', 'default')
    dev_info = get_dev_info(api_key)
    if not dev_info: return jsonify({"status": "error", "message": "Invalid API Key."})
    
    base_url = f"{dev_info['assigned_db']}/projects/{api_key}/db"
    if action == 'save' or action == 'edit':
        requests.put(f"{base_url}/{key}.json", json=data.get('data') if action == 'save' else data.get('new_data'))
        return jsonify({"status": "success", "message": "Data saved!"})
    elif action == 'load':
        return jsonify({"status": "success", "data": requests.get(f"{base_url}/{key}.json").json()})
    elif action == 'all': 
        return jsonify({"status": "success", "data": requests.get(f"{base_url}.json").json() or {}})
    elif action == 'delete':
        requests.delete(f"{base_url}/{key}.json")
        return jsonify({"status": "success", "message": "Deleted."})

@app.route('/api/auth', methods=['POST', 'OPTIONS'])
def api_auth():
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = get_request_data()
    api_key, action, username = data.get('api_key'), data.get('action'), safe_email(data.get('username', ''))
    dev_info = get_dev_info(api_key)
    if not dev_info: return jsonify({"status": "error", "message": "Invalid API Key."})

    base_url = f"{dev_info['assigned_db']}/projects/{api_key}/auth"
    if action == 'register':
        if requests.get(f"{base_url}/{username}.json").json(): return jsonify({"status": "error", "message": "User exists!"})
        requests.put(f"{base_url}/{username}.json", json={"password": data.get('password'), "uid": str(uuid.uuid4())})
        return jsonify({"status": "success", "message": "Registered!"})
    elif action == 'login':
        user_data = requests.get(f"{base_url}/{username}.json").json()
        if user_data and user_data.get('password') == data.get('password'):
            return jsonify({"status": "success", "message": "Login successful", "uid": user_data['uid']})
        return jsonify({"status": "error", "message": "Invalid credentials."})
    elif action == 'all':
        res = requests.get(f"{base_url}.json").json()
        restored = {k.replace(',', '.'): v for k, v in (res or {}).items()}
        return jsonify({"status": "success", "data": restored})
    elif action == 'delete':
        requests.delete(f"{base_url}/{username}.json")
        return jsonify({"status": "success", "message": "Deleted."})

# ==========================================
#         STORAGE API (DYNAMIC UPLOAD)
# ==========================================
def upload_to_cloudinary(file, cloud_name, api_key, api_secret):
    """Uploads file to Cloudinary using REST API & SHA1 Signature"""
    timestamp = str(int(time.time()))
    string_to_sign = f"timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(string_to_sign.encode()).hexdigest()
    
    payload = {"api_key": api_key, "timestamp": timestamp, "signature": signature}
    files = {"file": file.read()}
    url = f"https://api.cloudinary.com/v1_1/{cloud_name}/auto/upload"
    
    res = requests.post(url, data=payload, files=files)
    if res.status_code == 200:
        return res.json().get('secure_url'), res.json().get('bytes', 0)
    return None, 0

@app.route('/api/upload', methods=['POST', 'OPTIONS'])
def api_upload():
    if request.method == 'OPTIONS': return jsonify({}), 200
    api_key = request.form.get('api_key')
    file = request.files.get('file')
    
    dev_info = get_dev_info(api_key)
    if not dev_info: return jsonify({"status": "error", "message": "Invalid API Key."})
    if not file: return jsonify({"status": "error", "message": "No file."})

    filename = secure_filename(file.filename)
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    # Get Live Config
    config = get_system_config()
    imgbb_key = config.get("imgbb_key", "")
    c_name = config.get("cloudinary", {}).get("cloud_name", "")
    c_key = config.get("cloudinary", {}).get("api_key", "")
    c_sec = config.get("cloudinary", {}).get("api_secret", "")

    file_url, file_size = None, 0

    # LOGIC: Images go to ImgBB (if key exists), everything else goes to Cloudinary
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp'] and imgbb_key:
        res = requests.post(f"https://api.imgbb.com/1/upload?key={imgbb_key}", files={"image": file.read()})
        if res.status_code == 200:
            file_url = res.json()['data']['url']
            file_size = res.json()['data']['size']
        else: return jsonify({"status": "error", "message": "ImgBB Upload Failed. Check API Key."})
    
    elif c_name and c_key and c_sec:
        file_url, file_size = upload_to_cloudinary(file, c_name, c_key, c_sec)
        if not file_url: return jsonify({"status": "error", "message": "Cloudinary Upload Failed."})
        
    else:
        return jsonify({"status": "error", "message": "Admin has not configured storage APIs yet."})

    # Save metadata in User's Firebase DB
    user_db = dev_info['assigned_db']
    safe_name = safe_email(filename)
    file_data = {"filename": filename, "url": file_url, "size": file_size, "ext": ext}
    requests.put(f"{user_db}/projects/{api_key}/storage/{safe_name}.json", json=file_data)
    
    return jsonify({"status": "success", "message": "Uploaded!", "url": file_url})

@app.route('/api/storage/list', methods=['POST', 'OPTIONS'])
def list_files():
    if request.method == 'OPTIONS': return jsonify({}), 200
    api_key = get_request_data().get('api_key')
    dev_info = get_dev_info(api_key)
    if not dev_info: return jsonify({"status": "error"})
    
    res = requests.get(f"{dev_info['assigned_db']}/projects/{api_key}/storage.json").json()
    files = []
    if res:
        for k, v in res.items():
            v['size_str'] = f"{v['size'] / 1024:.2f} KB"
            files.append(v)
    return jsonify({"status": "success", "files": files})

@app.route('/api/storage/delete', methods=['POST', 'OPTIONS'])
def delete_file_api():
    if request.method == 'OPTIONS': return jsonify({}), 200
    data = get_request_data()
    api_key, filename = data.get('api_key'), data.get('filename', '')
    dev_info = get_dev_info(api_key)
    if dev_info:
        requests.delete(f"{dev_info['assigned_db']}/projects/{api_key}/storage/{safe_email(filename)}.json")
        return jsonify({"status": "success", "message": "File record deleted."})
    return jsonify({"status": "error"})

@app.route('/api/usage', methods=['POST', 'OPTIONS'])
def usage():
    if request.method == 'OPTIONS': return jsonify({}), 200
    api_key = get_request_data().get('api_key')
    dev_info = get_dev_info(api_key)
    if not dev_info: return jsonify({"status": "error"})
    
    user_db = dev_info['assigned_db']
    db_data = requests.get(f"{user_db}/projects/{api_key}/db.json").json() or {}
    auth_data = requests.get(f"{user_db}/projects/{api_key}/auth.json").json() or {}
    files_data = requests.get(f"{user_db}/projects/{api_key}/storage.json").json() or {}
    
    db_bytes = len(json.dumps(db_data).encode('utf-8'))
    file_count = len(files_data)
    storage_bytes = sum(f.get('size', 0) for f in files_data.values())
    
    return jsonify({"status": "success", "plan": dev_info.get('plan', 'free'), "monthly_usage": {"storage": storage_bytes, "db": db_bytes, "auth": len(auth_data)}, "file_count": file_count, "total": f"{(storage_bytes + db_bytes) / 1024:.2f} KB"})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
