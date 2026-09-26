import os
import secrets
import hashlib


def create_file(path, content):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")


# ---------------------------------------------------------------------------
# Master key resolution.
#   Set the repo secret NCORE_MASTER_KEY (64 hex chars) for a stable key across
#   builds. If absent, a random key is generated for this build only.
#   The same value is written to encoder/master.key so the offline encoder and
#   the app agree. The key is NEVER shared with third parties and is not printed.
# ---------------------------------------------------------------------------
KEY_HEX = os.environ.get("NCORE_MASTER_KEY", "").strip().lower()
if len(KEY_HEX) != 64:
    KEY_HEX = secrets.token_hex(32)
    KEY_SOURCE = "generated for this build"
else:
    try:
        bytes.fromhex(KEY_HEX)
        KEY_SOURCE = "from env NCORE_MASTER_KEY"
    except ValueError:
        KEY_HEX = secrets.token_hex(32)
        KEY_SOURCE = "generated (invalid env value ignored)"
MASTER_KEY = bytes.fromhex(KEY_HEX)
KEY_FP = hashlib.sha256(MASTER_KEY).hexdigest()[:12]

print("[*] Generating NCore v3 encrypted bytecode engine...")
print("[*] master key source: %s, fingerprint: %s" % (KEY_SOURCE, KEY_FP))

# ===========================================================================
# Gradle / project scaffolding
# ===========================================================================

create_file("settings.gradle", """
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_SETTINGS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "NCoreNativeEngine"
include ':app'
""")

create_file("build.gradle", """
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath 'com.android.tools.build:gradle:8.2.2'
    }
}
task clean(type: Delete) {
    delete rootProject.buildDir
}
""")

create_file("gradle.properties", """
android.useAndroidX=true
android.enableJetifier=true
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
android.native.buildOutput=verbose
""")

# NDK version is pinned explicitly here AND in the CI workflow.
create_file("app/build.gradle", """
plugins {
    id 'com.android.application'
}

android {
    namespace 'com.ncore.engine'
    compileSdk 34
    // Pinned explicitly: never rely on whatever happens to ship with the runner.
    ndkVersion "26.3.11579264"

    defaultConfig {
        applicationId "com.ncore.engine"
        minSdk 21
        targetSdk 34
        versionCode 3
        versionName "3.0"

        ndk {
            abiFilters 'arm64-v8a', 'armeabi-v7a', 'x86_64'
        }

        externalNativeBuild {
            cmake {
                cppFlags "-std=c++17 -fvisibility=hidden -fstack-protector-strong"
                arguments "-DANDROID_STL=c++_shared"
            }
        }
    }

    buildTypes {
        release {
            minifyEnabled true
            shrinkResources true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
            // Signed with the debug key so the CI artifact is installable.
            signingConfig signingConfigs.debug
        }
        debug {
            minifyEnabled false
        }
    }

    externalNativeBuild {
        cmake {
            path "src/main/cpp/CMakeLists.txt"
            version "3.22.1"
        }
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
}

dependencies {
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
}
""")

create_file("app/proguard-rules.pro", """
# Keep the JNI callback surface used by the native interpreter.
-keep class com.ncore.engine.MainActivity { *; }
-keepclassmembers class com.ncore.engine.MainActivity {
    public void ncoreOn*(...);
    public native <methods>;
}
-keepclasseswithmembernames class * {
    native <methods>;
}
""")

create_file("app/src/main/AndroidManifest.xml", """
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <application
        android:allowBackup="false"
        android:icon="@android:drawable/sym_def_app_icon"
        android:label="NCore Native Engine"
        android:supportsRtl="true"
        android:theme="@style/Theme.AppCompat.Light.NoActionBar">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
""")

create_file(".gitignore", """
build/
.gradle/
local.properties
*.iml
.idea/
app/.cxx/
app/build/
# Never commit the shared encoder/app master key.
encoder/master.key
""")

# ===========================================================================
# Native build system (links libandroid + liblog explicitly).
# ===========================================================================

create_file("app/src/main/cpp/CMakeLists.txt", """
cmake_minimum_required(VERSION 3.22.1)
project(ncore_engine CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(
    ncore_engine
    SHARED
    crypto/sha256.cpp
    crypto/hmac.cpp
    crypto/hkdf.cpp
    crypto/chacha20.cpp
    native_engine.cpp
)

target_include_directories(ncore_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# NOTE: the previous build only linked liblog. libandroid is required for the
# native rendering/JNI surface; linking it explicitly fixes the missing-symbol
# problems that prevented a clean build.
find_library(log-lib log)
find_library(android-lib android)

target_link_libraries(
    ncore_engine
    ${log-lib}
    ${android-lib}
)

target_compile_options(ncore_engine PRIVATE
    -fvisibility=hidden
    -fstack-protector-strong
    -ffunction-sections
    -fdata-sections
    -Wall
    -Wextra
)

target_link_options(ncore_engine PRIVATE -Wl,--gc-sections)

# _FORTIFY_SOURCE needs optimization; enable it only for release builds.
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    target_compile_definitions(ncore_engine PRIVATE _FORTIFY_SOURCE=2)
endif()
""")

# ===========================================================================
# Generated master key header (app side)
# ===========================================================================

key_bytes = ", ".join("0x%02x" % b for b in MASTER_KEY)
create_file("app/src/main/cpp/ncore_key.h", """
#pragma once
#include <cstdint>

// Auto-generated. Contains the app-side secret used to derive the per-file
// ChaCha20 body key and HMAC key via HKDF-SHA256.
//
// Hardening note: this is obfuscation-grade protection. A determined attacker
// with the APK can recover this constant. For production secrecy bind the key
// to the Android Keystore / hardware-backed attestation or fetch it from a
// server after authentication. The format itself is designed so that even with
// the body key, the opcode permutation and glyph alphabet must also be solved.
static const uint8_t NCORE_MASTER_KEY[32] = {
""" + key_bytes + """
};
""")

# ===========================================================================
# Self-contained crypto primitives (no external dependencies -> no link issues)
# ===========================================================================

create_file("app/src/main/cpp/crypto/sha256.h", r"""
#pragma once
#include <cstddef>
#include <cstdint>

namespace ncore {
namespace crypto {

struct SHA256_CTX {
    uint32_t state[8];
    uint64_t bitlen;
    uint8_t data[64];
    size_t datalen;
};

void sha256_init(SHA256_CTX* ctx);
void sha256_update(SHA256_CTX* ctx, const uint8_t* data, size_t len);
void sha256_final(SHA256_CTX* ctx, uint8_t out[32]);
void sha256(const uint8_t* data, size_t len, uint8_t out[32]);

}  // namespace crypto
}  // namespace ncore
""")

create_file("app/src/main/cpp/crypto/sha256.cpp", r"""
#include "sha256.h"
#include <cstring>

namespace ncore {
namespace crypto {

static const uint32_t K[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u,
    0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
    0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u,
    0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
    0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
    0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
    0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au,
    0x5b9cca4fu, 0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
};

static inline uint32_t rotr(uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32 - n));
}

static void transform(SHA256_CTX* ctx, const uint8_t* block) {
    uint32_t w[64];
    for (int i = 0; i < 16; ++i) {
        w[i] = ((uint32_t)block[i * 4] << 24) | ((uint32_t)block[i * 4 + 1] << 16) |
               ((uint32_t)block[i * 4 + 2] << 8) | (uint32_t)block[i * 4 + 3];
    }
    for (int i = 16; i < 64; ++i) {
        uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = ctx->state[0], b = ctx->state[1], c = ctx->state[2], d = ctx->state[3];
    uint32_t e = ctx->state[4], f = ctx->state[5], g = ctx->state[6], h = ctx->state[7];
    for (int i = 0; i < 64; ++i) {
        uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        uint32_t ch = (e & f) ^ ((~e) & g);
        uint32_t t1 = h + S1 + ch + K[i] + w[i];
        uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = S0 + maj;
        h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    ctx->state[0] += a; ctx->state[1] += b; ctx->state[2] += c; ctx->state[3] += d;
    ctx->state[4] += e; ctx->state[5] += f; ctx->state[6] += g; ctx->state[7] += h;
}

void sha256_init(SHA256_CTX* ctx) {
    ctx->datalen = 0;
    ctx->bitlen = 0;
    ctx->state[0] = 0x6a09e667u; ctx->state[1] = 0xbb67ae85u;
    ctx->state[2] = 0x3c6ef372u; ctx->state[3] = 0xa54ff53au;
    ctx->state[4] = 0x510e527fu; ctx->state[5] = 0x9b05688cu;
    ctx->state[6] = 0x1f83d9abu; ctx->state[7] = 0x5be0cd19u;
}

void sha256_update(SHA256_CTX* ctx, const uint8_t* data, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        ctx->data[ctx->datalen++] = data[i];
        if (ctx->datalen == 64) {
            transform(ctx, ctx->data);
            ctx->bitlen += 512;
            ctx->datalen = 0;
        }
    }
}

void sha256_final(SHA256_CTX* ctx, uint8_t out[32]) {
    size_t i = ctx->datalen;
    if (ctx->datalen < 56) {
        ctx->data[i++] = 0x80;
        while (i < 56) ctx->data[i++] = 0x00;
    } else {
        ctx->data[i++] = 0x80;
        while (i < 64) ctx->data[i++] = 0x00;
        transform(ctx, ctx->data);
        std::memset(ctx->data, 0, 56);
    }
    ctx->bitlen += (uint64_t)ctx->datalen * 8;
    ctx->data[63] = (uint8_t)(ctx->bitlen);
    ctx->data[62] = (uint8_t)(ctx->bitlen >> 8);
    ctx->data[61] = (uint8_t)(ctx->bitlen >> 16);
    ctx->data[60] = (uint8_t)(ctx->bitlen >> 24);
    ctx->data[59] = (uint8_t)(ctx->bitlen >> 32);
    ctx->data[58] = (uint8_t)(ctx->bitlen >> 40);
    ctx->data[57] = (uint8_t)(ctx->bitlen >> 48);
    ctx->data[56] = (uint8_t)(ctx->bitlen >> 56);
    transform(ctx, ctx->data);
    for (i = 0; i < 4; ++i) {
        out[i] = (uint8_t)(ctx->state[0] >> (24 - i * 8));
        out[i + 4] = (uint8_t)(ctx->state[1] >> (24 - i * 8));
        out[i + 8] = (uint8_t)(ctx->state[2] >> (24 - i * 8));
        out[i + 12] = (uint8_t)(ctx->state[3] >> (24 - i * 8));
        out[i + 16] = (uint8_t)(ctx->state[4] >> (24 - i * 8));
        out[i + 20] = (uint8_t)(ctx->state[5] >> (24 - i * 8));
        out[i + 24] = (uint8_t)(ctx->state[6] >> (24 - i * 8));
        out[i + 28] = (uint8_t)(ctx->state[7] >> (24 - i * 8));
    }
}

void sha256(const uint8_t* data, size_t len, uint8_t out[32]) {
    SHA256_CTX ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, data, len);
    sha256_final(&ctx, out);
}

}  // namespace crypto
}  // namespace ncore
""")

create_file("app/src/main/cpp/crypto/hmac.h", r"""
#pragma once
#include <cstddef>
#include <cstdint>

namespace ncore {
namespace crypto {

void hmac_sha256(const uint8_t* key, size_t keyLen,
                 const uint8_t* msg, size_t msgLen,
                 uint8_t out[32]);

}  // namespace crypto
}  // namespace ncore
""")

create_file("app/src/main/cpp/crypto/hmac.cpp", r"""
#include "hmac.h"
#include "sha256.h"
#include <cstring>

namespace ncore {
namespace crypto {

void hmac_sha256(const uint8_t* key, size_t keyLen,
                 const uint8_t* msg, size_t msgLen,
                 uint8_t out[32]) {
    uint8_t k[64];
    std::memset(k, 0, sizeof(k));
    if (keyLen > 64) {
        sha256(key, keyLen, k);
    } else {
        std::memcpy(k, key, keyLen);
    }

    uint8_t ipad[64];
    uint8_t opad[64];
    for (int i = 0; i < 64; ++i) {
        ipad[i] = (uint8_t)(k[i] ^ 0x36);
        opad[i] = (uint8_t)(k[i] ^ 0x5c);
    }

    SHA256_CTX ctx;
    uint8_t inner[32];
    sha256_init(&ctx);
    sha256_update(&ctx, ipad, 64);
    sha256_update(&ctx, msg, msgLen);
    sha256_final(&ctx, inner);

    sha256_init(&ctx);
    sha256_update(&ctx, opad, 64);
    sha256_update(&ctx, inner, 32);
    sha256_final(&ctx, out);

    // Wipe intermediates.
    volatile uint8_t* vk = k;
    for (int i = 0; i < 64; ++i) { vk[i] = 0; ipad[i] = 0; opad[i] = 0; }
    volatile uint8_t* vi = inner;
    for (int i = 0; i < 32; ++i) vi[i] = 0;
}

}  // namespace crypto
}  // namespace ncore
""")

create_file("app/src/main/cpp/crypto/hkdf.h", r"""
#pragma once
#include <cstddef>
#include <cstdint>

namespace ncore {
namespace crypto {

// HKDF-SHA256 (RFC 5869): extract-then-expand.
void hkdf_sha256(const uint8_t* ikm, size_t ikmLen,
                 const uint8_t* salt, size_t saltLen,
                 const uint8_t* info, size_t infoLen,
                 uint8_t* out, size_t outLen);

}  // namespace crypto
}  // namespace ncore
""")

create_file("app/src/main/cpp/crypto/hkdf.cpp", r"""
#include "hkdf.h"
#include "hmac.h"
#include <cstring>

namespace ncore {
namespace crypto {

void hkdf_sha256(const uint8_t* ikm, size_t ikmLen,
                 const uint8_t* salt, size_t saltLen,
                 const uint8_t* info, size_t infoLen,
                 uint8_t* out, size_t outLen) {
    uint8_t zeroSalt[32];
    if (salt == nullptr || saltLen == 0) {
        std::memset(zeroSalt, 0, sizeof(zeroSalt));
        salt = zeroSalt;
        saltLen = sizeof(zeroSalt);
    }

    uint8_t prk[32];
    hmac_sha256(salt, saltLen, ikm, ikmLen, prk);

    uint8_t t[32];
    size_t tLen = 0;
    size_t pos = 0;
    uint8_t counter = 1;
    while (pos < outLen) {
        uint8_t block[32 + 64 + 1];
        size_t off = 0;
        if (tLen > 0) {
            std::memcpy(block, t, tLen);
            off += tLen;
        }
        if (infoLen > 0 && info != nullptr) {
            std::memcpy(block + off, info, infoLen);
            off += infoLen;
        }
        block[off++] = counter;
        hmac_sha256(prk, 32, block, off, t);
        tLen = 32;
        size_t take = outLen - pos;
        if (take > 32) take = 32;
        std::memcpy(out + pos, t, take);
        pos += take;
        ++counter;
    }

    volatile uint8_t* vp = prk;
    for (int i = 0; i < 32; ++i) vp[i] = 0;
    volatile uint8_t* vt = t;
    for (int i = 0; i < 32; ++i) vt[i] = 0;
}

}  // namespace crypto
}  // namespace ncore
""")

create_file("app/src/main/cpp/crypto/chacha20.h", r"""
#pragma once
#include <cstddef>
#include <cstdint>

namespace ncore {
namespace crypto {

// IETF ChaCha20 (RFC 8439), 32-bit block counter.
// out = in XOR keystream, starting at the given block counter.
void chacha20_xor(const uint8_t key[32], const uint8_t nonce[12],
                  uint32_t counter, const uint8_t* in, size_t inLen,
                  uint8_t* out);

}  // namespace crypto
}  // namespace ncore
""")

create_file("app/src/main/cpp/crypto/chacha20.cpp", r"""
#include "chacha20.h"
#include <cstring>

namespace ncore {
namespace crypto {

static inline uint32_t rotl32(uint32_t x, int c) {
    return (x << c) | (x >> (32 - c));
}

static inline uint32_t load32(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static inline void store32(uint8_t* p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static inline void quarterround(uint32_t* x, int a, int b, int c, int d) {
    x[a] += x[b]; x[d] ^= x[a]; x[d] = rotl32(x[d], 16);
    x[c] += x[d]; x[b] ^= x[c]; x[b] = rotl32(x[b], 12);
    x[a] += x[b]; x[d] ^= x[a]; x[d] = rotl32(x[d], 8);
    x[c] += x[d]; x[b] ^= x[c]; x[b] = rotl32(x[b], 7);
}

static void chacha_block(const uint8_t key[32], uint32_t counter,
                         const uint8_t nonce[12], uint8_t out[64]) {
    uint32_t st[16];
    st[0] = 0x61707865u; st[1] = 0x3320646eu;
    st[2] = 0x79622d32u; st[3] = 0x6b206574u;
    for (int i = 0; i < 8; ++i) st[4 + i] = load32(key + i * 4);
    st[12] = counter;
    for (int i = 0; i < 3; ++i) st[13 + i] = load32(nonce + i * 4);

    uint32_t x[16];
    std::memcpy(x, st, sizeof(x));
    for (int i = 0; i < 10; ++i) {
        quarterround(x, 0, 4, 8, 12);
        quarterround(x, 1, 5, 9, 13);
        quarterround(x, 2, 6, 10, 14);
        quarterround(x, 3, 7, 11, 15);
        quarterround(x, 0, 5, 10, 15);
        quarterround(x, 1, 6, 11, 12);
        quarterround(x, 2, 7, 8, 13);
        quarterround(x, 3, 4, 9, 14);
    }
    for (int i = 0; i < 16; ++i) store32(out + i * 4, x[i] + st[i]);
}

void chacha20_xor(const uint8_t key[32], const uint8_t nonce[12],
                  uint32_t counter, const uint8_t* in, size_t inLen,
                  uint8_t* out) {
    uint8_t ks[64];
    size_t off = 0;
    while (off < inLen) {
        chacha_block(key, counter, nonce, ks);
        size_t chunk = inLen - off;
        if (chunk > 64) chunk = 64;
        for (size_t i = 0; i < chunk; ++i) out[off + i] = in[off + i] ^ ks[i];
        off += chunk;
        ++counter;
    }
    volatile uint8_t* vk = ks;
    for (int i = 0; i < 64; ++i) vk[i] = 0;
}

}  // namespace crypto
}  // namespace ncore
""")

# ===========================================================================
# The native interpreter (app-only). Streams decrypted instructions and emits
# rendering callbacks; it never materialises a whole decoded document.
# ===========================================================================

create_file("app/src/main/cpp/native_engine.cpp", r"""
// NCore v3 native interpreter.
//
// Security model:
//   * The .ncore container is authenticated (HMAC-SHA256, encrypt-then-MAC) and
//     the body is encrypted with ChaCha20. Tampering fails closed.
//   * Even after decryption, instruction opcodes are remapped through a per-file
//     permutation and text is stored as indices into a per-file shuffled glyph
//     alphabet, so knowing the container layout is not enough.
//   * The interpreter consumes the ciphertext as a stream: only a 64-byte
//     plaintext window and the current text run exist in memory at any time.
//     There is no HTML string, no DOM and no WebView anywhere in this path.
//   * Every length/array read is bounds-checked against the real remaining
//     ciphertext; corrupted input aborts with a logged, non-silent error code.
#include <jni.h>
#include <android/log.h>

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

#include "crypto/chacha20.h"
#include "crypto/hkdf.h"
#include "crypto/hmac.h"
#include "ncore_key.h"

#define LOG_TAG "NCoreVM"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

namespace {

const uint8_t MAGIC[4] = {'N', 'C', 'B', '3'};
const size_t HEADER_SIZE = 48;
const size_t TAG_SIZE = 32;

enum {
    NC_OK = 0,
    NC_ERR_ARG = 1,
    NC_ERR_MAGIC = 2,
    NC_ERR_VERSION = 3,
    NC_ERR_SIZE = 4,
    NC_ERR_TAG = 5,
    NC_ERR_BOUNDS = 6,
    NC_ERR_OPCODE = 7,
    NC_ERR_ALPHABET = 8,
    NC_ERR_OOM = 9
};

enum {
    OP_END = 0x00,
    OP_STYLE = 0x01,
    OP_BLOCK_OPEN = 0x02,
    OP_BLOCK_CLOSE = 0x03,
    OP_TEXT = 0x04,
    OP_IMAGE = 0x05,
    OP_SPACER = 0x06
};

void secure_zero(void* p, size_t n) {
    volatile uint8_t* v = static_cast<volatile uint8_t*>(p);
    while (n--) *v++ = 0;
}

// Plaintext header reader with explicit bounds checking.
class SafeReader {
public:
    SafeReader(const uint8_t* d, size_t n) : m_d(d), m_n(n), m_p(0), m_err(NC_OK) {}

    bool need(size_t n) {
        if (m_p + n > m_n) {
            fail();
            return false;
        }
        return true;
    }
    uint8_t u8() {
        if (!need(1)) return 0;
        return m_d[m_p++];
    }
    uint16_t u16() {
        if (!need(2)) return 0;
        uint16_t v = (uint16_t)(m_d[m_p] | (m_d[m_p + 1] << 8));
        m_p += 2;
        return v;
    }
    uint32_t u32() {
        if (!need(4)) return 0;
        uint32_t v = (uint32_t)m_d[m_p] | ((uint32_t)m_d[m_p + 1] << 8) |
                     ((uint32_t)m_d[m_p + 2] << 16) | ((uint32_t)m_d[m_p + 3] << 24);
        m_p += 4;
        return v;
    }
    uint64_t u64() {
        if (!need(8)) return 0;
        uint64_t v = 0;
        for (int i = 7; i >= 0; --i) v = (v << 8) | m_d[m_p + i];
        m_p += 8;
        return v;
    }
    void bytes(uint8_t* out, size_t n) {
        if (!need(n)) {
            if (out) std::memset(out, 0, n);
            return;
        }
        std::memcpy(out, m_d + m_p, n);
        m_p += n;
    }
    bool ok() const { return m_err == NC_OK; }
    int error() const { return m_err; }

private:
    void fail() {
        if (m_err == NC_OK) {
            m_err = NC_ERR_BOUNDS;
            LOGE("bounds violation in header reader at offset %zu (size %zu)", m_p, m_n);
        }
    }
    const uint8_t* m_d;
    size_t m_n;
    size_t m_p;
    int m_err;
};

// Streaming decrypting reader. Decrypts one 64-byte ChaCha20 block at a time and
// keeps only that window in plaintext memory.
class CipherReader {
public:
    CipherReader(const uint8_t* cipher, size_t len, const uint8_t key[32],
                 const uint8_t nonce[12])
        : m_c(cipher), m_n(len), m_p(0), m_counter(0), m_fill(0), m_bp(0),
          m_err(NC_OK) {
        std::memcpy(m_key, key, 32);
        std::memcpy(m_nonce, nonce, 12);
    }

    ~CipherReader() { secure_zero(m_buf, sizeof(m_buf)); }

    size_t available() const { return (m_n - m_p) + (m_fill - m_bp); }

    uint8_t u8() {
        if (m_bp >= m_fill) {
            if (!fill()) {
                fail();
                return 0;
            }
        }
        return m_buf[m_bp++];
    }
    uint16_t u16() {
        uint16_t lo = u8();
        uint16_t hi = u8();
        return (uint16_t)(lo | (hi << 8));
    }
    uint32_t u32() {
        uint32_t v = 0;
        for (int i = 0; i < 4; ++i) v |= ((uint32_t)u8()) << (8 * i);
        return v;
    }
    void bytes(uint8_t* out, size_t n) {
        for (size_t i = 0; i < n; ++i) out[i] = u8();
    }
    bool ok() const { return m_err == NC_OK; }
    int error() const { return m_err; }

private:
    bool fill() {
        if (m_p >= m_n) return false;
        size_t chunk = m_n - m_p;
        if (chunk > 64) chunk = 64;
        ncore::crypto::chacha20_xor(m_key, m_nonce, m_counter, m_c + m_p, chunk, m_buf);
        m_p += chunk;
        m_fill = chunk;
        m_bp = 0;
        ++m_counter;
        return true;
    }
    void fail() {
        if (m_err == NC_OK) {
            m_err = NC_ERR_BOUNDS;
            LOGE("bounds violation in cipher stream at cipher offset %zu (size %zu)",
                 m_p, m_n);
        }
    }
    const uint8_t* m_c;
    size_t m_n;
    size_t m_p;
    uint8_t m_key[32];
    uint8_t m_nonce[12];
    uint32_t m_counter;
    uint8_t m_buf[64];
    size_t m_fill;
    size_t m_bp;
    int m_err;
};

class RenderSink {
public:
    virtual ~RenderSink() {}
    virtual void onStyle(uint16_t id, uint32_t fg, uint32_t bg, uint16_t size,
                         uint8_t bold, uint8_t italic, uint8_t underline,
                         uint8_t strike, uint8_t align, uint16_t mt, uint16_t mb,
                         uint16_t pad, uint16_t corner, uint16_t bw,
                         uint32_t bc) = 0;
    virtual void onBlockOpen(uint16_t kind, uint16_t styleId, uint16_t flags) = 0;
    virtual void onBlockClose() = 0;
    virtual void onText(uint16_t styleId, uint16_t flags, const uint32_t* cps,
                        size_t n, const uint8_t* url, size_t urlLen) = 0;
    virtual void onImage(uint16_t styleId, uint16_t w, uint16_t h,
                         const uint8_t* data, size_t len) = 0;
    virtual void onSpacer(uint16_t h) = 0;
};

bool constant_time_equal(const uint8_t* a, const uint8_t* b, size_t n) {
    uint8_t diff = 0;
    for (size_t i = 0; i < n; ++i) diff |= (uint8_t)(a[i] ^ b[i]);
    return diff == 0;
}

int run_ncore(const uint8_t* file, size_t len, RenderSink* sink) {
    if (file == nullptr || sink == nullptr) return NC_ERR_ARG;
    if (len < HEADER_SIZE + TAG_SIZE) {
        LOGE("file too small: %zu bytes", len);
        return NC_ERR_SIZE;
    }

    SafeReader hr(file, len);
    uint8_t magic[4];
    hr.bytes(magic, 4);
    if (!hr.ok() || std::memcmp(magic, MAGIC, 4) != 0) {
        LOGE("bad magic (not an NCB3 container)");
        return NC_ERR_MAGIC;
    }
    uint8_t version = hr.u8();
    uint8_t flags = hr.u8();
    uint16_t headerSize = hr.u16();
    uint8_t fileId[8];
    hr.bytes(fileId, 8);
    uint64_t bodyLen = hr.u64();
    uint8_t reserved[24];
    hr.bytes(reserved, 24);
    (void)flags;
    (void)reserved;

    if (!hr.ok() || version != 3 || headerSize != HEADER_SIZE) {
        LOGE("unsupported version/header: version=%u headerSize=%u", version, headerSize);
        return NC_ERR_VERSION;
    }
    if (bodyLen > (uint64_t)(len)) {
        LOGE("declared body length %llu exceeds file size", (unsigned long long)bodyLen);
        return NC_ERR_SIZE;
    }
    if (HEADER_SIZE + (size_t)bodyLen + TAG_SIZE != len) {
        LOGE("size mismatch: %zu != %zu + %llu + %zu", len, HEADER_SIZE,
             (unsigned long long)bodyLen, TAG_SIZE);
        return NC_ERR_SIZE;
    }

    // Derive keys.
    static const uint8_t INFO_BODY[] = "ncore3/body";
    static const uint8_t INFO_MAC[] = "ncore3/mac";
    uint8_t bodyKey[32];
    uint8_t macKey[32];
    ncore::crypto::hkdf_sha256(NCORE_MASTER_KEY, 32, fileId, 8, INFO_BODY,
                        sizeof(INFO_BODY) - 1, bodyKey, 32);
    ncore::crypto::hkdf_sha256(NCORE_MASTER_KEY, 32, fileId, 8, INFO_MAC,
                        sizeof(INFO_MAC) - 1, macKey, 32);

    // Encrypt-then-MAC verification over header || ciphertext.
    uint8_t tag[32];
    ncore::crypto::hmac_sha256(macKey, 32, file, HEADER_SIZE + (size_t)bodyLen, tag);
    if (!constant_time_equal(tag, file + HEADER_SIZE + (size_t)bodyLen, TAG_SIZE)) {
        LOGE("authentication tag mismatch: file is corrupt or tampered with");
        secure_zero(bodyKey, 32);
        secure_zero(macKey, 32);
        return NC_ERR_TAG;
    }
    secure_zero(macKey, 32);

    uint8_t nonce[12];
    std::memcpy(nonce, fileId, 8);
    std::memset(nonce + 8, 0, 4);

    CipherReader cr(file + HEADER_SIZE, (size_t)bodyLen, bodyKey, nonce);
    secure_zero(bodyKey, 32);

    // Body prologue: format minor, opcode permutation, glyph alphabet.
    (void)cr.u8();  // format minor
    uint8_t opMap[256];
    cr.bytes(opMap, 256);

    uint16_t alphabetSize = cr.u16();
    if (!cr.ok() || alphabetSize == 0) {
        LOGE("invalid alphabet size %u", alphabetSize);
        return NC_ERR_ALPHABET;
    }
    std::vector<uint32_t> alphabet(alphabetSize);
    for (uint16_t i = 0; i < alphabetSize; ++i) alphabet[i] = cr.u32();
    if (!cr.ok()) {
        LOGE("truncated glyph alphabet");
        return NC_ERR_BOUNDS;
    }

    std::vector<uint32_t> cpBuf;
    std::vector<uint8_t> urlBuf;
    bool sawEnd = false;

    while (cr.ok()) {
        uint8_t enc = cr.u8();
        if (!cr.ok()) break;
        uint8_t op = opMap[enc];

        if (op == OP_END) {
            sawEnd = true;
            break;
        } else if (op == OP_STYLE) {
            uint16_t id = cr.u16();
            uint32_t fg = cr.u32();
            uint32_t bg = cr.u32();
            uint16_t size = cr.u16();
            uint8_t bold = cr.u8();
            uint8_t italic = cr.u8();
            uint8_t underline = cr.u8();
            uint8_t strike = cr.u8();
            uint8_t align = cr.u8();
            uint16_t mt = cr.u16();
            uint16_t mb = cr.u16();
            uint16_t pad = cr.u16();
            uint16_t corner = cr.u16();
            uint16_t bw = cr.u16();
            uint32_t bc = cr.u32();
            if (!cr.ok()) break;
            sink->onStyle(id, fg, bg, size, bold, italic, underline, strike, align,
                          mt, mb, pad, corner, bw, bc);
        } else if (op == OP_BLOCK_OPEN) {
            uint16_t kind = cr.u16();
            uint16_t styleId = cr.u16();
            uint16_t flags = cr.u16();
            if (!cr.ok()) break;
            sink->onBlockOpen(kind, styleId, flags);
        } else if (op == OP_BLOCK_CLOSE) {
            sink->onBlockClose();
        } else if (op == OP_TEXT) {
            uint16_t styleId = cr.u16();
            uint16_t flags = cr.u16();
            uint16_t urlLen = cr.u16();
            if (!cr.ok() || (size_t)urlLen > cr.available()) {
                LOGE("invalid url length %u (available %zu)", urlLen, cr.available());
                return NC_ERR_BOUNDS;
            }
            urlBuf.assign(urlLen, 0);
            if (urlLen) cr.bytes(urlBuf.data(), urlLen);

            uint32_t glyphCount = cr.u32();
            if (!cr.ok() || (uint64_t)glyphCount * 2ull > (uint64_t)cr.available()) {
                LOGE("invalid glyph count %u (available %zu)", glyphCount, cr.available());
                return NC_ERR_BOUNDS;
            }
            cpBuf.assign(glyphCount, 0);
            for (uint32_t i = 0; i < glyphCount; ++i) {
                uint16_t g = cr.u16();
                cpBuf[i] = (g < alphabetSize) ? alphabet[g] : 0xFFFDu;
            }
            if (!cr.ok()) break;
            sink->onText(styleId, flags, cpBuf.empty() ? nullptr : cpBuf.data(),
                         cpBuf.size(), urlBuf.empty() ? nullptr : urlBuf.data(),
                         urlBuf.size());
            // Wipe this run immediately; it is the only plaintext that existed.
            if (!cpBuf.empty()) secure_zero(cpBuf.data(), cpBuf.size() * sizeof(uint32_t));
            if (!urlBuf.empty()) secure_zero(urlBuf.data(), urlBuf.size());
        } else if (op == OP_IMAGE) {
            uint16_t styleId = cr.u16();
            uint16_t w = cr.u16();
            uint16_t h = cr.u16();
            uint32_t dataLen = cr.u32();
            if (!cr.ok() || (size_t)dataLen > cr.available()) {
                LOGE("invalid image length %u (available %zu)", dataLen, cr.available());
                return NC_ERR_BOUNDS;
            }
            std::vector<uint8_t> img(dataLen);
            if (dataLen) cr.bytes(img.data(), dataLen);
            if (!cr.ok()) break;
            sink->onImage(styleId, w, h, img.empty() ? nullptr : img.data(), img.size());
        } else if (op == OP_SPACER) {
            uint16_t h = cr.u16();
            if (!cr.ok()) break;
            sink->onSpacer(h);
        } else {
            LOGE("unknown opcode 0x%02x (encoded 0x%02x) - aborting", op, enc);
            return NC_ERR_OPCODE;
        }
    }

    if (!cr.ok()) {
        LOGE("decode aborted by bounds failure");
        return cr.error();
    }
    if (!sawEnd) {
        LOGE("stream ended without OP_END");
        return NC_ERR_BOUNDS;
    }
    LOGI("NCore stream interpreted successfully");
    return NC_OK;
}

// ---- JNI bridge -----------------------------------------------------------

class JniSink : public RenderSink {
public:
    JniSink(JNIEnv* env, jobject obj) : m_env(env), m_obj(obj) {
        jclass cls = env->GetObjectClass(obj);
        m_style = env->GetMethodID(cls, "ncoreOnStyle", "(IIIIIIIIIIIIIII)V");
        m_blockOpen = env->GetMethodID(cls, "ncoreOnBlockOpen", "(III)V");
        m_blockClose = env->GetMethodID(cls, "ncoreOnBlockClose", "()V");
        m_text = env->GetMethodID(cls, "ncoreOnText", "(II[ILjava/lang/String;)V");
        m_image = env->GetMethodID(cls, "ncoreOnImage", "(III[B)V");
        m_spacer = env->GetMethodID(cls, "ncoreOnSpacer", "(I)V");
    }

    bool valid() const {
        return m_style && m_blockOpen && m_blockClose && m_text && m_image && m_spacer;
    }

    void onStyle(uint16_t id, uint32_t fg, uint32_t bg, uint16_t size, uint8_t bold,
                 uint8_t italic, uint8_t underline, uint8_t strike, uint8_t align,
                 uint16_t mt, uint16_t mb, uint16_t pad, uint16_t corner,
                 uint16_t bw, uint32_t bc) override {
        m_env->CallVoidMethod(m_obj, m_style, (jint)id, (jint)fg, (jint)bg, (jint)size,
                              (jint)bold, (jint)italic, (jint)underline, (jint)strike,
                              (jint)align, (jint)mt, (jint)mb, (jint)pad, (jint)corner,
                              (jint)bw, (jint)bc);
    }
    void onBlockOpen(uint16_t kind, uint16_t styleId, uint16_t flags) override {
        m_env->CallVoidMethod(m_obj, m_blockOpen, (jint)kind, (jint)styleId, (jint)flags);
    }
    void onBlockClose() override { m_env->CallVoidMethod(m_obj, m_blockClose); }
    void onText(uint16_t styleId, uint16_t flags, const uint32_t* cps, size_t n,
                const uint8_t* url, size_t urlLen) override {
        jintArray arr = m_env->NewIntArray((jsize)n);
        if (arr == nullptr) return;
        m_env->SetIntArrayRegion(arr, 0, (jsize)n, reinterpret_cast<const jint*>(cps));
        jstring jurl = nullptr;
        if (url != nullptr && urlLen > 0) {
            jurl = m_env->NewStringUTF(reinterpret_cast<const char*>(url));
        }
        m_env->CallVoidMethod(m_obj, m_text, (jint)styleId, (jint)flags, arr, jurl);
        if (jurl) m_env->DeleteLocalRef(jurl);
        // Overwrite the transient code-point array with zeros.
        std::vector<jint> zeros(n, 0);
        m_env->SetIntArrayRegion(arr, 0, (jsize)n, zeros.data());
        m_env->DeleteLocalRef(arr);
    }
    void onImage(uint16_t styleId, uint16_t w, uint16_t h, const uint8_t* data,
                 size_t len) override {
        jbyteArray arr = nullptr;
        if (data != nullptr && len > 0) {
            arr = m_env->NewByteArray((jsize)len);
            if (arr) {
                m_env->SetByteArrayRegion(arr, 0, (jsize)len,
                                          reinterpret_cast<const jbyte*>(data));
            }
        }
        m_env->CallVoidMethod(m_obj, m_image, (jint)styleId, (jint)w, (jint)h, arr);
        if (arr) m_env->DeleteLocalRef(arr);
    }
    void onSpacer(uint16_t h) override {
        m_env->CallVoidMethod(m_obj, m_spacer, (jint)h);
    }

private:
    JNIEnv* m_env;
    jobject m_obj;
    jmethodID m_style = nullptr;
    jmethodID m_blockOpen = nullptr;
    jmethodID m_blockClose = nullptr;
    jmethodID m_text = nullptr;
    jmethodID m_image = nullptr;
    jmethodID m_spacer = nullptr;
};

}  // namespace

extern "C" JNIEXPORT jint JNICALL
Java_com_ncore_engine_MainActivity_nativeRunNCore(JNIEnv* env, jobject thiz,
                                                  jbyteArray data) {
    if (data == nullptr) return NC_ERR_ARG;
    jsize n = env->GetArrayLength(data);
    if (n <= 0) return NC_ERR_ARG;

    jbyte* buf = env->GetByteArrayElements(data, nullptr);
    if (buf == nullptr) return NC_ERR_OOM;

    JniSink sink(env, thiz);
    if (!sink.valid()) {
        LOGE("JNI callback method resolution failed");
        env->ReleaseByteArrayElements(data, buf, JNI_ABORT);
        return NC_ERR_ARG;
    }

    int rc = run_ncore(reinterpret_cast<const uint8_t*>(buf), (size_t)n, &sink);
    env->ReleaseByteArrayElements(data, buf, JNI_ABORT);

    jclass cls = env->GetObjectClass(thiz);
    if (rc == NC_OK) {
        jmethodID done = env->GetMethodID(cls, "ncoreOnComplete", "()V");
        if (done) env->CallVoidMethod(thiz, done);
    } else {
        jmethodID err = env->GetMethodID(cls, "ncoreOnError", "(I)V");
        if (err) env->CallVoidMethod(thiz, err, (jint)rc);
    }
    return (jint)rc;
}
""")

# ===========================================================================
# Android host: renders the streamed instructions as native views.
# There is no WebView and no HTML string on this path.
# ===========================================================================

create_file("app/src/main/java/com/ncore/engine/MainActivity.java", """
package com.ncore.engine;

import android.content.Intent;
import android.graphics.BitmapFactory;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.Map;

public class MainActivity extends AppCompatActivity {

    static {
        System.loadLibrary("ncore_engine");
    }

    // Native entry point: streams the encrypted bytecode and drives the callbacks.
    public native int nativeRunNCore(byte[] data);

    private static final int EK_HR = 27;
    private static final int ALIGN_LEFT = 0;
    private static final int ALIGN_CENTER = 1;
    private static final int ALIGN_RIGHT = 2;
    private static final int ALIGN_JUSTIFY = 3;

    private static class Style {
        int fg = 0xFF212121;
        int bg = 0x00000000;
        int size = 16;
        boolean bold;
        boolean italic;
        boolean underline;
        boolean strike;
        int align = ALIGN_LEFT;
        int mt = 0;
        int mb = 0;
        int pad = 0;
        int corner = 0;
        int bw = 0;
        int bc = 0xFFE0E0E0;
    }

    private final Map<Integer, Style> styles = new HashMap<>();
    private final Deque<LinearLayout> stack = new ArrayDeque<>();
    private LinearLayout uiContainer;
    private boolean hrOpened = false;

    private final ActivityResultLauncher<Intent> openNCoreLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                if (result.getResultCode() == RESULT_OK && result.getData() != null) {
                    Uri uri = result.getData().getData();
                    try (InputStream is = getContentResolver().openInputStream(uri);
                         ByteArrayOutputStream buffer = new ByteArrayOutputStream()) {
                        byte[] chunk = new byte[16384];
                        int nRead;
                        while ((nRead = is.read(chunk, 0, chunk.length)) != -1) {
                            buffer.write(chunk, 0, nRead);
                        }
                        renderNCore(buffer.toByteArray());
                    } catch (Exception e) {
                        Toast.makeText(this, "Read error: " + e.getMessage(),
                                Toast.LENGTH_LONG).show();
                    }
                }
            });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(12), dp(12), dp(12), dp(12));

        Button btnOpen = new Button(this);
        btnOpen.setText("OPEN .NCORE FILE");
        btnOpen.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.setType("*/*");
            openNCoreLauncher.launch(intent);
        });

        Button btnClear = new Button(this);
        btnClear.setText("CLEAR");
        btnClear.setOnClickListener(v -> {
            uiContainer.removeAllViews();
            styles.clear();
        });

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.addView(btnOpen);
        bar.addView(btnClear);

        ScrollView scroll = new ScrollView(this);
        scroll.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1.0f));
        scroll.setFillViewport(true);

        uiContainer = new LinearLayout(this);
        uiContainer.setOrientation(LinearLayout.VERTICAL);
        uiContainer.setLayoutParams(new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        scroll.addView(uiContainer);

        root.addView(bar);
        root.addView(scroll);
        setContentView(root);
    }

    private void renderNCore(byte[] bytes) {
        if (bytes == null || bytes.length == 0) {
            Toast.makeText(this, "Empty file", Toast.LENGTH_SHORT).show();
            return;
        }
        uiContainer.removeAllViews();
        styles.clear();
        stack.clear();
        stack.push(uiContainer);
        hrOpened = false;
        int rc = nativeRunNCore(bytes);
        if (rc != 0) {
            Log.e("NCoreVM", "nativeRunNCore returned error code " + rc);
        }
    }

    // ---- Callbacks invoked from native code --------------------------------

    public void ncoreOnStyle(int id, int fg, int bg, int size, int bold, int italic,
                             int underline, int strike, int align, int mt, int mb,
                             int pad, int corner, int bw, int bc) {
        Style s = new Style();
        s.fg = fg;
        s.bg = bg;
        s.size = size;
        s.bold = bold != 0;
        s.italic = italic != 0;
        s.underline = underline != 0;
        s.strike = strike != 0;
        s.align = align;
        s.mt = mt;
        s.mb = mb;
        s.pad = pad;
        s.corner = corner;
        s.bw = bw;
        s.bc = bc;
        styles.put(id, s);
    }

    public void ncoreOnBlockOpen(int kind, int styleId, int flags) {
        Style s = styles.get(styleId);
        if (s == null) {
            s = new Style();
        }
        LinearLayout parent = stack.peek();

        if (kind == EK_HR) {
            View line = new View(this);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, Math.max(1, s.bw));
            lp.topMargin = dp(s.mt);
            lp.bottomMargin = dp(s.mb);
            line.setLayoutParams(lp);
            line.setBackgroundColor(s.bc);
            parent.addView(line);
            hrOpened = true;
            return;
        }

        LinearLayout box = new LinearLayout(this);
        box.setOrientation(flags == 1 ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        applyBlockStyle(box, s, parent);

        parent.addView(box);
        stack.push(box);
    }

    public void ncoreOnBlockClose() {
        if (hrOpened) {
            hrOpened = false;
            return;
        }
        if (stack.size() > 1) {
            stack.pop();
        }
    }

    public void ncoreOnText(int styleId, int flags, int[] cps, String url) {
        if (cps == null || cps.length == 0) {
            return;
        }
        Style s = styles.get(styleId);
        if (s == null) {
            s = new Style();
        }
        LinearLayout parent = stack.peek();

        TextView tv = new TextView(this);
        tv.setText(new String(cps, 0, cps.length));
        tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, s.size);
        tv.setTextColor(url != null ? 0xFF1976D2 : s.fg);

        int tf = Typeface.NORMAL;
        if (s.bold && s.italic) {
            tf = Typeface.BOLD_ITALIC;
        } else if (s.bold) {
            tf = Typeface.BOLD;
        } else if (s.italic) {
            tf = Typeface.ITALIC;
        }
        tv.setTypeface(null, tf);
        if (s.underline || url != null) {
            tv.setPaintFlags(tv.getPaintFlags() | Paint.UNDERLINE_TEXT_FLAG);
        }
        if (s.strike) {
            tv.setPaintFlags(tv.getPaintFlags() | Paint.STRIKE_THRU_TEXT_FLAG);
        }
        if (s.bg != 0) {
            tv.setBackgroundColor(s.bg);
        }

        int width = parent.getOrientation() == LinearLayout.HORIZONTAL
                ? ViewGroup.LayoutParams.WRAP_CONTENT
                : ViewGroup.LayoutParams.MATCH_PARENT;
        tv.setLayoutParams(new LinearLayout.LayoutParams(
                width, ViewGroup.LayoutParams.WRAP_CONTENT));
        applyAlign(tv, s.align);

        if (url != null && !url.isEmpty()) {
            final String target = url;
            tv.setOnClickListener(v -> {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(target)));
                } catch (Exception e) {
                    Toast.makeText(this, "Cannot open link", Toast.LENGTH_SHORT).show();
                }
            });
        }
        parent.addView(tv);
    }

    public void ncoreOnImage(int styleId, int w, int h, byte[] data) {
        Style s = styles.get(styleId);
        if (s == null) {
            s = new Style();
        }
        ImageView iv = new ImageView(this);
        if (data != null && data.length > 0) {
            android.graphics.Bitmap bmp =
                    BitmapFactory.decodeByteArray(data, 0, data.length);
            if (bmp != null) {
                iv.setImageBitmap(bmp);
            } else {
                iv.setImageResource(android.R.drawable.ic_menu_gallery);
            }
        } else {
            iv.setImageResource(android.R.drawable.ic_menu_gallery);
        }
        int width = w > 0 ? dp(w) : ViewGroup.LayoutParams.WRAP_CONTENT;
        int height = h > 0 ? dp(h) : ViewGroup.LayoutParams.WRAP_CONTENT;
        iv.setLayoutParams(new LinearLayout.LayoutParams(width, height));
        applyAlign(iv, s.align);
        stack.peek().addView(iv);
    }

    public void ncoreOnSpacer(int h) {
        View v = new View(this);
        v.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Math.max(1, dp(h))));
        stack.peek().addView(v);
    }

    public void ncoreOnError(int code) {
        Log.e("NCoreVM", "decode error code " + code);
        Toast.makeText(this, "NCore decode error (code " + code + ")", Toast.LENGTH_LONG)
                .show();
    }

    public void ncoreOnComplete() {
        Toast.makeText(this, "Rendered with NCore native engine", Toast.LENGTH_SHORT).show();
    }

    // ---- Styling helpers ---------------------------------------------------

    private void applyBlockStyle(LinearLayout box, Style s, LinearLayout parent) {
        GradientDrawable gd = new GradientDrawable();
        gd.setColor(s.bg);
        if (s.corner > 0) {
            gd.setCornerRadius(dp(s.corner));
        }
        if (s.bw > 0) {
            gd.setStroke(dp(s.bw), s.bc);
        }
        box.setBackground(gd);
        int p = dp(s.pad);
        box.setPadding(p, p, p, p);

        int width = parent.getOrientation() == LinearLayout.HORIZONTAL
                ? ViewGroup.LayoutParams.WRAP_CONTENT
                : ViewGroup.LayoutParams.MATCH_PARENT;
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                width, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(s.mt);
        lp.bottomMargin = dp(s.mb);
        box.setLayoutParams(lp);
        applyAlign(box, s.align);
    }

    private void applyAlign(View v, int align) {
        int gravity = Gravity.START;
        if (align == ALIGN_CENTER) {
            gravity = Gravity.CENTER_HORIZONTAL;
        } else if (align == ALIGN_RIGHT) {
            gravity = Gravity.END;
        }
        if (v.getLayoutParams() instanceof LinearLayout.LayoutParams) {
            ((LinearLayout.LayoutParams) v.getLayoutParams()).gravity = gravity;
        }
        if (v instanceof TextView) {
            ((TextView) v).setGravity(gravity);
        }
    }

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value,
                getResources().getDisplayMetrics()));
    }
}
""")

# ===========================================================================
# The offline encoder (separate tool). The app never compiles HTML -> .ncore.
# ===========================================================================

create_file("encoder/ncore_encode.py", r'''
#!/usr/bin/env python3
# NCore v3 offline encoder.
#
# This tool is intentionally NOT part of the Android app. The app only ships the
# native interpreter, so a memory dump of the running app can never be turned
# back into a valid .ncore file or an HTML compiler.
#
# Pipeline:
#   HTML/CSS -> DOM -> instruction stream -> opcode permutation + glyph alphabet
#            -> ChaCha20(bodyKey) -> HMAC-SHA256 tag -> .ncore
#
# Usage:
#   python3 ncore_encode.py input.html output.ncore [--key-file master.key]
#   python3 ncore_encode.py --dump output.ncore
import argparse
import base64
import hashlib
import hmac
import os
import random
import re
import struct
import sys
from html.parser import HTMLParser

MAGIC = b'NCB3'
VERSION = 3
HEADER_SIZE = 48
TAG_SIZE = 32

OP_END = 0x00
OP_STYLE = 0x01
OP_BLOCK_OPEN = 0x02
OP_BLOCK_CLOSE = 0x03
OP_TEXT = 0x04
OP_IMAGE = 0x05
OP_SPACER = 0x06

K_ROOT = 0
K_DIV = 1
K_P = 2
K_H1 = 3
K_H2 = 4
K_H3 = 5
K_H4 = 6
K_H5 = 7
K_H6 = 8
K_BLOCKQUOTE = 9
K_PRE = 10
K_UL = 11
K_OL = 12
K_LI = 13
K_TABLE = 14
K_TR = 15
K_TD = 16
K_TH = 17
K_SECTION = 18
K_HEADER = 19
K_FOOTER = 20
K_MAIN = 21
K_NAV = 22
K_ASIDE = 23
K_ARTICLE = 24
K_BUTTON = 25
K_IMG = 26
K_HR = 27
K_BR = 28
K_LABEL = 29

BLOCK_KINDS = {
    'div': K_DIV, 'p': K_P, 'h1': K_H1, 'h2': K_H2, 'h3': K_H3, 'h4': K_H4,
    'h5': K_H5, 'h6': K_H6, 'blockquote': K_BLOCKQUOTE, 'pre': K_PRE,
    'ul': K_UL, 'ol': K_OL, 'li': K_LI, 'table': K_TABLE, 'tr': K_TR,
    'td': K_TD, 'th': K_TH, 'section': K_SECTION, 'header': K_HEADER,
    'footer': K_FOOTER, 'main': K_MAIN, 'nav': K_NAV, 'aside': K_ASIDE,
    'article': K_ARTICLE, 'button': K_BUTTON, 'label': K_LABEL,
    'figure': K_SECTION, 'figcaption': K_P, 'dl': K_DIV, 'dt': K_LI,
    'dd': K_LI, 'form': K_DIV, 'fieldset': K_DIV, 'details': K_DIV,
    'summary': K_P, 'caption': K_P,
}

VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
             'link', 'meta', 'param', 'source', 'track', 'wbr'}

INLINE_KINDS = {'span', 'a', 'b', 'strong', 'i', 'em', 'u', 's', 'strike',
                'code', 'small', 'mark', 'sup', 'sub', 'font', 'q', 'cite',
                'abbr', 'time'}

STYLE_KEYS = ['fg', 'bg', 'size', 'bold', 'italic', 'underline', 'strike',
              'align', 'mt', 'mb', 'pad', 'corner', 'bw', 'bc']

DEFAULT_ST = {
    'fg': 0xFF212121, 'bg': 0x00000000, 'size': 16, 'bold': 0, 'italic': 0,
    'underline': 0, 'strike': 0, 'align': 0, 'mt': 8, 'mb': 8, 'pad': 0,
    'corner': 0, 'bw': 0, 'bc': 0xFFE0E0E0,
}

INHERITED = ('fg', 'size', 'bold', 'italic', 'underline', 'strike', 'align')

ALIGN_MAP = {'left': 0, 'start': 0, 'center': 1, 'right': 2, 'end': 2,
             'justify': 3}

NAMED_COLORS = {
    'black': '000000', 'white': 'ffffff', 'red': 'ff0000', 'green': '008000',
    'blue': '0000ff', 'yellow': 'ffff00', 'orange': 'ffa500', 'purple': '800080',
    'gray': '808080', 'grey': '808080', 'silver': 'c0c0c0', 'maroon': '800000',
    'navy': '000080', 'teal': '008080', 'olive': '808000', 'lime': '00ff00',
    'aqua': '00ffff', 'cyan': '00ffff', 'magenta': 'ff00ff', 'fuchsia': 'ff00ff',
    'brown': 'a52a2a', 'pink': 'ffc0cb', 'gold': 'ffd700', 'darkgray': 'a9a9a9',
    'darkgrey': 'a9a9a9', 'lightgray': 'd3d3d3', 'lightgrey': 'd3d3d3',
}

# ---------------------------------------------------------------------------
# ChaCha20 / HKDF (matching the native implementation byte for byte)
# ---------------------------------------------------------------------------

MASK32 = 0xffffffff


def _rotl(v, c):
    return ((v << c) & MASK32) | (v >> (32 - c))


def _qr(x, a, b, c, d):
    x[a] = (x[a] + x[b]) & MASK32
    x[d] ^= x[a]
    x[d] = _rotl(x[d], 16)
    x[c] = (x[c] + x[d]) & MASK32
    x[b] ^= x[c]
    x[b] = _rotl(x[b], 12)
    x[a] = (x[a] + x[b]) & MASK32
    x[d] ^= x[a]
    x[d] = _rotl(x[d], 8)
    x[c] = (x[c] + x[d]) & MASK32
    x[b] ^= x[c]
    x[b] = _rotl(x[b], 7)


def chacha_block(key, counter, nonce):
    st = [0x61707865, 0x3320646e, 0x79622d32, 0x6b206574]
    st += list(struct.unpack('<8I', key))
    st.append(counter & MASK32)
    st += list(struct.unpack('<3I', nonce))
    x = list(st)
    for _ in range(10):
        _qr(x, 0, 4, 8, 12); _qr(x, 1, 5, 9, 13)
        _qr(x, 2, 6, 10, 14); _qr(x, 3, 7, 11, 15)
        _qr(x, 0, 5, 10, 15); _qr(x, 1, 6, 11, 12)
        _qr(x, 2, 7, 8, 13); _qr(x, 3, 4, 9, 14)
    out = [(x[i] + st[i]) & MASK32 for i in range(16)]
    return struct.pack('<16I', *out)


def chacha20_xor(key, nonce, data, counter=0):
    out = bytearray(len(data))
    for off in range(0, len(data), 64):
        ks = chacha_block(key, counter, nonce)
        chunk = data[off:off + 64]
        for i in range(len(chunk)):
            out[off + i] = chunk[i] ^ ks[i]
        counter = (counter + 1) & MASK32
    return bytes(out)


def hkdf_sha256(ikm, salt, info, length):
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    okm = b''
    t = b''
    i = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:length]


# ---------------------------------------------------------------------------
# DOM
# ---------------------------------------------------------------------------

class Node(object):
    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = attrs
        self.children = []


class DomBuilder(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.root = Node('#root', {})
        self.stack = [self.root]
        self.style_blocks = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        node = Node(tag, {k.lower(): (v or '') for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        self.stack[-1].children.append(
            Node(tag, {k.lower(): (v or '') for k, v in attrs}))

    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.stack[-1].tag == 'script':
            return
        if self.stack[-1].tag == 'style':
            self.style_blocks.append(data)
            return
        self.stack[-1].children.append(data)


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS_RULES = []


def parse_decls(text):
    decls = {}
    for part in text.split(';'):
        if ':' not in part:
            continue
        prop, _, val = part.partition(':')
        prop = prop.strip().lower()
        val = val.strip()
        if prop and val:
            decls[prop] = val
    return decls


def selector_specificity(sel):
    spec = 0
    spec += 100 * sel.count('#')
    spec += 10 * sel.count('.')
    spec += len(re.findall(r'(?<![.#\w-])[a-z][a-z0-9]*', sel))
    return spec


def compile_css(css_text):
    css_text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.S)
    for match in re.findall(r'([^{}]+)\{([^{}]*)\}', css_text):
        selectors, body = match
        decls = parse_decls(body)
        for sel in selectors.split(','):
            sel = sel.strip().lower()
            if sel:
                CSS_RULES.append((sel, selector_specificity(sel), decls))


def selector_matches(sel, node):
    if sel == '*':
        return True
    m = re.match(r'^([a-z0-9]+)?((?:[.#][A-Za-z0-9_-]+)*)$', sel)
    if not m:
        return False
    tag, rest = m.group(1), m.group(2) or ''
    if tag and tag != node.tag:
        return False
    for token in re.findall(r'[.#][A-Za-z0-9_-]+', rest):
        if token[0] == '.':
            classes = node.attrs.get('class', '').split()
            if token[1:] not in classes:
                return False
        else:
            if node.attrs.get('id') != token[1:]:
                return False
    return True


def parse_color(value):
    value = value.strip().lower()
    if value in ('', 'transparent', 'none', 'initial', 'inherit'):
        return 0x00000000
    if value in NAMED_COLORS:
        value = '#' + NAMED_COLORS[value]
    if value.startswith('#'):
        h = value[1:]
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        if len(h) == 4:
            h = ''.join(c * 2 for c in h)
        if len(h) == 6:
            return 0xFF000000 | int(h, 16)
        if len(h) == 8:
            return int(h, 16)
    m = re.match(r'rgba?\(([^)]*)\)', value)
    if m:
        parts = [p.strip() for p in m.group(1).split(',')]
        try:
            r = int(float(parts[0]))
            g = int(float(parts[1]))
            b = int(float(parts[2]))
            a = 255 if len(parts) < 4 else int(float(parts[3]) * 255)
            return ((a & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)
        except (ValueError, IndexError):
            return 0xFF212121
    return 0xFF212121


def parse_len(value, base=16):
    value = value.strip().lower()
    m = re.match(r'^(-?[\d.]+)(px|pt|em|rem|%)?$', value)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2) or 'px'
    if unit == 'px':
        return int(round(n))
    if unit == 'pt':
        return int(round(n * 1.3333))
    if unit in ('em', 'rem'):
        return int(round(n * base))
    return None


def apply_decls(style, decls):
    if 'color' in decls:
        style['fg'] = parse_color(decls['color'])
    if 'background' in decls:
        style['bg'] = parse_color(decls['background'])
    if 'background-color' in decls:
        style['bg'] = parse_color(decls['background-color'])
    if 'font-size' in decls:
        size = parse_len(decls['font-size'])
        if size is not None:
            style['size'] = max(1, size)
    if 'font-weight' in decls:
        fw = decls['font-weight'].strip().lower()
        if fw in ('bold', 'bolder') or (fw.isdigit() and int(fw) >= 600):
            style['bold'] = 1
        elif fw in ('normal', 'lighter') or fw == '400':
            style['bold'] = 0
    if 'font-style' in decls:
        style['italic'] = 1 if decls['font-style'].strip().lower() in ('italic', 'oblique') else 0
    if 'text-align' in decls:
        key = decls['text-align'].strip().lower()
        if key in ALIGN_MAP:
            style['align'] = ALIGN_MAP[key]
    if 'text-decoration' in decls or 'text-decoration-line' in decls:
        deco = decls.get('text-decoration') or decls.get('text-decoration-line')
        deco = deco.lower()
        if 'underline' in deco:
            style['underline'] = 1
        if 'line-through' in deco:
            style['strike'] = 1
    if 'margin' in decls:
        parts = decls['margin'].split()
        if parts:
            top = parse_len(parts[0])
            bottom = parse_len(parts[2]) if len(parts) >= 3 else (
                parse_len(parts[0]) if len(parts) >= 1 else None)
            if top is not None:
                style['mt'] = min(255, max(0, top))
            if bottom is not None:
                style['mb'] = min(255, max(0, bottom))
    if 'margin-top' in decls:
        v = parse_len(decls['margin-top'])
        if v is not None:
            style['mt'] = min(255, max(0, v))
    if 'margin-bottom' in decls:
        v = parse_len(decls['margin-bottom'])
        if v is not None:
            style['mb'] = min(255, max(0, v))
    if 'padding' in decls:
        v = parse_len(decls['padding'].split()[0])
        if v is not None:
            style['pad'] = min(255, max(0, v))
    if 'padding-top' in decls:
        v = parse_len(decls['padding-top'])
        if v is not None:
            style['pad'] = min(255, max(0, v))
    if 'border-radius' in decls:
        v = parse_len(decls['border-radius'].split()[0])
        if v is not None:
            style['corner'] = min(255, max(0, v))
    if 'border' in decls:
        parts = decls['border'].split()
        for p in parts:
            ln = parse_len(p)
            if ln is not None:
                style['bw'] = min(255, max(0, ln))
            elif p.startswith('#') or p in NAMED_COLORS:
                style['bc'] = parse_color(p)
    if 'border-width' in decls:
        v = parse_len(decls['border-width'].split()[0])
        if v is not None:
            style['bw'] = min(255, max(0, v))
    if 'border-color' in decls:
        style['bc'] = parse_color(decls['border-color'])


def compute_style(node, parent_style):
    style = dict(DEFAULT_ST)
    for key in INHERITED:
        style[key] = parent_style[key]
    tag = node.tag
    if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
        style['size'] = {'h1': 30, 'h2': 24, 'h3': 19, 'h4': 16,
                         'h5': 13, 'h6': 12}[tag]
        style['bold'] = 1
        style['mt'] = 12
        style['mb'] = 8
    elif tag == 'p':
        style['mt'] = 8
        style['mb'] = 8
    elif tag == 'li':
        style['mt'] = 2
        style['mb'] = 2
    elif tag == 'button':
        style['fg'] = 0xFFFFFFFF
        style['bg'] = 0xFF1E88E5
        style['bold'] = 1
        style['size'] = 15
        style['align'] = 1
        style['mt'] = 8
        style['mb'] = 8
        style['pad'] = 12
        style['corner'] = 24
    elif tag == 'a':
        style['fg'] = 0xFF1976D2
        style['underline'] = 1
    elif tag in ('code', 'pre'):
        style['fg'] = 0xFF6A1B9A
        style['bg'] = 0x0F000000
        style['pad'] = 2
    elif tag in ('blockquote',):
        style['bg'] = 0x0A000000
        style['pad'] = 10
        style['bw'] = 3
        style['bc'] = 0xFFBDBDBD
    elif tag in ('th',):
        style['bold'] = 1
        style['bg'] = 0x14000000
        style['pad'] = 6
    elif tag in ('td',):
        style['pad'] = 6
    elif tag in ('table',):
        style['bw'] = 1
        style['bc'] = 0xFFDDDDDD
    elif tag == 'mark':
        style['bg'] = 0xFFFFFF00

    matched = [r for r in CSS_RULES if selector_matches(r[0], node)]
    matched.sort(key=lambda r: r[1])
    for _, _, decls in matched:
        apply_decls(style, decls)

    if 'style' in node.attrs:
        apply_decls(style, parse_decls(node.attrs['style']))

    return style


# ---------------------------------------------------------------------------
# Emitter
# ---------------------------------------------------------------------------

WS_RE = re.compile(r'\s+')


class Emitter(object):
    def __init__(self, alphabet, enc_of, base_dir):
        self.alphabet = alphabet
        self.enc_of = enc_of
        self.glyph = {cp: i for i, cp in enumerate(alphabet)}
        self.repl = self.glyph.get(0xFFFD, 0)
        self.base_dir = base_dir
        self.ops = bytearray()
        self.style_defs = bytearray()
        self.style_ids = {}
        self.next_style = 1

    def op(self, real_opcode):
        self.ops.append(self.enc_of[real_opcode])

    def u8(self, v):
        self.ops.append(v & 0xFF)

    def u16(self, v):
        self.ops += struct.pack('<H', v & 0xFFFF)

    def u32(self, v):
        self.ops += struct.pack('<I', v & 0xFFFFFFFF)

    def style_id(self, style):
        key = tuple(style[k] for k in STYLE_KEYS)
        if key in self.style_ids:
            return self.style_ids[key]
        sid = self.next_style
        self.next_style += 1
        self.style_ids[key] = sid
        self.style_defs.append(self.enc_of[OP_STYLE])
        self.style_defs += struct.pack('<H', sid)
        self.style_defs += struct.pack('<II', style['fg'] & 0xFFFFFFFF,
                                       style['bg'] & 0xFFFFFFFF)
        self.style_defs += struct.pack('<H', style['size'] & 0xFFFF)
        self.style_defs.append(style['bold'] & 0xFF)
        self.style_defs.append(style['italic'] & 0xFF)
        self.style_defs.append(style['underline'] & 0xFF)
        self.style_defs.append(style['strike'] & 0xFF)
        self.style_defs.append(style['align'] & 0xFF)
        self.style_defs += struct.pack('<HHHHH', style['mt'] & 0xFFFF,
                                       style['mb'] & 0xFFFF, style['pad'] & 0xFFFF,
                                       style['corner'] & 0xFFFF, style['bw'] & 0xFFFF)
        self.style_defs += struct.pack('<I', style['bc'] & 0xFFFFFFFF)
        return sid

    def emit_text(self, text, style, url):
        if not text:
            return
        sid = self.style_id(style)
        self.op(OP_TEXT)
        self.u16(sid)
        self.u16(0)
        url_bytes = url.encode('utf-8') if url else b''
        self.u16(len(url_bytes))
        self.ops += url_bytes
        glyphs = [self.glyph.get(ord(ch), self.repl) for ch in text]
        self.u32(len(glyphs))
        for g in glyphs:
            self.u16(g)

    def emit_image(self, node, parent_style):
        src = node.attrs.get('src', '')
        data = b''
        if src.startswith('data:') and ',' in src:
            try:
                data = base64.b64decode(src.split(',', 1)[1])
            except Exception:
                data = b''
        elif src and not src.startswith(('http://', 'https://')) and self.base_dir:
            candidate = os.path.join(self.base_dir, src)
            if os.path.isfile(candidate):
                with open(candidate, 'rb') as handle:
                    data = handle.read()
        width = parse_len(node.attrs.get('width', '')) or 0
        height = parse_len(node.attrs.get('height', '')) or 0
        sid = self.style_id(compute_style(node, parent_style))
        self.op(OP_IMAGE)
        self.u16(sid)
        self.u16(max(0, min(65535, width)))
        self.u16(max(0, min(65535, height)))
        self.u32(len(data))
        self.ops += data

    def emit_spacer(self, height):
        self.op(OP_SPACER)
        self.u16(max(0, min(65535, height)))

    def emit_block_open(self, kind, style, flags):
        self.op(OP_BLOCK_OPEN)
        self.u16(kind)
        self.u16(self.style_id(style))
        self.u16(flags)

    def emit_block_close(self):
        self.op(OP_BLOCK_CLOSE)

    def build_body(self):
        body = bytearray()
        body.append(1)  # format minor
        return body


def emit_children(em, node, style, link):
    pending = []

    def flush():
        if not pending:
            return
        text = WS_RE.sub(' ', ''.join(pending)).strip()
        del pending[:]
        if text:
            em.emit_text(text, style, link)

    for child in node.children:
        if isinstance(child, str):
            pending.append(child)
            continue
        tag = child.tag
        if tag == 'script' or tag == 'style':
            continue
        if tag in VOID_TAGS:
            flush()
            if tag == 'br':
                em.emit_spacer(6)
            elif tag == 'hr':
                em.emit_block_open(K_HR, compute_style(child, style), 0)
                em.emit_block_close()
            elif tag == 'img':
                em.emit_image(child, style)
            continue
        if tag in INLINE_KINDS:
            flush()
            child_style = compute_style(child, style)
            child_link = child.attrs.get('href', link) if tag == 'a' else link
            emit_children(em, child, child_style, child_link)
            continue
        flush()
        emit_block(em, child, style)
    flush()


def emit_block(em, node, parent_style):
    tag = node.tag
    style = compute_style(node, parent_style)
    if tag == 'hr':
        em.emit_block_open(K_HR, style, 0)
        em.emit_block_close()
        return
    if tag == 'br':
        em.emit_spacer(6)
        return
    if tag == 'img':
        em.emit_image(node, parent_style)
        return

    kind = BLOCK_KINDS.get(tag, K_DIV)
    if tag in ('ul', 'ol'):
        em.emit_block_open(kind, style, 0)
        index = 0
        for child in node.children:
            if isinstance(child, str) or child.tag != 'li':
                continue
            index += 1
            marker = '- ' if tag == 'ul' else (str(index) + '. ')
            item_style = compute_style(child, style)
            em.emit_block_open(K_LI, item_style, 1)
            em.emit_text(marker, item_style, None)
            emit_children(em, child, item_style, None)
            em.emit_block_close()
        em.emit_block_close()
        return

    flags = 1 if tag == 'tr' else 0
    em.emit_block_open(kind, style, flags)
    emit_children(em, node, style, None)
    em.emit_block_close()


# ---------------------------------------------------------------------------
# Encode / decode
# ---------------------------------------------------------------------------

def collect_codepoints(node, acc):
    for child in node.children:
        if isinstance(child, str):
            acc.update(child)
        else:
            collect_codepoints(child, acc)


def encode(html_bytes, master_key, out_path):
    text = html_bytes.decode('utf-8', 'replace')
    builder = DomBuilder()
    builder.feed(text)
    builder.close()
    compile_css('\n'.join(builder.style_blocks))

    file_id = os.urandom(8)
    seed = int.from_bytes(file_id, 'big') ^ 0x9E3779B97F4A7C15
    rnd = random.Random(seed)

    codepoints = set(' \t\n\r0123456789.-+*#:;,/%()[]')
    codepoints.add('\uFFFD')
    collect_codepoints(builder.root, codepoints)
    codepoints = {cp for cp in codepoints if ord(cp) <= 0xFFFF}
    if len(codepoints) > 65535:
        raise SystemExit('too many distinct characters (>65535)')
    alphabet = sorted(ord(cp) for cp in codepoints)
    rnd.shuffle(alphabet)

    op_map = list(range(256))
    rnd.shuffle(op_map)
    enc_of = [0] * 256
    for i, real in enumerate(op_map):
        enc_of[real] = i

    base_dir = os.path.dirname(os.path.abspath(out_path)) if out_path else None
    em = Emitter(alphabet, enc_of, base_dir)
    emit_children(em, builder.root, dict(DEFAULT_ST), None)
    enc_end = bytes([enc_of[OP_END]])

    body = bytearray()
    body.append(1)
    body += bytes(op_map)
    body += struct.pack('<H', len(alphabet))
    for cp in alphabet:
        body += struct.pack('<I', cp)
    body += em.style_defs
    body += em.ops
    body += enc_end

    body_key = hkdf_sha256(master_key, file_id, b'ncore3/body', 32)
    mac_key = hkdf_sha256(master_key, file_id, b'ncore3/mac', 32)
    nonce = file_id + b'\x00\x00\x00\x00'
    cipher = chacha20_xor(body_key, nonce, bytes(body), 0)

    header = MAGIC + struct.pack('<BBH', VERSION, 0, HEADER_SIZE) + file_id + \
        struct.pack('<Q', len(cipher)) + b'\x00' * 8 + b'\x00' * 16
    if len(header) != HEADER_SIZE:
        raise SystemExit('internal header size bug')
    tag = hmac.new(mac_key, header + cipher, hashlib.sha256).digest()

    if out_path:
        with open(out_path, 'wb') as handle:
            handle.write(header + cipher + tag)
    return len(body), len(cipher)


def decode(path, key):
    with open(path, 'rb') as handle:
        data = handle.read()
    if len(data) < HEADER_SIZE + TAG_SIZE or data[:4] != MAGIC:
        raise SystemExit('not an NCB3 file')
    file_id = data[8:16]
    body_len = struct.unpack_from('<Q', data, 16)[0]
    body = data[HEADER_SIZE:HEADER_SIZE + body_len]
    tag = data[HEADER_SIZE + body_len:HEADER_SIZE + body_len + TAG_SIZE]
    mac_key = hkdf_sha256(key, file_id, b'ncore3/mac', 32)
    body_key = hkdf_sha256(key, file_id, b'ncore3/body', 32)
    if not hmac.compare_digest(
            tag, hmac.new(mac_key, data[:HEADER_SIZE + body_len], hashlib.sha256).digest()):
        raise SystemExit('authentication failed')
    plain = chacha20_xor(body_key, file_id + b'\x00' * 4, body, 0)
    pos = 1
    op_map = plain[pos:pos + 256]
    pos += 256
    n = struct.unpack_from('<H', plain, pos)[0]
    pos += 2
    alphabet = list(struct.unpack_from('<%dI' % n, plain, pos))
    pos += 4 * n
    lines = ['alphabet: %d glyphs' % n]

    def rd(fmt, size):
        nonlocal pos
        val = struct.unpack_from(fmt, plain, pos)
        pos += size
        return val

    while pos < len(plain):
        real = op_map[plain[pos]]
        pos += 1
        if real == OP_END:
            lines.append('END')
            break
        if real == OP_STYLE:
            sid, = rd('<H', 2)
            fg, bg = rd('<II', 8)
            size, = rd('<H', 2)
            bold, italic, under, strike, align = rd('<BBBBB', 5)
            mt, mb, pad, corner, bw = rd('<HHHHH', 10)
            bc, = rd('<I', 4)
            lines.append('STYLE #%d fg=%08x bg=%08x size=%d b=%d i=%d u=%d s=%d '
                         'al=%d mt=%d mb=%d pad=%d r=%d bw=%d bc=%08x'
                         % (sid, fg, bg, size, bold, italic, under, strike, align,
                            mt, mb, pad, corner, bw, bc))
        elif real == OP_BLOCK_OPEN:
            kind, sid, flags = rd('<HHH', 6)
            lines.append('BLOCK_OPEN kind=%d style=%d flags=%d' % (kind, sid, flags))
        elif real == OP_BLOCK_CLOSE:
            lines.append('BLOCK_CLOSE')
        elif real == OP_SPACER:
            h, = rd('<H', 2)
            lines.append('SPACER %d' % h)
        elif real == OP_TEXT:
            sid, flags = rd('<HH', 4)
            url_len, = rd('<H', 2)
            url = plain[pos:pos + url_len].decode('utf-8', 'replace') if url_len else ''
            pos += url_len
            count, = rd('<I', 4)
            chars = []
            for _ in range(count):
                g, = rd('<H', 2)
                chars.append(chr(alphabet[g]))
            tail = (' url=%s' % url) if url else ''
            lines.append('TEXT style=%d flags=%d: %s%s' % (sid, flags, ''.join(chars), tail))
        elif real == OP_IMAGE:
            sid, w, h = rd('<HHH', 6)
            ln, = rd('<I', 4)
            pos += ln
            lines.append('IMAGE style=%d %dx%d bytes=%d' % (sid, w, h, ln))
        else:
            lines.append('UNKNOWN opcode 0x%02x' % real)
            break
    return lines


def load_key(path, explicit):
    if explicit:
        raw = explicit.strip()
        if len(raw) == 64:
            return bytes.fromhex(raw)
        with open(path, 'rb') as handle:
            return handle.read().strip()
    with open(path, 'r') as handle:
        return bytes.fromhex(handle.read().strip())


def main():
    parser = argparse.ArgumentParser(description='NCore v3 encoder')
    parser.add_argument('input', nargs='?', help='input HTML file')
    parser.add_argument('output', nargs='?', help='output .ncore file')
    parser.add_argument('--key-file', default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'master.key'))
    parser.add_argument('--key', default=None, help='64 hex chars (overrides key file)')
    parser.add_argument('--dump', metavar='NCORE', help='decode a .ncore for QA')
    args = parser.parse_args()

    key = load_key(args.key_file, args.key)

    if args.dump:
        for line in decode(args.dump, key):
            print(line)
        return 0

    if not args.input or not args.output:
        parser.error('input and output are required unless --dump is used')

    with open(args.input, 'rb') as handle:
        html_bytes = handle.read()
    plain_len, cipher_len = encode(html_bytes, key, args.output)
    print('wrote %s (%d plaintext bytes, %d ciphertext bytes)' % (
        args.output, plain_len, cipher_len))
    return 0


if __name__ == '__main__':
    sys.exit(main())
''')

create_file("encoder/master.key", KEY_HEX)

# ===========================================================================
# Gradle wrapper (actually used by CI now)
# ===========================================================================

create_file("gradle/wrapper/gradle-wrapper.properties", """
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.5-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")

print("[OK] NCore v3 encrypted native engine generated successfully.")
print("[OK] Encoder: encoder/ncore_encode.py  (app contains interpreter only)")
