package com.example.protector;

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
