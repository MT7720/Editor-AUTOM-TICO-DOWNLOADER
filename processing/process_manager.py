"""Gerenciamento compartilhado de processos FFmpeg."""

from __future__ import annotations

import atexit
import logging
import threading
import subprocess
from typing import Dict

logger = logging.getLogger(__name__)

__all__ = ["FFmpegProcessManager", "process_manager"]


class FFmpegProcessManager:
    """Gerencia processos FFmpeg em execução para garantir a limpeza na saída."""

    def __init__(self) -> None:
        self.active_processes: Dict[int, subprocess.Popen] = {}
        self.lock = threading.Lock()
        atexit.register(self.shutdown)

    def add(self, process: subprocess.Popen) -> None:
        with self.lock:
            self.active_processes[process.pid] = process
            logger.debug("Processo %s adicionado. Total: %s", process.pid, len(self.active_processes))

    def remove(self, process: subprocess.Popen) -> None:
        with self.lock:
            if process.pid in self.active_processes:
                del self.active_processes[process.pid]
                logger.debug("Processo %s removido. Restantes: %s", process.pid, len(self.active_processes))

    def terminate_all(self) -> None:
        with self.lock:
            if not self.active_processes:
                return
            logger.info("Encerrando %s processo(s) FFmpeg ativo(s)...", len(self.active_processes))
            processes_to_kill = list(self.active_processes.values())

        for process in processes_to_kill:
            try:
                if process.poll() is None:
                    logger.warning("Forçando o encerramento do processo %s...", process.pid)
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        logger.error("O processo %s não encerrou, matando.", process.pid)
                        process.kill()
            except Exception as exc:  # pragma: no cover - medida defensiva
                logger.error("Erro ao encerrar o processo %s: %s", process.pid, exc)

        with self.lock:
            self.active_processes.clear()

    def shutdown(self) -> None:
        self.terminate_all()


process_manager = FFmpegProcessManager()
