from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, current_user
# توجه: مدل User را باید اینجا ایمپورت کنید
from models import db, User 

auth = Blueprint('auth', __name__) # template_folder معمولا در سطح app تنظیم می‌شود

# --- مسیرهای احراز هویت (Auth) ---

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('profile'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        remember = True if request.form.get('remember') else False
        if user and user.check_password(request.form.get('password')):
            login_user(user, remember=remember)
            # به‌روزرسانی استریک به محض ورود
            # user.update_streak()
            db.session.commit()
            flash(f'خوش آمدید!', 'success')
            return redirect(url_for('lessons'))
        flash('نام کاربری یا رمز عبور اشتباه است', 'error')
    return render_template('auth/login.html', current_page='login')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(username=request.form.get('username')).first():
            flash('این نام کاربری قبلاً انتخاب شده است', 'error')
            return redirect(url_for('auth.register'))
        
        if User.query.filter_by(email=request.form.get('email')).first():
            flash('این ایمیل قبلاً ثبت نام شده است', 'error')
            return redirect(url_for('auth.register'))
        
        user = User(username=request.form.get('username'), email=request.form.get('email'))
        user.set_password(request.form.get('password'))
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', current_page='register')


@auth.route('/logout')
def logout():
    logout_user()
    flash('با موفقیت خارج شدید.', 'info')
    return redirect(url_for('index'))