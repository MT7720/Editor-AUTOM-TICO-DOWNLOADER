import os
from pathlib import Path
from typing import Dict # CORREÇÃO: Adicionada a importação que faltava

# --- SIMULAÇÃO DOS PARÂMETROS DO PROGRAMA ---

# Simula os caminhos dos arquivos que seriam usados no processamento.
# Você pode alterar esses caminhos para os seus próprios, se quiser, mas não é necessário.
ffmpeg_path = r"C:\ffmpeg\bin\ffmpeg.exe"
base_video_path = r"C:\temp\slideshow_stitched.mp4"
narration_path = r"C:\audios\60 ALE.mp3"
music_path = r"C:\musicas\minha_musica.mp3"
subtitle_path = r"C:\legendas\60 ALE.srt"
output_path = r"D:\videos_prontos\video_final_60_ALE.mp4"

# Simula as configurações de estilo e volume
params = {
    'ffmpeg_path': ffmpeg_path,
    'output_folder': os.path.dirname(output_path),
    'output_filename_single': os.path.basename(output_path),
    'narration_volume': 0,
    'music_volume': -15,
    'subtitle_style': {
        'fontsize': 28, 'text_color': '#FFFFFF', 'outline_color': '#000000',
        'bold': True, 'italic': False, 'position': 'Inferior Central',
        'font_file': '', 'position_map': {'Inferior Central': 2}
    }
}

# --- FUNÇÕES AUXILIARES (Copiadas do programa principal para o teste) ---

def _escape_ffmpeg_path(path_str: str) -> str:
    return str(Path(path_str)).replace('\\', '/').replace(':', '\\:')

def _build_subtitle_style_string(style_params: Dict) -> str:
    # Esta função apenas cria a string de estilo, não precisa de alterações.
    font_name = Path(style_params.get('font_file')).stem if style_params.get('font_file') else 'Arial'
    def to_ass_color(hex_color: str) -> str:
        hex_color = hex_color.lstrip('#')
        return f"&H{hex_color[4:6]}{hex_color[2:4]}{hex_color[0:2]}".upper()
    style_parts = {
        'FontName': font_name, 'FontSize': style_params.get('fontsize', 28),
        'PrimaryColour': to_ass_color(style_params.get('text_color', '#FFFFFF')),
        'OutlineColour': to_ass_color(style_params.get('outline_color', '#000000')),
        'BorderStyle': 1, 'Outline': 2, 'Shadow': 1,
        'Bold': -1 if style_params.get('bold', True) else 0,
        'Italic': -1 if style_params.get('italic', False) else 0,
        'Alignment': style_params.get('position_map', {}).get(style_params.get('position'), 2),
        'MarginV': int(style_params.get('fontsize', 28) * 0.7)
    }
    return ",".join(f"{k}={v}" for k, v in style_parts.items())


# --- LÓGICA DE MONTAGEM DO COMANDO (COM O BUG) ---

def build_command_com_bug():
    print("--- 1. GERANDO COMANDO COM A LÓGICA ANTIGA (COM BUG) ---")
    
    inputs = ["-i", base_video_path]
    video_input_idx = 0
    narration_input_idx, music_input_idx = -1, -1
    
    # LÓGICA COM BUG: A contagem dos índices estava errada.
    if narration_path:
        inputs.extend(["-i", narration_path])
        narration_input_idx = len(inputs) // 2 
        
    if music_path:
        inputs.extend(["-i", music_path])
        music_input_idx = len(inputs) // 2
        
    if subtitle_path:
        # A legenda não é um input, mas precisa de um índice de áudio.
        # O erro acontecia aqui ao tentar referenciar um índice que não existia.
        # Ex: [3:a] quando só havia 3 inputs (índices 0, 1, 2).
        pass

    print(f"Índices de Input Gerados (Errado):")
    print(f"  Vídeo: {video_input_idx}, Narração: {narration_input_idx}, Música: {music_input_idx}\n")
    # A montagem do filtro falharia aqui, então não vamos montá-lo.
    print("Resultado: O filtro tentaria usar um índice de arquivo inválido, como '[3:a]', causando o erro.\n")


# --- LÓGICA DE MONTAGEM DO COMANDO (CORRIGIDA) ---

def build_command_corrigido():
    print("--- 2. GERANDO COMANDO COM A LÓGICA NOVA (CORRIGIDA) ---")

    inputs = ["-i", base_video_path]
    filter_complex_parts = []
    
    # LÓGICA CORRIGIDA: Usa um contador simples para os índices.
    video_input_idx = 0
    narration_input_idx, music_input_idx = -1, -1
    current_input_idx = 0

    if narration_path:
        inputs.extend(["-i", narration_path])
        current_input_idx += 1
        narration_input_idx = current_input_idx
        
    if music_path:
        inputs.extend(["-i", music_path])
        current_input_idx += 1
        music_input_idx = current_input_idx
    
    print(f"Índices de Input Gerados (Correto):")
    print(f"  Vídeo: {video_input_idx}, Narração: {narration_input_idx}, Música: {music_input_idx}\n")

    # Montagem do filtro de áudio (agora com os índices corretos)
    if narration_input_idx != -1 and music_input_idx != -1:
        filter_complex_parts.extend([
            f"[{narration_input_idx}:a]volume=0dB[narr_vol]",
            f"[{music_input_idx}:a]volume=-15dB[music_vol]",
            "[narr_vol][music_vol]amix=inputs=2[aout]"
        ])
        final_audio_stream = "[aout]"
    elif narration_input_idx != -1:
        filter_complex_parts.append(f"[{narration_input_idx}:a]volume=0dB[aout]")
        final_audio_stream = "[aout]"
    else: # Apenas música
        final_audio_stream = f"[{music_input_idx}:a]"

    # Montagem do filtro de vídeo (legenda)
    final_video_stream = f"[{video_input_idx}:v]"
    if subtitle_path:
        style_str = _build_subtitle_style_string(params['subtitle_style'])
        escaped_sub_path = _escape_ffmpeg_path(subtitle_path)
        subtitle_filter = f"subtitles=filename='{escaped_sub_path}':force_style='{style_str}'"
        filter_complex_parts.insert(0, f"[{video_input_idx}:v]{subtitle_filter}[vout]")
        final_video_stream = "[vout]"

    # Montagem final do comando
    cmd = [params['ffmpeg_path'], "-y", *inputs]
    if filter_complex_parts:
        cmd.extend(["-filter_complex", ";".join(filter_complex_parts)])
    
    cmd.extend(["-map", final_video_stream, "-map", final_audio_stream])
    cmd.extend(["-c:v", "copy", "-c:a", "aac", "-shortest", output_path])

    print("Comando FFmpeg Final (Corrigido):")
    # Usa ' ' para juntar e facilitar a leitura
    print(' '.join(f'"{c}"' if ' ' in c else c for c in cmd))


if __name__ == "__main__":
    build_command_com_bug()
    print("-" * 60)
    build_command_corrigido()

