# Editor-Autom-tico

Este repositório contém um editor de vídeo simplificado usando `ttkbootstrap` e utilitários para FFmpeg.

## Executando a interface gráfica

Para iniciar a interface gráfica, basta executar:

```bash
python main.py
```

Durante o desenvolvimento, as verificações de integridade do `security.runtime_guard`
ficam desativadas para permitir ajustes livres no código-fonte. A validação de hashes
dos recursos é aplicada apenas nos executáveis empacotados (por exemplo, builds
gerados com PyInstaller), garantindo que distribuições oficiais mantenham os ficheiros
críticos intactos.

## Monitoramento da licença

Depois de validada, a aplicação continua a verificar periodicamente o status da licença junto ao Keygen utilizando o identificador salvo no ficheiro `license.json`. Em caso de falha de rede temporária, o processo regista o erro nos logs e aguarda um intervalo crescente (exponencial) antes de repetir a verificação, evitando encerramentos acidentais. Caso o servidor informe que a licença expirou ou se tornou inválida, o utilizador é avisado e o programa termina imediatamente para impedir o uso não autorizado.

O token do produto utilizado para contactar a API da Keygen **não** está mais presente no código-fonte. Durante o build (ou execução em desenvolvimento), defina a variável de ambiente `KEYGEN_PRODUCT_TOKEN` ou forneça um caminho através de `KEYGEN_PRODUCT_TOKEN_FILE` apontando para um ficheiro seguro contendo o token. Alternativamente, o binário distribuído inclui o recurso protegido `security/product_token.dat`, carregado automaticamente quando nenhuma variável de ambiente está definida. Se o token continuar inacessível (por exemplo, após uma remoção acidental do ficheiro), reinstale a aplicação ou contacte o suporte técnico. Os pipelines de CI/CD devem injectar esse segredo antes de executar os testes ou distribuir os binários.

O ficheiro `license.json` armazenado no diretório de dados da aplicação é agora cifrado com AES-GCM usando uma chave derivada do _fingerprint_ da máquina. Esse identificador é obtido preferencialmente através de APIs nativas do Windows (MachineGuid, SMBIOS ou número de série do volume) e apenas recorre a dados multiplataforma (`uuid.getnode` e `platform.uname`) como último recurso, eliminando dependências de comandos externos. Cada payload inclui um _hash_ autenticado; qualquer tentativa de adulteração resulta na eliminação do ficheiro e na necessidade de reativação manual da licença.

## Organização das abas do editor

- **Editor: Vídeo** – ajuste a resolução, codec, comportamento do slideshow e configure o encerramento (fade out) que escurece a imagem enquanto reduz o áudio.
- **Editor: Áudio** – concentre-se apenas nos volumes da narração e da trilha sonora, sem controles de encerramento duplicados.
