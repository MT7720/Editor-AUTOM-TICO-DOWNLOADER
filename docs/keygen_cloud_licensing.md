# Fluxo de Licenciamento com Keygen.sh

Este guia explica como preparar a conta Keygen, emitir licenças e gerar os tokens
compatíveis com o Editor Automático. O objectivo é aproveitar o Keygen para
gestão comercial (clientes, políticas e auditoria) mantendo a activação offline
através dos tokens assinados localmente.

## 1. Preparar a conta

1. Aceda a [https://app.keygen.sh/](https://app.keygen.sh/) e crie uma conta ou
   utilize uma existente.
2. Dentro da conta, crie um **Product** para o Editor Automático. Guarde o
   `ACCOUNT ID` apresentado no painel (por omissão, o projecto utiliza
   `9798e344-f107-4cfd-bc83-af9b8e75d352`).
3. Em *Settings → Product Tokens*, gere um **Product Token** de longa duração.
   Este valor **nunca** deve ser distribuído a clientes finais; guarde-o em um
   cofre seguro e exponha-o apenas para serviços internos (por exemplo, a
   pipeline CI/CD ou a máquina que irá emitir licenças).
4. Crie uma ou mais **Policies** conforme os planos de licenciamento desejados
   (ex.: número de máquinas, duração, modalidade de subscrição). O identificador
   de cada política será utilizado ao criar licenças.

## 2. Configurar variáveis de ambiente

Os utilitários do repositório esperam os seguintes valores:

```bash
export KEYGEN_ACCOUNT_ID="<ACCOUNT ID DA SUA CONTA>"
export KEYGEN_PRODUCT_TOKEN="<TOKEN DE PRODUTO GERADO NO PAINEL>"
# Opcional: definir um endpoint self-hosted para a API
# export KEYGEN_API_BASE_URL="https://api.keygen.sh/v1/accounts/<ACCOUNT ID>"
```

A aplicação desktop continua a validar os tokens offline com a chave pública
configurada em `security/license_authority_keys.json`. Certifique-se de que este
ficheiro contém o par de chaves Ed25519 correcto ou defina
`LICENSE_AUTHORITY_KEY_FILE` para apontar para a localização segura do par de
chaves.

## 3. Consultar políticas e criar licenças

O script `tools/keygen_license_cli.py` disponibiliza comandos para interagir com
a API do Keygen usando JSON:API. Para listar as políticas configuradas:

```bash
python tools/keygen_license_cli.py policies
```

Exemplo de saída:

```
Políticas disponíveis:
- ID: 23f1...c901
  Nome: Plano Anual
  Licenças máximas: 3
```

Para emitir uma nova licença associada à política acima:

```bash
python tools/keygen_license_cli.py create-license \
  --policy 23f1...c901 \
  --name "ACME Corp." \
  --email suporte@acme.test \
  --expiry 2026-01-31T23:59:59Z \
  --max-machines 3
```

O comando imprime o `id` e o `key` atribuídos pelo Keygen, juntamente com os
atributos devolvidos pela API. Guarde o identificador para futuras emissões ou
revogações.

## 4. Gerar tokens offline para os clientes

O Editor Automático espera receber um token compacto (payload + assinatura
Ed25519) no acto de activação. Para gerar o token a partir de uma licença
existente no Keygen:

```bash
python tools/keygen_license_cli.py issue-token \
  --license 1f4d...2aa1 \
  --fingerprint maquina-123 \
  --serial acme-maquina-123
```

O comando reutiliza `security/license_authority.py` para assinar os dados usando
as chaves internas e produzir um token compatível com o cliente. Se a licença no
Keygen possuir um campo `expiry`, o mesmo será adoptado automaticamente; caso
contrário, forneça `--expiry` com um timestamp ISO 8601.

A resposta JSON contém:

- `license`: o identificador da licença no Keygen;
- `fingerprint`: a impressão digital utilizada;
- `token`: o valor que deve ser entregue ao cliente (copie e cole no diálogo de
  activação);
- `expiry`, `seats` e `serial`: metadados úteis para registo interno.

Distribua apenas o campo `token` aos clientes finais. Os demais campos servem
para auditoria e podem ser armazenados em sistemas internos.

## 5. Utilizar as licenças no Editor Automático

1. Abra o Editor Automático na máquina do cliente.
2. Quando solicitado, cole o `token` gerado no passo anterior.
3. O `license_checker.py` irá validar a assinatura, verificar a expiração e
   assegurar que o `fingerprint` corresponde à máquina actual. Em seguida, o
   ficheiro cifrado `license.json` será actualizado com os dados da activação.

Caso seja necessário revogar o acesso, actualize a lista de seriais em
`security/license_revocations.json` (ou no endpoint configurado em
`LICENSE_REVOCATION_URL`). Ao detectar um serial revogado, a aplicação encerra
automaticamente e solicita uma nova activação.

## 6. Boas práticas adicionais

- Mantenha o `KEYGEN_PRODUCT_TOKEN` fora de máquinas de clientes. Utilize um
  serviço intermediário (como `security/token_broker_service.py`) quando for
  necessário distribuir credenciais temporárias para activação online.
- Documente os `serials` emitidos e mantenha um registo de que máquina/cliente
  recebeu cada token. Isso facilita revogações e reemissões.
- Periodicamente valide se as políticas e licenças no Keygen continuam alinhadas
  com os planos comerciais oferecidos.

Com estes passos, o Keygen passa a servir como a origem única de verdade para as
licenças, enquanto o Editor Automático mantém a activação offline e resistente a
alterações locais.
