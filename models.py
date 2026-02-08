from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    current_level = db.Column(db.String(10), default='A1')
    daily_goal = db.Column(db.Integer, default=10)
    streak_days = db.Column(db.Integer, default=0)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    streak_days = db.Column(db.Integer, default=0)
    best_streak = db.Column(db.Integer, default=0)
    last_active_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user_words = db.relationship('UserWord', backref='user', lazy=True, cascade='all, delete-orphan')
    review_sessions = db.relationship('ReviewSession', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def update_streak(self):
        """بروزرسانی استریک کاربر"""
        today = datetime.utcnow().date()
        last_active_date = self.last_active.date() if self.last_active else None
        
        if last_active_date:
            days_diff = (today - last_active_date).days
            
            if days_diff == 1:
                # کاربر دیروز هم فعال بوده
                self.streak_days += 1
            elif days_diff > 1:
                # شکستن استریک
                self.streak_days = 1
            # اگر days_diff == 0 یعنی امروز قبلاً فعالیت داشته
        else:
            # اولین فعالیت
            self.streak_days = 1
        
        self.last_active = datetime.utcnow()

class Word(db.Model):
    __tablename__ = 'words'
    
    id = db.Column(db.Integer, primary_key=True)
    lemma = db.Column(db.String(100), nullable=False)
    article = db.Column(db.String(10))  # der, die, das
    plural = db.Column(db.String(100))  # جمع کلمه
    part_of_speech = db.Column(db.String(50))
    cefr_level = db.Column(db.String(10))
    lesson = db.Column(db.String(10))  # شماره درس
    german_definition = db.Column(db.Text)
    persian_translation = db.Column(db.String(200))
    example_german = db.Column(db.Text)
    example_persian = db.Column(db.Text)
    ipa = db.Column(db.String(100))
    frequency_rank = db.Column(db.Integer, default=1000)
    
    # Relationships
    user_words = db.relationship('UserWord', backref='word', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Word {self.article} {self.lemma}>'
    
    def get_display_text(self):
        """متن نمایشی کلمه همراه با مقاله"""
        if self.article:
            return f"{self.article} {self.lemma}"
        return self.lemma

class UserWord(db.Model):
    """مدل وضعیت حافظه کاربر برای هر کلمه"""
    __tablename__ = 'user_words'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    word_id = db.Column(db.Integer, db.ForeignKey('words.id'), nullable=False)
    
    # وضعیت حافظه
    memory_strength = db.Column(db.Float, default=0.0)
    memory_state = db.Column(db.String(20), default='new')
    stability = db.Column(db.Float, default=1.0)
    
    # تاریخ‌ها
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_reviewed = db.Column(db.DateTime)
    next_review = db.Column(db.DateTime, default=datetime.utcnow)
    
    # تاریخچه عملکرد
    total_reviews = db.Column(db.Integer, default=0)
    correct_reviews = db.Column(db.Integer, default=0)
    consecutive_correct = db.Column(db.Integer, default=0)
    avg_response_time = db.Column(db.Float, default=0.0)
    
    # نرخ فرسایش
    decay_rate = db.Column(db.Float, default=0.3)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'word_id', name='unique_user_word'),)
    
    def update_performance(self, is_correct, response_time):
        """بروزرسانی عملکرد کاربر برای این کلمه"""
        self.total_reviews += 1
        
        if is_correct:
            self.correct_reviews += 1
            self.consecutive_correct += 1
        else:
            self.consecutive_correct = 0
        
        # میانگین زمان پاسخ
        if self.avg_response_time == 0:
            self.avg_response_time = response_time
        else:
            self.avg_response_time = (self.avg_response_time * (self.total_reviews - 1) + response_time) / self.total_reviews
        
        self.last_reviewed = datetime.utcnow()

class ReviewSession(db.Model):
    __tablename__ = 'review_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_type = db.Column(db.String(20))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    words_learned = db.Column(db.Integer, default=0)
    words_reviewed = db.Column(db.Integer, default=0)
    total_correct = db.Column(db.Integer, default=0)
    total_questions = db.Column(db.Integer, default=0)
    
    # Relationships
    review_logs = db.relationship('ReviewLog', backref='session', lazy=True, cascade='all, delete-orphan')

class ReviewLog(db.Model):
    __tablename__ = 'review_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('review_sessions.id'), nullable=False)
    user_word_id = db.Column(db.Integer, db.ForeignKey('user_words.id'), nullable=False)
    
    exercise_type = db.Column(db.String(20))
    response_time = db.Column(db.Float)
    was_correct = db.Column(db.Boolean)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user_word = db.relationship('UserWord', backref='review_logs')