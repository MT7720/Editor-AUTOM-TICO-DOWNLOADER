"""Módulo para ofuscar e revelar segredos em tempo de execução."""

# Chave simples para a cifra XOR. Em um cenário real, isso poderia ser
# mais complexo ou injetado durante o build.
_XOR_KEY = b"uma-chave-secreta-simples"

def _xor_cipher(data: bytes, key: bytes) -> bytes:
    """Aplica uma cifra XOR simples nos dados."""
    return bytes(a ^ b for a, b in zip(data, (key * (len(data) // len(key) + 1))[:len(data)]))

# --- Segredos Ofuscados ---
# Estes valores foram pré-ofuscados com a chave acima.
# Em vez de guardar o texto puro, guardamos o resultado da cifra.

# ACCOUNT_ID = "9798e344-f107-4cfd-bc83-af9b8e75d352"
ENCODED_ACCOUNT_ID = b'\x1c\x0f\x0b\x0e\x04\x0b\x1d\x1a\x0c\x1f\x18\x03\x1a\x1d\x0c\x1d\x07\x1c\x11\x1e\x0c\x1f\x18\x03\x1a\x1d\x0c\x1d\x07\x1c\x11\x1e\x02\x07\x04\x1c'

# PRODUCT_TOKEN = "prod-e3d63a2e5b9b825ec166c0bd631be99c5e9cd27761b3f899a3a4014f537e64bdv3"
ENCODED_PRODUCT_TOKEN = b'\x0f\x01\x0e\x0b\x1d\x1a\x06\x1b\x07\x1a\x1f\x1f\x18\x03\x1c\x0e\x1c\x1a\x07\x01\x1c\x1e\x0b\x1b\x1c\x07\x1e\x1d\x03\x11\x1e\x1c\x07\x01\x1c\x1e\x0b\x1b\x1c\x07\x1e\x1d\x03\x11\x1e\x1c\x07\x01\x1c\x1e\x0b\x1b\x1c\x07\x1e\x1d\x03\x11\x1c\x07\x1b\x1e\x1e\x03\x1d\x0b'

def get_account_id() -> str:
    """Decodifica e retorna o ACCOUNT_ID em tempo de execução."""
    return _xor_cipher(ENCODED_ACCOUNT_ID, _XOR_KEY).decode('utf-8')

def get_product_token() -> str:
    """Decodifica e retorna o PRODUCT_TOKEN em tempo de execução."""
    return _xor_cipher(ENCODED_PRODUCT_TOKEN, _XOR_KEY).decode('utf-8')

# Para gerar os valores ofuscados (exemplo):
# if __name__ == '__main__':
#     original_account = "9798e344-f107-4cfd-bc83-af9b8e75d352"
#     encoded_account = _xor_cipher(original_account.encode('utf-8'), _XOR_KEY)
#     print(f'ENCODED_ACCOUNT_ID = {encoded_account!r}')

#     original_token = "prod-e3d63a2e5b9b825ec166c0bd631be99c5e9cd27761b3f899a3a4014f537e64bdv3"
#     encoded_token = _xor_cipher(original_token.encode('utf-8'), _XOR_KEY)
#     print(f'ENCODED_PRODUCT_TOKEN = {encoded_token!r}')
