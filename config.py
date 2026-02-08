import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-123-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///instance/database.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_PERMANENT = False
    SESSION_TYPE = 'filesystem'