import threading
import socket
import select
import struct

class Server():
    def __init__(self, expe):
        self.expe = expe
        self.quality_buffer = []

        self.new_clients = []
        self.current_clients = []

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
                        conn, addr = self.serv_sock.accept()

                    except OSError as e:
                        if e.errno == 22: #  Invalid argument
                            running = False
                            break

                    print("New connection from", addr)
                    self.new_clients.append(conn)
                    read_list.append(conn)
                else:
                    if not self.thr_read_quality(s):
                        read_list.remove(conn)

        print("Socket to Perf collector closed.")

    def thr_read_quality(self, comm_sock):
        try:
            c = comm_sock.recv(1).decode("ascii")
            if c == "\0":
                self.thr_quality_to_agent("".join(self.quality_buffer))
                self.quality_buffer[:] = []
            else:
                self.quality_buffer.append(c)

            return True
        except Exception:
            return False

    def thr_quality_to_agent(self, msg):
        measurement.agentinterface.quality.send_str(msg)

    def send_quality_backlog(self, client_sock):
        table = self.expe.quality
        if not (table and table.rows):
            return

        client_sock.send(f"#{table.tid} {table.table_name}|{len(table.rows)}\0".encode("ascii"))
        for row in table.rows:
            client_sock.send(str(row).encode("ascii") + b"\0")

    def initialize_new_client(self, client_sock):
        client_sock.send(struct.pack("I", len(self.expe.tables)))
        for i, table in enumerate(self.expe.tables):
            msg = f"#{i} {table.table_name}|" +";".join([f for f in table.fields]) + "\0"
            client_sock.send(msg.encode("ascii"))

    def periodic_checkup(self):
        self.initialize_new_clients()

    def initialize_new_clients(self):
        clients, self.new_clients = self.new_clients, [] # should be atomic

        for client in clients:
            self.initialize_new_client(client)
            self.send_quality_backlog(client)
            self.current_clients.append(client)

    def send_all(self, line):
        for client in self.current_clients[:]:
            try:
                client.send(line + b"\0")
            except Exception as e:
                # safe as we're using a copy of the list
                self.current_clients.remove(client)
                print(f"Client {client.getsockname()} disconnected ({e})")

    def new_table_row(self, table, row):
        self.send_all(f"#{table.tid} {table.table_name}|1".encode("ascii"))
        self.send_all(str(row).encode("ascii"))

    def new_table(self, table):
        pass
