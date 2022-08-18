import hmac
import hashlib


def generate_hash(key, message):
    if type(key) == str:
        key = key.encode('utf-8')

    if type(message) == str:
        message = message.encode('utf-8')

    h = hmac.new(key, message, hashlib.sha256)
    return h.hexdigest()
