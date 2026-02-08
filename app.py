from flask import Flask, render_template, request, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from utils.vocabulary_loader import VocabularyLoader
from datetime import datetime
import json
import os
from pathlib import Path
import glob

# ایجاد پوشه instance اگر وجود ندارد
project_root = Path(__file__).parent
instance_path = project_root / 'instance'
instance_path.mkdir(exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-key-123-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{instance_path}/database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_TYPE'] = 'filesystem'

from models import db, User

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Import blueprints بعد از ایجاد app و db
try:
    from routes.auth import auth_bp
    from routes.learning import learning_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(learning_bp)
except ImportError as e:
    print(f"Warning: Could not import blueprints: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/load_vocabulary')
@login_required
def load_vocabulary():
    """بارگذاری کلمات از تمام فایل‌های JSON"""
    loader = VocabularyLoader()
    result = loader.load_all_files()
    return jsonify(result)

@app.route('/vocabulary_stats')
@login_required
def vocabulary_stats():
    """دریافت آمار کلمات"""
    loader = VocabularyLoader()
    stats = loader.get_stats()
    return jsonify(stats)

@app.route('/clear_vocabulary')
@login_required
def clear_vocabulary():
    """پاک کردن کلمات (فقط برای توسعه)"""
    loader = VocabularyLoader()
    result = loader.clear_database()
    return jsonify(result)

@app.route('/check_vocabulary')
@login_required
def check_vocabulary():
    """بررسی وضعیت کلمات در دیتابیس"""
    from models import Word
    
    total_words = Word.query.count()
    a1_words = Word.query.filter_by(cefr_level='A1').count()
    
    return jsonify({
        'total_words': total_words,
        'a1_words': a1_words,
        'message': f'تعداد کل کلمات: {total_words} (سطح A1: {a1_words})'
    })

if __name__ == '__main__':
    with app.app_context():
        # Import all models
        from models import Word, UserWord, ReviewSession, ReviewLog
        db.create_all()
    
    # ایجاد پوشه templates اگر وجود ندارد
    templates_path = project_root / 'templates'
    templates_path.mkdir(exist_ok=True)
    
    print("=" * 50)
    print("🚀 Solingo - سیستم یادگیری زبان آلمانی")
    print("=" * 50)
    print(f"📁 مسیر پروژه: {project_root}")
    print(f"🗃️  مسیر دیتابیس: {instance_path}/database.db")
    print(f"📊 مسیر داده‌ها: {project_root}/data/")
    print("=" * 50)
    print("🌐 آدرس: http://localhost:5000")
    print("=" * 50)
    print("💡 دستورات مفید:")
    print("   - /load_vocabulary : بارگذاری کلمات از فایل‌های JSON")
    print("   - /check_vocabulary : بررسی وضعیت کلمات")
    print("=" * 50)
    
    app.run(debug=True, port=5000)