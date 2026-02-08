"""
ماژول تولید تمرین‌های مختلف
"""
import random
from typing import List, Dict, Any
from models import Word, UserWord

class ExerciseGenerator:
    """تولیدکننده تمرین‌های مختلف"""
    
    @staticmethod
    def multiple_choice(word: Word, count: int = 4) -> Dict[str, Any]:
        """تمرین چندگزینه‌ای"""
        options = ExerciseGenerator._get_distractors(word, count - 1)
        options.append(word.persian_translation)
        random.shuffle(options)
        
        return {
            'type': 'multiple_choice',
            'question': f"معنی '{word.get_display_text()}' چیست؟",
            'options': options,
            'correct_answer': word.persian_translation,
            'hint': word.part_of_speech
        }
    
    @staticmethod
    def typing(word: Word) -> Dict[str, Any]:
        """تمرین تایپینگ"""
        return {
            'type': 'typing',
            'question': f"ترجمه آلمانی '{word.persian_translation}' را بنویسید:",
            'correct_answer': word.lemma,
            'hint': word.article if hasattr(word, 'article') else '',
            'accept_variations': True
        }
    
    @staticmethod
    def article_practice(word: Word) -> Dict[str, Any]:
        """تمرین انتخاب مقاله"""
        if not hasattr(word, 'article') or not word.article:
            return ExerciseGenerator.multiple_choice(word)
        
        articles = ['der', 'die', 'das']
        options = articles.copy()
        random.shuffle(options)
        
        return {
            'type': 'article_choice',
            'question': f"مقاله صحیح برای '{word.lemma}' کدام است؟",
            'options': options,
            'correct_answer': word.article,
            'hint': f"جمع: {word.plural}" if hasattr(word, 'plural') and word.plural else ''
        }
    
    @staticmethod
    def sentence_completion(word: Word) -> Dict[str, Any]:
        """تکمیل جمله"""
        if not word.example_german:
            return ExerciseGenerator.multiple_choice(word)
        
        sentence = word.example_german
        blanked_sentence = sentence.replace(word.lemma, '__________')
        
        options = ExerciseGenerator._get_similar_words(word, 3)
        options.append(word.lemma)
        random.shuffle(options)
        
        return {
            'type': 'sentence_completion',
            'question': f"جمله را با کلمه صحیح کامل کنید:",
            'sentence': blanked_sentence,
            'options': options,
            'correct_answer': word.lemma,
            'translation': word.example_persian if word.example_persian else ''
        }
    
    @staticmethod
    def listening_practice(word: Word) -> Dict[str, Any]:
        """تمرین شنیداری (شبه)"""
        # در نسخه فعلی، فقط متن نمایش داده می‌شود
        # در آینده با فایل‌های صوتی واقعی جایگزین می‌شود
        return {
            'type': 'listening',
            'question': f"کلمه را با توجه به تلفظ آن تشخیص دهید:",
            'pronunciation': word.ipa if word.ipa else f"/{word.lemma}/",
            'options': ExerciseGenerator._get_distractors(word, 3, include_translation=False),
            'correct_answer': word.lemma,
            'hint': 'تلفظ: ' + (word.ipa if word.ipa else '')
        }
    
    @staticmethod
    def _get_distractors(correct_word: Word, count: int, include_translation: bool = True) -> List[str]:
        """گزینه‌های انحرافی"""
        from models import db
        
        # جستجوی کلمات هم‌خانواده
        same_pos = Word.query.filter(
            Word.part_of_speech == correct_word.part_of_speech,
            Word.id != correct_word.id,
            Word.cefr_level == correct_word.cefr_level
        ).limit(20).all()
        
        distractors = []
        if same_pos:
            sample = random.sample(same_pos, min(count, len(same_pos)))
            if include_translation:
                distractors = [w.persian_translation for w in sample]
            else:
                distractors = [w.lemma for w in sample]
        
        # اگر کافی نبود، کلمات تصادفی اضافه کن
        if len(distractors) < count:
            all_words = Word.query.filter(Word.id != correct_word.id).limit(50).all()
            extra = random.sample(all_words, min(count - len(distractors), len(all_words)))
            if include_translation:
                distractors.extend([w.persian_translation for w in extra])
            else:
                distractors.extend([w.lemma for w in extra])
        
        return distractors[:count]
    
    @staticmethod
    def _get_similar_words(word: Word, count: int) -> List[str]:
        """کلمات مشابه"""
        # در نسخه اولیه، کلمات هم‌سطح
        similar = Word.query.filter(
            Word.cefr_level == word.cefr_level,
            Word.id != word.id,
            Word.part_of_speech == word.part_of_speech
        ).limit(count * 2).all()
        
        if len(similar) >= count:
            selected = random.sample(similar, count)
            return [w.lemma for w in selected]
        
        # اگر کافی نبود
        all_words = Word.query.filter(Word.id != word.id).limit(50).all()
        return [w.lemma for w in random.sample(all_words, min(count, len(all_words)))]
    
    @staticmethod
    def generate_for_word(word: Word, user_word: UserWord = None) -> Dict[str, Any]:
        """تولید تمرین مناسب برای کلمه"""
        if not user_word:
            # برای کلمات جدید، تمرین‌های ساده
            exercises = ['multiple_choice', 'typing']
        else:
            # بر اساس وضعیت حافظه، تمرین‌های مختلف
            state = user_word.memory_state
            if state in ['new', 'learning']:
                exercises = ['multiple_choice', 'typing', 'article_practice']
            elif state == 'weak':
                exercises = ['typing', 'sentence_completion', 'multiple_choice']
            else:  # strong, mastered
                exercises = ['sentence_completion', 'listening_practice', 'typing']
        
        # انتخاب تصادفی نوع تمرین
        exercise_type = random.choice(exercises)
        
        # تولید تمرین
        if exercise_type == 'multiple_choice':
            return ExerciseGenerator.multiple_choice(word)
        elif exercise_type == 'typing':
            return ExerciseGenerator.typing(word)
        elif exercise_type == 'article_practice':
            return ExerciseGenerator.article_practice(word)
        elif exercise_type == 'sentence_completion':
            return ExerciseGenerator.sentence_completion(word)
        elif exercise_type == 'listening_practice':
            return ExerciseGenerator.listening_practice(word)
        else:
            return ExerciseGenerator.multiple_choice(word)