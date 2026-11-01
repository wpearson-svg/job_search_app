package io.github.wpearsonsvg.wildthing.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/** The desktop's forest-and-gold tokens (static/style.css). Gold is for fills, and for text only on dark. No purple. */
object Palette {
    val forest = Color(0xFF12291F)
    val forest2 = Color(0xFF1B3A2D)
    val gold = Color(0xFFB8860B)
    val gold2 = Color(0xFFD4A017)
    val goldLight = Color(0xFFE8C766)
    val cream = Color(0xFFF6F1E3)
    val link = Color(0xFF1F5C42)
    val sideText = Color(0xFFE9E2CC)
}

private val Light = lightColorScheme(
    primary = Palette.link, onPrimary = Color.White,
    primaryContainer = Color(0xFFDCEBE2), onPrimaryContainer = Palette.forest,
    secondary = Palette.gold, onSecondary = Palette.forest,
    secondaryContainer = Color(0xFFEFE3B8), onSecondaryContainer = Color(0xFF4A3600),
    tertiary = Color(0xFF3B6E57), onTertiary = Color.White,
    tertiaryContainer = Color(0xFFE8EFEA), onTertiaryContainer = Palette.forest,
    background = Palette.cream, onBackground = Color(0xFF1A1A1A),
    surface = Palette.cream, onSurface = Color(0xFF1A1A1A),
    surfaceVariant = Color(0xFFEDE6D2), onSurfaceVariant = Color(0xFF5B665D),
    surfaceContainerLowest = Color.White, surfaceContainerLow = Color(0xFFFFFCF4),
    surfaceContainer = Color(0xFFFBF7EC), surfaceContainerHigh = Color(0xFFF1EBDA), surfaceContainerHighest = Color(0xFFEAE3CF),
    surfaceTint = Palette.link, inverseSurface = Palette.forest, inverseOnSurface = Palette.sideText, inversePrimary = Palette.goldLight,
    outline = Color(0xFFB9AE8E), outlineVariant = Color(0xFFE1D9C0),
    error = Color(0xFFB3261E), onError = Color.White, errorContainer = Color(0xFFF9DEDC), onErrorContainer = Color(0xFF410E0B),
    scrim = Color.Black,
)

private val Dark = darkColorScheme(
    primary = Palette.goldLight, onPrimary = Palette.forest,
    primaryContainer = Color(0xFF1F4A37), onPrimaryContainer = Color(0xFF9FD6B6),
    secondary = Palette.gold2, onSecondary = Palette.forest,
    secondaryContainer = Color(0xFF3A4A1F), onSecondaryContainer = Palette.goldLight,
    tertiary = Color(0xFF9FD6B6), onTertiary = Palette.forest,
    tertiaryContainer = Color(0xFF1C4232), onTertiaryContainer = Color(0xFFCDE9D8),
    background = Color(0xFF0F1F18), onBackground = Color(0xFFEDE7D3),
    surface = Color(0xFF0F1F18), onSurface = Color(0xFFEDE7D3),
    surfaceVariant = Color(0xFF2C4D3D), onSurfaceVariant = Color(0xFFA9BDB1),
    surfaceContainerLowest = Color(0xFF0A1812), surfaceContainerLow = Color(0xFF12261D),
    surfaceContainer = Color(0xFF16352A), surfaceContainerHigh = Color(0xFF1B3D30), surfaceContainerHighest = Color(0xFF224636),
    surfaceTint = Palette.goldLight, inverseSurface = Color(0xFFEDE7D3), inverseOnSurface = Palette.forest, inversePrimary = Palette.link,
    outline = Color(0xFF4C6B5B), outlineVariant = Color(0xFF2C4D3D),
    error = Color(0xFFFF8F86), onError = Color(0xFF410E0B), errorContainer = Color(0xFF5C1A15), onErrorContainer = Color(0xFFFFDAD6),
    scrim = Color.Black,
)

@Immutable
data class Extra(
    val scoreHi: Pair<Color, Color>, val scoreMid: Pair<Color, Color>, val scoreLo: Pair<Color, Color>,
    val bar: Color, val onBar: Color, val barAccent: Color, val warn: Color, val good: Color,
)

private val LightExtra = Extra(Palette.forest2 to Palette.gold2, Color(0xFFEFE3B8) to Color(0xFF6B4E00),
    Color(0xFFECEAE2) to Color(0xFF666666), Palette.forest, Palette.sideText, Palette.gold2, Color(0xFF8A5A00), Palette.link)
private val DarkExtra = Extra(Palette.gold to Palette.forest, Color(0xFF3A4A1F) to Palette.goldLight,
    Color(0xFF2A4A3A) to Color(0xFFB9C9BF), Color(0xFF0A1812), Palette.sideText, Palette.gold2, Palette.goldLight, Color(0xFF9FD6B6))

val LocalExtra = staticCompositionLocalOf { LightExtra }

/** Status chip colors: distinct from each other and from the green theme, the same on light and dark. */
fun statusColors(status: String, scheme: ColorScheme, extra: Extra): Pair<Color, Color> = when (status) {
    "applied" -> Color(0xFF2E7D5B) to Color.White
    "phone_screen" -> Color(0xFF3B7EA1) to Color.White
    "interview" -> Color(0xFFC77D14) to Color.White
    "offer" -> Color(0xFF1E8E3E) to Color.White
    "rejected", "no_response", "withdrawn" -> Color(0xFF7A6F6A) to Color.White
    "saved" -> Color.Transparent to scheme.onSurface
    else -> extra.scoreLo
}

@Composable
fun WildThingTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    androidx.compose.runtime.CompositionLocalProvider(LocalExtra provides if (dark) DarkExtra else LightExtra) {
        MaterialTheme(colorScheme = if (dark) Dark else Light, content = content)
    }
}
