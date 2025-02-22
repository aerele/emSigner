from base64 import b64decode, b64encode

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


class AES_ECB_Cipher:
	def __init__(self, key):
		self.key = key

	def encrypt(self, raw_data, encode=True):
		cipher = AES.new(self.key, AES.MODE_ECB)
		padded_data = pad(raw_data.encode() if isinstance(raw_data, str) else raw_data, AES.block_size)
		encrypted = cipher.encrypt(padded_data)
		return b64encode(encrypted) if encode else encrypted

	def decrypt(self, encrypted_data, decode=True):
		cipher = AES.new(self.key, AES.MODE_ECB)
		decoded_data = b64decode(encrypted_data)
		decrypted = cipher.decrypt(decoded_data)
		return unpad(decrypted, AES.block_size).decode() if decode else unpad(decrypted, AES.block_size)
