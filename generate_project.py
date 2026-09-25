import os

def create_file(path, content):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")

print("[*] Generating Android NDK HTML Encryptor & Runner Project...")

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

# 1.5. Gradle Properties Setup
create_file("gradle.properties", """
android.useAndroidX=true
android.enableJetifier=true
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
""")

# 2. App Module Build Script (With NDK & CMake)
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

# 3. Android Manifest (Added Internet for WebView if needed)
create_file("app/src/main/AndroidManifest.xml", """
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />

    <application
        android:allowBackup="true"
        android:icon="@android:drawable/sym_def_app_icon"
        android:label="NCore Engine"
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

# 4. CMake Build Script for Native C++
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

# 5. Native C++ Core Engine (In-Memory Encryption/Decryption)
create_file("app/src/main/cpp/native_engine.cpp", r"""
#include <jni.h>
#include <string>
#include <android/log.h>

#define LOG_TAG "NCoreNativeEngine"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

// Custom Encryption Key (Hidden in Compiled C++)
const char ENCRYPTION_KEY[] = "NCORE_SUPER_SECRET_KEY_2026";

extern "C" JNIEXPORT jbyteArray JNICALL
Java_com_ncore_engine_MainActivity_encryptData(JNIEnv* env, jobject /* this */, jbyteArray rawData) {
    jsize length = env->GetArrayLength(rawData);
    jbyte* buffer = env->GetByteArrayElements(rawData, nullptr);
    
    jbyteArray result = env->NewByteArray(length);
    jbyte* resultBuffer = env->GetByteArrayElements(result, nullptr);

    // Simple XOR cipher logic in RAM
    size_t keyLen = sizeof(ENCRYPTION_KEY) - 1;
    for (int i = 0; i < length; i++) {
        resultBuffer[i] = buffer[i] ^ ENCRYPTION_KEY[i % keyLen];
    }

    env->ReleaseByteArrayElements(rawData, buffer, JNI_ABORT);
    env->ReleaseByteArrayElements(result, resultBuffer, 0);
    
    LOGI("Data encrypted successfully. Size: %d bytes", length);
    return result;
}

extern "C" JNIEXPORT jbyteArray JNICALL
Java_com_ncore_engine_MainActivity_decryptData(JNIEnv* env, jobject /* this */, jbyteArray encryptedData) {
    jsize length = env->GetArrayLength(encryptedData);
    jbyte* buffer = env->GetByteArrayElements(encryptedData, nullptr);
    
    jbyteArray result = env->NewByteArray(length);
    jbyte* resultBuffer = env->GetByteArrayElements(result, nullptr);

    // XOR decryption (same as encryption)
    size_t keyLen = sizeof(ENCRYPTION_KEY) - 1;
    for (int i = 0; i < length; i++) {
        resultBuffer[i] = buffer[i] ^ ENCRYPTION_KEY[i % keyLen];
    }

    env->ReleaseByteArrayElements(encryptedData, buffer, JNI_ABORT);
    env->ReleaseByteArrayElements(result, resultBuffer, 0);
    
    LOGI("Data decrypted successfully in RAM. Size: %d bytes", length);
    return result;
}
""")

# 6. Android MainActivity Host (UI, File Picker, WebView, JNI Bridge)
create_file("app/src/main/java/com/ncore/engine/MainActivity.java", """
package com.ncore.engine;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.util.Base64;
import android.view.ViewGroup;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Toast;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class MainActivity extends AppCompatActivity {

    static {
        System.loadLibrary("ncore_engine");
    }

    // Native Methods
    public native byte[] encryptData(byte[] rawData);
    public native byte[] decryptData(byte[] encryptedData);

    private byte[] selectedFileBytes = null;
    private byte[] currentEncryptedBytes = null;
    private WebView webView;

    // File Picker for Raw HTML
    private final ActivityResultLauncher<Intent> htmlPickerLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                if (result.getResultCode() == RESULT_OK && result.getData() != null) {
                    Uri uri = result.getData().getData();
                    try {
                        InputStream is = getContentResolver().openInputStream(uri);
                        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                        int nRead;
                        byte[] data = new byte[16384];
                        while ((nRead = is.read(data, 0, data.length)) != -1) {
                            buffer.write(data, 0, nRead);
                        }
                        selectedFileBytes = buffer.toByteArray();
                        is.close();
                        Toast.makeText(this, "HTML Loaded! Ready to encrypt.", Toast.LENGTH_SHORT).show();
                    } catch (Exception e) {
                        e.printStackTrace();
                        Toast.makeText(this, "Failed to read file.", Toast.LENGTH_SHORT).show();
                    }
                }
            }
    );

    // File Picker for Encrypted File
    private final ActivityResultLauncher<Intent> encryptedPickerLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                if (result.getResultCode() == RESULT_OK && result.getData() != null) {
                    Uri uri = result.getData().getData();
                    try {
                        InputStream is = getContentResolver().openInputStream(uri);
                        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                        int nRead;
                        byte[] data = new byte[16384];
                        while ((nRead = is.read(data, 0, data.length)) != -1) {
                            buffer.write(data, 0, nRead);
                        }
                        currentEncryptedBytes = buffer.toByteArray();
                        is.close();
                        
                        // Decrypt in RAM instantly and load to WebView
                        byte[] decryptedBytes = decryptData(currentEncryptedBytes);
                        String htmlContent = new String(decryptedBytes, StandardCharsets.UTF_8);
                        
                        // Load into WebView without saving to disk
                        webView.loadDataWithBaseURL(null, htmlContent, "text/html", "UTF-8", null);
                        Toast.makeText(this, "Decrypted & Running in RAM!", Toast.LENGTH_SHORT).show();
                        
                    } catch (Exception e) {
                        e.printStackTrace();
                        Toast.makeText(this, "Failed to read encrypted file.", Toast.LENGTH_SHORT).show();
                    }
                }
            }
    );

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // UI Setup
        LinearLayout rootLayout = new LinearLayout(this);
        rootLayout.setOrientation(LinearLayout.VERTICAL);
        rootLayout.setPadding(32, 32, 32, 32);

        // Control Panel
        LinearLayout controlsLayout = new LinearLayout(this);
        controlsLayout.setOrientation(LinearLayout.HORIZONTAL);
        
        Button btnSelectHtml = new Button(this);
        btnSelectHtml.setText("Load HTML");
        
        Button btnEncrypt = new Button(this);
        btnEncrypt.setText("Encrypt & Save");
        
        Button btnRun = new Button(this);
        btnRun.setText("Run Encrypted");

        controlsLayout.addView(btnSelectHtml);
        controlsLayout.addView(btnEncrypt);
        controlsLayout.addView(btnRun);

        // WebView Setup
        webView = new WebView(this);
        WebSettings webSettings = webView.getSettings();
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        
        LinearLayout.LayoutParams webParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 
                ViewGroup.LayoutParams.MATCH_PARENT);
        webParams.topMargin = 32;
        webView.setLayoutParams(webParams);

        rootLayout.addView(controlsLayout);
        rootLayout.addView(webView);
        setContentView(rootLayout);

        // Button Listeners
        btnSelectHtml.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("*/*");
            htmlPickerLauncher.launch(intent);
        });

        btnEncrypt.setOnClickListener(v -> {
            if (selectedFileBytes == null) {
                Toast.makeText(this, "Load an HTML file first!", Toast.LENGTH_SHORT).show();
                return;
            }
            
            // Send to Native C++ for Encryption
            currentEncryptedBytes = encryptData(selectedFileBytes);
            
            // Save Encrypted file to device
            try {
                File dir = getExternalFilesDir(null);
                File outFile = new File(dir, "encrypted_ncore.bin");
                FileOutputStream fos = new FileOutputStream(outFile);
                fos.write(currentEncryptedBytes);
                fos.close();
                Toast.makeText(this, "Saved: " + outFile.getAbsolutePath(), Toast.LENGTH_LONG).show();
            } catch (Exception e) {
                e.printStackTrace();
                Toast.makeText(this, "Save Failed!", Toast.LENGTH_SHORT).show();
            }
        });

        btnRun.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("*/*");
            encryptedPickerLauncher.launch(intent);
        });
    }
}
""")

# 7. Gradle Wrapper Properties
create_file("gradle/wrapper/gradle-wrapper.properties", """
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.5-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")

print("[✔] Full File Picker, Encryption Engine, and Runner UI Scaffolding Complete!")
