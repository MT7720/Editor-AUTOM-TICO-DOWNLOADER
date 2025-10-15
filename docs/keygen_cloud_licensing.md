# Fluxo de Licenciamento com Keygen.sh

Este guia descreve o novo processo de activação totalmente online do Editor
Automático. O cliente deixa de aceitar bundles seleccionados manualmente e passa
a contactar a API do Keygen assim que o utilizador informa a chave de licença no
`CustomLicenseDialog`.

## 1. Preparar a conta

1. Aceda a [https://app.keygen.sh/](https://app.keygen.sh/) e crie uma conta ou
   utilize uma existente.
2. Dentro da conta, crie um **Product** para o Editor Automático. Guarde o
   `ACCOUNT ID` apresentado no painel (por omissão, o projecto utiliza
   `9798e344-f107-4cfd-bcd3-af9b8e75d352`).
3. Em *Settings → Product Tokens*, gere um **Product Token** de longa duração.
   Guarde-o num cofre e nunca o distribua directamente aos clientes.
4. Configure as **Policies** com a quantidade de máquinas, duração e demais
   parâmetros comerciais. O identificador de cada política será utilizado ao
   emitir licenças.

## 2. Provisionar as credenciais para o cliente

O módulo `security.secrets` procura automaticamente os dados de `account_id`,
`product_token` e `api_base_url` nas seguintes origens (em ordem de prioridade):

1. **`KEYGEN_LICENSE_BUNDLE`** – cadeia Base64 contendo o JSON assinado gerado
   pelo broker interno. Utilize esta opção para pipelines CI/CD ou scripts de
   build temporários.
2. **`KEYGEN_LICENSE_BUNDLE_PATH`** – caminho para o ficheiro JSON assinado com
   o mesmo conteúdo do item anterior. Certifique-se de que o ficheiro possui
   permissões restritivas (`chmod 600` em POSIX).
3. **Variáveis individuais (`KEYGEN_ACCOUNT_ID` e `KEYGEN_PRODUCT_TOKEN`)** –
   destinadas a ambientes controlados. Prefira os bundles assinados sempre que
   possível.
4. **`resources/license_credentials.json`** – ficheiro empacotado juntamente
   com o executável PyInstaller. Deve conter o JSON assinado e permanecer fora
   do repositório.
5. **Campos `license_account_id`, `license_product_token` e
   `license_api_base_url` em `video_editor_config.json`** – úteis para imagens de
   máquina virtual ou pacotes MSI que precisam transportar os segredos de forma
   declarativa. Valores relativos em `license_credentials_path` continuam
   suportados para apontar para bundles externos.

Escolha um único método e garanta que os ficheiros sejam protegidos durante a
transmissão e o armazenamento. Após o build, remova quaisquer credenciais
temporárias das máquinas de compilação.

## 3. Autoridade de licenças e chaves

- A emissão de tokens Ed25519 acontece exclusivamente em infraestrutura
  controlada (servidores de build ou pipelines internos). A chave privada nunca
  é adicionada ao repositório nem copiada para estações de desenvolvimento.
- Os pipelines devem injectar o caminho para a chave através da variável
  ``LICENSE_AUTHORITY_KEY_FILE`` ao executar ``security.license_authority`` ou
  ``tools/keygen_license_cli.py issue-token``. Fora destes ambientes a chave não
  é carregada e a emissão falha por segurança.
- O cliente distribui apenas ``security/license_authority_public_key.json``, que
  contém a chave pública embutida e suficiente para validar assinaturas. As
  operações de activação continuam a depender do Keygen; os tokens offline
  servem apenas para compatibilidade com instalações antigas.

## 4. Automatizar builds e distribuição

Antes de executar `build_all.bat`, injete as credenciais através de uma das
opções anteriores. O script aborta caso nenhum segredo seja encontrado.
Distribuições oficiais devem incluir apenas os ficheiros empacotados
necessários (`resources/license_credentials.json`, se for o caso); evite copiar
credenciais adicionais para o instalador.

## 5. Activação no cliente

Ao iniciar, o `license_checker.py` tenta reutilizar a activação guardada em
`license.json` e revalida-la junto ao Keygen. Caso não haja licença válida, o
utilizador verá apenas o `CustomLicenseDialog`, que recolhe a chave e chama
`activate_new_license`. O diálogo mostra o estado da operação (aguardando,
problemas de rede, credenciais ausentes) e fecha-se automaticamente quando a
activação é concluída.

O ficheiro `license.json` permanece cifrado com AES-GCM a partir do fingerprint
local. Alterações manuais invalidam o conteúdo e desencadeiam uma nova activação
online.

## 6. Revogações e manutenção

Actualize periodicamente `security/license_revocations.json` ou configure o
endpoint indicado por `LICENSE_REVOCATION_URL`. Ao detectar um serial revogado,
a aplicação encerra e solicita nova activação. Utilize as ferramentas em
`tools/keygen_license_cli.py` para consultar políticas, criar licenças e gerir
máquinas activadas.

## 7. Migração de instalações antigas

Ambientes que ainda utilizam tokens Ed25519 emitidos offline devem seguir o
roteiro de [`docs/offline_license_issuance.md`](docs/offline_license_issuance.md)
para revogar os tokens legados e proceder com a activação online. Após a
migração, remova quaisquer bundles antigos e confirme que apenas os métodos
listados acima permanecem activos.
