import matrix_view.table_stats
from common import Matrix

from . import hello
from . import osu
from . import osu_collective

def register():
    osu.SimpleNet()
    hello.Hello()
    osu_collective.SimpleNet()
