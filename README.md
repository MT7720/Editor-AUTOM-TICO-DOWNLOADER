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

## Processo de build seguro

O pipeline de empacotamento exige uma chave HMAC externa para assinar o manifesto de
integridade. Antes de executar `build_all.bat`, defina a variável de ambiente
`RUNTIME_GUARD_HMAC_KEY` com a chave codificada em Base64 (armazenada de forma segura,
fora do repositório). O script de build irá:

1. Regenerar o `security/runtime_manifest.json` com a lista de recursos críticos.
2. Assinar cada entrada utilizando `tools/sign_runtime_manifest.py`.
3. Incorporar o manifesto assinado no pacote final.

Caso precise atualizar manualmente o manifesto, execute:

```bash
python gerar_manifest.py
python tools/sign_runtime_manifest.py --manifest security/runtime_manifest.json --base-dir .
```

Ambos os passos requerem a variável `RUNTIME_GUARD_HMAC_KEY` configurada. Se um valor
inválido for informado, a etapa de build será interrompida com uma mensagem de erro.

## Monitoramento da licença

A activação do Editor Automático é agora completamente offline. Cada licença é emitida como um token compacto assinado com Ed25519 pela autoridade interna (`security/license_authority.py`). O cliente embute a chave pública correspondente e valida localmente o token, garantindo que:

- o `fingerprint` da máquina está incluído no payload e coincide com o equipamento actual;
- a data de expiração (`exp`) ainda não foi atingida; e
- o número de série (`serial`) não aparece na lista de revogações distribuída.

O ficheiro `license.json` continua cifrado com AES-GCM usando uma chave derivada do fingerprint da máquina. Qualquer alteração manual invalida o ficheiro e força nova activação.

> ⚠️ As credenciais do Keygen (account ID e product token) deixaram de ser
> embutidas no código. O módulo `security.secrets` exige um pacote de segredos
> entregue por canal autenticado (`KEYGEN_LICENSE_BUNDLE` ou
> `KEYGEN_LICENSE_BUNDLE_PATH`). Consulte [`docs/keygen_cloud_licensing.md`](docs/keygen_cloud_licensing.md)
> para instruções sobre como gerar o bundle durante o build e injectá-lo via
> variáveis de ambiente seguras.

### Revogação e reemissão

Para remover acessos comprometidos, distribua periodicamente um ficheiro JSON com a chave `revoked` contendo a lista de seriais revogados (por defeito em `security/license_revocations.json`). Também é possível apontar `LICENSE_REVOCATION_URL` para um endpoint HTTPS que devolve o mesmo formato. O `license_checker.py` actualiza e utiliza esta lista durante as verificações periódicas, encerrando a aplicação caso detecte um token revogado.

Quando for necessário reemitir uma licença, gere um novo token com `security.license_authority` e entregue-o ao cliente. Tokens antigos permanecerão inválidos assim que o número de série antigo constar da lista de revogação.

### Fluxo de emissão offline

O módulo `security/license_authority.py` inclui funções reutilizáveis e uma pequena ferramenta de automação para emissão em lote. Consulte [`docs/offline_license_issuance.md`](docs/offline_license_issuance.md) para instruções completas sobre a geração dos tokens, bem como orientações de migração para quem ainda utiliza chaves Keygen legadas.

Para equipas que pretendem continuar a gerir clientes e políticas através do Keygen, o guia [`docs/keygen_cloud_licensing.md`](docs/keygen_cloud_licensing.md) descreve como criar licenças na plataforma e gerar os tokens offline compatíveis com o Editor Automático.

## Organização das abas do editor

- **Editor: Vídeo** – ajuste a resolução, codec, comportamento do slideshow e configure o encerramento (fade out) que escurece a imagem enquanto reduz o áudio.
- **Editor: Faixa** – personalize a faixa informativa exibida no início do conteúdo, escolhendo cores, duração, idioma e estilo do texto com pré-visualização integrada.
- **Editor: Áudio** – concentre-se apenas nos volumes da narração e da trilha sonora, sem controles de encerramento duplicados.
- **Editor: Introdução** – redija a mensagem inicial, escolha a fonte preferida, ative o negrito quando quiser dar mais presença ao texto e deixe o aplicativo traduzir automaticamente para cada idioma.
