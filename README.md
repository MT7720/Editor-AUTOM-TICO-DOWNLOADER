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

Depois de validada, a aplicação continua a verificar periodicamente o token de licença armazenado em `license.json`. O conteúdo é assinado com Ed25519 pela autoridade interna (`security/license_authority.py`) e contém o identificador do cliente, _fingerprint_ da máquina, número de lugares e uma data de expiração opcional. Durante a execução o cliente volta a verificar a assinatura localmente, consulta a lista de revogações configurada através da variável de ambiente `LICENSE_REVOCATION_URL` (ficheiro local ou endpoint HTTPS com JSON) e garante que o número de série do token é igual ou superior ao mínimo exigido para a licença. Em caso de falha temporária ao actualizar a lista de revogações, o último token válido continua a ser aceite para evitar interrupções inesperadas; contudo, o monitor continua a tentar novamente até obter a confirmação.

O utilitário `security/license_authority.py` centraliza a emissão de tokens. Utilize-o directamente, definindo o caminho da chave privada com `LICENSE_AUTHORITY_PRIVATE_KEY_PATH`, ou invoque-o via CLI:

```bash
# emitir uma licença isolada
python -m security.license_authority issue CUST-001 3f0c... \
  --license-id LIC-001 --seat-count 2 --expiry "2024-12-31T23:59:59Z"

# emissão em massa a partir de um CSV
python -m security.license_authority bulk clientes.csv tokens.json
```

O ficheiro CSV deve conter as colunas `customer_id` e `fingerprint`, podendo opcionalmente indicar `expiry`, `license_id`, `seat_count` e `serial`. O output (`tokens.json`) apresenta a lista de clientes com os respectivos tokens prontos para distribuição. Para ambientes de produção recomenda-se armazenar a chave privada num cofre e injectá-la através da variável de ambiente `LICENSE_AUTHORITY_PRIVATE_KEY_PATH`; o repositório inclui apenas chaves de desenvolvimento para efeitos de teste automatizado.

O ficheiro `license.json` guardado no diretório de dados continua a ser cifrado com AES-GCM utilizando uma chave derivada do _fingerprint_ da máquina. Os identificadores são obtidos preferencialmente através das APIs nativas do Windows (MachineGuid, SMBIOS ou número de série do volume) e apenas recorrem a dados multiplataforma (`uuid.getnode` e `platform.uname`) como último recurso. Qualquer tentativa de adulteração remove o ficheiro e exige uma nova activação.

### Migração a partir das activações Keygen

1. Exporte da plataforma Keygen a lista de licenças activas e respectivos clientes.
2. No posto do utilizador, recolha o ficheiro `license.json` existente para obter o _fingerprint_ registado (ou solicite o fingerprint directamente através do menu de activação).
3. Gere novos tokens offline com `security/license_authority.py`, preenchendo `license_id` e `serial` para que futuras reemissões possam ser forçadas via `minimum_serial` na lista de revogações.
4. Distribua os tokens emitidos aos clientes. Ao introduzir um token válido, o ficheiro `license.json` antigo é substituído pelo formato assinado e passa a beneficiar das verificações offline e da lista de revogação periódica.

A variável de ambiente `KEYGEN_PRODUCT_TOKEN` permanece aceite apenas para compatibilidade retroactiva com scripts legados, mas deixou de ser necessária para activar ou validar licenças.

## Organização das abas do editor

- **Editor: Vídeo** – ajuste a resolução, codec, comportamento do slideshow e configure o encerramento (fade out) que escurece a imagem enquanto reduz o áudio.
- **Editor: Áudio** – concentre-se apenas nos volumes da narração e da trilha sonora, sem controles de encerramento duplicados.
