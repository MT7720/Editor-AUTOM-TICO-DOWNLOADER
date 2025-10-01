# Editor-Autom-tico

Este repositório contém um editor de vídeo simplificado usando `ttkbootstrap` e utilitários para FFmpeg.

## Executando a interface gráfica

Para iniciar a interface gráfica, basta executar:

```bash
python main.py
```

## Monitoramento da licença

Depois de validada, a aplicação continua a verificar periodicamente o status da licença junto ao Keygen utilizando o identificador salvo no ficheiro `license.json`. Em caso de falha de rede temporária, o processo regista o erro nos logs e aguarda um intervalo crescente (exponencial) antes de repetir a verificação, evitando encerramentos acidentais. Caso o servidor informe que a licença expirou ou se tornou inválida, o utilizador é avisado e o programa termina imediatamente para impedir o uso não autorizado.

## Organização das abas do editor

- **Editor: Vídeo** – ajuste a resolução, codec, comportamento do slideshow e configure o encerramento (fade out) que escurece a imagem enquanto reduz o áudio.
- **Editor: Áudio** – concentre-se apenas nos volumes da narração e da trilha sonora, sem controles de encerramento duplicados.
