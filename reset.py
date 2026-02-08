# reset_db.py
import os
import shutil
import sys

def reset_database():
    """ریست کامل دیتابیس"""
    
    print("=" * 60)
    print("🔄 Complete reset of the Solingo project")
    print("=" * 60)
    
    # ۱. حذف دیتابیس
    if os.path.exists('instance'):
        try:
            shutil.rmtree('instance')
            print("✅ The instance folder was deleted.")
        except Exception as e:
            print(f"⚠️  Error deleting instance: {e}")
    
    # ۲. حذف cacheهای پایتون
    print("\n🗑️  Delete cache files...")
    cache_found = False
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            cache_path = os.path.join(root, '__pycache__')
            try:
                shutil.rmtree(cache_path)
                print(f"  Delete: {cache_path}")
                cache_found = True
            except:
                pass
    
    if not cache_found:
        print("  No cache files found.")
    
    # ۳. import و ایجاد دیتابیس
    print("\n🗃️  Create a new database...")
    try:
        # اضافه کردن مسیر پروژه به sys.path
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        from app import app
        from models import db
        
        with app.app_context():
            # حذف جداول اگر وجود دارند
            try:
                db.drop_all()
                print("✅ Old tables have been deleted.")
            except:
                print("⚠️ Error deleting old tables")
                pass
            
            # ایجاد جداول جدید
            db.create_all()
            print("✅ New tables were created.")
            
            # اجرای seed data
            # print("\n🌱 Adding initial data...")
            # try:
            #     from database.seed_data import seed_initial_data
            #     if seed_initial_data():
            #         print("✅ Initial data added.")
            #     else:
            #         print("⚠️  Error adding initial data")
            # except Exception as e:
            #     print(f"❌ Error in seed data: {e}")
            
            print("\n" + "=" * 60)
            print("🎉 The hard reset was successful!")
            print("📁 Database structure:")
            print("-" * 40)
            
            # نمایش تعداد جداول
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            for table in tables:
                print(f"  📄 {table}")
            
            print("-" * 40)
            print(f"  Number of tables: {len(tables)}")
            print("=" * 60)
                
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    # تایید از کاربر
    confirm = input("\n⚠️  Are you sure you want to completely reset the database? (y/n): ")
    
    if confirm.lower() == 'y':
        reset_database()
        print("\n🚀 Now you can run the program:")
        print("  python app.py")
    else:
        print("❌ The operation was canceled.")