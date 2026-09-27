package com.example.protector;

/**
 * Thin JNI wrapper around the native ChaCha20 + HMAC-SHA256 implementation.
 *
 * All key material and plaintext only ever exist inside native buffers and are
 * wiped with a secure zeroing routine once they are no longer needed.
 */
public final class NativeCrypto {

    static {
        System.loadLibrary("protector");
    }

    private NativeCrypto() {
    }

    /**
     * Encrypt-then-MAC.
     *
     * @param plaintext     data to protect (UTF-8 bytes of the merged document)
     * @param key           32-byte master key
     * @param randomMaterial 28 random bytes: 16 for the salt + 12 for the nonce
     * @return salt(16) || nonce(12) || ciphertext || tag(32), or null on error
     */
    public static native byte[] encrypt(byte[] plaintext, byte[] key, byte[] randomMaterial);

    /**
     * Verify the HMAC tag and decrypt.
     *
     * @param blob salt(16) || nonce(12) || ciphertext || tag(32)
     * @param key  32-byte master key
     * @return the original plaintext, or null when authentication fails
     */
    public static native byte[] decrypt(byte[] blob, byte[] key);
}
