# Editor-Autom-tico

Este repositório contém um editor de vídeo simplificado usando `ttkbootstrap` e utilitários para FFmpeg.

## Executando a interface gráfica

Para iniciar a interface gráfica, basta executar:

```bash
python main.py
```

> ℹ️ Antes de iniciar, garanta que o serviço de licenciamento possui acesso à
> internet e que as credenciais do Keygen foram provisionadas por um canal
> autenticado. É possível injectá-las via `KEYGEN_LICENSE_BUNDLE`,
> `KEYGEN_LICENSE_BUNDLE_PATH` ou pelas variáveis `KEYGEN_ACCOUNT_ID` e
> `KEYGEN_PRODUCT_TOKEN` (em ambientes controlados). Também pode preencher os
> campos `license_account_id` (sempre o UUID da **conta** Keygen, por exemplo
> `9798e344-f107-4cfd-bcd3-af9b8e75d352`) e `license_product_token` de
> `video_editor_config.json` ou distribuir o ficheiro
> `resources/license_credentials.json`. Sem esses valores, a activação não
> conseguirá contactar a API do Keygen e o processo de build falhará
> imediatamente.

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

> ✅ O ficheiro `security/product_token.dat` deixou de fazer parte dos artefatos
> monitorados pelo manifesto e não deve ser incluído nos pacotes distribuídos.
> As credenciais do Keygen devem continuar a ser injectadas dinamicamente via
> `KEYGEN_LICENSE_BUNDLE`/`KEYGEN_LICENSE_BUNDLE_PATH` durante o processo de
> build.

Caso precise atualizar manualmente o manifesto, execute:

```bash
python gerar_manifest.py
python tools/sign_runtime_manifest.py --manifest security/runtime_manifest.json --base-dir .
```

Ambos os passos requerem a variável `RUNTIME_GUARD_HMAC_KEY` configurada. Se um valor
inválido for informado, a etapa de build será interrompida com uma mensagem de erro.

## Monitoramento da licença

A activação do Editor Automático passou a ser exclusivamente online. Ao iniciar,
o `license_checker.py` tenta reutilizar a activação guardada em `license.json` e
revalidá-la junto da API do Keygen. Quando a licença não existe ou deixa de ser
válida, o utilizador vê apenas o `CustomLicenseDialog`, que apresenta o campo de
chave e chama `activate_new_license` imediatamente. Todas as mensagens de
progresso e de erro são exibidas no próprio diálogo, eliminando caixas de
mensagens adicionais.

O ficheiro `license.json` continua cifrado com AES-GCM usando uma chave derivada
do fingerprint da máquina. Qualquer alteração manual invalida o conteúdo e força
uma nova activação online.

### Provisionamento automático de credenciais

O módulo `security.secrets` procura as credenciais do Keygen nesta ordem:

1. `KEYGEN_LICENSE_BUNDLE` com um JSON assinado em Base64.
2. `KEYGEN_LICENSE_BUNDLE_PATH` apontando para o ficheiro JSON equivalente.
3. Variáveis `KEYGEN_ACCOUNT_ID` e `KEYGEN_PRODUCT_TOKEN` (opção de
   desenvolvimento ou CI controlado).
4. Ficheiro empacotado `resources/license_credentials.json` com o bundle
   provisionado.
5. Campos `license_account_id`, `license_product_token` e opcionalmente
   `license_api_base_url` em `video_editor_config.json`.

Escolha uma das alternativas acima para que o cliente consiga contactar o Keygen
sem intervenção manual. Os instaladores oficiais gerados pelo pipeline de CI/CD
recebem o bundle assinado automaticamente (via `KEYGEN_LICENSE_BUNDLE`), de modo
que o utilizador final continue a introduzir apenas a sua chave de licença. Caso
o bundle esteja ausente, `security.secrets` interrompe o build com uma mensagem
explícita para evitar executáveis sem credenciais. O guia
[`docs/keygen_cloud_licensing.md`](docs/keygen_cloud_licensing.md) explica como
gerar o bundle, distribuir os segredos e automatizar o abastecimento durante o
build.

### Revogação e reemissão

Os mecanismos de revogação permanecem inalterados: distribua um ficheiro com a
chave `revoked` (por defeito em `security/license_revocations.json`) ou exponha
um endpoint configurado em `LICENSE_REVOCATION_URL`. Sempre que uma licença for
reemitida, inclua o serial antigo na lista para impedir reutilizações.

### Migração de tokens offline

Implementações antigas que dependiam de tokens Ed25519 locais devem seguir as
orientações de [`docs/offline_license_issuance.md`](docs/offline_license_issuance.md)
para revogar os tokens herdados e migrar definitivamente para o fluxo online.

## Organização das abas do editor

- **Editor: Vídeo** – ajuste a resolução, codec, comportamento do slideshow e configure o encerramento (fade out) que escurece a imagem enquanto reduz o áudio.
- **Editor: Faixa** – personalize a faixa informativa exibida no início do conteúdo, escolhendo cores, duração, idioma e estilo do texto com pré-visualização integrada.
- **Editor: Áudio** – concentre-se apenas nos volumes da narração e da trilha sonora, sem controles de encerramento duplicados.
- **Editor: Introdução** – redija a mensagem inicial, escolha a fonte preferida, ative o negrito quando quiser dar mais presença ao texto e deixe o aplicativo traduzir automaticamente para cada idioma.
