from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('learning.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            user.update_streak()
            db.session.commit()
            
            flash('با موفقیت وارد شدید!', 'success')
            return redirect(url_for('learning.dashboard'))
        
        flash('نام کاربری یا رمز عبور اشتباه است', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('learning.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # اعتبارسنجی
        errors = []
        
        if not username or len(username) < 3:
            errors.append('نام کاربری باید حداقل ۳ کاراکتر باشد')
        
        if not email or '@' not in email:
            errors.append('ایمیل معتبر وارد کنید')
        
        if not password or len(password) < 6:
            errors.append('رمز عبور باید حداقل ۶ کاراکتر باشد')
        
        if password != confirm_password:
            errors.append('رمز عبور و تکرار آن مطابقت ندارند')
        
        # بررسی وجود کاربر
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            errors.append('این نام کاربری قبلاً ثبت شده است')
        
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            errors.append('این ایمیل قبلاً ثبت شده است')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
        else:
            # ایجاد کاربر جدید
            user = User(username=username, email=email)
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            flash('ثبت‌نام با موفقیت انجام شد! لطفاً وارد شوید.', 'success')
            return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('با موفقیت خارج شدید', 'info')
    return redirect(url_for('index'))