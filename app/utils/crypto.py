import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _get_fernet():
    """Derive a Fernet key from SECRET_KEY using SHA-256."""
    secret = current_app.config['SECRET_KEY']
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    key = hashlib.sha256(secret).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)


def encrypt_token(plaintext):
    """Encrypt a token string using Fernet."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    return f.encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt_token(ciphertext):
    """Decrypt a token string. Returns None if decryption fails."""
    if not ciphertext:
        return ciphertext
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except (InvalidToken, Exception):
        return None
