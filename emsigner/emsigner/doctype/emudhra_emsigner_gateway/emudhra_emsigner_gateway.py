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

import base64, json
import binascii
import hashlib
import os
import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.Util.Padding import pad

def generate_hash(encrypted_data):
    """Generate SHA256 hash of the encrypted data."""
    hash_object = hashlib.sha256(encrypted_data.encode('utf-8'))
    return hash_object.hexdigest()

def load_key(file_path):
    """Load a key from the provided file path."""
    with open(file_path, "rb") as key_file:
        return key_file.read()

def encrypt_data(data, session_key):
    """Encrypt data using AES in ECB mode without an IV."""
    cipher = AES.new(session_key, AES.MODE_ECB)
    padded_data = pad(data, AES.block_size)
    return base64.b64encode(cipher.encrypt(padded_data)).decode()

def encrypt_session_key(session_key, public_key):
    """Encrypt a symmetric key using an RSA public key."""
    public_key = RSA.import_key(public_key)
    cipher = PKCS1_v1_5.new(public_key)
    ciphertext = cipher.encrypt(session_key)
    return base64.b64encode(ciphertext).decode()

def send_request(step5_output, step2_output, step4_output, url):
    """Send an HTTP POST request with the encrypted data."""
    payload = {
        'Parameter1': step5_output,
        'Parameter2': step2_output,
        'Parameter3': step4_output
    }
    print(payload)
    response = requests.post(url, json=payload)
    return response.text

def test_em():
    # Example input data
    data = json.dumps({
        "Name": "test",
        "FileType": "PDF",
        "SelectPage": "ALL",
        "SignaturePosition": "Bottom-Right",
        "AuthToken": "84387b11-b039-4759-9986-22f2524719d8",
        "File": "JVBERi0xLjMKMyAwIG9iago8PC9UeXBlIC9QYWdlCi9QYXJlbnQgMSAwIFIKL1Jlc291cmNlcyAyIDAgUgovQ29udGVudHMgNCAwIFI+PgplbmRvYmoKNCAwIG9iago8PC9GaWx0ZXIgL0ZsYXRlRGVjb2RlIC9MZW5ndGggMzQ4Pj4Kc3RyZWFtCnicbZHNTsMwEITvPMUcQSpu/oO5ASVCnCo1F45us2kDSRzZjkp5euzUoqAgWYoVzcy3no3wehWwNMfx6rHEsggRZiwIUNZ4Lt2vKOAsi5DzxKnKCtcb0Q0tYb0qsJK7saPe3KB89/plESGM/kTEIQs58piz4JxQHhoNewT0JWtPPSlhqMKom36P9ckcZA/RVzAHQuE0bbNVQp0YfgF9ehiwPJ7S3+SInehtDFmnxXgXjMROkUVMvMrPrnFszAGGPs0CTSf2pBcwYtu6r6N3UhGbAbM0YcEZWNjMUZGGrM/Ay6vu574oZRmffLd4GrWRXfPlaKilG8YRtTlZ+sya8pzFibduxmGQyliXQje2pnHEwU0/92V82sfkexhtDU6Hre3i4x91ErAs9eoXEhWpaahaSmOvcjCN7Oe25C5mPPN9UItaEU2N+yf6XRiy1bgVCI2eqKLqp9pvvYa8wwplbmRzdHJlYW0KZW5kb2JqCjEgMCBvYmoKPDwvVHlwZSAvUGFnZXMKL0tpZHMgWzMgMCBSIF0KL0NvdW50IDEKL01lZGlhQm94IFswIDAgNTk1LjI4IDg0MS44OV0KPj4KZW5kb2JqCjUgMCBvYmoKPDwvVHlwZSAvRm9udAovQmFzZUZvbnQgL0hlbHZldGljYS1Cb2xkCi9TdWJ0eXBlIC9UeXBlMQovRW5jb2RpbmcgL1dpbkFuc2lFbmNvZGluZwo+PgplbmRvYmoKNiAwIG9iago8PC9UeXBlIC9Gb250Ci9CYXNlRm9udCAvSGVsdmV0aWNhCi9TdWJ0eXBlIC9UeXBlMQovRW5jb2RpbmcgL1dpbkFuc2lFbmNvZGluZwo+PgplbmRvYmoKMiAwIG9iago8PAovUHJvY1NldCBbL1BERiAvVGV4dCAvSW1hZ2VCIC9JbWFnZUMgL0ltYWdlSV0KL0ZvbnQgPDwKL0YxIDUgMCBSCi9GMiA2IDAgUgo+PgovWE9iamVjdCA8PAo+Pgo+PgplbmRvYmoKNyAwIG9iago8PAovUHJvZHVjZXIgKFB5RlBERiAxLjcuMiBodHRwOi8vcHlmcGRmLmdvb2dsZWNvZGUuY29tLykKL0NyZWF0aW9uRGF0ZSAoRDoyMDI1MDEyODA2NTM0MCkKPj4KZW5kb2JqCjggMCBvYmoKPDwKL1R5cGUgL0NhdGFsb2cKL1BhZ2VzIDEgMCBSCi9PcGVuQWN0aW9uIFszIDAgUiAvRml0SCBudWxsXQovUGFnZUxheW91dCAvT25lQ29sdW1uCj4+CmVuZG9iagp4cmVmCjAgOQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDA1MDUgMDAwMDAgbiAKMDAwMDAwMDc4OSAwMDAwMCBuIAowMDAwMDAwMDA5IDAwMDAwIG4gCjAwMDAwMDAwODcgMDAwMDAgbiAKMDAwMDAwMDU5MiAwMDAwMCBuIAowMDAwMDAwNjkzIDAwMDAwIG4gCjAwMDAwMDA5MDMgMDAwMDAgbiAKMDAwMDAwMTAxMiAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9TaXplIDkKL1Jvb3QgOCAwIFIKL0luZm8gNyAwIFIKPj4Kc3RhcnR4cmVmCjExMTUKJSVFT0YK",
        "PageNumber": "1",
        "PreviewRequired": True,
        "PagelevelCoordinates": "",
        "CustomizeCoordinates": "",
        "SUrl": "www.google.com",
        "FUrl": "www.youtube.com",
        "CUrl": "www.w3schools.com",
        "ReferenceNumber": "",
        "Enableuploadsignature": True,
        "Enablefontsignature": True,
        "EnableDrawSignature": True,
        "EnableeSignaturePad": False,
        "IsCompressed": False,
        "IsCosign": False,
        "Storetodb": False,
        "IsGSTN": False,
        "IsGSTN3B": False,
        "IsCustomized": False,
        "eSign_SignerId": "",
        "TransactionNumber": "",
        "SignatureMode": 1,
        "AuthenticationMode": 1,
        "EnableInitials": False,
        "IsInitialsCustomized": False,
        "SelectInitialsPage": None,
        "InitialsPosition": None,
        "InitialsCustomizeCoordinates": "",
        "InitialsPagelevelCordinates": "",
        "InitialsPageNumbers": "",
        "ValidateAllPlaceholders": False,
        "Anchor": "Middle",
        "InitialSearchtext": None,
        "InitialsAnchor": None,
        "Reason": "test",
        "EnableFetchSignerInfo": None
    })
    
    # Generate symmetric key
    session_key = os.urandom(16)
    session_key = binascii.hexlify(session_key).decode('utf-8').encode('utf-8')
    print(session_key, "session_key")
    
    # Encrypt data using AES in ECB mode
    encrypted_payload = encrypt_data(data.encode("utf-8"), session_key)
    print(encrypted_payload, "encrypted_payload")
    
    # Generate hash of encrypted data
    data_hash = generate_hash(encrypted_payload)
    encrypted_hash_result = encrypt_data(data_hash.encode("utf-8"), session_key)
    print(encrypted_hash_result, "encrypted_hash_result")
    
    # Load public key and encrypt symmetric key
    public_key = load_key("/home/vimalnarmu/Documents/public_key.txt")
    encrypted_key = encrypt_session_key(session_key, public_key)
    
    # Send the request
    url = "https://demosignergateway.emsigner.com/eMsecure/V3_0/Index"
    response = send_request(
        encrypted_key,
        encrypted_payload,
        encrypted_hash_result,
        url
    )

    print("Response from server:", response)
