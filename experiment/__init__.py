import os
import yaml
from collections import defaultdict
from database import Database
import machine

class Field:
    def __init__(self, name, table_name, field_name):
        self.name = name
        self.table_name = table_name
        self.field_name = field_name
        # self.check = 'Integer ??'

all_fields = {}
def add_field(name, table_name, field_name):
    if name in all_fields:
        raise Exception("Multiple fields with same name %s" % name)
    field = Field(name, table_name, field_name)
    all_fields[name] = field

def get_all_tables():
    return set([f.table_name for f in all_fields.values() if f.table_name])

def get_table_fields(table_name):
    fields = set([f.field_name for f in all_fields.values()
                  if f.table_name is None or f.table_name == table_name])
    fields.add("id")

    return list(fields)

# special field
add_field('time', None, None)

add_field('guest.gpu_memory', 'guest_stats', 'gpu_memory')
add_field('guest.gpu', 'guest_stats', 'gpu_usage')
add_field('guest.encode', 'guest_stats', 'encode_usage')
add_field('guest.decode', 'guest_stats', 'decode_usage')

add_field('host.cpu', 'host_stats', 'cpu_usage')

add_field('client.gpu', 'client_stats', 'gpu_usage')
add_field('client.app_gpu', 'client_stats', 'app_gpu_usage')
add_field('client.cpu', 'client_stats', 'cpu_usage')
add_field('client.app_cpu', 'client_stats', 'app_cpu_usage')

add_field('guest.time', 'frames', 'agent_time')
add_field('guest.frame_size', 'frames', 'size')
add_field('guest.capture_duration', 'frames', 'capture_duration')
add_field('guest.encode_duration', 'frames', 'encode_duration')
add_field('guest.send_duration', 'frames', 'send_duration')
add_field('host.frame_size', 'frames', 'size')
add_field('host.mm_time', 'frames', 'mm_time')
add_field('client.time', 'frames', 'client_time')
add_field('client.frame_size', 'frames', 'size')
add_field('client.mm_time', 'frames', 'mm_time')
add_field('client.decode_duration', 'frames', 'decode_duration')
add_field('client.queue', 'frames', 'queue_size')

class Table:
    def __init__(self, field_names):
        self.fields = []
        self.rows = []
        table = None
        for field in field_names:
            if not field in all_fields:
                raise Exception("Field %s not recognized" % field)
            field = all_fields[field]
            # check all fields are from the same table (or special)
            if table is not None and field.table_name is not None:
                if table != field.table_name:
                    raise Exception("fields from multiple tables not accepted %s" % field_names)
            if table is None:
                table = field.table_name
            self.fields.append(field)
        if table is None:
            raise Exception('Created table does not have fields to be saved')
        self.table_name = table

    def add(self, *args):
        '''Add a row to the table'''
        # here we should check the fields
        # (numeric, present or not)
        assert len(args) == len(self.fields)
        self.rows.append(tuple(args))

def collapse_tables_time(tables):
    time = all_fields['time']
    fields = [time]
    for table in tables:
        assert time in table.fields
        for field in table.fields:
            if field == time:
                continue
            assert not field in fields, "Field %s fields %s" % (field, fields)
            fields.append(field)
    new_table = Table([f.name for f in fields])
    rows = {}
    empty = []
    for table in tables:
        idx = table.fields.index(time)
        for row in table.rows:
            row = list(row)
            t = row.pop(idx)
            if t in rows:
                rows[t] += row
            else:
                rows[t] = empty + row
        empty += [None] * (len(table.fields)-1)
    for t in sorted(rows):
        row = [t] + rows[t] + empty
        row = row[:len(empty)+1]
        new_table.add(*row)
    new_table.fields[0] = Field('time', new_table.table_name, 'time')
    return new_table

def frames_table_part(table):
    '''Get which part of frames virtual table (guest/host/client) is'''
    assert table.table_name == 'frames', "frames_table_part called with wrong table!"
    parts = set()
    for f in table.fields:
        if f.name != 'time':
            parts.add(f.name.split('.', 1)[0])
    assert len(parts) == 1, "Too complex table"
    return parts.pop()

def fix_table_time(table):
    if not all_fields['time'] in table.fields:
        return
    idx = table.fields.index(all_fields['time'])

    assert table.table_name != 'frames', "Frame table should not have time field"
    # TODO hacky
    table.fields[idx] = Field('time', table.table_name, 'time')

class NotEnoughHostFramesExperimentException(Exception): pass
class NoGuestFramesInHostFramesExperimentException(Exception): pass

def collapse_frames_guest_host(guest_table, host_table):
    '''Collapse guest and host frame information using frame_size'''
    size = len(guest_table.rows)

    # how many line to match (90% but don't exclude more than 10
    # frames)
    match_size = size - min(10, size // 10)

    if len(host_table.rows) < match_size:
        raise NotEnoughHostFramesExperimentException()

    idx_frame_guest = guest_table.fields.index(all_fields['guest.frame_size'])
    idx_frame_host = host_table.fields.index(all_fields['host.frame_size'])

    def match(start):
        for i in range(0, match_size):
            if (guest_table.rows[i][idx_frame_guest] !=
                    host_table.rows[i+start][idx_frame_host]):
                return False
        return True

    for start in range(len(host_table.rows) - match_size, -1, -1):
        if not match(start):
            continue
        # found a match
        fields = [f.name for f in guest_table.fields]
        fields += [f.name for f in host_table.fields if f.name != 'host.frame_size']
        new_table = Table(fields)
        for g_row, h_row in zip(guest_table.rows, host_table.rows[start:]):
            if g_row[idx_frame_guest] != h_row[idx_frame_host]:
                break
            row = g_row + h_row[0:idx_frame_host] + h_row[idx_frame_host+1:]
            new_table.add(*row)
        return new_table

    raise NoGuestFramesInHostFramesExperimentException()

def collapse_frames_host_client(host_table, client_table):
    '''Collapse host and client frame information using frame_size and mm_time'''

    try:
        idx_frame_host = host_table.fields.index(all_fields['host.frame_size'])
    except Exception:
        idx_frame_host = host_table.fields.index(all_fields['guest.frame_size'])
    idx_time_host = host_table.fields.index(all_fields['host.mm_time'])
    idx_frame_client = client_table.fields.index(all_fields['client.frame_size'])
    idx_time_client = client_table.fields.index(all_fields['client.mm_time'])

    # create a dictionary from table
    c_rows = {}
    for row in client_table.rows:
        c_rows[(row[idx_time_client], row[idx_frame_client])] = row

    fields = [f.name for f in host_table.fields]
    fields += [f.name for f in client_table.fields] # if f.name != 'client.frame_size']
    empty = (None,) * len(client_table.fields)
    new_table = Table(fields)

    for row in host_table.rows:
        key = (row[idx_time_host], row[idx_frame_host])
        row += c_rows.get(key, empty)
        new_table.add(*row)

    return new_table

def collapse_tables(tables):
    if len(tables) == 1:
        return tables[0]

    if tables[0].table_name != 'frames':
        return collapse_tables_time(tables)
    parts = {}
    for table in tables:
        parts[frames_table_part(table)] = table
    if 'guest' in parts:
        assert 'host' in parts, "Cannot bind guest and client frame information directly"
        parts['host'] = collapse_frames_guest_host(parts['guest'], parts['host'])
        del parts['guest']
    if 'client' in parts:
        assert 'host' in parts, "Cannot bind guest and client frame information directly"
        return collapse_frames_host_client(parts['host'], parts['client'])
    raise NotImplementedError("Frames table collapsing")

class Experiment:
    def __init__(self, cfg):
        # TODO pass configuration
        self.database = Database()
        self.tables = []
        self.attachments = {}
        self.parameters = {}
        self.machines = {}
        for k,c in cfg.get('machines', {}).items():
            self.machines[k] = machine.create_machine(c)

    def create_table(self, fields):
        '''Create a table based on fields passed.
        fields should be a list of field names.'''
        # will check if fields are available
        # some can compare only once
        # fields are like "client.cpu" kind of
        # time is for all, not conflicting
        table = Table(fields)
        self.tables.append(table)
        return table

    def add_attachment(self, name, content):
        '''Add information to experiment.'''
        if name in self.attachments:
            raise Exception("Attempting to set duplicate attachment %s" % name)
        self.attachments[name] = content

    def set_param(self, name, value):
        '''Set a parameter'''
        if name in self.parameters and self.parameters[name] != value:
            raise Exception("Attempting to set duplicate parameter %s" % name)
        self.parameters[name] = value

    def save(self):
        '''Save the experiment to the database.'''

        # If something goes wrong dump all tables so we can debug
        debug_tables = []
        for i, table in enumerate(self.tables):
            debug_table = 'debug_table%d.yaml' % i
            debug_tables.append(debug_table)
            with open(debug_table, 'w', encoding='utf8') as outfile:
                yaml.dump(table, outfile, allow_unicode=True)

        # TODO
        # We should group informations on multiple tables that goes to
        # same physical table
        table_groups = defaultdict(list)
        for table in self.tables:
            table_groups[table.table_name].append(table)
        new_tables = []
        for name, tables in table_groups.items():
            if len(tables) == 1:
                new_tables.append(tables[0])
            else:
                new_tables.append(collapse_tables(tables))
        self.tables = new_tables
        # Collapse information for frames matching mm_time and size
        # - agent (size) must match with host (size), check sequence,
        #   we should find the agent sequence in the host, ignore the
        #   additional rows in the host
        # - host (size, mm_time) must match with client (size,
        #   mm_time)
        # Create experiments row
        # TODO time, description
        self.database.new_experiment(self.parameters)
        # Save attachments
        self.database.save_table('attachments', ['name', 'content'], self.attachments.items())
        for table in self.tables:
            fix_table_time(table)
            field_names = [f.field_name for f in table.fields]
            self.database.save_table(table.table_name, field_names, table.rows)
        self.database.commit()

        # delete debug files, everything went fine
        for debug_table in debug_tables:
            os.unlink(debug_table)
