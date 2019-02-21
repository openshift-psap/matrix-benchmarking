import inspect
import os
import sqlite3

class Database:
    def __init__(self, cfg={}):
        db = sqlite3.connect('benchmark.db')

        cur_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        with open(os.path.join(cur_dir, 'smart_streaming_ddl_sqlite.sql')) as f:
            cursor = db.cursor()
            cursor.executescript(f.read())
            db.commit()

        cursor = db.cursor()
        cursor.execute('PRAGMA foreign_keys = ON')
        db.commit()
