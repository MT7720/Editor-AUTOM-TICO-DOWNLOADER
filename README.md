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
críticos intactos. O processo de geração da chave de assinatura e a rotação das
assinaturas do manifesto estão documentados em [`docs/runtime_guard_key_rotation.md`](docs/runtime_guard_key_rotation.md).

## Monitoramento da licença

A activação do Editor Automático é agora completamente offline. Cada licença é emitida como um token compacto assinado com Ed25519 pela autoridade interna (`security/license_authority.py`). O cliente embute a chave pública correspondente e valida localmente o token, garantindo que:

- o `fingerprint` da máquina está incluído no payload e coincide com o equipamento actual;
- a data de expiração (`exp`) ainda não foi atingida; e
- o número de série (`serial`) não aparece na lista de revogações distribuída.

O ficheiro `license.json` continua cifrado com AES-GCM usando uma chave derivada do fingerprint da máquina. Qualquer alteração manual invalida o ficheiro e força nova activação.

### Revogação e reemissão

Para remover acessos comprometidos, distribua periodicamente um ficheiro JSON com a chave `revoked` contendo a lista de seriais revogados (por defeito em `security/license_revocations.json`). Também é possível apontar `LICENSE_REVOCATION_URL` para um endpoint HTTPS que devolve o mesmo formato. O `license_checker.py` actualiza e utiliza esta lista durante as verificações periódicas, encerrando a aplicação caso detecte um token revogado.

Quando for necessário reemitir uma licença, gere um novo token com `security.license_authority` e entregue-o ao cliente. Tokens antigos permanecerão inválidos assim que o número de série antigo constar da lista de revogação.

### Fluxo de emissão offline

O módulo `security/license_authority.py` inclui funções reutilizáveis e uma pequena ferramenta de automação para emissão em lote. Consulte [`docs/offline_license_issuance.md`](docs/offline_license_issuance.md) para instruções completas sobre a geração dos tokens, bem como orientações de migração para quem ainda utiliza chaves Keygen legadas.

## Organização das abas do editor

- **Editor: Vídeo** – ajuste a resolução, codec, comportamento do slideshow e configure o encerramento (fade out) que escurece a imagem enquanto reduz o áudio.
- **Editor: Áudio** – concentre-se apenas nos volumes da narração e da trilha sonora, sem controles de encerramento duplicados.
