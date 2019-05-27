#!/usr/bin/python3
import sys
import copy
import psycopg2
import psycopg2.extras
import sqlite3
import utils.yaml

cfg = utils.yaml.load_multiple("benchmark.yaml", "secure.yaml")
cfg = utils.yaml.subyaml(cfg, 'databases/remote')

# TODO support other databases?
# One issue is the placeholders different (postgresql uses '%s' while
# others mainly uses '?')
# Also getting last inserted id can be different
assert cfg['type'] == 'postgresql'

db1 = None
c1 = None
db2 = None
c2 = None

def copy_table(name, new_id):
    # get table schema (to exclude 'id_experiment' field)
    sql = 'select * from %s where 0=1' % name
    c1.execute(sql)
    names = [desc[0] for desc in c1.description if desc[0] != 'id_experiment']
    fields = ','.join(names)

    # extract data
    sql = 'select %s from %s' % (fields, name)
    c1.execute(sql)
    def all_rows():
        for row in c1.fetchall():
            yield row

    # import into new database
    placeholders = ','.join(['%s'] * len(names))
    sql = ('insert into %s(id_experiment,%s) values %%s' %
           (name, fields))
    template = '(%s,%s)' % (new_id, placeholders)
    psycopg2.extras.execute_values(c2, sql, all_rows(), template)

try:
    # open local database
    # TODO why not use configuration and class?
    db1 = sqlite3.connect('benchmark.db')
    c1 = db1.cursor()
    c1.execute('PRAGMA foreign_keys = ON')
    db1.commit()

    # TODO debug
#    sql = 'update experiments set imported = FALSE'
#    c1.execute(sql)
#    db1.commit()

    # get rows to import, read them all should not be many
    sql = 'select * from experiments where imported = FALSE'
    c1.execute(sql)
    names = [description[0] for description in c1.description]
    experiments = c1.fetchall()

    # if there are no rows to import exit, here we don't even attempt
    # the connection to the destination database
    if len(experiments) == 0:
        print('No rows to import.')
        sys.exit(0)

    # connect to destination
    database = cfg.get('database', cfg['user'])
    db2 = psycopg2.connect(user = cfg['user'],
                           password = cfg['password'],
                           host = cfg['host'],
                           port = cfg.get('port', '5432'),
                           database = database)
    c2 = db2.cursor()

    # import experiment by experiment
    for row in experiments:
        row = dict(zip(names, row))
        print('Importing experiment with ID %s' % row['id'])

        # check if row was already imported (like dropped connection)
        sql = 'select id from experiments where uuid=%s'
        c2.execute(sql, (row['uuid'],))
        if not c2.fetchone():
            # insert row, get id
            row_insert = copy.deepcopy(row)
            del row_insert['id']
            del row_insert['imported']
            # TODO portability, placeholder and 'returning id'
            placeholders = ','.join(['%s'] * len(row_insert))
            sql = ('insert into experiments(%s) values(%s) returning id' % (
                   ','.join(row_insert.keys()), placeholders))
            c2.execute(sql, tuple(row_insert.values()))
            new_id = c2.fetchone()[0]
            print('ID on new table will be %s' % new_id)

            # copy table by table replacing id_experiment from source
            # with new_id
            for table in ['attachments', 'frames', 'guest_stats', 'host_stats', 'client_stats']:
                copy_table(table, new_id)

            # commit remote transaction now that we inserted
            # everything for the current importing experiment
            db2.commit()
        else:
            print('Local experiment %s was already inserted!' % row['id'])

        # update local database
        sql = 'update experiments set imported = TRUE where id=?'
        c1.execute(sql, (row['id'],))
        # commit local update
        db1.commit()

except psycopg2.Error as error :
    print ("Error while connecting to PostgreSQL", error)
finally:
    #closing database connection.
    if c2:
        c2.close()
    if db2:
        db2.close()
        print("PostgreSQL connection is closed")
