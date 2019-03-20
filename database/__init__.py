import inspect
import os
import copy
import sqlite3
import uuid

class Database:
    def __init__(self):
        db = sqlite3.connect('benchmark.db')

        cur_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        with open(os.path.join(cur_dir, 'smart_streaming_ddl_sqlite.sql')) as f:
            cursor = db.cursor()
            cursor.executescript(f.read())
            db.commit()

        cursor = db.cursor()
        cursor.execute('PRAGMA foreign_keys = ON')
        db.commit()
        self.db = db
        self.id_experiment = None

    def new_experiment(self, parameters):
        '''Create a new experiment, will be used for other tables'''
        cursor = self.db.cursor()
        fields = copy.deepcopy(parameters)
        fields['uuid'] = str(uuid.uuid4())
        fields['imported'] = 0
        field_list = ', '.join(fields.keys())
        placeholders = ','.join(['?' for _ in fields.keys()])
        sql = ('insert into experiments(%s) values(%s)' %
               (field_list, placeholders))
        cursor.execute(sql, tuple(fields.values()))
        self.id_experiment = cursor.lastrowid

    def save_table(self, table_name, field_names, row_generator):
        '''Save a table.
        field_names is the array of names,
        row_generator is a generator function go get rows from'''
        if self.id_experiment is None:
            raise Exception('Trying to insert table %s without experiment created' % table_name)
        cursor = self.db.cursor()
        field_list = ', '.join(field_names)
        placeholders = ','.join(['?' for _ in field_names])
        sql = ('insert into %s(id_experiment, %s) values(%d,%s)' %
               (table_name, field_list, self.id_experiment, placeholders))
        cursor.executemany(sql, row_generator)

    def commit(self):
        '''Save when everything is fine'''
        self.db.commit()
