#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_project.py
===================

Single-file project generator (scaffolding script) that builds a complete
Android application from embedded templates.

The generated app ("HTML Protector"):

  * imports a plain .html file plus any number of .js and .css files,
  * merges them into one single self-contained HTML document,
  * encrypts the merged document with ChaCha20 + HMAC-SHA256 (encrypt-then-MAC)
    implemented in a small self-contained native C++ layer (no external deps),
  * exports the encrypted result as a text file that looks like gibberish to
    browsers and editors,
  * can open such an encrypted file and run it directly inside a WebView,
    producing exactly the original page.

Run:
    python3 generate_project.py

Then build with Gradle (the GitHub workflow does this automatically):
    gradle assembleDebug
"""

import os
import random
import struct
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))

PACKAGE = "com.example.protector"
JAVA_DIR = os.path.join("app", "src", "main", "java", *PACKAGE.split("."))
CPP_DIR = os.path.join("app", "src", "main", "cpp")
RES_DIR = os.path.join("app", "src", "main", "res")


# --------------------------------------------------------------------------- #
# Small file helpers
# --------------------------------------------------------------------------- #
def write_text(rel_path, content):
    path = os.path.join(ROOT, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    print("  +", rel_path)


def write_bytes(rel_path, data):
    path = os.path.join(ROOT, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    print("  +", rel_path)


# --------------------------------------------------------------------------- #
# Random launcher icon (pure Python PNG encoder)
# --------------------------------------------------------------------------- #
def _png_bytes(width, height, pixels):
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type: none
        for x in range(width):
            r, g, b, a = pixels[y][x]
            raw += bytes((r, g, b, a))

    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        body = struct.pack(">I", len(data)) + tag + data
        return body + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def _icon_pixels(size):
    rng = random.Random()
    c1 = tuple(rng.randint(25, 230) for _ in range(3))
    c2 = tuple(rng.randint(25, 230) for _ in range(3))

    pixels = [[(0, 0, 0, 255) for _ in range(size)] for _ in range(size)]
    for y in range(size):
        t = y / max(1, size - 1)
        base = tuple(int(c1[i] * (1.0 - t) + c2[i] * t) for i in range(3))
        row = pixels[y]
        for x in range(size):
            row[x] = (base[0], base[1], base[2], 255)

    def blend(x, y, color, alpha):
        if 0 <= x < size and 0 <= y < size:
            r0, g0, b0, _ = pixels[y][x]
            f = alpha / 255.0
            pixels[y][x] = (
                int(r0 * (1.0 - f) + color[0] * f),
                int(g0 * (1.0 - f) + color[1] * f),
                int(b0 * (1.0 - f) + color[2] * f),
                255,
            )

    for _ in range(rng.randint(3, 6)):
        color = tuple(rng.randint(0, 255) for _ in range(3))
        alpha = rng.randint(90, 200)
        if rng.random() < 0.7:
            cx = rng.uniform(0.2, 0.8) * size
            cy = rng.uniform(0.2, 0.8) * size
            radius = rng.uniform(0.12, 0.34) * size
            for y in range(max(0, int(cy - radius) - 1),
                           min(size, int(cy + radius) + 2)):
                for x in range(max(0, int(cx - radius) - 1),
                               min(size, int(cx + radius) + 2)):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                        blend(x, y, color, alpha)
        else:
            rw = rng.uniform(0.15, 0.55) * size
            rh = rng.uniform(0.15, 0.55) * size
            x0 = int(rng.uniform(0, max(1.0, size - rw)))
            y0 = int(rng.uniform(0, max(1.0, size - rh)))
            for y in range(y0, min(size, y0 + int(rh))):
                for x in range(x0, min(size, x0 + int(rw))):
                    blend(x, y, color, alpha)

    return pixels


def generate_icons():
    densities = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }
    for folder, size in densities.items():
        pixels = _icon_pixels(size)
        write_bytes(
            os.path.join(RES_DIR, folder, "ic_launcher.png"),
            _png_bytes(size, size, pixels),
        )


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #
def build_files():
    android_manifest = r"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <application
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@style/Theme.Protector">

        <activity
            android:name=".MainActivity"
            android:configChanges="orientation|screenSize|keyboardHidden|screenLayout"
            android:exported="true"
            android:launchMode="singleTop">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>

</manifest>
"""

    layout = r"""<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:padding="12dp">

    <TextView
        android:id="@+id/title"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="@string/app_name"
        android:textSize="18sp"
        android:textStyle="bold" />

    <TextView
        android:id="@+id/status"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:paddingTop="4dp"
        android:paddingBottom="8dp"
        android:text="@string/status_idle"
        android:textSize="13sp" />

    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="horizontal">

        <com.google.android.material.button.MaterialButton
            android:id="@+id/btn_import"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:minWidth="0dp"
            android:paddingStart="4dp"
            android:paddingEnd="4dp"
            android:text="@string/btn_import"
            android:textSize="11sp" />

        <com.google.android.material.button.MaterialButton
            android:id="@+id/btn_export"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_marginStart="6dp"
            android:layout_weight="1"
            android:minWidth="0dp"
            android:paddingStart="4dp"
            android:paddingEnd="4dp"
            android:text="@string/btn_export"
            android:textSize="11sp" />

        <com.google.android.material.button.MaterialButton
            android:id="@+id/btn_open"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_marginStart="6dp"
            android:layout_weight="1"
            android:minWidth="0dp"
            android:paddingStart="4dp"
            android:paddingEnd="4dp"
            android:text="@string/btn_open"
            android:textSize="11sp" />
    </LinearLayout>

    <WebView
        android:id="@+id/webview"
        android:layout_width="match_parent"
        android:layout_height="0dp"
        android:layout_marginTop="8dp"
        android:layout_weight="1" />

</LinearLayout>
"""

    strings = r"""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">HTML Protector</string>
    <string name="status_idle">Import an HTML file (optional JS/CSS), then encrypt and export.</string>
    <string name="btn_import">Import</string>
    <string name="btn_export">Encrypt &amp; Export</string>
    <string name="btn_open">Open Encrypted</string>
</resources>
"""

    colors = r"""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="primary">#3B4FE4</color>
    <color name="primary_dark">#2A39A8</color>
    <color name="accent">#00BFA6</color>
</resources>
"""

    themes = r"""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.Protector" parent="Theme.Material3.DayNight.NoActionBar">
        <item name="colorPrimary">@color/primary</item>
        <item name="colorOnPrimary">#FFFFFF</item>
        <item name="colorSecondary">@color/accent</item>
        <item name="colorOnSecondary">#FFFFFF</item>
    </style>
</resources>
"""

    java_main = r"""package com.example.protector;

import android.content.ContentResolver;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.util.Base64;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class MainActivity extends AppCompatActivity {

    /**
     * Master key used for this personal build. Replace it with your own 64 hex
     * characters (32 bytes) before building a real distribution.
     */
    private static final String MASTER_KEY_HEX =
            "7f1c9a3e5d2b8046c1f3a5e7092b4d6e8a0c1e3f5b7d9a2c4e6f80123b5d7a9e";

    private final SecureRandom secureRandom = new SecureRandom();

    private WebView webView;
    private TextView status;
    private String mergedHtml = null;

    private final ActivityResultLauncher<String[]> importLauncher =
            registerForActivityResult(new ActivityResultContracts.OpenMultipleDocuments(),
                    uris -> {
                        if (uris == null || uris.isEmpty()) {
                            return;
                        }
                        handleImport(uris);
                    });

    private final ActivityResultLauncher<String> exportLauncher =
            registerForActivityResult(new ActivityResultContracts.CreateDocument("text/html"),
                    uri -> {
                        if (uri == null) {
                            return;
                        }
                        handleExport(uri);
                    });

    private final ActivityResultLauncher<String[]> openEncryptedLauncher =
            registerForActivityResult(new ActivityResultContracts.OpenDocument(),
                    uri -> {
                        if (uri == null) {
                            return;
                        }
                        handleOpenEncrypted(uri);
                    });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        status = findViewById(R.id.status);
        webView = findViewById(R.id.webview);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setBuiltInZoomControls(false);

        Button importButton = findViewById(R.id.btn_import);
        Button exportButton = findViewById(R.id.btn_export);
        Button openButton = findViewById(R.id.btn_open);

        importButton.setOnClickListener(view -> importLauncher.launch(new String[]{"*/*"}));

        exportButton.setOnClickListener(view -> {
            if (mergedHtml == null) {
                toast("Import an HTML file first");
                return;
            }
            exportLauncher.launch("protected.html");
        });

        openButton.setOnClickListener(view -> openEncryptedLauncher.launch(new String[]{"*/*"}));
    }

    // --------------------------------------------------------------------- //
    // Import HTML + JS + CSS, then merge into one document
    // --------------------------------------------------------------------- //
    private void handleImport(List<Uri> uris) {
        List<String> cssFiles = new ArrayList<>();
        List<String> jsFiles = new ArrayList<>();
        String html = null;
        String htmlName = null;
        int accepted = 0;

        for (Uri uri : uris) {
            String name = displayName(uri);
            String lower = name.toLowerCase(Locale.US);
            String content;
            try {
                content = readText(uri);
            } catch (IOException error) {
                toast("Cannot read: " + name);
                continue;
            }

            if (lower.endsWith(".css")) {
                cssFiles.add(content);
                accepted++;
            } else if (lower.endsWith(".js") || lower.endsWith(".mjs")) {
                jsFiles.add(content);
                accepted++;
            } else if (lower.endsWith(".html") || lower.endsWith(".htm")) {
                if (html == null) {
                    html = content;
                    htmlName = name;
                    accepted++;
                }
            } else {
                String mime = getContentResolver().getType(uri);
                if ("text/css".equals(mime)) {
                    cssFiles.add(content);
                    accepted++;
                } else if ("text/html".equals(mime)) {
                    if (html == null) {
                        html = content;
                        htmlName = name;
                        accepted++;
                    }
                } else if ("application/javascript".equals(mime)
                        || "text/javascript".equals(mime)) {
                    jsFiles.add(content);
                    accepted++;
                }
            }
        }

        if (html == null) {
            status.setText("No HTML file was selected.");
            toast("No HTML file selected");
            return;
        }

        mergedHtml = mergeHtml(html, cssFiles, jsFiles);
        showHtml(mergedHtml);
        status.setText("Merged " + accepted + " file(s) from " + htmlName
                + " (" + cssFiles.size() + " css, " + jsFiles.size() + " js). Ready to encrypt.");
        toast("Merged " + accepted + " file(s)");
    }

    static String mergeHtml(String html, List<String> cssFiles, List<String> jsFiles) {
        StringBuilder styleBlock = new StringBuilder();
        for (String css : cssFiles) {
            styleBlock.append("<style>\n").append(css).append("\n</style>\n");
        }
        StringBuilder scriptBlock = new StringBuilder();
        for (String js : jsFiles) {
            scriptBlock.append("<script>\n").append(js).append("\n</script>\n");
        }

        String result = html;

        if (styleBlock.length() > 0) {
            String lower = result.toLowerCase(Locale.US);
            int headEnd = lower.indexOf("</head>");
            if (headEnd >= 0) {
                result = result.substring(0, headEnd) + styleBlock + result.substring(headEnd);
            } else {
                int bodyStart = lower.indexOf("<body");
                if (bodyStart >= 0) {
                    result = result.substring(0, bodyStart) + styleBlock + result.substring(bodyStart);
                } else {
                    result = styleBlock + result;
                }
            }
        }

        if (scriptBlock.length() > 0) {
            String lower = result.toLowerCase(Locale.US);
            int bodyEnd = lower.lastIndexOf("</body>");
            if (bodyEnd >= 0) {
                result = result.substring(0, bodyEnd) + scriptBlock + result.substring(bodyEnd);
            } else {
                result = result + scriptBlock;
            }
        }

        return result;
    }

    // --------------------------------------------------------------------- //
    // Encrypt merged document and export it
    // --------------------------------------------------------------------- //
    private void handleExport(Uri uri) {
        try {
            byte[] plain = mergedHtml.getBytes(StandardCharsets.UTF_8);
            byte[] key = hexToBytes(MASTER_KEY_HEX);
            byte[] nonceMaterial = new byte[28];
            secureRandom.nextBytes(nonceMaterial);

            byte[] blob = NativeCrypto.encrypt(plain, key, nonceMaterial);
            Arrays.fill(plain, (byte) 0);
            Arrays.fill(key, (byte) 0);
            Arrays.fill(nonceMaterial, (byte) 0);
            if (blob == null) {
                toast("Encryption failed");
                return;
            }

            String armored = armor(blob);
            try (OutputStream out = getContentResolver().openOutputStream(uri, "wt")) {
                if (out == null) {
                    throw new IOException("null output stream");
                }
                out.write(armored.getBytes(StandardCharsets.US_ASCII));
                out.flush();
            }

            status.setText("Exported encrypted file (" + armored.length()
                    + " characters). It is unreadable without this app.");
            toast("Encrypted file exported");
        } catch (Exception error) {
            status.setText("Export failed.");
            toast("Export failed: " + error.getMessage());
        }
    }

    // --------------------------------------------------------------------- //
    // Open an encrypted file and run it directly
    // --------------------------------------------------------------------- //
    private void handleOpenEncrypted(Uri uri) {
        try {
            String text = readText(uri);
            String compact = text.replaceAll("\\s+", "");
            byte[] blob = Base64.decode(compact, Base64.DEFAULT);
            byte[] key = hexToBytes(MASTER_KEY_HEX);

            byte[] plain = NativeCrypto.decrypt(blob, key);
            Arrays.fill(key, (byte) 0);
            if (plain == null) {
                status.setText("Decryption failed (wrong key or corrupted file).");
                toast("Decryption failed");
                return;
            }

            String html = new String(plain, StandardCharsets.UTF_8);
            Arrays.fill(plain, (byte) 0);
            showHtml(html);
            status.setText("Running encrypted content: " + displayName(uri));
            toast("Encrypted file is running");
        } catch (Exception error) {
            status.setText("Cannot open encrypted file.");
            toast("Open failed: " + error.getMessage());
        }
    }

    // --------------------------------------------------------------------- //
    // Helpers
    // --------------------------------------------------------------------- //
    private void showHtml(String html) {
        webView.loadDataWithBaseURL("https://localhost/", html, "text/html", "UTF-8", null);
    }

    private String readText(Uri uri) throws IOException {
        ContentResolver resolver = getContentResolver();
        try (InputStream in = resolver.openInputStream(uri)) {
            if (in == null) {
                throw new IOException("null input stream");
            }
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int read;
            while ((read = in.read(chunk)) != -1) {
                buffer.write(chunk, 0, read);
            }
            String text = new String(buffer.toByteArray(), StandardCharsets.UTF_8);
            if (!text.isEmpty() && text.charAt(0) == '\uFEFF') {
                text = text.substring(1);
            }
            return text;
        }
    }

    private String displayName(Uri uri) {
        String result = uri.getLastPathSegment() == null ? "file" : uri.getLastPathSegment();
        try (Cursor cursor = getContentResolver().query(uri, null, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) {
                    String name = cursor.getString(index);
                    if (name != null && !name.isEmpty()) {
                        result = name;
                    }
                }
            }
        } catch (Exception ignored) {
            // Fall back to the last path segment.
        }
        return result;
    }

    private static String armor(byte[] blob) {
        String base64 = Base64.encodeToString(blob, Base64.NO_WRAP);
        StringBuilder builder = new StringBuilder(base64.length() + base64.length() / 76 + 1);
        for (int offset = 0; offset < base64.length(); offset += 76) {
            builder.append(base64, offset, Math.min(base64.length(), offset + 76)).append('\n');
        }
        return builder.toString();
    }

    static byte[] hexToBytes(String hex) {
        int length = hex.length();
        byte[] out = new byte[length / 2];
        for (int i = 0; i < length; i += 2) {
            out[i / 2] = (byte) ((Character.digit(hex.charAt(i), 16) << 4)
                    + Character.digit(hex.charAt(i + 1), 16));
        }
        return out;
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }
}
"""

    java_native = r"""package com.example.protector;

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
"""

    native_cpp = r"""#ifndef PROTECTOR_CRYPTO_TEST
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
"""

    cmake = r"""cmake_minimum_required(VERSION 3.22.1)

project(protector LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(protector SHARED native_crypto.cpp)

find_library(log-lib log)
target_link_libraries(protector ${log-lib})
"""

    root_build_gradle = r"""// Top-level build file. Module configuration lives in app/build.gradle.
plugins {
    id 'com.android.application' version '8.5.2' apply false
}
"""

    settings_gradle = r"""pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = 'HtmlProtector'
include ':app'
"""

    gradle_properties = r"""org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
org.gradle.daemon=false
android.useAndroidX=true
android.nonTransitiveRClass=true
"""

    app_build_gradle = r"""plugins {
    id 'com.android.application'
}

android {
    namespace 'com.example.protector'
    compileSdk 34
    ndkVersion '26.1.10909125'

    defaultConfig {
        applicationId 'com.example.protector'
        minSdk 21
        targetSdk 34
        versionCode 1
        versionName '1.0'

        ndk {
            abiFilters 'armeabi-v7a', 'arm64-v8a', 'x86', 'x86_64'
        }

        externalNativeBuild {
            cmake {
                cppFlags '-std=c++17 -O2 -fvisibility=hidden'
            }
        }
    }

    externalNativeBuild {
        cmake {
            path file('src/main/cpp/CMakeLists.txt')
            version '3.22.1'
        }
    }

    buildTypes {
        debug {
            debuggable true
        }
        release {
            minifyEnabled false
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'),
                    'proguard-rules.pro'
        }
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
}

dependencies {
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'androidx.activity:activity:1.8.2'
    implementation 'com.google.android.material:material:1.11.0'
}
"""

    proguard = r"""# Keep the JNI bridge; its method names are referenced from native code.
-keep class com.example.protector.NativeCrypto { *; }
"""

    files = {
        "settings.gradle": settings_gradle,
        "build.gradle": root_build_gradle,
        "gradle.properties": gradle_properties,
        "app/build.gradle": app_build_gradle,
        "app/proguard-rules.pro": proguard,
        "app/src/main/AndroidManifest.xml": android_manifest,
        "app/src/main/res/layout/activity_main.xml": layout,
        "app/src/main/res/values/strings.xml": strings,
        "app/src/main/res/values/colors.xml": colors,
        "app/src/main/res/values/themes.xml": themes,
        os.path.join(JAVA_DIR, "MainActivity.java"): java_main,
        os.path.join(JAVA_DIR, "NativeCrypto.java"): java_native,
        os.path.join(CPP_DIR, "native_crypto.cpp"): native_cpp,
        os.path.join(CPP_DIR, "CMakeLists.txt"): cmake,
    }
    return files


def main():
    print("Generating HTML Protector Android project...")
    files = build_files()
    for rel_path, content in files.items():
        write_text(rel_path, content)
    generate_icons()
    print("\nDone. Project generated at:", ROOT)
    print("Next: run 'gradle assembleDebug' (or push to GitHub and use build.yml).")


if __name__ == "__main__":
    main()
