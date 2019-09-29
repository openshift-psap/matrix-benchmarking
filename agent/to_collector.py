import threading
import socket
import select
import struct
import measurement

class Server():
    def __init__(self, expe, loop):
        self.expe = expe
        self.quality_buffer = []
        self.loop = loop

        self.new_clients = []
        self.current_clients = []

    def start(self):
        self.serv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serv_sock.setblocking(0)
        self.serv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            PORT = 1230
            self.serv_sock.bind(('0.0.0.0', PORT))
        except OSError as e:
            if e.errno == 98:
                print(f"Port {PORT} already in use. Is the SmartLocalAgent already running?")

            raise e

        self.serv_sock.listen(5)
        self.thr = threading.Thread(target=self.thr_accept_socket)
        self.thr.start()

    def terminate(self):
        self.serv_sock.shutdown(socket.SHUT_RDWR)
        self.thr.join()

    def thr_accept_socket(self):
        read_list = [self.serv_sock]
        running = True
        while running:
            readable, writable, errored = select.select(read_list, [], [])

            for s in readable:
                if s == self.serv_sock:
                    try:
                        conn, (addr, port) = self.serv_sock.accept()
                    except OSError as e:
                        if e.errno == 22: #  Invalid argument
                            running = False
                            break
                        else:
                            print("ERROR:", e.__class__.__name__, ":", e)
                            continue

                    print(f"New connection from {addr}:{port}")
                    self.new_clients.append(conn)
                    read_list.append(conn)
                    self.loop.stop()
                else:
                    if not self.thr_read_quality(s):
                        read_list.remove(s)

        print("Socket to Perf collector closed.")

    def thr_read_quality(self, comm_sock):
        try:
            c = comm_sock.recv(1).decode("ascii")

            if not c: return False

            if c == "\0":
                self.thr_quality_to_agent("".join(self.quality_buffer))
                self.quality_buffer[:] = []
            else:
                self.quality_buffer.append(c)

            return True
        except Exception as e:
            print("thr_read_quality failed:", e)
            return False

    def thr_quality_to_agent(self, msg):
        measurement.agentinterface.quality.send_str(msg)

    def send_quality_backlog(self, client_sock):
        table = self.expe.quality
        if not (table and table.rows):
            return

        msg = f"@{table.table_name}|{len(table.rows)}".encode("ascii")
        self.send_one(msg, client_sock)

        for row in table.rows:
            self.send_one(str(row).encode("ascii"), client_sock)

    def initialize_new_client(self, client_sock):
        client_sock.send(struct.pack("I", len(self.expe.tables)))

        for table in self.expe.tables.values():
            self.send_table_def(table, client_sock)

    def periodic_checkup(self):
        self.initialize_new_clients()

    def initialize_new_clients(self):
        clients, self.new_clients = self.new_clients, [] # should be atomic

        for client in clients:
            self.initialize_new_client(client)
            self.send_quality_backlog(client)
            self.current_clients.append(client)

    def send_one(self, msg, client_sock):
        return client_sock.send(msg + b"\0")

    def send_all(self, msg):
        for client_sock in self.current_clients[:]:
            try:
                self.send_one(msg, client_sock)
            except Exception as e:
                # safe as we're using a copy of the list
                self.current_clients.remove(client_sock)
                addr, port = client_sock.getsockname()
                print(f"Client {addr}:{port} disconnected ({e})")

    def new_table_row(self, table, row):
        self.send_all(f"@{table.table_name}|1".encode("ascii"))
        self.send_all(str(row).encode("ascii"))

    def new_table(self, table):
        self.send_table_def(table)

    def send_table_def(self, table, client_sock=None):
        msg = (f"#{table.table_name}|" +";".join([f for f in table.fields])).encode("ascii")

        if client_sock:
            self.send_one(msg, client_sock)
        else:
            self.send_all(msg)
