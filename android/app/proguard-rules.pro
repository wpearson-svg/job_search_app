# kotlinx.serialization (export file)
-keepattributes *Annotation*, InnerClasses
-keepclassmembers class wildthing.core.** { *** Companion; }
-keepclasseswithmembers class wildthing.core.** { kotlinx.serialization.KSerializer serializer(...); }
