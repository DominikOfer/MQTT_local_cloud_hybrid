#original example from here: https://gist.github.com/syedrakib/d71c463fc61852b8d366 heavily edited and added salt.
#AES encryption with salt

from Crypto.Cipher import AES
import base64, os

def encrypt_message(private_msg, password, padding_character):
	salt = os.urandom(16)

	secret_key = base64.b64decode(password) + salt
	# use the decoded secret key to create a AES cipher
	cipher = AES.new(secret_key)
	# pad the private_msg
	# because AES encryption requires the length of the msg to be a multiple of 16
	padded_private_msg = private_msg + (padding_character * ((16-len(private_msg)) % 16))
	# use the cipher to encrypt the padded message
	encrypted_msg = cipher.encrypt(padded_private_msg)
	# encode the encrypted msg for storing safely in the database
	encoded_encrypted_msg = base64.b64encode(salt + encrypted_msg)
	#encoded_encrypted_msg = base64.b64encode(encrypted_msg)
	# return encoded encrypted message
	return encoded_encrypted_msg#base64.b64encode(salt) + encoded_encrypted_msg

def decrypt_message(encoded_encrypted_msg, password, padding_character):
	if type(encoded_encrypted_msg) == str:
		encoded_encrypted_msg = encoded_encrypted_msg.encode('utf-8')

	decoded_encrypted_msg = base64.b64decode(encoded_encrypted_msg)
	salt = decoded_encrypted_msg[0:16]
	ciphertext_sans_salt = decoded_encrypted_msg[16:]

	# decode the encoded encrypted message and encoded secret key
	secret_key = base64.b64decode(password) + salt
	encrypted_msg = ciphertext_sans_salt
	# use the decoded secret key to create a AES cipher
	cipher = AES.new(secret_key)
	# use the cipher to decrypt the encrypted message
	decrypted_msg = cipher.decrypt(encrypted_msg)
	decrypted_msg = decrypted_msg.decode("utf-8")
	# unpad the encrypted message
	unpadded_decrypted_msg = decrypted_msg.rstrip(padding_character)
	# return a decrypted original private message
	return unpadded_decrypted_msg
