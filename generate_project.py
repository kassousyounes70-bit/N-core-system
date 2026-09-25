import os

def create_file(path, content):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")

print("[*] Generating Android NDK Custom Native Engine (No WebView)...")

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
        versionName "1.0"

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
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
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

# 5. Native C++ Core Engine (HTML Compiler & Bytecode Interpreter)
create_file("app/src/main/cpp/native_engine.cpp", r"""
#include <jni.h>
#include <string>
#include <vector>
#include <android/log.h>

#define LOG_TAG "NCoreNativeEngine"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// NCore Custom Language Opcodes
const uint8_t OP_TEXT = 0x01;
const uint8_t OP_BUTTON = 0x02;
const char MAGIC_HEADER[] = "NCORE_V1";

// Helper function to extract text between tags
std::string extractTagContent(const std::string& html, const std::string& startTag, const std::string& endTag, size_t& searchPos) {
    size_t start = html.find(startTag, searchPos);
    if (start == std::string::npos) return "";
    
    start += startTag.length();
    size_t end = html.find(endTag, start);
    if (end == std::string::npos) return "";
    
    searchPos = end + endTag.length();
    return html.substr(start, end - start);
}

// 1. COMPILER: Translates standard HTML tags into NCore Custom Bytecode (Gibberish)
extern "C" JNIEXPORT jbyteArray JNICALL
Java_com_ncore_engine_MainActivity_compileHtmlToNCore(JNIEnv* env, jobject /* this */, jbyteArray htmlData) {
    jsize length = env->GetArrayLength(htmlData);
    jbyte* buffer = env->GetByteArrayElements(htmlData, nullptr);
    std::string htmlContent(reinterpret_cast<char*>(buffer), length);
    env->ReleaseByteArrayElements(htmlData, buffer, JNI_ABORT);

    std::vector<uint8_t> outBuffer;
    
    // Add Magic Header
    for (char c : MAGIC_HEADER) {
        if (c != '\0') outBuffer.push_back(c);
    }

    size_t searchPos = 0;
    
    // Very simple parser for demonstration: extracts <p> and <button>
    // Converts them into native binary opcodes
    while (searchPos < htmlContent.length()) {
        size_t nextP = htmlContent.find("<p>", searchPos);
        size_t nextBtn = htmlContent.find("<button>", searchPos);
        
        if (nextP == std::string::npos && nextBtn == std::string::npos) break;

        if (nextP != std::string::npos && (nextBtn == std::string::npos || nextP < nextBtn)) {
            std::string content = extractTagContent(htmlContent, "<p>", "</p>", searchPos);
            if (!content.empty()) {
                outBuffer.push_back(OP_TEXT);
                outBuffer.push_back(static_cast<uint8_t>(content.length()));
                outBuffer.insert(outBuffer.end(), content.begin(), content.end());
            }
        } else if (nextBtn != std::string::npos) {
            std::string content = extractTagContent(htmlContent, "<button>", "</button>", searchPos);
            if (!content.empty()) {
                outBuffer.push_back(OP_BUTTON);
                outBuffer.push_back(static_cast<uint8_t>(content.length()));
                outBuffer.insert(outBuffer.end(), content.begin(), content.end());
            }
        }
    }

    jbyteArray result = env->NewByteArray(outBuffer.size());
    env->SetByteArrayRegion(result, 0, outBuffer.size(), reinterpret_cast<const jbyte*>(outBuffer.data()));
    
    LOGI("HTML compiled to NCore Bytecode successfully. Size: %zu bytes", outBuffer.size());
    return result;
}

// 2. INTERPRETER: Reads the NCore Bytecode and builds Native UI directly
extern "C" JNIEXPORT void JNICALL
Java_com_ncore_engine_MainActivity_executeNCoreBytecode(JNIEnv* env, jobject instance, jbyteArray bytecodeData) {
    jsize length = env->GetArrayLength(bytecodeData);
    jbyte* buffer = env->GetByteArrayElements(bytecodeData, nullptr);

    if (length < 8) {
        LOGE("Invalid NCore file size");
        env->ReleaseByteArrayElements(bytecodeData, buffer, JNI_ABORT);
        return;
    }

    std::string header(reinterpret_cast<char*>(buffer), 8);
    if (header != MAGIC_HEADER) {
        LOGE("Invalid NCore Magic Header!");
        env->ReleaseByteArrayElements(bytecodeData, buffer, JNI_ABORT);
        return;
    }

    // Get Java methods to draw native UI
    jclass mainActivityClass = env->GetObjectClass(instance);
    jmethodID addTextMethod = env->GetMethodID(mainActivityClass, "addNativeText", "(Ljava/lang/String;)V");
    jmethodID addButtonMethod = env->GetMethodID(mainActivityClass, "addNativeButton", "(Ljava/lang/String;)V");

    size_t index = 8; // Skip header

    // Read opcodes and execute
    while (index < static_cast<size_t>(length)) {
        uint8_t opcode = static_cast<uint8_t>(buffer[index++]);

        if (opcode == OP_TEXT || opcode == OP_BUTTON) {
            if (index >= static_cast<size_t>(length)) break;
            
            uint8_t strLen = static_cast<uint8_t>(buffer[index++]);
            
            if (index + strLen > static_cast<size_t>(length)) break;
            
            std::string content(reinterpret_cast<char*>(buffer + index), strLen);
            index += strLen;

            jstring jContent = env->NewStringUTF(content.c_str());

            if (opcode == OP_TEXT) {
                env->CallVoidMethod(instance, addTextMethod, jContent);
            } else if (opcode == OP_BUTTON) {
                env->CallVoidMethod(instance, addButtonMethod, jContent);
            }

            env->DeleteLocalRef(jContent);
        }
    }

    env->ReleaseByteArrayElements(bytecodeData, buffer, JNI_ABORT);
    LOGI("NCore Bytecode executed and rendered natively.");
}
""")

# 6. Android MainActivity Host (UI, File Picker, Native JNI Bridge)
create_file("app/src/main/java/com/ncore/engine/MainActivity.java", """
package com.ncore.engine;

import android.content.Intent;
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

    // Native Engine Methods
    public native byte[] compileHtmlToNCore(byte[] htmlData);
    public native void executeNCoreBytecode(byte[] bytecodeData);

    private byte[] importedHtmlBytes = null;
    private LinearLayout uiContainer;

    // 1. Picker: Import raw HTML file
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
                        Toast.makeText(this, "HTML Imported! Tap 'Compile to NCore'.", Toast.LENGTH_SHORT).show();
                    } catch (Exception e) {
                        e.printStackTrace();
                    }
                }
            }
    );

    // 2. Saver: Export the Custom NCore Bytecode (The Gibberish File)
    private final ActivityResultLauncher<Intent> saveNCoreLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                if (result.getResultCode() == RESULT_OK && result.getData() != null) {
                    Uri uri = result.getData().getData();
                    try (OutputStream os = getContentResolver().openOutputStream(uri)) {
                        if (importedHtmlBytes != null && os != null) {
                            // Compile HTML to our custom language format
                            byte[] ncoreBytecode = compileHtmlToNCore(importedHtmlBytes);
                            os.write(ncoreBytecode);
                            Toast.makeText(this, "Compiled file saved successfully!", Toast.LENGTH_LONG).show();
                        }
                    } catch (Exception e) {
                        e.printStackTrace();
                    }
                }
            }
    );

    // 3. Picker: Select a compiled .ncore file to execute natively
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
                        
                        // Clear the UI canvas before rendering new file
                        uiContainer.removeAllViews();
                        
                        // Send the Gibberish bytecode directly to C++ interpreter
                        executeNCoreBytecode(buffer.toByteArray());
                        
                        Toast.makeText(this, "Executing NCore Engine...", Toast.LENGTH_SHORT).show();
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
        rootLayout.setPadding(24, 24, 24, 24);

        LinearLayout controlsLayout = new LinearLayout(this);
        controlsLayout.setOrientation(LinearLayout.HORIZONTAL);

        Button btnImportHtml = new Button(this);
        btnImportHtml.setText("1. Import HTML");

        Button btnCompileSave = new Button(this);
        btnCompileSave.setText("2. Compile to NCore");

        Button btnOpenRun = new Button(this);
        btnOpenRun.setText("3. Run NCore File");

        controlsLayout.addView(btnImportHtml);
        controlsLayout.addView(btnCompileSave);
        controlsLayout.addView(btnOpenRun);

        // This is the blank canvas where C++ will draw the UI directly
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

        // Action 1
        btnImportHtml.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("*/*");
            selectHtmlLauncher.launch(intent);
        });

        // Action 2
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

        // Action 3
        btnOpenRun.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("*/*");
            openNCoreLauncher.launch(intent);
        });
    }

    // --- Native Callbacks (Called directly from C++ JNI) ---
    // The engine reads the bytecode and executes these methods.
    
    public void addNativeText(String text) {
        TextView textView = new TextView(this);
        textView.setText(text);
        textView.setTextSize(18f);
        textView.setPadding(0, 16, 0, 16);
        uiContainer.addView(textView);
    }

    public void addNativeButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setOnClickListener(v -> 
            Toast.makeText(this, "Native Button Clicked: " + text, Toast.LENGTH_SHORT).show()
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

print("[✔] NCore Native Engine Scaffolded Successfully!")
