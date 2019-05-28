#!/bin/env python

from collections import Iterator

class DatabaseData(Iterator):
    _table = None
    _members = None

    def __init__(self, database, args):
        Iterator.__init__(self)
        self.database = database
        self.args = args
        self.cur = 0
    # __init__

    def __getattr__(self, attr):
        if attr not in self._members:
            raise AttributeError("%s has no attribute %s", self.__class__.__name__, attr)
        return self.args[self._members.index(attr)]
    # __getattr__

    def __str__(self):
        _str = "%s\n\t" % self.__class__.__name__
        for m in self._members:
            _str = "%s%s : %s\n\t" % (_str, m, self.__getattr__(m))
        _str = "%s%s" % (_str, "\b\b")
        return _str
    # __str__

    def __len__(self):
        return len(self._members)
    # __len__

    @classmethod
    def load(_class, database, _id=None):
        if not _class._table:
            raise Exception("database table not provided")

        query = "select * from %s" % (_class._table)
        if _id:
            query = "%s where id_experiment is %s" % (query, _id)

        cursor = database.cursor()
        cursor.execute(query)
        return [_class(database, args) for args in cursor.fetchall()]
    # load

    def next(self):
        if self.cur >= len(self._members):
            self.cur = 0
            raise StopIteration

        key = self._members[self.cur]
        val = self.args[self.cur]
        self.cur += 1
        return key, val
    # next
# DatabaseData


class GuestData(DatabaseData):
    _table = "guest_stats"
    _members = ["id", "time", "gpu_memory", "gpu_usage",
                "encode_usage", "decode_usage"]
# GuestData


class HostData(DatabaseData):
    _table = "host_stats"
    _members = ["id", "time", "cpu_usage"]
# HostData


class ClientData(DatabaseData):
    _table = "client_stats"
    _members = ["id", "time", "gpu_usage", "app_gpu_usage",
                "cpu_usage", "app_cpu_usage"]
# ClientData


class FramesData(DatabaseData):
    _table = "frames"
    _members = ["id", "agent_time", "size", "mm_time", "capture_duration",
                "encode_duration", "send_duration", "client_time",
                "decode_duration", "queue_size"]
# FramesData


class ExperimentData(DatabaseData):
    _table = "experiments"
    _members = ["id", "time", "description", "fps", "width",
                "height", "gop", "bitrate", "num_ref_frames",
                "uuid", "imported"]

    def __init__(self, database, args):
        DatabaseData.__init__(self, database, args)
        self.frames = FramesData.load(self.database, self.id)
        self.guest_stats = GuestData.load(self.database, self.id)
        self.host_stats = HostData.load(self.database, self.id)
        self.client_stats = ClientData.load(self.database, self.id)
    # __init__

    def dump(self):
        _str = "%s\n\t" % DatabaseData.__str__(self)
        for l in [self.frames, self.guest_stats, self.host_stats, self.client_stats]:
            for i in l:
                _str = "%s%s\n\t" % (_str, i)
        _str = "%s%s" % (_str, "\b\b")
        print(_str)
    # dump
# ExperimentData


if __name__ == "__main__":
    import sqlite3
    db = sqlite3.connect("benchmark.db")
    experiments = ExperimentData.load(db)
    for e in experiments:
        e.dump()
    db.close()
# __main__