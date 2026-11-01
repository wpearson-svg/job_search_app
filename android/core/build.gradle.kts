// Plain Kotlin: the rules both versions share (scoring, gaps, AI requests and replies, source parsers, export format).
// No Android code here, so its tests run on any PC against the shared fixtures in ../../shared_tests.
plugins {
    id("org.jetbrains.kotlin.jvm")
    id("org.jetbrains.kotlin.plugin.serialization")
}

val repoRoot = rootProject.projectDir.parentFile

// skills.json, config.json, default_instructions.md and docs/AI_INSTRUCTIONS.md stay in the repo (one copy for both versions).
// They are copied into this module's resources at build time; never edit a copy.
val sharedResources by tasks.registering(Copy::class) {
    from(repoRoot) { include("skills.json", "config.json", "default_instructions.md") }
    from(repoRoot.resolve("docs")) { include("AI_INSTRUCTIONS.md") }
    into(layout.buildDirectory.dir("generated/shared/wildthing"))
}
sourceSets.main { resources.srcDir(layout.buildDirectory.dir("generated/shared")) }
tasks.named("processResources") { dependsOn(sharedResources) }

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.1")
    testImplementation(kotlin("test"))
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.test {
    useJUnitPlatform()
    systemProperty("shared.dir", repoRoot.resolve("shared_tests").absolutePath)
    inputs.dir(repoRoot.resolve("shared_tests"))
    inputs.dir(repoRoot.resolve("docs"))
}
