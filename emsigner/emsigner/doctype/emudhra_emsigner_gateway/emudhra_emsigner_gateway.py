# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import frappe
from base64 import b64encode
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
import os
import json
from frappe.model.document import Document


class EmudhraemSignerGateway(Document):
	pass


def get_new_session_key():
	return get_random_bytes(32)

def encrypt_data_using_session_key(skey, data):
	data = json.dumps(data).encode('utf-8')
	cipher = AES.new(skey, AES.MODE_ECB)
	

	padded_data = pad(data, AES.block_size)

	encrypted_data = cipher.encrypt(padded_data)
	print(encrypted_data)

	cipher = AES.new(skey, AES.MODE_ECB)

	padded_data = cipher.decrypt(encrypted_data)

	data = unpad(padded_data, AES.block_size)

	print(json.loads(data.decode('utf-8')))

	return encrypted_data

skey = get_new_session_key()
data = {"name": "Sandy"}


encrypt_data_using_session_key(skey, data)

