import threading

ENABLE_STDIN_QUALITY = False

class ConsoleQuality():
    def __init__(self):
        self.agents = {}
        self.running = None
        if not ENABLE_STDIN_QUALITY:
            return

        self.thr = threading.Thread(target=self.thread_routine)
        self.thr.daemon = True
        self.thr.start()

    def send_str(self, line):
        print("Quality Input: >>", line)

        mode, found, msg = line.partition(":")
        if not found \
           or not mode in self.agents \
           or "\0" in msg \
           or len(msg) > 127:
            print("Invalid message. Valid modes:", ",".join(self.agents.keys()))
            return

        self.agents[mode].send((msg+"\0").encode("ascii"))

    def thread_routine(self):
        self.running = True
        print("Quality Input: Running")

        while self.running:
            try:
                line = input()
                if line == "bye":
                    break
            except EOFError:
                break
            except Exception as e:
                print("Quality Input: error:", e)
                continue

            self.send_str(line)

        self.running = False
        print("Quality Input: done")

    def register(self, name, sock):
        self.agents[name] = sock

    def stop(self):
        if not self.running: return
        self.running = False

quality = ConsoleQuality()
