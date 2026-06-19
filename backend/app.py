from flask import Flask, jsonify, request, session, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime
import os
import uuid

app = Flask(__name__)
app.secret_key = 'your-secret-key-12345'

# Database Setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///engg_adda.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB max size

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

CORS(app, supports_credentials=True, origins=["http://localhost:5500", "http://127.0.0.1:5500"])

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'zip', 'rar', 'txt', 'ppt', 'pptx', 'xls', 'xlsx', 'ods', 'csv', 'jpg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ===== MODELS =====
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50)) # 'study' or 'project'
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)    # Added Description Field!
    branch = db.Column(db.String(100))  
    semester = db.Column(db.String(50)) 
    year = db.Column(db.String(50))     
    subject = db.Column(db.String(200)) # Stores 'Major/Minor' for projects, or 'DBMS' for study
    
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    uploaded_by = db.Column(db.String(80), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    downloads = db.Column(db.Integer, default=0)

with app.app_context():
    db.create_all()
    if not os.path.exists('uploads'):
        os.makedirs('uploads')

# ===== ROUTES =====
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username exists'}), 400
    if User.query.filter_by(email=data.get('email', '')).first():
        return jsonify({'error': 'Email exists'}), 400
    
    user = User(username=data['username'], email=data.get('email', f"{data['username']}@test.com"))
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'Account created!'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    session['user_id'] = user.id
    session['username'] = user.username
    return jsonify({'message': 'Login success!', 'user': {'username': user.username}})

@app.route('/api/me', methods=['GET'])
def get_user():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    user = User.query.get(session['user_id'])
    return jsonify({'user': {'username': user.username}})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out'})

@app.route('/api/upload', methods=['POST'])
def upload():
    if 'username' not in session:
        return jsonify({'error': 'Login first'}), 401
    
    title = request.form.get('title')
    category = request.form.get('category', 'project')
    description = request.form.get('description', '')
    branch = request.form.get('branch', 'N/A')
    semester = request.form.get('semester', 'N/A')
    year = request.form.get('year', 'N/A')
    subject = request.form.get('subject', 'N/A')
    
    if not title:
        return jsonify({'error': 'Title is required'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'No file attached'}), 400
    
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file format'}), 400
    
    original = file.filename
    ext = original.rsplit('.', 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join('uploads', new_name)
    file.save(path)
    
    new_resource = Resource(
        category=category, title=title, description=description,
        branch=branch, semester=semester, year=year, subject=subject,
        filename=new_name, original_filename=original, filepath=path,
        uploaded_by=session['username']
    )
    db.session.add(new_resource)
    db.session.commit()
    
    return jsonify({'message': 'Uploaded successfully!'}), 201

@app.route('/api/resources', methods=['GET'])
def get_resources():
    query = Resource.query
    
    # Apply filters if provided in URL
    if request.args.get('category'): query = query.filter_by(category=request.args.get('category'))
    if request.args.get('branch'): query = query.filter_by(branch=request.args.get('branch'))
    if request.args.get('subject'): query = query.filter_by(subject=request.args.get('subject'))
    if request.args.get('uploaded_by'): query = query.filter_by(uploaded_by=request.args.get('uploaded_by'))
        
    resources = query.order_by(Resource.uploaded_at.desc()).all()
    return jsonify({
        'resources': [{
            'id': r.id, 'category': r.category, 'title': r.title, 'description': r.description,
            'branch': r.branch, 'semester': r.semester, 'year': r.year, 'subject': r.subject,
            'filename': r.original_filename, 'uploaded_by': r.uploaded_by,
            'uploaded_at': r.uploaded_at.strftime('%Y-%m-%d'), 'downloads': r.downloads
        } for r in resources]
    })

@app.route('/api/download/<int:rid>', methods=['GET'])
def download(rid):
    resource = Resource.query.get(rid)
    if not resource:
        return jsonify({'error': 'Not found'}), 404
    resource.downloads += 1
    db.session.commit()
    return send_file(resource.filepath, as_attachment=True, download_name=resource.original_filename)

@app.route('/api/resources/<int:rid>', methods=['DELETE'])
def delete(rid):
    if 'username' not in session: return jsonify({'error': 'Login first'}), 401
    resource = Resource.query.get(rid)
    if not resource: return jsonify({'error': 'Not found'}), 404
    if resource.uploaded_by != session['username']: return jsonify({'error': 'Unauthorized'}), 403

    if os.path.exists(resource.filepath): os.remove(resource.filepath)
    db.session.delete(resource)
    db.session.commit()
    return jsonify({'message': 'Deleted!'})

if __name__ == '__main__':
    app.run(debug=True, port=5001)