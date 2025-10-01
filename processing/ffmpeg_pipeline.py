"""Funções utilitárias para interação com FFmpeg."""

from __future__ import annotations

import json
import locale
import logging
import os
import platform
import shutil
import subprocess
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Dict, List, Optional, Tuple

from .process_manager import process_manager

logger = logging.getLogger(__name__)

__all__ = [
    "stream_reader",
    "execute_ffmpeg",
    "escape_ffmpeg_path",
    "probe_media_properties",
    "get_codec_params",
]


def stream_reader(stream, line_queue: Queue) -> None:
    if not stream:
        return

    encoding = locale.getpreferredencoding(False) or "utf-8"

    try:
        while True:
            chunk = stream.readline()
            if not chunk:
                break

            if isinstance(chunk, bytes):
                decoded = chunk.decode(encoding, errors="replace")
            else:
                decoded = chunk

            line_queue.put(decoded)
    except Exception as exc:  # pragma: no cover - leitura defensiva
        logger.warning("O leitor de stream encontrou um erro: %s", exc)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def execute_ffmpeg(
    cmd: List[str],
    duration: float,
    progress_callback: Optional[Callable[[float], None]],
    cancel_event: threading.Event,
    log_prefix: str,
    progress_queue: Queue,
) -> bool:
    ffmpeg_path = cmd[0]
    if not os.path.isfile(ffmpeg_path):
        error_msg = f"ERRO FATAL: O caminho para o FFmpeg é inválido: '{ffmpeg_path}'"
        progress_queue.put(("status", error_msg, "error"))
        logger.critical("FFmpeg executable check failed: '%s'", ffmpeg_path)
        return False

    logger.info("[%s] Executing FFmpeg: %s", log_prefix, ffmpeg_path)
    progress_queue.put(("status", f"[{log_prefix}] Iniciando processo FFmpeg...", "info"))

    cmd_with_progress = [ffmpeg_path] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

    logger.debug("[%s] Comando FFmpeg: %s", log_prefix, " ".join(map(str, cmd_with_progress)))

    try:
        process = subprocess.Popen(
            cmd_with_progress,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
            shell=False,
        )
    except (FileNotFoundError, OSError) as exc:
        logger.critical("Erro ao executar o FFmpeg em '%s': %s", ffmpeg_path, exc, exc_info=True)
        progress_queue.put(("status", f"Erro crítico ao executar o FFmpeg: {exc}", "error"))
        return False

    process_manager.add(process)

    output_queue: Queue[str] = Queue()
    stdout_thread = threading.Thread(target=stream_reader, args=(process.stdout, output_queue), daemon=True)
    stderr_thread = threading.Thread(target=stream_reader, args=(process.stderr, output_queue), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    full_output = ""
    last_reported_pct = 0.0
    stall_warning_threshold = 45.0
    stall_warning_interval = 15.0
    stall_abort_threshold = 120.0
    last_activity_time = time.monotonic()
    last_progress_time = last_activity_time
    last_progress_pct = 0.0
    progress_updates_seen = False
    last_warning_bucket = 0
    stalled = False
    last_nonempty_line = ""

    while process.poll() is None:
        if cancel_event.is_set():
            logger.warning("[%s] Cancelamento solicitado. Encerrando FFmpeg %s.", log_prefix, process.pid)
            progress_queue.put(("status", f"[{log_prefix}] Cancelamento em andamento...", "warning"))
            process.terminate()
            break

        try:
            chunk = output_queue.get(timeout=0.1)
            last_activity_time = time.monotonic()
            last_warning_bucket = 0
            for line in chunk.split("\n"):
                full_output += line + "\n"
                stripped = line.strip()
                if "out_time_ms=" in stripped or "out_time_us=" in stripped or stripped.startswith("out_time="):
                    key, _, value = stripped.partition("=")
                    key = key.strip()
                    value = value.strip()

                    current_time_sec = None
                    if key == "out_time_ms" and value.isdigit():
                        current_time_sec = int(value) / 1_000_000
                    elif key == "out_time_us" and value.isdigit():
                        current_time_sec = int(value) / 1_000_000
                    elif key == "out_time" and value:
                        try:
                            h, m, s = value.split(":")
                            current_time_sec = int(h) * 3600 + int(m) * 60 + float(s)
                        except ValueError:
                            current_time_sec = None

                    if current_time_sec is not None and duration > 0:
                        progress_pct = min(current_time_sec / duration, 1.0)
                        if (
                            progress_pct > last_progress_pct + 1e-6
                            or (progress_pct >= 1.0 and last_progress_pct < 1.0)
                        ):
                            last_progress_time = time.monotonic()
                            last_progress_pct = progress_pct
                            progress_updates_seen = True
                        if progress_callback:
                            progress_callback(progress_pct)
                        if progress_pct - last_reported_pct >= 0.01:
                            progress_queue.put(("status", f"[{log_prefix}] {int(progress_pct * 100)}% concluído", "info"))
                            last_reported_pct = progress_pct
                else:
                    stripped_line = line.strip()
                    if stripped_line:
                        last_nonempty_line = stripped_line
                        logger.debug("[%s/ffmpeg] %s", log_prefix, stripped_line)
        except Empty:
            now = time.monotonic()
            inactive_duration = now - last_activity_time
            progress_inactive_duration = now - last_progress_time

            if inactive_duration > stall_warning_threshold:
                bucket = int((inactive_duration - stall_warning_threshold) / stall_warning_interval)
                if bucket > last_warning_bucket:
                    last_warning_bucket = bucket
                    progress_queue.put((
                        "status",
                        f"[{log_prefix}] FFmpeg não envia atualizações há {int(inactive_duration)}s...",
                        "warning",
                    ))

            if progress_updates_seen and progress_inactive_duration > stall_abort_threshold:
                stalled = True
                process.terminate()
                break

            continue

    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    process_manager.remove(process)

    if process.returncode == 0 and not stalled:
        if progress_callback:
            progress_callback(1.0)
        return True

    if stalled and process.returncode == 0:
        process.returncode = -1
    if stalled:
        logger.error("[%s] FFmpeg interrompido por falta de progresso.", log_prefix)
        stall_detail = last_nonempty_line or "Nenhuma mensagem adicional do FFmpeg."
        progress_queue.put((
            "status",
            f"[{log_prefix}] FFmpeg interrompido por falta de progresso. Última saída conhecida: {stall_detail}",
            "error",
        ))

    logger.error("[%s] FFmpeg falhou com o código %s.", log_prefix, process.returncode)
    logger.error("[%s] Log FFmpeg:\n%s", log_prefix, full_output)
    error_lines = [line for line in full_output.lower().splitlines() if "error" in line or "invalid" in line]
    if not error_lines and last_nonempty_line:
        error_lines = [last_nonempty_line]
    error_snippet = "\n".join(error_lines[-3:]) if error_lines else "\n".join(full_output.strip().split("\n")[-5:])

    progress_queue.put(("status", f"[{log_prefix}] ERRO no FFmpeg: {error_snippet}", "error"))
    return False


def escape_ffmpeg_path(path_str: str) -> str:
    return (
        str(Path(path_str))
        .replace("\\", "/")
        .replace(":", r"\:")
        .replace("'", r"\'")
    )


def probe_media_properties(path: str, ffmpeg_path: str) -> Optional[Dict[str, Any]]:
    if not path or not os.path.isfile(path):
        return None

    ffprobe_exe_name = "ffprobe.exe" if platform.system() == "Windows" else "ffprobe"

    final_ffprobe_path = ""
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        derived_path = os.path.normpath(os.path.join(Path(ffmpeg_path).parent, ffprobe_exe_name))
        if os.path.isfile(derived_path):
            final_ffprobe_path = derived_path

    if not final_ffprobe_path:
        found_in_path = shutil.which(ffprobe_exe_name)
        if found_in_path:
            logger.info("ffprobe não encontrado via caminho do FFmpeg. Usando ffprobe do PATH: %s", found_in_path)
            final_ffprobe_path = found_in_path
        else:
            logger.error("ffprobe não encontrado. Verifique o caminho do FFmpeg ou o PATH do sistema.")
            return None

    try:
        cmd = [
            final_ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            os.path.normpath(path),
        ]
        creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
            creationflags=creation_flags,
            encoding="utf-8",
            errors="ignore",
        )
        return json.loads(result.stdout)
    except FileNotFoundError:
        logger.error("ffprobe não pôde ser executado em '%s'. Verifique a instalação do FFmpeg.", final_ffprobe_path)
        return None
    except Exception as exc:  # pragma: no cover - comportamento dependente do ambiente
        logger.warning("Não foi possível obter propriedades de '%s': %s", Path(path).name, exc)
        return None


def get_codec_params(params: Dict[str, Any], force_reencode: bool = False) -> List[str]:
    video_codec_choice = params.get("video_codec", "Automático")
    available_encoders = params.get("available_encoders", [])

    if not force_reencode:
        logger.info("Nenhuma recodificação de vídeo necessária. Usando '-c:v copy'.")
        return ["-c:v", "copy"]

    encoder = "libx264"
    codec_flags = ["-preset", "veryfast", "-crf", "23"]

    use_gpu = (
        (video_codec_choice == "Automático" and any(e in available_encoders for e in ["h264_nvenc", "hevc_nvenc"]))
        or "GPU" in video_codec_choice
    )

    if use_gpu:
        logger.info("Tentando usar aceleração por GPU (NVENC)...")
        if "h264_nvenc" in available_encoders:
            encoder, codec_flags = "h264_nvenc", ["-preset", "p2", "-cq", "23", "-rc-lookahead", "8"]
            logger.info("Selecionado encoder GPU: h264_nvenc com preset p2")
        elif "hevc_nvenc" in available_encoders:
            encoder, codec_flags = "hevc_nvenc", ["-preset", "p2", "-cq", "23", "-rc-lookahead", "8"]
            logger.info("Selecionado encoder GPU: hevc_nvenc com preset p2")
        else:
            logger.warning(
                "Aceleração por GPU solicitada, mas nenhum encoder NVENC foi encontrado. Voltando para CPU (libx264)."
            )
    else:
        codec_flags = ["-preset", "superfast", "-crf", "26"]
        logger.info("Selecionado encoder CPU: libx264 com preset superfast")

    return ["-c:v", encoder, *codec_flags, "-pix_fmt", "yuv420p"]
