import threading
import socket
import select
import struct
import measurement

force_recheck = None

class Server():
    current = None

    def __init__(self, port, expe, loop):
        self.expe = expe
        self.feedback_buffer = []
        self.loop = loop
        self.port = port

        self.new_clients = []
        self.current_clients = []
        assert Server.current is None, "agent.to_collector.Server is not a singleton :("
        Server.current = self

    def start(self):
        self.serv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serv_sock.setblocking(0)
        self.serv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.serv_sock.bind(('0.0.0.0', self.port))
        except OSError as e:
            if e.errno == 98:
                print(f"Port {self.port} already in use. Is this local_agent already running?")
            self.serv_sock.close()
            raise

        self.serv_sock.listen(5)
        self.thr = threading.Thread(target=self.thr_accept_socket)
        self.thr.start()

    def terminate(self):
        self.serv_sock.shutdown(socket.SHUT_RDWR)
        self.thr.join()
        self.serv_sock.close()

    def thr_accept_socket(self):
        read_list = [self.serv_sock]
        running = True
        while running:
            read_list = [s for s in read_list[:] if s.fileno() != -1]
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

                    print(f"Performance collector connected from {addr}")
                    self.new_clients.append(conn)
                    read_list.append(conn)
                    force_recheck.append(True)
                else:
                    if not self.thr_read_feedback(s):
                        read_list.remove(s)

    def thr_read_feedback(self, comm_sock):
        try:
            c = comm_sock.recv(1).decode("ascii")

            if not c: return False

            if c == "\0":
                self.thr_feedback_to_agent("".join(self.feedback_buffer))
                self.feedback_buffer[:] = []
            else:
                self.feedback_buffer.append(c)

            return True
        except ConnectionResetError: pass # Collector disconnected
        except Exception as e:
            print("thr_read_feedback failed:", e)
        return False

    def thr_feedback_to_agent(self, msg):
        measurement.agentinterface.feedback.send_str(msg)

    def send_feedback_backlog(self, client_sock):
        table = self.expe.feedback
        if not (table and table.rows):
            return

        msg = f"@{table.table_name}|{len(table.rows)}".encode("ascii")
        self.send_one(msg, client_sock)

        for row in table.rows:
            self.send_one(", ".join(map(str, row)).encode("ascii"), client_sock)

    def initialize_new_client(self, client_sock):
        client_sock.send(struct.pack("I", len(self.expe.tables)))

        for table in self.expe.tables.values():
            self.send_table_def(table, client_sock)

    def periodic_checkup(self):
        self.initialize_new_clients()

    def initialize_new_clients(self):
        clients, self.new_clients = self.new_clients, [] # should be atomic

        for client in clients:
            try:
                self.initialize_new_client(client)
                self.send_feedback_backlog(client)
            except Exception as e:
                print(f"Client {client} disconnected during initialization ({e})")
                continue

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
                client_sock.close()

    def new_table_row(self, table, row):
        self.send_all(f"@{table.table_name}|1".encode("ascii"))
        self.send_all(", ".join(map(str, row)).encode("ascii"))

    def new_table(self, table):
        self.send_table_def(table)

    def send_table_def(self, table, client_sock=None):
        msg = (f"#{table.table_name}|" +";".join([f for f in table.fields])).encode("ascii")

        if client_sock:
            self.send_one(msg, client_sock)
        else:
            self.send_all(msg)
