from flask import Flask, render_template, jsonify, redirect, url_for, flash, request
from flask_login import LoginManager, login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func
import os
import random
import json

from models import db, User, UserWord, ScoreLog

from auth import auth as auth_blueprint

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///solingo.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

app.register_blueprint(auth_blueprint, url_prefix="/auth")

# ایجاد دیتابیس
with app.app_context():
    db.create_all()

# --- تنظیمات Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- توابع کمکی ---


def get_all_lesson_files():
    data_dir = "./data"
    if not os.path.exists(data_dir):
        return []
    return [f.replace(".json", "") for f in os.listdir(data_dir) if f.endswith(".json")]


def load_lesson_data(lesson_id):
    file_path = f"./data/{lesson_id}.json"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# --- مسیرها (Routes) ---


@app.route("/")
def index():
    return render_template("index.html", current_page="home")


@app.route("/lessons")
@login_required
def lessons():
    lesson_files = sorted(get_all_lesson_files())
    lessons_data = []
    for file_id in lesson_files:
        words = load_lesson_data(file_id)
        if words:
            lessons_data.append(
                {
                    "id": file_id,
                    "level": words[0]["word"].get("level", "A1"),
                    "lesson_number": words[0]["word"].get("Lesson", file_id),
                }
            )
    return render_template("lessons.html", lessons=lessons_data, current_page="lessons")


@app.route("/level/<lesson_id>")
@login_required
def level(lesson_id):
    """نمایش لیست کلمات یک درس خاص و سطح یادگیری فعلی کاربر در آن‌ها"""
    words = load_lesson_data(lesson_id)
    if not words:
        flash("درس مورد نظر یافت نشد.", 'error')
        return redirect(url_for("lessons"))

    # استخراج لِمای کلمات این درس
    lemmas = [w["word"]["lemma"] for w in words]

    # گرفتن پیشرفت کاربر برای این کلمات از دیتابیس جدید
    progress_rows = UserWord.query.filter(
        UserWord.user_id == current_user.id, UserWord.lemma.in_(lemmas)
    ).all()

    # تبدیل به دیکشنری برای دسترسی سریع: {lemma: score}
    scores = {p.lemma: p.total_score for p in progress_rows}

    # تزریق امتیاز هر کلمه به داده‌های ارسالی به قالب
    for word in words:
        word["learning_level"] = scores.get(word["word"]["lemma"], 0)

    return render_template("level.html", words=words, lesson_id=lesson_id)


@app.route("/learn/<lesson_id>")
@login_required
def learn(lesson_id):
    """صفحه تمرین تعاملی (فلش‌کارت/تست)"""
    return render_template("learn.html", lesson_id=lesson_id, current_page="learn")


@app.route("/api/get_session/<lesson_id>")
@login_required
def get_session(lesson_id):
    """API برای ارسال کلمات درس به صفحه تمرین با احتساب پیشرفت کاربر"""
    lesson_words = load_lesson_data(lesson_id)
    if not lesson_words:
        return jsonify({"status": "error", "message": "No words found"}), 404

    # گرفتن امتیازها از دیتابیس SQLAlchemy
    lemmas = [w["word"]["lemma"] for w in lesson_words]
    progress_rows = UserWord.query.filter(
        UserWord.user_id == current_user.id, UserWord.lemma.in_(lemmas)
    ).all()

    scores = {p.lemma: p.total_score for p in progress_rows}

    # تزریق سطح یادگیری به هر کلمه
    for word in lesson_words:
        word["learning_level"] = scores.get(word["word"]["lemma"], 0)

    # شافل کردن کلمات برای تنوع در یادگیری
    random.shuffle(lesson_words)
    return jsonify(lesson_words)


@app.route("/profile")
@login_required
def profile():
    learned_count = UserWord.query.filter(UserWord.user_id == current_user.id).count()
    mastered_count = UserWord.query.filter(
        UserWord.user_id == current_user.id,
        (
            UserWord.score_listening
            + UserWord.score_writing
            + UserWord.score_reading
            + UserWord.score_article
        )
        >= 6,
    ).count()

    weak_words = (
        UserWord.query.filter(
            UserWord.user_id == current_user.id, UserWord.wrong_count > 0
        )
        .order_by(UserWord.wrong_count.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "profile.html",
        user=current_user,
        learned_count=learned_count,
        mastered_count=mastered_count,
        weak_words=weak_words,
        current_page="profile",
    )


@app.route("/api/update_score", methods=["POST"])
@login_required
def update_score():
    data = request.json
    lemma = data["lemma"]
    q_type = data.get("question_type")  # 'listening', 'writing', 'reading', 'article'
    is_correct = data.get("correct", True)

    word_progress = UserWord.query.filter_by(
        user_id=current_user.id, lemma=lemma
    ).first()

    if not word_progress:
        word_progress = UserWord(user_id=current_user.id, lemma=lemma)
        db.session.add(word_progress)

    if is_correct:
        if q_type == "listening-typing":
            word_progress.score_listening += 1
        elif q_type == "typing":
            word_progress.score_writing += 1
        elif q_type == "mcq":
            word_progress.score_reading += 1
        elif q_type == "article":
            word_progress.score_article += 1
    else:
        word_progress.wrong_count += 1
        # اختیاری: در صورت اشتباه، امتیاز آن بخش کمی کم شود
        if q_type == "typing":
            word_progress.score_writing = max(0, word_progress.score_writing - 1)

    word_progress.last_practiced = datetime.utcnow()
    current_user.update_streak()
    db.session.commit()
    return jsonify({"status": "success", "new_total_score": word_progress.total_score})


@app.route("/api/get_lesson_stats/<lesson_id>")
@login_required
def get_lesson_stats(lesson_id):
    words = load_lesson_data(lesson_id)
    lemmas = [w["word"]["lemma"] for w in words]

    progress_rows = UserWord.query.filter(
        UserWord.user_id == current_user.id, UserWord.lemma.in_(lemmas)
    ).all()

    scores = {p.lemma: p.total_score for p in progress_rows}
    words_started = len([s for s in scores.values() if s > 0])
    total_score = sum(scores.values())

    learning_percentage = (
        round((total_score / (len(words) * 6)) * 100, 1) if words else 0
    )

    return jsonify(
        {
            "status": "success",
            "total_words": len(words),
            "words_started": words_started,
            "learning_percentage": learning_percentage,
        }
    )


@app.route('/api/get_overall_stats')
@login_required
def get_overall_stats():
    # ۱. پیدا کردن تمام فایل‌های JSON و شمردن کل کلمات موجود
    total_words_count = 0
    lesson_files = get_all_lesson_files()
    for lesson_id in lesson_files:
        data = load_lesson_data(lesson_id)
        total_words_count += len(data)

    # ۲. محاسبه مجموع امتیازات برای استفاده در فیلترها
    # این فرمول معادل همان total_score در مدل است اما برای کوئری SQL
    total_score_formula = (
        UserWord.score_listening + 
        UserWord.score_writing + 
        UserWord.score_reading + 
        UserWord.score_article
    )

    # تعداد کل کلماتی که کاربر حداقل یک بار تمرین کرده
    learned = UserWord.query.filter(UserWord.user_id == current_user.id).count()

    # کلمات تثبیت شده (مجموع امتیازات ۶ یا بیشتر)
    long_term = UserWord.query.filter(
        UserWord.user_id == current_user.id,
        total_score_formula >= 6
    ).count()

    # کلماتی که در حال یادگیری هستند (امتیاز بین ۱ تا ۵)
    review = UserWord.query.filter(
        UserWord.user_id == current_user.id,
        total_score_formula > 0,
        total_score_formula < 6
    ).count()

    return jsonify({
        "status": "success",
        "total_words": total_words_count,
        "learned_words": learned,
        "long_term_words": long_term,
        "review_words": review,
        "ignored_words": 0,
        "streak": current_user.streak_days
    })


@app.route("/api/finish_lesson", methods=["POST"])
@login_required
def finish_lesson():
    try:
        current_user.update_streak()

        # محاسبه امتیاز (آخر هفته ۲ برابر)
        base_points = 100
        is_weekend = datetime.utcnow().weekday() >= 5  # شنبه و یکشنبه (میلادی)

        final_points = base_points * 2 if is_weekend else base_points

        # اضافه کردن به XP کل و لاگ
        current_user.xp += final_points
        new_score = ScoreLog(user_id=current_user.id, points=final_points)

        db.session.add(new_score)
        db.session.commit()

        return jsonify(
            {"status": "success", "xp_gained": final_points, "is_double": is_weekend}
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- مسیر کلمات ضعیف ---
@app.route("/weak-words-practice")
@login_required
def weak_words_practice():
    # ۱. پیدا کردن ۱۰ کلمه‌ای که بیشترین اشتباه را داشته‌اند
    weak_records = (
        UserWord.query.filter(
            UserWord.user_id == current_user.id, UserWord.wrong_count > 0
        )
        .order_by(UserWord.wrong_count.desc())
        .limit(10)
        .all()
    )

    if not weak_records:
        flash("هنوز کلمه ضعیفی ندارید! بیشتر تمرین کنید.", 'info')
        return redirect(url_for("index"))

    # ۲. استخراج اطلاعات کامل این کلمات از فایل‌های JSON
    all_lessons = get_all_lesson_files()
    weak_words_data = []
    lemmas_to_find = [r.lemma for r in weak_records]

    for lesson_id in all_lessons:
        lesson_data = load_lesson_data(lesson_id)
        for word_entry in lesson_data:
            if word_entry["word"]["lemma"] in lemmas_to_find:
                # اضافه کردن اطلاعات پیشرفت دیتابیس به دیتای JSON
                record = next(
                    r for r in weak_records if r.lemma == word_entry["word"]["lemma"]
                )
                word_entry["wrong_count"] = record.wrong_count
                word_entry["score_stats"] = {
                    "listening": record.score_listening,
                    "writing": record.score_writing,
                    "reading": record.score_reading,
                    "article": record.score_article,
                }
                weak_words_data.append(word_entry)
                lemmas_to_find.remove(word_entry["word"]["lemma"])
        if not lemmas_to_find:
            break

    return render_template(
        "learn.html",
        current_page="weak-words-practice",
        lesson_id="تمرین کلمات دشوار",
        special_data=json.dumps(weak_words_data),
    )


@app.route("/leaderboard")
@login_required
def leaderboard():
    # پیدا کردن شروع هفته (مثلاً دوشنبه یا شنبه - اینجا ۷ روز اخیر)
    start_of_week = datetime.utcnow() - timedelta(days=7)

    # کوئری برای گرفتن کاربران هم‌گروه و جمع امتیازات هفته اخیرشان
    group_users = (
        db.session.query(User, func.sum(ScoreLog.points).label("weekly_xp"))
        .join(ScoreLog, isouter=True)
        .filter(
            User.league == current_user.league, User.group_id == current_user.group_id
        )
        .filter((ScoreLog.created_at >= start_of_week) | (ScoreLog.id == None))
        .group_by(User.id)
        .order_by(func.sum(ScoreLog.points).desc())
        .all()
    )

    return render_template(
        "leaderboard.html",
        group_users=group_users,
        current_page="leaderboard",
        page_title="لیگ",
    )


@app.route("/shop")
@login_required
def shop():
    return render_template("shop.html", current_page="shop", page_title="فروشگاه")


@app.route("/api/buy_freeze", methods=["POST"])
@login_required
def buy_freeze():
    price = 200
    if current_user.gems >= price:
        current_user.gems -= price
        current_user.streak_freeze_count += 1
        db.session.commit()
        return jsonify(
            {
                "status": "success",
                "message": "یخ‌ساز با موفقیت خریداری شد",
                "gems": current_user.gems,
            }
        )
    return jsonify({"status": "error", "message": "الماس کافی ندارید!"}), 400


def assign_to_group(user):
    # پیدا کردن آخرین گروهی که در لیگ 10 تشکیل شده و ظرفیت دارد
    latest_group = (
        db.session.query(User.group_id)
        .filter_by(league=10)
        .group_by(User.group_id)
        .having(func.count(User.id) < 20)
        .first()
    )

    if latest_group:
        user.group_id = latest_group[0]
    else:
        # اگر همه گروه‌ها پر بودند، گروه جدید بساز
        max_group = db.session.query(func.max(User.group_id)).scalar() or 0
        user.group_id = max_group + 1


def process_league_updates():
    # گرفتن تمام گروه‌های موجود
    groups = db.session.query(User.league, User.group_id).distinct().all()
    # پیدا کردن شروع هفته (مثلاً دوشنبه یا شنبه - اینجا ۷ روز اخیر)
    start_of_week = datetime.utcnow() - timedelta(days=7)

    for league_num, group_id in groups:
        # گرفتن کاربران این گروه به ترتیب امتیاز هفته
        # نکته: باید امتیاز هفته را از جدول ScoreLog که قبلاً ساختیم جمع بزنیم
        users_in_group = (
            db.session.query(User)
            .filter_by(league=league_num, group_id=group_id)
            .join(ScoreLog)
            .filter(ScoreLog.created_at >= start_of_week)
            .group_by(User.id)
            .order_by(func.sum(ScoreLog.points).desc())
            .all()
        )

        for index, user in enumerate(users_in_group):
            rank = index + 1

            if rank <= 4:  # صعود
                if user.league > 1:
                    user.league -= 1
            elif rank >= 12:  # سقوط
                if user.league < 10:
                    user.league += 1

            # در هر صورت بعد از جابجایی لیگ، باید در گروه جدید در لیگ جدید ست شوند
            # این بخش را می‌توان با یک تابع بازتوزیع (Re-shuffling) انجام داد

    def reward_and_promote(user, rank):
        rewards = {1: 100, 2: 50, 3: 25, 4: 10}

        if rank in rewards:
            user.gems += rewards[rank]
            # منطق صعود به لیگ بالاتر
            if user.league > 1:
                user.league -= 1


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Solingo Language Learning Platform")
    print("=" * 60)
    print(f"🌐 Server URL: http://127.0.0.1:5000")
    print("=" * 60)
    print("📱 Press Ctrl+C to stop the server")
    print("=" * 60)

    app.run(debug=True, host="0.0.0.0", port=5000)
