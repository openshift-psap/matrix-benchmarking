import asyncio
import subprocess
import sys

async def stream_as_generator(loop, stream):
    reader = asyncio.StreamReader(loop=loop)
    reader_protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: reader_protocol, stream)

    while True:
        line = await reader.readline()
        if not line: break
        yield line.decode('utf-8')

class LiveCollect():
    def __init__(self):
        self.lines = []
        self.alive = False
        self.exception = []

    def connect(self, loop, process=None):
        self.alive = True
        if not process:
            process = self.process

        async def follow_stream():
            async for line in stream_as_generator(loop, self.stream):
                try:
                    process(line)
                except StopIteration:
                    break
                except Exception as e:
                    self.exception.append((e, sys.exc_info()))
            self.alive = False

        loop.create_task(follow_stream())

    def process(self, line):
        self.lines.append(line)

    def stop(self):
        pass


class FollowFile(LiveCollect):
    def __init__(self, path):
        super().__init__()

        self.path = path

    def start(self):
        subprocess.check_output(["test", "-e", self.path])

        self.tail = subprocess.Popen(["tail", "-f", self.path],
                                     shell=use_shell ,close_fds=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     stdin=subprocess.PIPE)
        self.tail.stdin.close()

        self.stream = self.tail.stdout

    def stop(self):
        self.tail.terminate()
        self.tail.wait(2)


class LiveStream(LiveCollect):

    def start(self, stream):
        self.stream = stream

class LiveSocket(LiveCollect):
    def __init__(self, sock, async_read):
        super().__init__()

        self.sock = sock
        self.async_read = async_read

    def connect(self, loop, process=None):
        self.alive = True
        if not process:
            process = self.process

        async def follow_socket():
            reader, writer = await asyncio.open_connection(sock=self.sock)
            while True:
                entry = await self.async_read(reader)

                if entry is False: # None is allowed
                    break

                process(entry)

            addr, port = self.sock.getpeername()
            print(f"Connection to {addr}:{port} closed.")
            self.alive = False

        loop.create_task(follow_socket())
