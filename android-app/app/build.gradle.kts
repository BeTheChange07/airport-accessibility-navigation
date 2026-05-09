import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    id("com.google.android.libraries.mapsplatform.secrets-gradle-plugin")
}

val localProperties = Properties().apply {
    val localFile = rootProject.file("local.properties")
    if (localFile.exists()) {
        localFile.inputStream().use { load(it) }
    }
}
// trim() to defend against a stray trailing space in local.properties — a
// trailing whitespace inside the URL silently breaks Retrofit's baseUrl,
// so amenity polling requests never reach the server.
val apiBaseUrl: String = (
    localProperties.getProperty("API_BASE_URL")
        ?: (project.findProperty("API_BASE_URL") as String?)
        ?: "http://10.0.2.2:5000/"
    ).trim()

// We generate a small ApiConfig.kt at configuration time instead of
// using AGP's `buildConfigField` / `BuildConfig` class. Reason: Android
// Studio has a long-standing indexing bug where the generated BuildConfig
// class shows up as "Unresolved reference" in the editor even though the
// compiler finds it fine.
//
// Doing the write during *configuration* (not inside a task) guarantees
// the file exists the moment Gradle sync finishes — before the IDE
// indexes sources. That means a fresh clone / sync works with zero
// "Unresolved reference 'ApiConfig'" errors, no build required first.
// The local.properties override still works identically.
val generatedConfigDir: java.io.File =
    layout.buildDirectory.dir("generated/source/apiconfig/main").get().asFile

run {
    val pkgDir = generatedConfigDir.resolve("com/example/se6387map")
    pkgDir.mkdirs()
    val file = pkgDir.resolve("ApiConfig.kt")
    val contents =
        """
        // Generated at build time. Do not edit.
        // Source of truth: local.properties -> API_BASE_URL
        package com.example.se6387map

        object ApiConfig {
            const val BASE_URL = "$apiBaseUrl"
        }
        """.trimIndent() + "\n"
    // Only rewrite if contents changed, so we don't trigger needless
    // incremental rebuilds on every sync.
    if (!file.exists() || file.readText() != contents) {
        file.writeText(contents)
    }
}

android {
    namespace = "com.example.se6387map"
    compileSdk {
        version = release(36) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "com.example.se6387map"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
        manifestPlaceholders["MAPS_API_KEY"] = localProperties.getProperty("MAPS_API_KEY")
            ?: (project.findProperty("MAPS_API_KEY") as String?)
                    ?: ""
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
    }

    sourceSets["main"].kotlin.srcDir(generatedConfigDir)
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    debugImplementation(libs.androidx.compose.ui.tooling)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    // Google Maps
    implementation("com.google.maps.android:maps-compose:6.2.1")
    implementation("com.google.android.gms:play-services-maps:19.0.0")
    implementation("com.google.android.gms:play-services-location:21.3.0")

    // Networking
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")

    // ViewModel
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
}