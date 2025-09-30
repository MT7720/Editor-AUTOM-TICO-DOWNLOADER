import threading
import queue
import time
from video_processing_logic import process_entrypoint

# Simula entrada de parâmetros mínimos para um vídeo simples
params = {
    'ffmpeg_path': '/caminho/para/ffmpeg',  # Substituir
    'media_type': 'video_single',
    'media_path_single': 'exemplo.mp4',
    'narration_file_single': 'narra.mp3',
    'music_file_single': '',
    'subtitle_file_single': '',
    'output_folder': './saidas',
    'output_filename_single': 'teste_exportado.mp4',
    'video_codec': 'Automático',
    'resolution': '1080p (1920x1080)',
    'available_encoders': ['libx264'],
    'subtitle_style': {
        'fontsize': 28,
        'text_color': '#FFFFFF',
        'outline_color': '#000000',
        'bold': True,
        'italic': False,
        'position': 'Inferior Central',
        'font_file': '',
        'position_map': {
            'Inferior Central': 2
        }
    }
}

# Filas de comunicação
progress_queue = queue.Queue()
cancel_event = threading.Event()

# Roda a exportação em thread para simular o app
def run_export():
    process_entrypoint(params, progress_queue, cancel_event)

threading.Thread(target=run_export).start()

# Coleta os logs
while True:
    try:
        msg = progress_queue.get(timeout=1)
        print(msg)
        if msg[0] == "finish":
            break
    except queue.Empty:
        continue
