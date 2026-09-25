import os

def create_file(path, content):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")

print("[*] Generating Upgraded NCore Custom Native Rendering Engine...")

# 1. Root Settings & Build Scripts
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
""")

create_file("app/build.gradle", """
plugins {
    id 'com.android.application'
}

android {
    namespace 'com.ncore.engine'
    compileSdk 34

    defaultConfig {
        applicationId "com.ncore.engine"
        minSdk 21
        targetSdk 34
        versionCode 1
        versionName "2.0"

        externalNativeBuild {
            cmake {
                cppFlags "-std=c++17"
            }
        }
    }

    buildTypes {
        release {
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
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

create_file("app/src/main/AndroidManifest.xml", """
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/manifest/android">
    <application
        android:allowBackup="true"
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

create_file("app/src/main/cpp/CMakeLists.txt", """
cmake_minimum_required(VERSION 3.22.1)
project("ncore_engine")

add_library(
    ncore_engine
    SHARED
    native_engine.cpp
)

find_library(
    log-lib
    log
)

target_link_libraries(
    ncore_engine
    ${log-lib}
)
""")

# 5. Native C++ Core Engine (Advanced Parser & Bytecode Interpreter)
create_file("app/src/main/cpp/native_engine.cpp", r"""
#include <jni.h>
#include <string>
#include <vector>
#include <algorithm>
#include <android/log.h>

#define LOG_TAG "NCoreNativeEngine"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

const uint8_t OP_TEXT = 0x01;
const uint8_t OP_BUTTON = 0x02;
const char MAGIC_HEADER[] = "NCORE_V2";

struct RenderNode {
    uint8_t opcode;
    bool isBold;
    uint32_t textColor; // ARGB
    uint32_t bgColor;   // ARGB
    uint8_t fontSize;
    std::string text;
};

// Helper to remove nested HTML tags and extract raw clean text
std::string cleanHtmlTags(const std::string& input, bool& outIsBold) {
    std::string result = "";
    outIsBold = false;
    bool inTag = false;
    std::string currentTag = "";

    for (size_t i = 0; i < input.length(); ++i) {
        char c = input[i];
        if (c == '<') {
            inTag = true;
            currentTag = "";
        } else if (c == '>') {
            inTag = false;
            std::transform(currentTag.begin(), currentTag.end(), currentTag.begin(), ::tolower);
            if (currentTag == "strong" || currentTag == "b") {
                outIsBold = true;
            }
        } else {
            if (inTag) {
                currentTag += c;
            } else {
                result += c;
            }
        }
    }
    return result;
}

extern "C" JNIEXPORT jbyteArray JNICALL
Java_com_ncore_engine_MainActivity_compileHtmlToNCore(JNIEnv* env, jobject /* this */, jbyteArray htmlData) {
    jsize length = env->GetArrayLength(htmlData);
    jbyte* buffer = env->GetByteArrayElements(htmlData, nullptr);
    std::string htmlContent(reinterpret_cast<char*>(buffer), length);
    env->ReleaseByteArrayElements(htmlData, buffer, JNI_ABORT);

    std::vector<uint8_t> outBuffer;
    
    // Add Magic Header NCORE_V2
    for (char c : MAGIC_HEADER) {
        if (c != '\0') outBuffer.push_back(c);
    }

    std::vector<RenderNode> nodes;
    size_t pos = 0;

    while (pos < htmlContent.length()) {
        size_t tagOpen = htmlContent.find('<', pos);
        if (tagOpen == std::string::npos) break;

        size_t tagClose = htmlContent.find('>', tagOpen);
        if (tagClose == std::string::npos) break;

        std::string tagName = htmlContent.substr(tagOpen + 1, tagClose - tagOpen - 1);
        std::transform(tagName.begin(), tagName.end(), tagName.begin(), ::tolower);

        // Process paragraph / text block
        if (tagName == "p" || tagName.rfind("p ", 0) == 0 || tagName == "div" || tagName.rfind("div ", 0) == 0) {
            size_t endBlock = htmlContent.find("</", tagClose);
            if (endBlock != std::string::npos) {
                std::string rawText = htmlContent.substr(tagClose + 1, endBlock - tagClose - 1);
                bool isBold = false;
                std::string cleanText = cleanHtmlTags(rawText, isBold);

                if (!cleanText.empty()) {
                    RenderNode node;
                    node.opcode = OP_TEXT;
                    node.isBold = isBold;
                    node.textColor = 0xFF212121; // Dark Gray Default
                    node.bgColor = 0x00000000;   // Transparent
                    node.fontSize = 16;
                    node.text = cleanText;
                    nodes.push_back(node);
                }
                pos = endBlock;
            }
        } 
        // Process button element
        else if (tagName == "button" || tagName.rfind("button ", 0) == 0) {
            size_t endBlock = htmlContent.find("</button>", tagClose);
            if (endBlock != std::string::npos) {
                std::string rawText = htmlContent.substr(tagClose + 1, endBlock - tagClose - 1);
                bool isBold = false;
                std::string cleanText = cleanHtmlTags(rawText, isBold);

                if (!cleanText.empty()) {
                    RenderNode node;
                    node.opcode = OP_BUTTON;
                    node.isBold = true;
                    node.textColor = 0xFFFFFFFF; // White Text
                    node.bgColor = 0xFF1E88E5;   // Material Blue
                    node.fontSize = 14;
                    node.text = cleanText;
                    nodes.push_back(node);
                }
                pos = endBlock;
            }
        }
        pos = tagClose + 1;
    }

    // Binary Serialization Protocol
    for (const auto& node : nodes) {
        outBuffer.push_back(node.opcode);
        outBuffer.push_back(node.isBold ? 0x01 : 0x00);
        
        // Write Text Color (4 bytes)
        outBuffer.push_back((node.textColor >> 24) & 0xFF);
        outBuffer.push_back((node.textColor >> 16) & 0xFF);
        outBuffer.push_back((node.textColor >> 8) & 0xFF);
        outBuffer.push_back(node.textColor & 0xFF);

        // Write BG Color (4 bytes)
        outBuffer.push_back((node.bgColor >> 24) & 0xFF);
        outBuffer.push_back((node.bgColor >> 16) & 0xFF);
        outBuffer.push_back((node.bgColor >> 8) & 0xFF);
        outBuffer.push_back(node.bgColor & 0xFF);

        outBuffer.push_back(node.fontSize);

        // Text Length (2 bytes)
        uint16_t textLen = static_cast<uint16_t>(node.text.length());
        outBuffer.push_back((textLen >> 8) & 0xFF);
        outBuffer.push_back(textLen & 0xFF);

        outBuffer.insert(outBuffer.end(), node.text.begin(), node.text.end());
    }

    jbyteArray result = env->NewByteArray(outBuffer.size());
    env->SetByteArrayRegion(result, 0, outBuffer.size(), reinterpret_cast<const jbyte*>(outBuffer.data()));
    
    LOGI("HTML Compiled into NCore Protocol. Generated %zu nodes.", nodes.size());
    return result;
}

extern "C" JNIEXPORT void JNICALL
Java_com_ncore_engine_MainActivity_executeNCoreBytecode(JNIEnv* env, jobject instance, jbyteArray bytecodeData) {
    jsize length = env->GetArrayLength(bytecodeData);
    jbyte* buffer = env->GetByteArrayElements(bytecodeData, nullptr);

    if (length < 8) {
        env->ReleaseByteArrayElements(bytecodeData, buffer, JNI_ABORT);
        return;
    }

    std::string header(reinterpret_cast<char*>(buffer), 8);
    if (header != MAGIC_HEADER) {
        LOGE("Invalid Header! File is corrupt or untrusted.");
        env->ReleaseByteArrayElements(bytecodeData, buffer, JNI_ABORT);
        return;
    }

    jclass mainActivityClass = env->GetObjectClass(instance);
    jmethodID addTextMethod = env->GetMethodID(mainActivityClass, "addNativeText", "(Ljava/lang/String;ZIII)V");
    jmethodID addButtonMethod = env->GetMethodID(mainActivityClass, "addNativeButton", "(Ljava/lang/String;II)V");

    size_t index = 8; // Skip Magic Header

    while (index < static_cast<size_t>(length)) {
        uint8_t opcode = static_cast<uint8_t>(buffer[index++]);
        bool isBold = static_cast<uint8_t>(buffer[index++]) == 0x01;

        uint32_t textColor = (static_cast<uint8_t>(buffer[index]) << 24) |
                             (static_cast<uint8_t>(buffer[index + 1]) << 16) |
                             (static_cast<uint8_t>(buffer[index + 2]) << 8) |
                             static_cast<uint8_t>(buffer[index + 3]);
        index += 4;

        uint32_t bgColor = (static_cast<uint8_t>(buffer[index]) << 24) |
                           (static_cast<uint8_t>(buffer[index + 1]) << 16) |
                           (static_cast<uint8_t>(buffer[index + 2]) << 8) |
                           static_cast<uint8_t>(buffer[index + 3]);
        index += 4;

        uint8_t fontSize = static_cast<uint8_t>(buffer[index++]);

        uint16_t strLen = (static_cast<uint8_t>(buffer[index]) << 8) | static_cast<uint8_t>(buffer[index + 1]);
        index += 2;

        std::string content(reinterpret_cast<char*>(buffer + index), strLen);
        index += strLen;

        jstring jContent = env->NewStringUTF(content.c_str());

        if (opcode == OP_TEXT) {
            env->CallVoidMethod(instance, addTextMethod, jContent, isBold, (jint)textColor, (jint)bgColor, (jint)fontSize);
        } else if (opcode == OP_BUTTON) {
            env->CallVoidMethod(instance, addButtonMethod, jContent, (jint)textColor, (jint)bgColor);
        }

        env->DeleteLocalRef(jContent);
    }

    env->ReleaseByteArrayElements(bytecodeData, buffer, JNI_ABORT);
}
""")

# 6. Android MainActivity Host (UI, Native Dynamic Styling Bridge)
create_file("app/src/main/java/com/ncore/engine/MainActivity.java", """
package com.ncore.engine;

import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;

public class MainActivity extends AppCompatActivity {

    static {
        System.loadLibrary("ncore_engine");
    }

    public native byte[] compileHtmlToNCore(byte[] htmlData);
    public native void executeNCoreBytecode(byte[] bytecodeData);

    private byte[] importedHtmlBytes = null;
    private LinearLayout uiContainer;

    private final ActivityResultLauncher<Intent> selectHtmlLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                if (result.getResultCode() == RESULT_OK && result.getData() != null) {
                    Uri uri = result.getData().getData();
                    try (InputStream is = getContentResolver().openInputStream(uri);
                         ByteArrayOutputStream buffer = new ByteArrayOutputStream()) {
                        int nRead;
                        byte[] data = new byte[16384];
                        while ((nRead = is.read(data, 0, data.length)) != -1) {
                            buffer.write(data, 0, nRead);
                        }
                        importedHtmlBytes = buffer.toByteArray();
                        Toast.makeText(this, "HTML Imported successfully!", Toast.LENGTH_SHORT).show();
                    } catch (Exception e) {
                        e.printStackTrace();
                    }
                }
            }
    );

    private final ActivityResultLauncher<Intent> saveNCoreLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                if (result.getResultCode() == RESULT_OK && result.getData() != null) {
                    Uri uri = result.getData().getData();
                    try (OutputStream os = getContentResolver().openOutputStream(uri)) {
                        if (importedHtmlBytes != null && os != null) {
                            byte[] ncoreBytecode = compileHtmlToNCore(importedHtmlBytes);
                            os.write(ncoreBytecode);
                            Toast.makeText(this, "NCore File Compiled & Saved!", Toast.LENGTH_LONG).show();
                        }
                    } catch (Exception e) {
                        e.printStackTrace();
                    }
                }
            }
    );

    private final ActivityResultLauncher<Intent> openNCoreLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                if (result.getResultCode() == RESULT_OK && result.getData() != null) {
                    Uri uri = result.getData().getData();
                    try (InputStream is = getContentResolver().openInputStream(uri);
                         ByteArrayOutputStream buffer = new ByteArrayOutputStream()) {
                        int nRead;
                        byte[] data = new byte[16384];
                        while ((nRead = is.read(data, 0, data.length)) != -1) {
                            buffer.write(data, 0, nRead);
                        }
                        
                        uiContainer.removeAllViews();
                        executeNCoreBytecode(buffer.toByteArray());
                        Toast.makeText(this, "Rendered with NCore Native Engine!", Toast.LENGTH_SHORT).show();
                    } catch (Exception e) {
                        e.printStackTrace();
                    }
                }
            }
    );

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout rootLayout = new LinearLayout(this);
        rootLayout.setOrientation(LinearLayout.VERTICAL);
        rootLayout.setPadding(32, 32, 32, 32);

        LinearLayout controlsLayout = new LinearLayout(this);
        controlsLayout.setOrientation(LinearLayout.HORIZONTAL);

        Button btnImportHtml = new Button(this);
        btnImportHtml.setText("1. IMPORT HTML");

        Button btnCompileSave = new Button(this);
        btnCompileSave.setText("2. COMPILE TO NCORE");

        Button btnOpenRun = new Button(this);
        btnOpenRun.setText("3. RUN NCORE FILE");

        controlsLayout.addView(btnImportHtml);
        controlsLayout.addView(btnCompileSave);
        controlsLayout.addView(btnOpenRun);

        uiContainer = new LinearLayout(this);
        uiContainer.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams canvasParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT);
        canvasParams.topMargin = 32;
        uiContainer.setLayoutParams(canvasParams);

        rootLayout.addView(controlsLayout);
        rootLayout.addView(uiContainer);
        setContentView(rootLayout);

        btnImportHtml.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("*/*");
            selectHtmlLauncher.launch(intent);
        });

        btnCompileSave.setOnClickListener(v -> {
            if (importedHtmlBytes == null) {
                Toast.makeText(this, "Please import an HTML file first!", Toast.LENGTH_SHORT).show();
                return;
            }
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.setType("application/octet-stream");
            intent.putExtra(Intent.EXTRA_TITLE, "app_code.ncore");
            saveNCoreLauncher.launch(intent);
        });

        btnOpenRun.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("*/*");
            openNCoreLauncher.launch(intent);
        });
    }

    // --- Dynamic Native Callbacks Invoked by C++ Engine ---

    public void addNativeText(String text, boolean isBold, int textColor, int bgColor, int fontSize) {
        TextView textView = new TextView(this);
        textView.setText(text);
        textView.setTextSize((float) fontSize);
        textView.setTextColor(textColor);

        if (isBold) {
            textView.setTypeface(null, Typeface.BOLD);
        }

        if (bgColor != 0) {
            textView.setBackgroundColor(bgColor);
        }

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, 8, 0, 8);
        textView.setLayoutParams(params);

        uiContainer.addView(textView);
    }

    public void addNativeButton(String text, int textColor, int bgColor) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(textColor);
        button.setTypeface(null, Typeface.BOLD);

        // Render Native Shape with rounded corners
        GradientDrawable shape = new GradientDrawable();
        shape.setCornerRadius(24f);
        shape.setColor(bgColor);
        button.setBackground(shape);

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, 16, 0, 16);
        button.setLayoutParams(params);

        button.setOnClickListener(v -> 
            Toast.makeText(this, "Native Action Executed: " + text, Toast.LENGTH_SHORT).show()
        );

        uiContainer.addView(button);
    }
}
""")

create_file("gradle/wrapper/gradle-wrapper.properties", """
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.5-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")

print("[✔] NCore Upgraded Native Engine Generated Successfully!")
