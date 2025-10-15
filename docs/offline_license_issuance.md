# Emissão Offline de Licenças (Descontinuada)

A partir da migração para activação exclusivamente online, o Editor Automático
já não aceita tokens Ed25519 emitidos localmente. Este documento explica como
identificar instalações antigas, revogar os tokens herdados e preparar a
transição para o fluxo descrito em
[`docs/keygen_cloud_licensing.md`](docs/keygen_cloud_licensing.md).

## 1. Inventariar tokens existentes

1. Recolha os ficheiros `license.json` das estações que ainda executam versões
   antigas.
2. Utilize `security/license_tools.py --inspect <ficheiro>` para extrair o
   `serial` e o `fingerprint` registados.
3. Registe os seriais num repositório seguro (planilha, base de dados ou sistema
   de tickets).

## 2. Revogar tokens antigos

1. Actualize `security/license_revocations.json` adicionando todos os seriais
   inventariados.
2. Se utilizar o endpoint configurado em `LICENSE_REVOCATION_URL`, publique a
   mesma lista para que as instalações detectem a revogação imediatamente.
3. Distribua uma actualização da aplicação contendo este repositório actualizado
   antes de iniciar a activação online.

## 3. Preparar a activação online

1. Siga o guia de [`docs/keygen_cloud_licensing.md`](docs/keygen_cloud_licensing.md)
   para provisionar `account_id` e `product_token` automaticamente.
2. Informe os clientes de que a activação passou a exigir ligação à internet e
   que o novo diálogo de licenciamento (`CustomLicenseDialog`) substitui os
   antigos fluxos com bundles locais.
3. Disponibilize novas chaves/licenças no painel do Keygen e comunique o
   processo de recolha da chave no diálogo. Builds sem credenciais deixam de ser
   produzidos, garantindo que apenas instaladores oficiais (que injectam o
   bundle automaticamente) chegam aos clientes.

## 4. Limpar artefactos obsoletos

- Remova `security/license_authority_keys.json` e quaisquer cópias locais da
  chave privada de emissão.
- Apague scripts personalizados que geravam tokens offline.
- Certifique-se de que `resources/license_credentials.json` contém apenas as
  credenciais oficiais do Keygen ou que os campos do `video_editor_config.json`
  estão actualizados.

Após concluir estes passos, todas as instalações utilizarão exclusivamente o
fluxo online suportado pelo Keygen, simplificando auditorias e revogações.
