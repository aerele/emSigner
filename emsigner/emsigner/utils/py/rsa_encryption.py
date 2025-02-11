from base64 import b64encode

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA


class RSAEncryption:
	def __init__(self, pubcertificate_path):
		with open(pubcertificate_path) as f:
			pub_key = f.read()
			self.cipher_rsa = PKCS1_v1_5.new(RSA.importKey(pub_key))

	def encrypt(self, raw_data):
		return b64encode(self.cipher_rsa.encrypt(raw_data))
