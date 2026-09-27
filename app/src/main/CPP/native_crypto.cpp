#ifndef PROTECTOR_CRYPTO_TEST
#include <jni.h>
#endif

#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace {

constexpr size_t kKeyLen = 32;
constexpr size_t kSaltLen = 16;
constexpr size_t kNonceLen = 12;
constexpr size_t kTagLen = 32;

inline uint32_t rotl32(uint32_t value, int bits) {
    return (value << bits) | (value >> (32 - bits));
}

inline uint32_t ror32(uint32_t value, int bits) {
    return (value >> bits) | (value << (32 - bits));
}

inline uint32_t load32_le(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

inline uint32_t load32_be(const uint8_t* p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

inline void store32_le(uint8_t* p, uint32_t value) {
    p[0] = (uint8_t)(value);
    p[1] = (uint8_t)(value >> 8);
    p[2] = (uint8_t)(value >> 16);
    p[3] = (uint8_t)(value >> 24);
}

inline void store32_be(uint8_t* p, uint32_t value) {
    p[0] = (uint8_t)(value >> 24);
    p[1] = (uint8_t)(value >> 16);
    p[2] = (uint8_t)(value >> 8);
    p[3] = (uint8_t)(value);
}

inline void store64_be(uint8_t* p, uint64_t value) {
    for (int i = 0; i < 8; i++) {
        p[i] = (uint8_t)(value >> (56 - 8 * i));
    }
}

inline void secure_zero(void* buffer, size_t length) {
    volatile uint8_t* p = (volatile uint8_t*)buffer;
    while (length-- > 0) {
        *p++ = 0;
    }
}

// ---------------------------------------------------------------------------
// ChaCha20 (RFC 8439) - 96-bit nonce, 32-bit block counter
// ---------------------------------------------------------------------------
inline void quarter_round(uint32_t& a, uint32_t& b, uint32_t& c, uint32_t& d) {
    a += b; d ^= a; d = rotl32(d, 16);
    c += d; b ^= c; b = rotl32(b, 12);
    a += b; d ^= a; d = rotl32(d, 8);
    c += d; b ^= c; b = rotl32(b, 7);
}

void chacha20_block(const uint8_t key[kKeyLen], uint32_t counter,
                    const uint8_t nonce[kNonceLen], uint8_t out[64]) {
    uint32_t state[16];
    state[0] = 0x61707865;
    state[1] = 0x3320646e;
    state[2] = 0x79622d32;
    state[3] = 0x6b206574;
    for (int i = 0; i < 8; i++) {
        state[4 + i] = load32_le(key + 4 * i);
    }
    state[12] = counter;
    state[13] = load32_le(nonce + 0);
    state[14] = load32_le(nonce + 4);
    state[15] = load32_le(nonce + 8);

    uint32_t x[16];
    for (int i = 0; i < 16; i++) {
        x[i] = state[i];
    }

    for (int i = 0; i < 10; i++) {
        quarter_round(x[0], x[4], x[8], x[12]);
        quarter_round(x[1], x[5], x[9], x[13]);
        quarter_round(x[2], x[6], x[10], x[14]);
        quarter_round(x[3], x[7], x[11], x[15]);
        quarter_round(x[0], x[5], x[10], x[15]);
        quarter_round(x[1], x[6], x[11], x[12]);
        quarter_round(x[2], x[7], x[8], x[13]);
        quarter_round(x[3], x[4], x[9], x[14]);
    }

    for (int i = 0; i < 16; i++) {
        store32_le(out + 4 * i, x[i] + state[i]);
    }
}

void chacha20_xor(const uint8_t key[kKeyLen], const uint8_t nonce[kNonceLen],
                  uint32_t counter, uint8_t* data, size_t length) {
    uint8_t block[64];
    size_t offset = 0;
    while (offset < length) {
        chacha20_block(key, counter++, nonce, block);
        size_t take = (length - offset < 64) ? (length - offset) : 64;
        for (size_t i = 0; i < take; i++) {
            data[offset + i] ^= block[i];
        }
        offset += take;
    }
}

// ---------------------------------------------------------------------------
// SHA-256
// ---------------------------------------------------------------------------
const uint32_t kSha256K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

struct Sha256 {
    uint32_t state[8];
    uint8_t buffer[64];
    size_t buffered;
    uint64_t total;
};

void sha256_init(Sha256* ctx) {
    ctx->state[0] = 0x6a09e667;
    ctx->state[1] = 0xbb67ae85;
    ctx->state[2] = 0x3c6ef372;
    ctx->state[3] = 0xa54ff53a;
    ctx->state[4] = 0x510e527f;
    ctx->state[5] = 0x9b05688c;
    ctx->state[6] = 0x1f83d9ab;
    ctx->state[7] = 0x5be0cd19;
    ctx->buffered = 0;
    ctx->total = 0;
}

void sha256_transform(Sha256* ctx, const uint8_t* data) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++) {
        w[i] = load32_be(data + 4 * i);
    }
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ror32(w[i - 15], 7) ^ ror32(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = ror32(w[i - 2], 17) ^ ror32(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }

    uint32_t a = ctx->state[0], b = ctx->state[1], c = ctx->state[2], d = ctx->state[3];
    uint32_t e = ctx->state[4], f = ctx->state[5], g = ctx->state[6], h = ctx->state[7];

    for (int i = 0; i < 64; i++) {
        uint32_t s1 = ror32(e, 6) ^ ror32(e, 11) ^ ror32(e, 25);
        uint32_t ch = (e & f) ^ ((~e) & g);
        uint32_t temp1 = h + s1 + ch + kSha256K[i] + w[i];
        uint32_t s0 = ror32(a, 2) ^ ror32(a, 13) ^ ror32(a, 22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temp2 = s0 + maj;
        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }

    ctx->state[0] += a;
    ctx->state[1] += b;
    ctx->state[2] += c;
    ctx->state[3] += d;
    ctx->state[4] += e;
    ctx->state[5] += f;
    ctx->state[6] += g;
    ctx->state[7] += h;
}

void sha256_update(Sha256* ctx, const uint8_t* data, size_t length) {
    ctx->total += length;
    while (length > 0) {
        size_t space = 64 - ctx->buffered;
        size_t take = (space < length) ? space : length;
        memcpy(ctx->buffer + ctx->buffered, data, take);
        ctx->buffered += take;
        data += take;
        length -= take;
        if (ctx->buffered == 64) {
            sha256_transform(ctx, ctx->buffer);
            ctx->buffered = 0;
        }
    }
}

void sha256_final(Sha256* ctx, uint8_t out[32]) {
    uint64_t bits = ctx->total * 8;
    uint8_t pad = 0x80;
    sha256_update(ctx, &pad, 1);
    uint8_t zero = 0;
    while (ctx->buffered != 56) {
        sha256_update(ctx, &zero, 1);
    }
    uint8_t lengthBytes[8];
    store64_be(lengthBytes, bits);
    sha256_update(ctx, lengthBytes, 8);
    for (int i = 0; i < 8; i++) {
        store32_be(out + 4 * i, ctx->state[i]);
    }
}

void sha256(const uint8_t* data, size_t length, uint8_t out[32]) {
    Sha256 ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, data, length);
    sha256_final(&ctx, out);
}

// ---------------------------------------------------------------------------
// HMAC-SHA256
// ---------------------------------------------------------------------------
void hmac_sha256(const uint8_t* key, size_t keyLength, const uint8_t* message,
                 size_t messageLength, uint8_t out[32]) {
    uint8_t block[64];
    memset(block, 0, sizeof(block));
    if (keyLength > 64) {
        sha256(key, keyLength, block);
    } else {
        memcpy(block, key, keyLength);
    }

    uint8_t ipad[64];
    uint8_t opad[64];
    for (int i = 0; i < 64; i++) {
        ipad[i] = block[i] ^ 0x36;
        opad[i] = block[i] ^ 0x5c;
    }

    Sha256 ctx;
    uint8_t inner[32];
    sha256_init(&ctx);
    sha256_update(&ctx, ipad, 64);
    sha256_update(&ctx, message, messageLength);
    sha256_final(&ctx, inner);

    sha256_init(&ctx);
    sha256_update(&ctx, opad, 64);
    sha256_update(&ctx, inner, 32);
    sha256_final(&ctx, out);

    secure_zero(block, sizeof(block));
    secure_zero(ipad, sizeof(ipad));
    secure_zero(opad, sizeof(opad));
    secure_zero(inner, sizeof(inner));
}

// Sub-key derivation: HMAC(master, salt || label)
void derive_key(const uint8_t master[kKeyLen], const uint8_t salt[kSaltLen],
                const char* label, uint8_t out[kKeyLen]) {
    uint8_t message[kSaltLen + 3];
    memcpy(message, salt, kSaltLen);
    memcpy(message + kSaltLen, label, 3);
    hmac_sha256(master, kKeyLen, message, kSaltLen + 3, out);
    secure_zero(message, sizeof(message));
}

int constant_time_equal(const uint8_t* a, const uint8_t* b, size_t length) {
    uint8_t diff = 0;
    for (size_t i = 0; i < length; i++) {
        diff |= (uint8_t)(a[i] ^ b[i]);
    }
    return diff == 0;
}

}  // namespace

#ifndef PROTECTOR_CRYPTO_TEST
extern "C" {

JNIEXPORT jbyteArray JNICALL
Java_com_example_protector_NativeCrypto_encrypt(JNIEnv* env, jclass,
                                                jbyteArray jPlain,
                                                jbyteArray jKey,
                                                jbyteArray jRandom) {
    if (jPlain == nullptr || jKey == nullptr || jRandom == nullptr) {
        return nullptr;
    }
    if (env->GetArrayLength(jKey) != (jsize)kKeyLen ||
        env->GetArrayLength(jRandom) != (jsize)(kSaltLen + kNonceLen)) {
        return nullptr;
    }

    jsize plainLength = env->GetArrayLength(jPlain);
    uint8_t master[kKeyLen];
    uint8_t randomMaterial[kSaltLen + kNonceLen];
    env->GetByteArrayRegion(jKey, 0, (jsize)kKeyLen, (jbyte*)master);
    env->GetByteArrayRegion(jRandom, 0, (jsize)(kSaltLen + kNonceLen),
                            (jbyte*)randomMaterial);

    uint8_t salt[kSaltLen];
    uint8_t nonce[kNonceLen];
    memcpy(salt, randomMaterial, kSaltLen);
    memcpy(nonce, randomMaterial + kSaltLen, kNonceLen);

    uint8_t encKey[kKeyLen];
    uint8_t macKey[kKeyLen];
    derive_key(master, salt, "enc", encKey);
    derive_key(master, salt, "mac", macKey);

    size_t cipherLength = (size_t)(plainLength > 0 ? plainLength : 0);
    uint8_t* cipher = (uint8_t*)malloc(cipherLength > 0 ? cipherLength : 1);
    if (cipher == nullptr) {
        secure_zero(master, sizeof(master));
        return nullptr;
    }
    if (cipherLength > 0) {
        env->GetByteArrayRegion(jPlain, 0, plainLength, (jbyte*)cipher);
    }
    chacha20_xor(encKey, nonce, 1, cipher, cipherLength);

    size_t macLength = kSaltLen + kNonceLen + cipherLength;
    uint8_t* macInput = (uint8_t*)malloc(macLength);
    if (macInput == nullptr) {
        secure_zero(cipher, cipherLength);
        free(cipher);
        secure_zero(master, sizeof(master));
        return nullptr;
    }
    memcpy(macInput, salt, kSaltLen);
    memcpy(macInput + kSaltLen, nonce, kNonceLen);
    if (cipherLength > 0) {
        memcpy(macInput + kSaltLen + kNonceLen, cipher, cipherLength);
    }

    uint8_t tag[kTagLen];
    hmac_sha256(macKey, kKeyLen, macInput, macLength, tag);
    secure_zero(macInput, macLength);
    free(macInput);

    size_t blobLength = kSaltLen + kNonceLen + cipherLength + kTagLen;
    uint8_t* blob = (uint8_t*)malloc(blobLength);
    if (blob == nullptr) {
        secure_zero(cipher, cipherLength);
        free(cipher);
        secure_zero(master, sizeof(master));
        return nullptr;
    }
    memcpy(blob, salt, kSaltLen);
    memcpy(blob + kSaltLen, nonce, kNonceLen);
    if (cipherLength > 0) {
        memcpy(blob + kSaltLen + kNonceLen, cipher, cipherLength);
    }
    memcpy(blob + kSaltLen + kNonceLen + cipherLength, tag, kTagLen);

    jbyteArray result = env->NewByteArray((jsize)blobLength);
    if (result != nullptr) {
        env->SetByteArrayRegion(result, 0, (jsize)blobLength, (jbyte*)blob);
    }

    secure_zero(cipher, cipherLength);
    free(cipher);
    secure_zero(blob, blobLength);
    free(blob);
    secure_zero(randomMaterial, sizeof(randomMaterial));
    secure_zero(encKey, sizeof(encKey));
    secure_zero(macKey, sizeof(macKey));
    secure_zero(master, sizeof(master));
    return result;
}

JNIEXPORT jbyteArray JNICALL
Java_com_example_protector_NativeCrypto_decrypt(JNIEnv* env, jclass,
                                                jbyteArray jBlob,
                                                jbyteArray jKey) {
    if (jBlob == nullptr || jKey == nullptr) {
        return nullptr;
    }
    if (env->GetArrayLength(jKey) != (jsize)kKeyLen) {
        return nullptr;
    }

    jsize blobLength = env->GetArrayLength(jBlob);
    if (blobLength < (jsize)(kSaltLen + kNonceLen + kTagLen)) {
        return nullptr;
    }

    uint8_t master[kKeyLen];
    uint8_t* blob = (uint8_t*)malloc((size_t)blobLength);
    if (blob == nullptr) {
        return nullptr;
    }
    env->GetByteArrayRegion(jKey, 0, (jsize)kKeyLen, (jbyte*)master);
    env->GetByteArrayRegion(jBlob, 0, blobLength, (jbyte*)blob);

    uint8_t salt[kSaltLen];
    uint8_t nonce[kNonceLen];
    memcpy(salt, blob, kSaltLen);
    memcpy(nonce, blob + kSaltLen, kNonceLen);

    size_t cipherLength = (size_t)blobLength - kSaltLen - kNonceLen - kTagLen;
    uint8_t* cipher = blob + kSaltLen + kNonceLen;
    uint8_t* tag = cipher + cipherLength;

    uint8_t encKey[kKeyLen];
    uint8_t macKey[kKeyLen];
    derive_key(master, salt, "enc", encKey);
    derive_key(master, salt, "mac", macKey);

    uint8_t expected[kTagLen];
    hmac_sha256(macKey, kKeyLen, blob, kSaltLen + kNonceLen + cipherLength, expected);

    if (!constant_time_equal(tag, expected, kTagLen)) {
        secure_zero(blob, (size_t)blobLength);
        free(blob);
        secure_zero(master, sizeof(master));
        secure_zero(encKey, sizeof(encKey));
        secure_zero(macKey, sizeof(macKey));
        return nullptr;
    }

    chacha20_xor(encKey, nonce, 1, cipher, cipherLength);

    jbyteArray result = env->NewByteArray((jsize)cipherLength);
    if (result != nullptr) {
        env->SetByteArrayRegion(result, 0, (jsize)cipherLength, (jbyte*)cipher);
    }

    secure_zero(blob, (size_t)blobLength);
    free(blob);
    secure_zero(encKey, sizeof(encKey));
    secure_zero(macKey, sizeof(macKey));
    secure_zero(master, sizeof(master));
    return result;
}

}  // extern "C"
#endif
