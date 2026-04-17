# os to access environment variables
import os
# base64 to encode and decode strings
import base64

# nacl for ed25519 signing and verification
from nacl.signing import SigningKey, VerifyKey

# Load signing key from environment - generate private key
SIGNING_KEY_HEX = os.getenv("CERT_EDDSA_SIGNING_KEY")

if SIGNING_KEY_HEX:
    # If a key exists in the environmeant, convert it from hex string → bytes → SigningKey object
    SIGNING_KEY = SigningKey(bytes.fromhex(SIGNING_KEY_HEX))
else:
    # If no key exists, generate a new random signing key
    SIGNING_KEY = SigningKey.generate()
    print("⚠️ WARNING: No persistent signing key set!")
    print("SAVE THIS KEY:", SIGNING_KEY.encode().hex())

    # Extract the public key from the signing key (used for verification)
VERIFY_KEY = SIGNING_KEY.verify_key 


def sign_data(data: str) -> str:
    """Sign data and return base64 signature"""
    # Sign the input string (convert to bytes first)
    signed = SIGNING_KEY.sign(data.encode('utf-8'))

    # Extract only the signature part and encode it to base64 for storage
    return base64.b64encode(signed.signature).decode('utf-8')


def verify_signature(data: str, signature_b64: str, public_key_hex: str) -> bool:
    """Verify using stored public key"""
    try:
        # Decode the base64 signature back into raw bytes
        signature = base64.b64decode(signature_b64)

        # Recreate the VerifyKey object using the stored public key (hex → bytes)
        verify_key = VerifyKey(bytes.fromhex(public_key_hex))

        # Verify that the signature matches the data
        # If invalid, this line will raise an exception
        verify_key.verify(data.encode('utf-8'), signature)

        # If no error occurs, signature is valid
        return True
    except Exception:
        # If any error occurs (invalid signature, wrong key, corrupted data)
        return False
    
    