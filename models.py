from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date

db = SQLAlchemy()

# --- مدل‌های دیتابیس ---

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    streak_days = db.Column(db.Integer, default=0) # پیش‌فرض 0
    last_active = db.Column(db.DateTime, nullable=True) # مقدار اولیه خالی
    league = db.Column(db.Integer, default=10)
    group_id = db.Column(db.Integer, default=1)
    xp = db.Column(db.Integer, default=0)
    gems = db.Column(db.Integer, default=100) # ۱۰۰ الماس هدیه ثبت‌نام
    streak_freeze_count = db.Column(db.Integer, default=0) # تعداد یخ‌سازهای خریداری شده
    
    @property
    def level(self):
        # یک فرمول ساده برای لول: هر 500 امتیاز یک لول
        return (self.xp // 500) + 1
    
    score_logs = db.relationship('ScoreLog', backref='user', lazy=True)
    progress = db.relationship('UserWord', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def update_streak(self):
        today = datetime.utcnow().date()
        
        if self.last_active and self.last_active.date() == today:
            if self.streak_days == 0:
                self.streak_days = 1
                return True
            return False
        
        if self.last_active:
            last_active_date = self.last_active.date()
            diff = (today - last_active_date).days

            if diff == 1:
                self.streak_days += 1
            else:
                self.streak_days = 1
        else:
            self.streak_days = 1
        
        self.last_active = datetime.utcnow()
        return True

class UserWord(db.Model):
    __tablename__ = 'user_words'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lemma = db.Column(db.String(64), nullable=False)
    
    # امتیاز مهارت‌ها (۰ تا ۳ یا بیشتر)
    score_listening = db.Column(db.Integer, default=0)
    score_writing = db.Column(db.Integer, default=0)
    score_reading = db.Column(db.Integer, default=0) # همان MCQ
    score_article = db.Column(db.Integer, default=0)
    
    # آمار خطاها برای تشخیص کلمات ضعیف
    wrong_count = db.Column(db.Integer, default=0)
    last_practiced = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def total_score(self):
        # میانگین یا مجموع امتیازات برای نمایش سطح کلی (مثلاً ۰ تا ۶)
        return min(6, (self.score_listening + self.score_writing + self.score_reading + self.score_article))

class ScoreLog(db.Model):
    __tablename__ = 'score_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    points = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)