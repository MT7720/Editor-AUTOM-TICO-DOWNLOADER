# Emissão Offline de Licenças

Este guia descreve como gerar e distribuir tokens de licença para o Editor Automático sem depender do Keygen. As licenças são representadas por _tokens_ compactos (payload JSON + assinatura Ed25519) que podem ser validados localmente pelo cliente.

## Pré-requisitos

- A máquina de emissão deve possuir o ficheiro `security/license_authority_keys.json` com a chave privada da autoridade. Defina a variável de ambiente `LICENSE_AUTHORITY_KEY_FILE` caso utilize um caminho personalizado ou um _hardware security module_.
- O Python deve ter acesso às dependências listadas em `requirements.txt` (especialmente `cryptography`).

## Fluxo manual

1. Abra um _shell_ seguro na máquina de emissão.
2. Opcional: exporte `LICENSE_AUTHORITY_KEY_FILE=/caminho/para/keys.json` caso os segredos residam fora do repositório.
3. Execute o seguinte trecho Python para gerar um token individual:

   ```python
   from datetime import datetime, timedelta, timezone
   from security.license_authority import issue_license_token

   token = issue_license_token(
       customer_id="cliente-123",
       fingerprint="fp-da-maquina",
       expiry=datetime.now(timezone.utc) + timedelta(days=365),
       seats=3,
   )
   print(token)
   ```

4. Entregue o token ao cliente pelo canal seguro estabelecido (por exemplo, portal de clientes ou ticket assinado).

## Emissão em lote via CLI

Para automatizar a geração de múltiplos tokens, prepare um ficheiro CSV com as colunas obrigatórias `customer_id`, `fingerprint`, `expiry` (ISO 8601) e `seats`. Uma coluna `serial` é opcional; se omitida, um identificador aleatório será atribuído.

```csv
customer_id,fingerprint,expiry,seats
cliente-1,fingerprint-aaaa,2025-01-01T00:00:00Z,5
cliente-2,fingerprint-bbbb,2024-08-15T12:00:00Z,2
```

Em seguida, execute:

```bash
python -m security.license_authority --input pedidos.csv --output tokens.json
```

O resultado `tokens.json` conterá uma lista de objectos com o token gerado, o `customer_id` e o `serial` associado. Distribua cada token individualmente e guarde o `serial` para auditorias ou revogações futuras.

## Lista de revogação

- O cliente lê por padrão `security/license_revocations.json`, que deve possuir a estrutura `{ "revoked": ["serial-1", "serial-2"] }`.
- Para actualizar automaticamente a partir de um serviço interno, forneça um endpoint HTTPS que devolva o mesmo JSON e defina `LICENSE_REVOCATION_URL` nas estações cliente.
- Sempre que um token for substituído, inclua o número de série antigo nesta lista. O `license_checker.py` cacheia as revogações por `LICENSE_REVOCATION_REFRESH` segundos (3600 por defeito).

## Migração de licenças Keygen

- Chaves no formato antigo (por exemplo, `AAAA-BBBB-CCCC-DDDD`) não são mais aceites. Ao introduzir uma chave dessas, a aplicação mostrará uma mensagem explicando a necessidade de solicitar um token offline.
- Para converter uma base instalada, gere novos tokens para cada cliente/máquina usando o fluxo acima. Entregue os tokens e, após confirmação, inclua os seriais antigos na lista de revogação para impedir reutilizações.
- O ficheiro de licença existente (`license.json`) continuará cifrado; ao guardar a nova activação a aplicação substitui automaticamente o conteúdo antigo.

## Boas práticas

- Nunca armazene a chave privada da autoridade no repositório ou em máquinas cliente. Utilize cofres (Azure Key Vault, AWS KMS, etc.) ou _hardware security modules_.
- Restrinja o acesso ao CSV de pedidos e ao ficheiro `tokens.json`, pois contêm identificadores sensíveis dos clientes.
- Versione a lista de revogações e mantenha registos de quando cada serial foi revogado.
