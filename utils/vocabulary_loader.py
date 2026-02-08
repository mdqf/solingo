import json
from pathlib import Path
from models import db, Word

class VocabularyLoader:
    """بارگذار خودکار کلمات از فایل‌های JSON"""
    
    def __init__(self, data_folder='data'):
        self.project_root = Path(__file__).parent.parent
        self.data_path = self.project_root / data_folder
    
    def load_all_files(self):
        """بارگذاری تمام فایل‌های JSON"""
        json_files = list(self.data_path.glob('*.json'))
        
        if not json_files:
            return {'success': False, 'message': 'هیچ فایل JSON یافت نشد'}
        
        results = []
        total_added = 0
        
        for json_file in json_files:
            result = self.load_file(json_file)
            results.append(result)
            total_added += result.get('added', 0)
        
        return {
            'success': True,
            'total_added': total_added,
            'files_processed': len(json_files),
            'details': results
        }
    
    def load_file(self, json_file):
        """بارگذاری یک فایل JSON خاص"""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                words_data = json.load(f)
            
            added_count = 0
            skipped_count = 0
            
            for word_data in words_data:
                # بررسی وجود کلمه
                existing = Word.query.filter_by(lemma=word_data['word']['lemma']).first()
                if not existing:
                    word = Word(
                        lemma=word_data['word']['lemma'],
                        article=word_data['word'].get('article', ''),
                        plural=word_data['word'].get('plural', ''),
                        part_of_speech=word_data['word'].get('part_of_speech', ''),
                        cefr_level=word_data['word'].get('level', 'A1'),
                        lesson=word_data['word'].get('Lesson', ''),
                        german_definition=word_data['meaning'].get('german_definition', ''),
                        persian_translation=word_data['meaning'].get('persian_translation', ''),
                        example_german=word_data['example'].get('german_sentence', '') if 'example' in word_data else '',
                        example_persian=word_data['example'].get('persian_translation', '') if 'example' in word_data else '',
                        ipa=word_data.get('audio', {}).get('ipa', ''),
                        frequency_rank=1000
                    )
                    db.session.add(word)
                    added_count += 1
                else:
                    skipped_count += 1
            
            db.session.commit()
            
            return {
                'file': json_file.name,
                'added': added_count,
                'skipped': skipped_count,
                'success': True
            }
            
        except Exception as e:
            return {
                'file': json_file.name,
                'error': str(e),
                'success': False
            }
    
    def get_stats(self):
        """دریافت آمار کلمات"""
        total_words = Word.query.count()
        
        # آمار بر اساس درس
        lessons = db.session.query(Word.lesson, db.func.count(Word.id)).group_by(Word.lesson).all()
        lessons_dict = {lesson: count for lesson, count in lessons if lesson}
        
        # آمار بر اساس سطح
        levels = db.session.query(Word.cefr_level, db.func.count(Word.id)).group_by(Word.cefr_level).all()
        levels_dict = {level: count for level, count in levels}
        
        # آمار بر اساس نوع کلمه
        pos = db.session.query(Word.part_of_speech, db.func.count(Word.id)).group_by(Word.part_of_speech).all()
        pos_dict = {pos_type: count for pos_type, count in pos}
        
        return {
            'total_words': total_words,
            'lessons': lessons_dict,
            'levels': levels_dict,
            'parts_of_speech': pos_dict
        }
    
    def clear_database(self):
        """پاک کردن تمام کلمات (برای تست)"""
        try:
            deleted_count = Word.query.delete()
            db.session.commit()
            return {'success': True, 'deleted': deleted_count}
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}