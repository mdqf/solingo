from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from exercises import ExerciseGenerator
from datetime import datetime, timedelta
import random
import time
import math

from models import db, User, Word, UserWord, ReviewSession, ReviewLog

learning_bp = Blueprint('learning', __name__)

# ===== Spaced Repetition Engine (مستقیم در این فایل) =====
class SpacedRepetitionEngine:
    """موتور تکرار فاصله‌دار"""
    
    BASE_INTERVALS = {
        'new': 1,      # 1 ساعت
        'learning': 6, # 6 ساعت
        'weak': 12,    # 12 ساعت
        'strong': 24,  # 1 روز
        'mastered': 48 # 2 روز
    }
    
    @staticmethod
    def calculate_review(user_word, is_correct, response_time):
        """محاسبه وضعیت بعدی بر اساس پاسخ کاربر"""
        # به‌روزرسانی عملکرد
        user_word.total_reviews += 1
        
        if is_correct:
            user_word.correct_reviews += 1
            user_word.consecutive_correct += 1
            
            # پاسخ سریع = قدرت بیشتر
            if response_time < 4:
                strength_increase = 0.25
            elif response_time < 8:
                strength_increase = 0.15
            else:
                strength_increase = 0.05
                
            # بونوس برای پاسخ‌های متوالی
            if user_word.consecutive_correct > 3:
                strength_increase += min(0.2, user_word.consecutive_correct * 0.03)
                
            user_word.memory_strength = min(1.0, user_word.memory_strength + strength_increase)
        else:
            user_word.consecutive_correct = 0
            user_word.memory_strength = max(0.0, user_word.memory_strength - 0.4)
        
        # تعیین وضعیت جدید
        if user_word.memory_strength >= 0.9:
            new_state = 'mastered'
        elif user_word.memory_strength >= 0.7:
            new_state = 'strong'
        elif user_word.memory_strength >= 0.5:
            new_state = 'weak'
        elif user_word.memory_strength >= 0.3:
            new_state = 'learning'
        else:
            new_state = 'new'
            
        user_word.memory_state = new_state
        
        # محاسبه زمان مرور بعدی
        base_hours = SpacedRepetitionEngine.BASE_INTERVALS.get(new_state, 1)
        
        if is_correct:
            multiplier = 1.0 + (user_word.consecutive_correct * 0.5)
            strength_multiplier = 1.0 + (user_word.memory_strength * 2.0)
            total_multiplier = multiplier * strength_multiplier
        else:
            total_multiplier = 0.5
        
        # اعمال نرخ فرسایش
        decay_factor = 1.5 - user_word.decay_rate
        total_multiplier *= decay_factor
        total_multiplier = max(0.5, min(total_multiplier, 10.0))
        
        interval_hours = base_hours * total_multiplier
        
        if interval_hours >= 24:
            interval_days = math.ceil(interval_hours / 24)
            next_review = datetime.utcnow() + timedelta(days=interval_days)
        else:
            next_review = datetime.utcnow() + timedelta(hours=interval_hours)
        
        user_word.next_review = next_review
        user_word.last_reviewed = datetime.utcnow()
        
        # میانگین زمان پاسخ
        if user_word.avg_response_time == 0:
            user_word.avg_response_time = response_time
        else:
            user_word.avg_response_time = (user_word.avg_response_time * (user_word.total_reviews - 1) + response_time) / user_word.total_reviews
        
        return {
            'next_review': next_review,
            'strength': user_word.memory_strength,
            'state': new_state,
            'consecutive_correct': user_word.consecutive_correct
        }
    
    @staticmethod
    def get_due_words(user_id, limit=20):
        """دریافت کلمات موعد مرور"""
        due_words = UserWord.query.filter(
            UserWord.user_id == user_id,
            UserWord.next_review <= datetime.utcnow(),
            UserWord.memory_state != 'mastered'
        ).order_by(
            UserWord.memory_strength.asc(),
            UserWord.next_review.asc()
        ).limit(limit).all()
        
        return due_words
    
    @staticmethod
    def get_new_words(user_id, limit=5):
        """دریافت کلمات جدید برای کاربر - نسخه بهبود یافته"""
        from sqlalchemy import and_, not_
        
        # کاربر را پیدا کن
        user = User.query.get(user_id)
        if not user:
            print(f"❌ کاربر {user_id} پیدا نشد")
            return []
        
        user_level = user.current_level if user else 'A1'
        
        # **اولویت‌بندی برای کاربران جدید**: از پایه‌ای‌ترین درس شروع کن
        print(f"🔍 جستجوی کلمات جدید برای کاربر {user_id} (سطح: {user_level})")
        
        # 1. ابتدا کلمات A1 درس ۴ (پایه‌ترین)
        base_words = Word.query.filter(
            and_(
                Word.cefr_level == 'A1',
                Word.lesson == '4',
                not_(Word.id.in_(
                    db.session.query(UserWord.word_id)
                    .filter(UserWord.user_id == user_id)
                    .subquery()
                ))
            )
        ).order_by(
            Word.frequency_rank.asc()
        ).limit(limit).all()
        
        if base_words:
            print(f"✅ {len(base_words)} کلمه از درس ۴ سطح A1 پیدا شد")
            return base_words
        
        print("⚠️ کلمه‌ای در درس ۴ سطح A1 پیدا نشد")
        
        # 2. سپس سایر کلمات A1 بر اساس درس
        a1_words = Word.query.filter(
            and_(
                Word.cefr_level == 'A1',
                not_(Word.id.in_(
                    db.session.query(UserWord.word_id)
                    .filter(UserWord.user_id == user_id)
                    .subquery()
                ))
            )
        ).order_by(
            Word.lesson.asc(),  # اول درس‌های پایین‌تر
            Word.frequency_rank.asc()
        ).limit(limit).all()
        
        if a1_words:
            print(f"✅ {len(a1_words)} کلمه از سایر درس‌های A1 پیدا شد")
            return a1_words
        
        print("⚠️ کلمه‌ای در سطح A1 پیدا نشد")
        
        # 3. اگر در سطح کاربر کلمه‌ای نبود، سطوح پایین‌تر را بررسی کن
        if user_level != 'A1':
            lower_level_words = Word.query.filter(
                and_(
                    Word.cefr_level == 'A1',
                    not_(Word.id.in_(
                        db.session.query(UserWord.word_id)
                        .filter(UserWord.user_id == user_id)
                        .subquery()
                    ))
                )
            ).order_by(
                Word.lesson.asc(),
                Word.frequency_rank.asc()
            ).limit(limit).all()
            
            if lower_level_words:
                print(f"✅ {len(lower_level_words)} کلمه از سطح پایین‌تر (A1) پیدا شد")
                return lower_level_words
        
        print("❌ هیچ کلمه جدیدی پیدا نشد")
        return []
    
    @staticmethod
    def should_introduce_new_words(user_id, due_count):
        """تعیین آیا باید کلمات جدید معرفی شود یا نه"""
        from models import UserWord
        
        # شمارش کلمات کاربر
        total_user_words = UserWord.query.filter_by(user_id=user_id).count()
        
        # ========== **اصلاح بحرانی** ==========
        # کاربر جدید → حتماً کلمه جدید معرفی کن
        if total_user_words == 0:
            print(f"👤 کاربر {user_id} جدید است. کلمات جدید معرفی می‌شود.")
            return True
        
        # اگر کاربر کلمات زیادی برای مرور دارد، کلمات جدید اضافه نکن
        if due_count >= 8:
            print(f"⚠️ کاربر {user_id} کلمات زیادی برای مرور دارد ({due_count}). کلمات جدید اضافه نمی‌شود.")
            return False
        
        # اگر کاربر کلمات جدید زیادی دارد (بیش از ۵ تا)، منتظر بمان
        new_words_count = UserWord.query.filter_by(
            user_id=user_id,
            memory_state='new'
        ).count()
        
        if new_words_count > 5:
            print(f"⚠️ کاربر {user_id} کلمات جدید زیادی دارد ({new_words_count}). کلمات جدید اضافه نمی‌شود.")
            return False
        
        # محاسبه نسبت کلمات تسلط یافته
        mastered_count = UserWord.query.filter_by(
            user_id=user_id,
            memory_state='mastered'
        ).count()
        
        if total_user_words > 0:
            mastery_ratio = mastered_count / total_user_words
            
            # اگر کاربر کمتر از ۳۰٪ کلمات را تسلط یافته، کلمات جدید اضافه کن
            if mastery_ratio < 0.3:
                print(f"✅ کاربر {user_id} تسلط کم ({mastery_ratio:.0%}). کلمات جدید معرفی می‌شود.")
                return True
            else:
                print(f"⚠️ کاربر {user_id} تسلط بالایی دارد ({mastery_ratio:.0%}). کلمات جدید اضافه نمی‌شود.")
                return False
        
        # حالت پیش‌فرض: کلمات جدید معرفی کن
        print(f"✅ حالت پیش‌فرض: کلمات جدید برای کاربر {user_id} معرفی می‌شود.")
        return True

# ===== Routes =====
@learning_bp.route('/dashboard')
@login_required
def dashboard():
    """داشبورد کاربر"""
    # آمار کاربر
    total_words = UserWord.query.filter_by(user_id=current_user.id).count()
    mastered_words = UserWord.query.filter_by(
        user_id=current_user.id,
        memory_state='mastered'
    ).count()
    
    # کلمات برای مرور امروز
    due_words_count = UserWord.query.filter(
        UserWord.user_id == current_user.id,
        UserWord.next_review <= datetime.utcnow(),
        UserWord.memory_state != 'mastered'
    ).count()
    
    # آخرین سشن‌ها
    recent_sessions = ReviewSession.query.filter_by(
        user_id=current_user.id
    ).order_by(
        ReviewSession.started_at.desc()
    ).limit(5).all()
    
    # توزیع وضعیت کلمات
    status_distribution = {}
    states = ['new', 'learning', 'weak', 'strong', 'mastered']
    for state in states:
        count = UserWord.query.filter_by(
            user_id=current_user.id,
            memory_state=state
        ).count()
        status_distribution[state] = count
    
    return render_template('learning/dashboard.html',
                         user=current_user,
                         total_words=total_words,
                         mastered_words=mastered_words,
                         due_words=due_words_count,
                         recent_sessions=recent_sessions,
                         status_distribution=status_distribution)

@learning_bp.route('/review')
@login_required
def review():
    """صفحه مرور و تمرین"""
    return render_template('learning/review.html')

@learning_bp.route('/start_session', methods=['GET'])
@login_required
def start_session():
    """شروع جلسه یادگیری جدید - صفحه اصلی"""
    return render_template('learning/session_start.html')

@learning_bp.route('/api/start_session', methods=['GET'])
@login_required
def api_start_session():
    """API to start a learning session - returns JSON"""
    try:
        print(f"\n{'='*60}")
        print(log_user_state(current_user.id))
        print(f"{'='*60}\n")
        print(f"\n🚀 Starting session for user {current_user.id} ({current_user.username})")
        
        # Get words for review
        due_words = SpacedRepetitionEngine.get_due_words(current_user.id, limit=10)
        print(f"📝 Due words for review: {len(due_words)}")
        
        # Get new words
        new_words = []
        if SpacedRepetitionEngine.should_introduce_new_words(current_user.id, len(due_words)):
            new_words = SpacedRepetitionEngine.get_new_words(current_user.id, limit=5)
            print(f"🆕 New words found: {len(new_words)}")
        else:
            print(f"⏸️ No new words will be introduced")
        
        # ========== **Error Handling & State Validation** ==========
        # Detailed user status check
        
        # 1. Count total available words in user's level
        user_level = current_user.current_level or 'A1'
        total_words_in_level = Word.query.filter_by(cefr_level=user_level).count()
        
        # 2. Count current user's words
        total_user_words = UserWord.query.filter_by(user_id=current_user.id).count()
        
        print(f"📊 User Statistics:")
        print(f"   - Level: {user_level}")
        print(f"   - Total available words: {total_words_in_level}")
        print(f"   - User's word count: {total_user_words}")
        print(f"   - Due words: {len(due_words)}")
        print(f"   - New words found: {len(new_words)}")
        
        # Various Scenarios
        if total_user_words == 0 and len(new_words) == 0:
            # New user but no words found in database
            print("❌ New User: No words found in database")
            return jsonify({
                'success': False,
                'message': 'No words available for learning! Please load vocabulary first.',
                'has_words': False,
                'reason': 'no_words_in_database',
                'suggestion': '/load_vocabulary'
            })
        
        elif total_user_words == 0 and len(new_words) > 0:
            # New user and words available - normal state
            print(f"✅ New User: {len(new_words)} new words being introduced")
            # Continue normal flow
        
        elif total_user_words > 0 and total_user_words >= total_words_in_level:
            # User has mastered all available words in this level
            print(f"🎉 User has mastered all {total_words_in_level} words in level {user_level}!")
            return jsonify({
                'success': False,
                'message': f'Well done! You have mastered all words in level {user_level}!',
                'has_words': False,
                'reason': 'all_words_mastered',
                'suggestion': 'level_up'
            })
        
        elif not due_words and not new_words:
            # Intermediate state - issue finding words
            print("⚠️ Unusual state: No words for review and no new words found")
            
            # Fallback: Try finding new words with less restriction
            fallback_new_words = SpacedRepetitionEngine.get_new_words(current_user.id, limit=10)
            if fallback_new_words:
                print(f"🔄 Fallback mode: {len(fallback_new_words)} new words found")
                new_words = fallback_new_words
            else:
                print("❌ Fallback mode failed to find words")
                return jsonify({
                    'success': False,
                    'message': 'The system could not find any words to learn. Please try again.',
                    'has_words': False,
                    'reason': 'no_words_found',
                    'suggestion': 'retry'
                })

        # Final check for words before session creation
        if not due_words and not new_words:
            return jsonify({
                'success': False,
                'message': 'No words available for learning! Either you have finished all words or you need to load new ones.',
                'has_words': False
            })
        
        # Create Review Session
        review_session = ReviewSession(
            user_id=current_user.id,
            session_type='mixed',
            started_at=datetime.utcnow()
        )
        db.session.add(review_session)
        
        # Create UserWord records for new words and store IDs
        new_user_word_ids = []
        for word in new_words:
            # Check if UserWord already exists
            existing_user_word = UserWord.query.filter_by(
                user_id=current_user.id,
                word_id=word.id
            ).first()
            
            if not existing_user_word:
                user_word = UserWord(
                    user_id=current_user.id,
                    word_id=word.id,
                    memory_state='new',
                    next_review=datetime.utcnow()
                )
                db.session.add(user_word)
                db.session.flush()  # Flush to get the ID
                new_user_word_ids.append(user_word.id)
            else:
                new_user_word_ids.append(existing_user_word.id)
        
        # Commit changes
        db.session.commit()
        
        # Build session word list using the algorithm
        due_user_word_ids = [uw.id for uw in due_words]
        all_user_word_ids = build_session_words(due_user_word_ids, new_user_word_ids)
        
        if not all_user_word_ids:
            return jsonify({
                'success': False,
                'message': 'Error creating learning session',
                'has_words': False
            })
        
        # Store in Flask session
        session['current_session_id'] = review_session.id
        session['user_word_ids'] = all_user_word_ids  # Storing UserWord IDs only
        session['current_index'] = 0
        session['question_start_time'] = time.time()
        session['session_start_time'] = time.time()
        
        # Prepare the first word
        first_user_word_id = all_user_word_ids[0]
        first_user_word = UserWord.query.get(first_user_word_id)
        
        if not first_user_word:
            return jsonify({
                'success': False,
                'message': 'Error retrieving the first word',
                'has_words': False
            })
        
        word_data = _prepare_word_data(first_user_word)
        exercise = _generate_exercise_based_on_state(first_user_word)
        
        return jsonify({
            'success': True,
            'session_id': review_session.id,
            'exercise': exercise,
            'total_words': len(all_user_word_ids),
            'current_position': 1,
            'word_data': word_data,
            'has_words': True,
            'user_word_id': first_user_word_id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error starting session: {str(e)}',
            'has_words': False
        })

@learning_bp.route('/get_next_exercise')
@login_required
def get_next_exercise():
    """دریافت تمرین بعدی"""
    current_index = session.get('current_index', 0)
    user_word_ids = session.get('user_word_ids', [])
    
    if current_index >= len(user_word_ids):
        # پایان جلسه
        session_id = session.get('current_session_id')
        if session_id:
            review_session = ReviewSession.query.get(session_id)
            if review_session:
                review_session.completed_at = datetime.utcnow()
                review_session.total_questions = current_index
                db.session.commit()
        
        return jsonify({'finished': True})
    
    # دریافت کلمه فعلی
    user_word_id = user_word_ids[current_index]
    user_word = UserWord.query.get(user_word_id)
    
    if not user_word:
        # اگر UserWord پیدا نشد، برو به بعدی
        session['current_index'] = current_index + 1
        session['question_start_time'] = time.time()
        return get_next_exercise()
    
    # تنظیم زمان شروع سوال
    session['question_start_time'] = time.time()
    
    # آماده‌سازی تمرین
    word_data = _prepare_word_data(user_word)
    exercise = _generate_exercise_based_on_state(user_word)
    
    # افزایش ایندکس برای سوال بعدی
    session['current_index'] = current_index + 1
    
    return jsonify({
        'exercise': exercise,
        'word_data': word_data,
        'user_word_id': user_word_id,
        'position': current_index + 1,
        'total': len(user_word_ids)
    })

@learning_bp.route('/submit_answer', methods=['POST'])
@login_required
def submit_answer():
    """ثبت پاسخ کاربر"""
    data = request.json
    user_word_id = data.get('user_word_id')
    answer = data.get('answer')
    exercise_type = data.get('exercise_type')
    
    # محاسبه زمان پاسخ - استفاده از زمان شروع سوال
    start_time = session.get('question_start_time', time.time())
    response_time = time.time() - start_time
    
    # بررسی پاسخ
    user_word = UserWord.query.get(user_word_id)
    if not user_word:
        return jsonify({
            'correct': False,
            'error': 'کلمه یافت نشد'
        }), 404
    
    word = user_word.word
    is_correct = _check_answer(word, exercise_type, answer)
    
    # بروزرسانی با موتور تکرار فاصله‌دار
    result = SpacedRepetitionEngine.calculate_review(user_word, is_correct, response_time)
    
    # ثبت لاگ
    review_log = ReviewLog(
        session_id=session.get('current_session_id'),
        user_word_id=user_word_id,
        exercise_type=exercise_type,
        response_time=response_time,
        was_correct=is_correct
    )
    db.session.add(review_log)
    
    # بروزرسانی سشن
    review_session = ReviewSession.query.get(session.get('current_session_id'))
    if review_session:
        review_session.total_questions += 1
        if is_correct:
            review_session.total_correct += 1
        
        if user_word.memory_state == 'new':
            review_session.words_learned += 1
        else:
            review_session.words_reviewed += 1
    
    db.session.commit()
    
    # آماده کردن پاسخ صحیح برای نمایش
    correct_answer = _get_correct_answer(word, exercise_type, answer)
    
    # محاسبه استریک
    streak_info = calculate_streak_info(current_user.id, is_correct)
    
    return jsonify({
        'correct': is_correct,
        'feedback': {
            'next_review': result['next_review'].strftime('%Y-%m-%d %H:%M'),
            'strength': round(result['strength'] * 100),
            'state': result['state'],
            'consecutive_correct': result['consecutive_correct'],
            'response_time': round(response_time, 2)
        },
        'correct_answer': correct_answer,
        'streak': streak_info
    })


@learning_bp.route('/session_stats')
@login_required
def session_stats():
    """آمار جلسات کاربر"""
    from datetime import datetime, timedelta
    
    # جلسات ۷ روز اخیر
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_sessions = ReviewSession.query.filter(
        ReviewSession.user_id == current_user.id,
        ReviewSession.started_at >= week_ago
    ).all()
    
    stats = {
        'total_sessions': len(recent_sessions),
        'total_words_learned': sum(s.words_learned for s in recent_sessions),
        'total_words_reviewed': sum(s.words_reviewed for s in recent_sessions),
        'accuracy': calculate_accuracy(recent_sessions),
        'daily_activity': get_daily_activity(recent_sessions)
    }
    
    return jsonify(stats)

def calculate_accuracy(sessions):
    """محاسبه دقت کاربر"""
    total_correct = sum(s.total_correct for s in sessions)
    total_questions = sum(s.total_questions for s in sessions)
    
    if total_questions > 0:
        return round((total_correct / total_questions) * 100, 1)
    return 0

def get_daily_activity(sessions):
    """فعالیت روزانه کاربر"""
    daily = {}
    for session in sessions:
        date = session.started_at.date().isoformat()
        if date not in daily:
            daily[date] = {
                'sessions': 0,
                'words': 0,
                'accuracy': 0
            }
        daily[date]['sessions'] += 1
        daily[date]['words'] += (session.words_learned + session.words_reviewed)
        if session.total_questions > 0:
            daily[date]['accuracy'] = round((session.total_correct / session.total_questions) * 100, 1)
    
    return daily

@learning_bp.route('/get_weak_words')
@login_required
def get_weak_words():
    """دریافت کلمات ضعیف کاربر"""
    weak_words = UserWord.query.filter(
        UserWord.user_id == current_user.id,
        UserWord.memory_state.in_(['weak', 'learning']),
        UserWord.next_review <= datetime.utcnow()
    ).order_by(
        UserWord.memory_strength.asc()
    ).limit(20).all()
    
    words_data = []
    for uw in weak_words:
        word_data = _prepare_word_data(uw)
        word_data['strength'] = round(uw.memory_strength * 100)
        word_data['last_reviewed'] = uw.last_reviewed.strftime('%Y-%m-%d') if uw.last_reviewed else 'هرگز'
        words_data.append(word_data)
    
    return jsonify({'words': words_data})

@learning_bp.route('/practice_word/<int:user_word_id>')
@login_required
def practice_word(user_word_id):
    """تمرین روی کلمه خاص"""
    user_word = UserWord.query.get_or_404(user_word_id)
    
    # بررسی مالکیت
    if user_word.user_id != current_user.id:
        return jsonify({'error': 'دسترسی غیرمجاز'}), 403
    
    # تولید تمرین
    word_data = _prepare_word_data(user_word)
    exercise = _generate_exercise(user_word)
    
    return jsonify({
        'exercise': exercise,
        'word_data': word_data,
        'message': 'تمرین روی کلمه خاص'
    })

@learning_bp.route('/advanced_review')
@login_required
def advanced_review():
    """صفحه تمرین پیشرفته"""
    return render_template('learning/advanced_review.html')

@learning_bp.route('/stats')
@login_required
def stats():
    """صفحه آمار و نمودارها"""
    return render_template('learning/stats.html')

@learning_bp.route('/introduction/<int:word_id>')
@login_required
def word_introduction(word_id):
    """صفحه معرفی اولیه کلمه"""
    word = Word.query.get_or_404(word_id)
    
    # بررسی آیا کاربر قبلاً این کلمه را دیده
    user_word = UserWord.query.filter_by(
        user_id=current_user.id,
        word_id=word_id
    ).first()
    
    if not user_word:
        # ایجاد رکورد اولیه
        user_word = UserWord(
            user_id=current_user.id,
            word_id=word_id,
            memory_state='new',
            next_review=datetime.utcnow()
        )
        db.session.add(user_word)
        db.session.commit()
    
    return render_template('learning/introduction.html', word=word, user_word=user_word)

@learning_bp.route('/start_learning_from_intro/<int:word_id>')
@login_required
def start_learning_from_intro(word_id):
    """شروع یادگیری کلمه بعد از معرفی"""
    # ایجاد سشن برای این کلمه
    review_session = ReviewSession(
        user_id=current_user.id,
        session_type='introduction',
        started_at=datetime.utcnow()
    )
    db.session.add(review_session)
    db.session.commit()
    
    # ذخیره در سشن
    session['current_session_id'] = review_session.id
    session['current_word_id'] = word_id
    session['is_introduction'] = True
    session['start_time'] = time.time()
    
    # دریافت کلمه
    user_word = UserWord.query.filter_by(
        user_id=current_user.id,
        word_id=word_id
    ).first_or_404()
    
    word_data = _prepare_word_data(user_word)
    exercise = _generate_exercise(user_word)
    
    return jsonify({
        'session_id': review_session.id,
        'exercise': exercise,
        'word_data': word_data,
        'is_introduction': True
    })

@learning_bp.route('/smart_start')
@login_required
def smart_start():
    """شروع هوشمند یادگیری برای کاربران جدید"""
    # بررسی آیا کاربر کلمه‌ای یاد گرفته
    user_words_count = UserWord.query.filter_by(user_id=current_user.id).count()
    
    if user_words_count == 0:
        # کاربر کاملاً جدید است
        # پیدا کردن اولین کلمه از درس ۴ سطح A1
        first_word = Word.query.filter_by(
            cefr_level='A1',
            lesson='4'
        ).order_by(
            Word.frequency_rank.asc()
        ).first()
        
        if first_word:
            # هدایت به صفحه معرفی اولین کلمه
            return redirect(url_for('learning.word_introduction', word_id=first_word.id))
        else:
            # اگر کلمه‌ای نیست، بارگذاری کلمات
            flash('لطفاً ابتدا کلمات را بارگذاری کنید.', 'warning')
            return redirect(url_for('load_vocabulary'))
    else:
        # کاربر قبلاً کلماتی یاد گرفته
        # بررسی کلمات نیازمند مرور
        due_words = SpacedRepetitionEngine.get_due_words(current_user.id, limit=1)
        
        if due_words:
            # کلمه‌ای برای مرور وجود دارد
            return redirect(url_for('learning.advanced_review'))
        else:
            # کلمه جدید پیدا کن
            new_words = SpacedRepetitionEngine.get_new_words(current_user.id, limit=1)
            if new_words:
                return redirect(url_for('learning.word_introduction', word_id=new_words[0].id))
            else:
                # همه کلمات را یاد گرفته
                flash('آفرین! شما تمام کلمات این سطح را یاد گرفته‌اید.', 'success')
                return redirect(url_for('learning.dashboard'))

@learning_bp.route('/get_next_lesson')
@login_required
def get_next_lesson():
    """پیشنهاد درس بعدی برای یادگیری"""
    # بررسی کلمات یاد گرفته شده در هر درس
    from sqlalchemy import func
    
    # آمار کلمات یاد گرفته شده در هر درس
    lesson_stats = db.session.query(
        Word.lesson,
        func.count(UserWord.id).label('learned'),
        func.count(Word.id).label('total')
    ).join(
        UserWord, UserWord.word_id == Word.id
    ).filter(
        UserWord.user_id == current_user.id,
        Word.lesson.isnot(None)
    ).group_by(
        Word.lesson
    ).all()
    
    # پیدا کردن درس‌های کامل نشده
    incomplete_lessons = []
    for lesson, learned, total in lesson_stats:
        if learned < total:
            completion_rate = (learned / total) * 100
            incomplete_lessons.append({
                'lesson': lesson,
                'learned': learned,
                'total': total,
                'completion': completion_rate
            })
    
    # مرتب‌سازی بر اساس درصد تکمیل (کمترین اول)
    incomplete_lessons.sort(key=lambda x: x['completion'])
    
    if incomplete_lessons:
        # پیشنهاد اولین درس ناقص
        next_lesson = incomplete_lessons[0]['lesson']
        
        # پیدا کردن کلمات یاد گرفته نشده در این درس
        learned_words_subquery = db.session.query(UserWord.word_id).filter(
            UserWord.user_id == current_user.id
        )
        
        next_words = Word.query.filter(
            Word.lesson == next_lesson,
            ~Word.id.in_(learned_words_subquery)
        ).order_by(
            Word.frequency_rank.asc()
        ).limit(3).all()
        
        return jsonify({
            'next_lesson': next_lesson,
            'completion': incomplete_lessons[0]['completion'],
            'next_words': [
                {
                    'id': w.id,
                    'lemma': w.lemma,
                    'translation': w.persian_translation
                }
                for w in next_words
            ]
        })
    
    # اگر همه درس‌ها کامل شده‌اند، درس بعدی سطح بالاتر
    return jsonify({
        'message': 'همه درس‌های این سطح را کامل کرده‌اید!',
        'suggest_level_up': True
    })

@learning_bp.route('/api/start_practice_session', methods=['GET'])
@login_required
def api_start_practice_session():
    """شروع جلسه تمرین روی کلمات ضعیف"""
    # دریافت کلمات ضعیف
    weak_words = UserWord.query.filter(
        UserWord.user_id == current_user.id,
        UserWord.memory_state.in_(['weak', 'learning']),
        UserWord.next_review <= datetime.utcnow()
    ).order_by(
        UserWord.memory_strength.asc()
    ).limit(10).all()
    
    if not weak_words:
        # اگر کلمه ضعیفی نیست، کلمات جدید پیدا کن
        weak_words = SpacedRepetitionEngine.get_new_words(current_user.id, limit=10)
        if not weak_words:
            return jsonify({
                'success': False,
                'message': 'کلمه‌ای برای تمرین پیدا نشد.'
            })
    
    # ایجاد سشن
    review_session = ReviewSession(
        user_id=current_user.id,
        session_type='practice',
        started_at=datetime.utcnow()
    )
    db.session.add(review_session)
    db.session.commit()
    
    # ذخیره در سشن
    session['current_session_id'] = review_session.id
    session['weak_word_ids'] = [uw.id for uw in weak_words]
    session['current_index'] = 0
    session['start_time'] = time.time()
    session['is_practice_session'] = True
    
    # آماده‌سازی اولین کلمه
    first_word = weak_words[0]
    word_data = _prepare_word_data(first_word)
    exercise = _generate_exercise(first_word)
    
    return jsonify({
        'success': True,
        'session_id': review_session.id,
        'exercise': exercise,
        'total_words': len(weak_words),
        'current_position': 1,
        'word_data': word_data,
        'is_practice': True
    })

@learning_bp.route('/debug_user_state')
@login_required
def debug_user_state():
    """صفحه دیباگ وضعیت کاربر"""
    user_id = current_user.id
    
    # جمع‌آوری اطلاعات
    user_info = {
        'id': user_id,
        'username': current_user.username,
        'level': current_user.current_level,
        'streak': current_user.streak_days,
        'last_active': current_user.last_active_date
    }
    
    # آمار کلمات
    words_info = {
        'total_words_in_level': Word.query.filter_by(cefr_level=current_user.current_level or 'A1').count(),
        'user_words_total': UserWord.query.filter_by(user_id=user_id).count(),
        'due_words': len(SpacedRepetitionEngine.get_due_words(user_id)),
        'should_introduce_new': SpacedRepetitionEngine.should_introduce_new_words(user_id, 0),
        'new_words_available': len(SpacedRepetitionEngine.get_new_words(user_id, limit=10))
    }
    
    # توزیع وضعیت
    states_dist = {}
    for state in ['new', 'learning', 'weak', 'strong', 'mastered']:
        states_dist[state] = UserWord.query.filter_by(
            user_id=user_id,
            memory_state=state
        ).count()
    
    return render_template('learning/debug_state.html',
                         user_info=user_info,
                         words_info=words_info,
                         states_dist=states_dist,
                         log=log_user_state(user_id))

# ===== توابع کمکی =====
def _prepare_word_data(user_word):
    """آماده‌سازی داده‌های کلمه"""
    word = user_word.word
    
    return {
        'user_word_id': user_word.id,
        'word_id': word.id,
        'lemma': word.lemma,
        'article': word.article,
        'plural': word.plural,
        'display_text': word.get_display_text(),  # اضافه کردن نمایش با مقاله
        'translation': word.persian_translation,
        'example': word.example_german,
        'ipa': word.ipa,
        'type': user_word.memory_state,
        'part_of_speech': word.part_of_speech,
        'definition': word.german_definition,
        'lesson': word.lesson
    }

def _generate_exercise(user_word):
    """تولید تمرین بر اساس وضعیت کلمه"""
    return ExerciseGenerator.generate_for_word(user_word.word, user_word)

def _get_multiple_choice_options(correct_word, count=4):
    """گزینه‌های چندگانه با گزینه انحرافی"""
    # گزینه صحیح
    options = [correct_word.persian_translation]
    
    # گزینه‌های انحرافی
    all_words = Word.query.filter(
        Word.id != correct_word.id,
        Word.cefr_level == correct_word.cefr_level
    ).limit(50).all()
    
    if len(all_words) >= count - 1:
        distractors = random.sample(all_words, count - 1)
        options.extend([word.persian_translation for word in distractors])
    else:
        # اگر کلمات کافی نبود، گزینه‌های عمومی اضافه کن
        general_options = ['سلام', 'خداحافظ', 'متشکرم', 'لطفاً']
        options.extend(general_options[:count - 1])
    
    random.shuffle(options)
    return options

def _get_random_word_except(exclude_id):
    """یک کلمه تصادفی غیر از کلمه داده‌شده"""
    words = Word.query.filter(Word.id != exclude_id).limit(50).all()
    return random.choice(words) if words else None

def _check_answer(word, exercise_type, user_answer):
    """بررسی صحت پاسخ برای انواع تمرین"""
    if exercise_type == 'multiple_choice':
        return user_answer == word.persian_translation
    
    elif exercise_type == 'typing':
        # تطبیق انعطاف‌پذیر برای تایپینگ
        correct = word.lemma.lower().strip()
        user = user_answer.lower().strip()
        
        # حذف فاصله‌های اضافی
        correct = ' '.join(correct.split())
        user = ' '.join(user.split())
        
        # تطبیق جزئی
        return correct == user
    
    elif exercise_type == 'article_choice':
        return user_answer == word.article
    
    elif exercise_type == 'sentence_completion':
        return user_answer.lower() == word.lemma.lower()
    
    elif exercise_type == 'listening':
        return user_answer.lower() == word.lemma.lower()
    
    elif exercise_type == 'recognition':
        return bool(user_answer)
    
    return False

def _get_correct_answer(word, exercise_type):
    """دریافت پاسخ صحیح برای نمایش به کاربر"""
    if exercise_type == 'multiple_choice':
        return word.persian_translation
    elif exercise_type == 'typing':
        return word.get_display_text()
    elif exercise_type == 'article_choice':
        return word.article
    elif exercise_type == 'sentence_completion':
        return word.lemma
    elif exercise_type == 'listening':
        return word.lemma
    else:
        return ''
    
def build_session_words(due_user_word_ids, new_user_word_ids):
    """ساخت جلسه با الگوریتم مناسب"""
    # اولویت: کلمات ضعیف اولویت اول
    weak_user_words = []
    learning_user_words = []
    other_due_user_words = []
    
    for uw_id in due_user_word_ids:
        user_word = UserWord.query.get(uw_id)
        if user_word:
            if user_word.memory_state == 'weak':
                weak_user_words.append(uw_id)
            elif user_word.memory_state == 'learning':
                learning_user_words.append(uw_id)
            else:
                other_due_user_words.append(uw_id)
    
    # ترکیب جلسه با نسبت‌های مناسب
    session_user_word_ids = []
    
    # 1. حداکثر ۵ کلمه ضعیف
    session_user_word_ids.extend(weak_user_words[:5])
    
    # 2. حداکثر ۳ کلمه در حال یادگیری
    session_user_word_ids.extend(learning_user_words[:3])
    
    # 3. حداکثر ۲ کلمه دیگر برای مرور
    session_user_word_ids.extend(other_due_user_words[:2])
    
    # 4. حداکثر ۴ کلمه جدید (اگر فضای خالی وجود دارد)
    remaining_slots = 10 - len(session_user_word_ids)
    if remaining_slots > 0 and new_user_word_ids:
        session_user_word_ids.extend(new_user_word_ids[:remaining_slots])
    
    # اگر هنوز کمتر از ۵ کلمه داریم، کلمات جدید بیشتری اضافه کن
    if len(session_user_word_ids) < 5 and new_user_word_ids:
        additional_needed = 5 - len(session_user_word_ids)
        already_added = len(session_user_word_ids) - (len(due_user_word_ids) + len(new_user_word_ids[:remaining_slots]))
        additional_new = new_user_word_ids[already_added:already_added + additional_needed]
        session_user_word_ids.extend(additional_new)
    
    # به هم ریختن ترتیب برای جلوگیری از خستگی
    import random
    random.shuffle(session_user_word_ids)
    
    return session_user_word_ids

def _generate_exercise_based_on_state(user_word):
    """تولید تمرین بر اساس وضعیت حافظه کاربر"""
    memory_state = user_word.memory_state
    consecutive_correct = user_word.consecutive_correct
    avg_response_time = user_word.avg_response_time
    
    # تعیین نوع تمرین بر اساس وضعیت حافظه
    if memory_state in ['new']:
        # برای کلمات جدید: تمرین‌های ساده تشخیصی
        exercise_types = ['recognition', 'multiple_choice_article', 'multiple_choice']
        weights = [0.4, 0.4, 0.2]  # اولویت با تشخیص و انتخاب مقاله
        
    elif memory_state in ['learning', 'weak']:
        # برای کلمات در حال یادگیری و ضعیف: تمرین‌های فعال
        if consecutive_correct >= 3:
            # اگر چند بار پشت هم صحیح جواب داده، تمرین سخت‌تر
            exercise_types = ['typing', 'sentence_completion', 'multiple_choice']
            weights = [0.5, 0.3, 0.2]
        else:
            # هنوز در حال یادگیری پایه
            exercise_types = ['multiple_choice', 'typing', 'article_choice']
            weights = [0.4, 0.4, 0.2]
            
    elif memory_state in ['strong', 'mastered']:
        # برای کلمات قوی: تمرین‌های چالشی
        if avg_response_time < 3:  # پاسخ‌های سریع
            exercise_types = ['typing', 'sentence_completion', 'reverse_translation']
            weights = [0.5, 0.3, 0.2]
        else:
            exercise_types = ['typing', 'multiple_choice', 'article_choice']
            weights = [0.4, 0.4, 0.2]
    
    else:
        # حالت پیش‌فرض
        exercise_types = ['multiple_choice', 'typing']
        weights = [0.5, 0.5]
    
    # انتخاب نوع تمرین با در نظر گرفتن وزن‌ها
    import random
    exercise_type = random.choices(exercise_types, weights=weights, k=1)[0]
    
    # تولید تمرین
    return _create_exercise_by_type(user_word, exercise_type)

def _create_exercise_by_type(user_word, exercise_type):
    """ایجاد تمرین بر اساس نوع"""
    word = user_word.word
    word_data = _prepare_word_data(user_word)
    
    if exercise_type == 'multiple_choice':
        options = _get_multiple_choice_options(word)
        return {
            'type': 'multiple_choice',
            'question': f"معنی '{word.get_display_text()}' چیست؟",
            'options': options,
            'correct_index': options.index(word.persian_translation),
            'difficulty': 'medium'
        }
    
    elif exercise_type == 'typing':
        return {
            'type': 'typing',
            'question': f"ترجمه آلمانی '{word.persian_translation}' را بنویسید:",
            'hint': word.part_of_speech,
            'difficulty': 'hard' if user_word.memory_state in ['strong', 'mastered'] else 'medium'
        }
    
    elif exercise_type == 'article_choice':
        articles = ['der', 'die', 'das']
        random.shuffle(articles)
        return {
            'type': 'article_choice',
            'question': f"مقاله صحیح برای '{word.lemma}' کدام است؟",
            'options': articles,
            'correct_index': articles.index(word.article) if word.article in articles else 0,
            'hint': f"جمع: {word.plural}" if word.plural else '',
            'difficulty': 'easy'
        }
    
    elif exercise_type == 'multiple_choice_article':
        # تمرین انتخاب معنی با نشان دادن مقاله
        options = _get_multiple_choice_options(word)
        return {
            'type': 'multiple_choice',
            'question': f"معنی '{word.article} {word.lemma}' چیست؟",
            'options': options,
            'correct_index': options.index(word.persian_translation),
            'difficulty': 'easy'
        }
    
    elif exercise_type == 'recognition':
        # آیا این ترجمه صحیح است؟
        is_correct = random.choice([True, False])
        if is_correct:
            return {
                'type': 'recognition',
                'question': f"آیا '{word.get_display_text()}' به معنی '{word.persian_translation}' است؟",
                'is_correct': True,
                'difficulty': 'easy'
            }
        else:
            # انتخاب کلمه تصادفی دیگر
            wrong_word = _get_random_word_except(word.id)
            return {
                'type': 'recognition',
                'question': f"آیا '{wrong_word.lemma if wrong_word else word.lemma}' به معنی '{word.persian_translation}' است؟",
                'is_correct': False,
                'difficulty': 'easy'
            }
    
    elif exercise_type == 'sentence_completion':
        if word.example_german:
            sentence = word.example_german
            blanked = sentence.replace(word.lemma, '__________')
            
            options = [word.lemma]
            distractors = _get_similar_words(word, 3)
            options.extend(distractors)
            random.shuffle(options)
            
            return {
                'type': 'sentence_completion',
                'question': 'جمله را کامل کنید:',
                'sentence': blanked,
                'options': options,
                'correct_index': options.index(word.lemma),
                'translation': word.example_persian if word.example_persian else '',
                'difficulty': 'hard'
            }
        else:
            # اگر مثالی ندارد، تمرین تایپینگ بده
            return _create_exercise_by_type(user_word, 'typing')
    
    elif exercise_type == 'reverse_translation':
        options = _get_multiple_choice_options(word, include_translation=False)
        options.append(word.lemma)
        random.shuffle(options)
        
        return {
            'type': 'reverse_translation',
            'question': f"کدام گزینه ترجمه آلمانی '{word.persian_translation}' است؟",
            'options': options,
            'correct_index': options.index(word.lemma),
            'difficulty': 'hard'
        }
    
    # حالت پیش‌فرض
    return _create_exercise_by_type(user_word, 'multiple_choice')

def calculate_streak_info(user_id, is_correct):
    """محاسبه اطلاعات استریک کاربر"""
    from datetime import datetime, timedelta
    
    user = User.query.get(user_id)
    if not user:
        return {'current': 0, 'best': 0}
    
    # بروزرسانی آخرین فعالیت
    user.last_active = datetime.utcnow()
    
    # محاسبه استریک
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    
    # بررسی آخرین فعالیت
    if user.last_active_date:
        last_active_date = user.last_active_date.date()
        
        if last_active_date == today:
            # امروز قبلاً فعالیت داشته، استریک تغییر نمی‌کند
            pass
        elif last_active_date == yesterday:
            # دیروز فعالیت داشته، استریک افزایش می‌یابد
            user.streak_days += 1
        else:
            # بیش از یک روز وقفه، استریک ریست می‌شود
            user.streak_days = 1
    else:
        # اولین فعالیت
        user.streak_days = 1
    
    # بروزرسانی بهترین استریک
    if user.streak_days > user.best_streak:
        user.best_streak = user.streak_days
    
    db.session.commit()
    
    return {
        'current': user.streak_days,
        'best': user.best_streak
    }

def _get_similar_words(word, count=3):
    """کلمات مشابه برای distractors"""
    # جستجوی کلمات هم‌خانواده در همان درس و سطح
    similar_words = Word.query.filter(
        Word.id != word.id,
        Word.cefr_level == word.cefr_level,
        Word.part_of_speech == word.part_of_speech
    ).limit(20).all()
    
    if len(similar_words) >= count:
        import random
        selected = random.sample(similar_words, count)
        return [w.lemma for w in selected]
    
    # اگر کافی نبود، کلمات هم‌سطح
    same_level = Word.query.filter(
        Word.id != word.id,
        Word.cefr_level == word.cefr_level
    ).limit(50).all()
    
    if same_level:
        import random
        selected = random.sample(same_level, min(count, len(same_level)))
        return [w.lemma for w in selected]
    
    # حالت پیش‌فرض
    return ['Haus', 'Buch', 'Stadt'][:count]

def log_user_state(user_id):
    """لاگ وضعیت کاربر برای دیباگ"""
    from models import UserWord, Word
    
    user = User.query.get(user_id)
    if not user:
        return "کاربر پیدا نشد"
    
    user_words = UserWord.query.filter_by(user_id=user_id).all()
    total_words = Word.query.filter_by(cefr_level=user.current_level or 'A1').count()
    
    log = f"""
📋 وضعیت کاربر {user.username} (ID: {user_id}):
├─ سطح فعلی: {user.current_level}
├─ کل کلمات موجود: {total_words}
├─ کلمات کاربر: {len(user_words)}
├─ توزیع وضعیت:
"""
    
    states = ['new', 'learning', 'weak', 'strong', 'mastered']
    for state in states:
        count = UserWord.query.filter_by(
            user_id=user_id,
            memory_state=state
        ).count()
        log += f"│  ├─ {state}: {count}\n"
    
    log += f"└─ کلمات موعد مرور: {len(SpacedRepetitionEngine.get_due_words(user_id))}"
    
    return log