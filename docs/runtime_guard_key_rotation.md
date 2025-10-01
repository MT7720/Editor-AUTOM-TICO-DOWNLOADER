# Runtime Guard – Rotação de Chave e Reassinatura do Manifesto

Este documento descreve como gerar uma nova chave de assinatura do manifesto,
armazená-la com segurança e reprocessar as assinaturas utilizadas pelo
`security/runtime_guard.py`.

## Visão Geral

1. **Gere uma nova chave HMAC** durante o processo de build (idealmente na
   pipeline de CI) e armazene-a como segredo da plataforma ou artefato seguro.
2. **Atualize a variável de ambiente `RUNTIME_GUARD_HMAC_KEY`** na etapa de
   build, fornecendo a chave codificada em Base64.
3. **Execute o script `tools/sign_runtime_manifest.py`** para recalcular os
   hashes dos artefatos monitorados e gerar as novas assinaturas.
4. **Distribua somente os artefatos assinados e a versão atualizada do
   `runtime_manifest.json`**. A chave secreta nunca deve ser incluída no
   repositório ou nos pacotes distribuídos.

## Gerando uma nova chave

```
openssl rand -base64 48 > runtime_guard_hmac.key
```

Armazene o conteúdo desse arquivo como segredo na infraestrutura de CI/CD.

## Reassinando o manifesto

Na etapa de build (após gerar os binários), execute:

```
export RUNTIME_GUARD_HMAC_KEY="$(cat runtime_guard_hmac.key)"
python tools/sign_runtime_manifest.py --base-dir . --executable default=dist/app.exe
```

Substitua `dist/app.exe` pelo caminho real do executável empacotado gerado pelo
PyInstaller ou ferramenta equivalente. Caso existam entradas adicionais para
executáveis, repita o parâmetro `--executable` para cada uma delas.

O script irá:

* recalcular os hashes dos arquivos listados em `security/runtime_manifest.json`;
* gerar assinaturas HMAC utilizando a chave fornecida; e
* sobrescrever o arquivo do manifesto com os novos valores.

## Rodando localmente para validação

Em ambientes de desenvolvimento, você pode usar uma chave temporária para
executar testes automatizados:

```
export RUNTIME_GUARD_HMAC_KEY="$(openssl rand -base64 32)"
python tools/sign_runtime_manifest.py
pytest tests/test_security_runtime_guard.py
```

Não faça commit da chave temporária – ela serve apenas para validar o fluxo.

## Rotação periódica

1. Gere uma nova chave seguindo o processo descrito acima.
2. Atualize o segredo correspondente na infraestrutura de CI/CD.
3. Reexecute o script `sign_runtime_manifest.py` durante o build para produzir
   novas assinaturas.
4. Distribua os artefatos resultantes e, se aplicável, atualize o manifesto no
   repositório.

Se o manifesto for versionado, inclua o arquivo atualizado (`security/runtime_manifest.json`)
no commit associado à release para manter a auditoria consistente.
