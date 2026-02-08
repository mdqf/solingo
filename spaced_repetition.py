import math
from datetime import datetime, timedelta
import random

class SpacedRepetitionEngine:
    """موتور تکرار فاصله‌دار"""
    
    # پارامترهای الگوریتم
    BASE_INTERVALS = {
        'new': 1,  # 1 ساعت
        'learning': 6,  # 6 ساعت
        'weak': 12,  # 12 ساعت
        'strong': 24,  # 1 روز
        'mastered': 48  # 2 روز
    }
    
    STRENGTH_THRESHOLDS = {
        'new': 0.0,
        'learning': 0.3,
        'weak': 0.5,
        'strong': 0.7,
        'mastered': 0.9
    }
    
    @classmethod
    def calculate_review(cls, user_word, is_correct, response_time):
        """
        محاسبه وضعیت بعدی بر اساس پاسخ کاربر
        """
        # به‌روزرسانی عملکرد
        user_word.update_performance(is_correct, response_time)
        
        # محاسبه قدرت حافظه جدید
        if is_correct:
            # پاسخ صحیح
            time_factor = max(0, 1 - (response_time / 15))  # جریمه برای پاسخ‌های آهسته
            
            if response_time < 4:
                # پاسخ سریع (کمتر از 4 ثانیه)
                strength_increase = 0.25 + (0.1 * time_factor)
            elif response_time < 8:
                # پاسخ متوسط
                strength_increase = 0.15 + (0.05 * time_factor)
            else:
                # پاسخ کند
                strength_increase = 0.05 + (0.02 * time_factor)
            
            # بونوس برای پاسخ‌های متوالی صحیح
            if user_word.consecutive_correct > 3:
                consecutive_bonus = min(0.2, user_word.consecutive_correct * 0.03)
                strength_increase += consecutive_bonus
            
            user_word.memory_strength = min(1.0, user_word.memory_strength + strength_increase)
            
        else:
            # پاسخ غلط - کاهش شدید
            penalty = 0.4 - (response_time / 50)  # پاسخ‌های سریع‌تر جریمه کمتری
            user_word.memory_strength = max(0.0, user_word.memory_strength - penalty)
        
        # تعیین وضعیت جدید
        new_state = cls._determine_state(user_word.memory_strength)
        user_word.memory_state = new_state
        
        # محاسبه زمان مرور بعدی
        next_review = cls._calculate_next_review(user_word, new_state, is_correct)
        user_word.next_review = next_review
        
        return {
            'next_review': next_review,
            'strength': user_word.memory_strength,
            'state': new_state,
            'consecutive_correct': user_word.consecutive_correct
        }
    
    @classmethod
    def _determine_state(cls, strength):
        """تعیین وضعیت بر اساس قدرت حافظه"""
        if strength >= cls.STRENGTH_THRESHOLDS['mastered']:
            return 'mastered'
        elif strength >= cls.STRENGTH_THRESHOLDS['strong']:
            return 'strong'
        elif strength >= cls.STRENGTH_THRESHOLDS['weak']:
            return 'weak'
        elif strength >= cls.STRENGTH_THRESHOLDS['learning']:
            return 'learning'
        else:
            return 'new'
    
    @classmethod
    def _calculate_next_review(cls, user_word, state, is_correct):
        """محاسبه زمان مرور بعدی"""
        base_hours = cls.BASE_INTERVALS.get(state, 1)
        
        # ضرب‌کننده بر اساس عملکرد
        if is_correct:
            # ضرب‌کننده تصاعدی برای پاسخ‌های متوالی صحیح
            multiplier = 1.0 + (user_word.consecutive_correct * 0.5)
            
            # ضرب‌کننده بر اساس قدرت حافظه
            strength_multiplier = 1.0 + (user_word.memory_strength * 2.0)
            
            total_multiplier = multiplier * strength_multiplier
            
        else:
            # برای پاسخ غلط، مرور زودتر
            total_multiplier = 0.5
        
        # اعمال نرخ فرسایش
        decay_factor = 1.5 - user_word.decay_rate  # 1.0 تا 1.5
        total_multiplier *= decay_factor
        
        # محدود کردن بازه
        total_multiplier = max(0.5, min(total_multiplier, 10.0))
        
        interval_hours = base_hours * total_multiplier
        
        # تبدیل به روز اگر بزرگ‌تر از 24 ساعت است
        if interval_hours >= 24:
            interval_days = math.ceil(interval_hours / 24)
            next_review = datetime.utcnow() + timedelta(days=interval_days)
        else:
            next_review = datetime.utcnow() + timedelta(hours=interval_hours)
        
        return next_review
    
    @classmethod
    def get_due_words(cls, user_id, limit=20):
        """دریافت کلمات موعد مرور"""
        from models import UserWord
        from datetime import datetime
        
        due_words = UserWord.query.filter(
            UserWord.user_id == user_id,
            UserWord.next_review <= datetime.utcnow(),
            UserWord.memory_state != 'mastered'
        ).order_by(
            UserWord.memory_strength.asc(),  # اول کلمات ضعیف
            UserWord.next_review.asc()
        ).limit(limit).all()
        
        return due_words
    
    @classmethod
    def get_new_words(cls, user_id, limit=5):
        """دریافت کلمات جدید برای کاربر"""
        from models import Word, UserWord, db
        from sqlalchemy import and_, not_
        
        # کلماتی که کاربر هنوز ندیده
        subquery = db.session.query(UserWord.word_id).filter(UserWord.user_id == user_id)
        user_level = db.session.query(db.func.max(User.current_level)).filter(User.id == user_id).scalar() or 'A1'
        
        new_words = Word.query.filter(
            and_(
                Word.cefr_level == user_level,
                not_(Word.id.in_(subquery))
            )
        ).order_by(
            Word.frequency_rank.asc()
        ).limit(limit).all()
        
        return new_words