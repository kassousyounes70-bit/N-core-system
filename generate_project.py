import os

def create_file(path, content):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")

def create_binary_file(path, data):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)

print("[*] Generating Android NDK Obfuscated Engine Project...")

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

# 3. Android Manifest
create_file("app/src/main/AndroidManifest.xml", """
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

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

# 5. Native C++ Core Engine (No HTML Decryption in RAM, Reads Raw Bytecode Directly)
create_file("app/src/main/cpp/native_engine.cpp", r"""
#include <jni.h>
#include <string>
#include <vector>
#include <android/log.h>

#define LOG_TAG "NCoreNativeEngine"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// Opcodes defined for UI construction
const uint8_t OP_CONTAINER = 0x01;
const uint8_t OP_TEXT      = 0x02;
const uint8_t OP_BUTTON    = 0x03;

extern "C" JNIEXPORT void JNICALL
Java_com_ncore_engine_MainActivity_parseAndRenderNativeUI(
        JNIEnv* env,
        jobject instance,
        jbyteArray rawData,
        jobject rootView) {

    jsize length = env->GetArrayLength(rawData);
    jbyte* buffer = env->GetByteArrayElements(rawData, nullptr);

    if (length < 14) {
        LOGE("Invalid file size");
        env->ReleaseByteArrayElements(rawData, buffer, JNI_ABORT);
        return;
    }

    // Verify Magic Header: NCORE_NATIVE_V1
    std::string magicHeader(reinterpret_cast<char*>(buffer), 15);
    if (magicHeader.rfind("NCORE_NATIVE_V1", 0) != 0) {
        LOGE("Header mismatch! File is corrupted or invalid.");
        env->ReleaseByteArrayElements(rawData, buffer, JNI_ABORT);
        return;
    }

    LOGI("Magic Header Verified. Starting direct JNI bytecode rendering...");

    // Obtain Java classes via reflection
    jclass mainActivityClass = env->GetObjectClass(instance);
    jmethodid addTextViewMethod = env->GetMethodID(mainActivityClass, "addNativeTextView", "(Ljava/lang/String;)V");
    jmethodid addButtonMethod = env->GetMethodID(mainActivityClass, "addNativeButton", "(Ljava/lang/String;)V");

    size_t index = 15; // Skip Magic Header bytes

    while (index < static_cast<size_t>(length)) {
        uint8_t opcode = static_cast<uint8_t>(buffer[index++]);

        if (opcode == OP_TEXT || opcode == OP_BUTTON) {
            if (index >= static_cast<size_t>(length)) break;
            uint8_t strLen = static_cast<uint8_t>(buffer[index++]);

            if (index + strLen > static_cast<size_t>(length)) break;
            std::string textContent(reinterpret_cast<char*>(buffer + index), strLen);
            index += strLen;

            jstring jstr = env->NewStringUTF(textContent.c_str());

            if (opcode == OP_TEXT) {
                env->CallVoidMethod(instance, addTextViewMethod, jstr);
            } else if (opcode == OP_BUTTON) {
                env->CallVoidMethod(instance, addButtonMethod, jstr);
            }

            env->DeleteLocalRef(jstr);
        }
    }

    env->ReleaseByteArrayElements(rawData, buffer, JNI_ABORT);
}
""")

# 6. Android MainActivity Host (Bridge to Native UI)
create_file("app/src/main/java/com/ncore/engine/MainActivity.java", """
package com.ncore.engine;

import android.os.Bundle;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import java.io.InputStream;

public class MainActivity extends AppCompatActivity {

    static {
        System.loadLibrary("ncore_engine");
    }

    private LinearLayout rootLayout;

    public native void parseAndRenderNativeUI(byte[] rawData, LinearLayout rootView);

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        rootLayout = new LinearLayout(this);
        rootLayout.setOrientation(LinearLayout.VERTICAL);
        rootLayout.setPadding(48, 48, 48, 48);

        setContentView(rootLayout);

        try {
            InputStream is = getAssets().open("index.html");
            byte[] rawBytes = new byte[is.available()];
            is.read(rawBytes);
            is.close();

            // Pass raw bytes straight to C++ engine
            parseAndRenderNativeUI(rawBytes, rootLayout);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    // Called from C++ JNI directly
    public void addNativeTextView(String text) {
        TextView textView = new TextView(this);
        textView.setText(text);
        textView.setTextSize(20f);
        textView.setPadding(0, 16, 0, 16);
        rootLayout.addView(textView);
    }

    // Called from C++ JNI directly
    public void addNativeButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setOnClickListener(v -> 
            Toast.makeText(MainActivity.this, "Engine Action Triggered!", Toast.LENGTH_SHORT).show()
        );
        rootLayout.addView(button);
    }
}
""")

# 7. Disguised Obfuscated Binary Asset (`index.html`)
# Header: "NCORE_NATIVE_V1" + Bytecodes for UI Elements
html_disguise_bytes = (
    b"NCORE_NATIVE_V1" +
    b"\x02\x15NCore Engine Online!" +  # OP_TEXT (Len 21)
    b"\x03\x0CExecute Code"           # OP_BUTTON (Len 12)
)
create_binary_file("app/src/main/assets/index.html", html_disguise_bytes)

# 8. Gradle Wrapper Properties
create_file("gradle/wrapper/gradle-wrapper.properties", """
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.5-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")

print("[✔] Project successfully scaffolded!")
