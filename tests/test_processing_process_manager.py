from processing.process_manager import FFmpegProcessManager


class DummyProcess:
    def __init__(self, pid: int):
        self.pid = pid
        self._alive = True

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self._alive = False

    def wait(self, timeout=None):
        self._alive = False

    def kill(self):
        self._alive = False


def test_process_manager_tracks_and_terminates_processes():
    manager = FFmpegProcessManager()
    proc = DummyProcess(123)
    manager.add(proc)
    assert manager.active_processes

    manager.terminate_all()
    assert not manager.active_processes
