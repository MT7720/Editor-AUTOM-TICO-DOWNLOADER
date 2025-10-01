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

O token de produto utilizado para contactar a API da Keygen **não** acompanha mais o binário. Durante o build (ou execução em desenvolvimento), defina a variável de ambiente `KEYGEN_PRODUCT_TOKEN` ou forneça um caminho através de `KEYGEN_PRODUCT_TOKEN_FILE` apontando para um ficheiro seguro contendo o token. Para ambientes de produção recomenda-se configurar o `security.token_broker_service`, que valida a chave de licença do utilizador e devolve um _token_ delegado de curta duração. Ao activar a aplicação, o `license_checker.py` utiliza a chave introduzida pelo utilizador para solicitar este token ao _broker_ definido em `KEYGEN_TOKEN_BROKER_URL`, guardando-o em cache apenas até perto da expiração. O endpoint deve exigir um segredo partilhado (`TOKEN_BROKER_SHARED_SECRET`) e nunca expor o `KEYGEN_PRODUCT_TOKEN` aos clientes finais.

Ao colocar o serviço de corretagem em produção:

1. Instale e execute `python -m security.token_broker_service` num ambiente controlado (por exemplo, atrás de um _reverse proxy_). Configure as variáveis `KEYGEN_PRODUCT_TOKEN`, `TOKEN_BROKER_SHARED_SECRET`, `TOKEN_BROKER_SCOPE` (opcional) e `TOKEN_BROKER_TOKEN_TTL` conforme as políticas internas.
2. Exponha apenas o endpoint `/v1/delegated-credentials` e utilize TLS para proteger o transporte.
3. Nas máquinas cliente, defina `KEYGEN_TOKEN_BROKER_URL` para o URL HTTPS do broker e forneça o segredo partilhado através de `KEYGEN_TOKEN_BROKER_SECRET` (por exemplo, injectado por um _installer_ ou sistema de gestão de dispositivos). Opcionalmente, redireccione `LICENSE_API_BASE_URL` para um _gateway_ interno caso deseje encapsular também o acesso à API do Keygen.
4. Garanta que o segredo nunca é gravado em disco em claro; utilize cofres de segredos do sistema operativo ou variáveis efémeras injectadas durante a activação.

O ficheiro `license.json` armazenado no diretório de dados da aplicação é agora cifrado com AES-GCM usando uma chave derivada do _fingerprint_ da máquina. Esse identificador é obtido preferencialmente através de APIs nativas do Windows (MachineGuid, SMBIOS ou número de série do volume) e apenas recorre a dados multiplataforma (`uuid.getnode` e `platform.uname`) como último recurso, eliminando dependências de comandos externos. Cada payload inclui um _hash_ autenticado; qualquer tentativa de adulteração resulta na eliminação do ficheiro e na necessidade de reativação manual da licença.

## Organização das abas do editor

- **Editor: Vídeo** – ajuste a resolução, codec, comportamento do slideshow e configure o encerramento (fade out) que escurece a imagem enquanto reduz o áudio.
- **Editor: Áudio** – concentre-se apenas nos volumes da narração e da trilha sonora, sem controles de encerramento duplicados.
