import subprocess
import shlex

# TODO if not utf-8 ?
# TODO if we want binary ?
def _decode_out(out):
    return out.decode('utf-8')

class Machine:
    '''Class to represent a local/remote machine'''
    def __init__(self):
        pass

    def upload(self, local, remote):
        '''Upload a file to remote machine'''
        raise NotImplemented('upload')

    def download(self, remote, local):
        '''Download a file from the remote machine'''
        raise NotImplemented('download')

    def run(self, args):
        '''Runs a command.

        args can be a string or a list of srgument.
        In the first case shell is used.
        '''
        raise NotImplemented('run')

    def Process(self, args):
        '''Create a process.
        '''
        raise NotImplemented('Process')

class LocalMachine(Machine):
    def __init__(self):
        super().__init__()

    def upload(self, local, remote):
        self.run(['cp', local, remote])

    def download(self, remote, local):
        self.run(['cp', remote, local])

    def run(self, args):
        if type(args) == str:
            out = subprocess.check_output([args], shell=True)
        else:
            out = subprocess.check_output(args)
        return _decode_out(out)

    def Process(self, args):
        if type(args) == str:
            return subprocess.Popen([args], shell=True)
        else:
            return subprocess.Popen(args)

class RemoteMachine(Machine):
    def __init__(self, hostname):
        super().__init__()
        self.hostname = hostname
        self.opts = ['-o', 'PasswordAuthentication=no']

    def upload(self, local, remote):
        self._scp(self._local(local), self._remote(remote))

    def download(self, remote, local):
        self._scp(self._remote(remote), self._local(local))

    def run(self, args):
        if type(args) != str:
            args = ' '.join([shlex.quote(arg) for arg in args])
        out = subprocess.check_output(['ssh', *self.opts, self.hostname, '--', args])
        return _decode_out(out)

    def Process(self, args):
        if type(args) != str:
            args = ' '.join([shlex.quote(arg) for arg in args])
        return subprocess.Popen(['ssh', *self.opts, self.hostname, '--', args])

    def _scp(self, source, dest):
        subprocess.check_call(['scp', *self.opts, source, dest])

    def _local(self, path):
        '''Canonize local path'''
        if path[0:1] != '/' or path[0:1] != '.':
            return './' + path
        return path

    def _remote(self, path):
        '''Canonize remote path'''
        return self.hostname + ':' + path
