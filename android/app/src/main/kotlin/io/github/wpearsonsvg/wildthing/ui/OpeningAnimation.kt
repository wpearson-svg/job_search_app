package io.github.wpearsonsvg.wildthing.ui

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.SoundPool
import android.provider.Settings
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import io.github.wpearsonsvg.wildthing.R
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlin.math.ceil
import kotlin.math.max

/**
 * The opening animation, ported from wildthing_open_animation.html: the crown fades in on forest green, two jaws
 * hinged on the left edge bite shut over it (with the "Chomp!" sound), the screen shakes, and the jaws swing open to
 * show the real app underneath. Cold start only. With animations switched off in Android, a short crossfade instead.
 */
private object Intro {
    const val LOGO_IN = 520
    const val LOGO_HOLD = 650
    const val CLOSE = 340
    const val SHAKE = 150
    const val HOLD_CLOSED = 130
    const val OPEN = 720
    const val OPEN_ANGLE = 105f
    const val TEETH_PER_WIDTH = 7f
    const val TOOTH_RATIO = 1.25f
    const val OFFSCREEN_SHIFT = 1.6f
    const val SOUND_IMPACT = 420       // ms into the sound where the chomp lands
    val EASE_CLOSE = CubicBezierEasing(.55f, 0f, .95f, .5f)
    val EASE_OPEN = CubicBezierEasing(.16f, .8f, .24f, 1f)
    val EASE_LOGO = CubicBezierEasing(.2f, .8f, .2f, 1f)

    val forest = Color(0xFF12291F)
    val body = Color(0xFF0A1B13)
    val body2 = Color(0xFF0D2419)
    val gum = Color(0xFF5A2024)
    val mouth = Color(0xFF050D09)
    val tooth = Color(0xFFF3EBD2)
    val toothEdge = Color(0xFFC8BB92)
    val scratch = Color(0xFFE3B341)
}

/** True when Android's animations are switched off (Developer options or accessibility "Remove animations"). */
fun reducedMotion(context: Context) =
    Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f

/** The chomp, quietly, and only when the phone is not on silent or vibrate and the setting allows it. */
private class Chomp(context: Context, enabled: Boolean) {
    private val audio = context.getSystemService(AudioManager::class.java)
    private val pool: SoundPool? = if (enabled && audio.ringerMode == AudioManager.RINGER_MODE_NORMAL)
        SoundPool.Builder().setMaxStreams(1).setAudioAttributes(AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_GAME).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build()).build()
    else null
    private var loaded = false
    private val id = pool?.let { p ->
        p.setOnLoadCompleteListener { _, _, status -> loaded = status == 0 }
        p.load(context, R.raw.chomp, 1)
    } ?: 0

    fun play() { if (loaded) pool?.play(id, 0.6f, 0.6f, 1, 0, 1f) }    // never full volume; skipped if not ready
    fun release() = pool?.release()
}

/**
 * Draws [content] (the real app), with the opening animation over it when [play] is true. The app is composed from
 * the start, so it is ready when the jaws open, and it stays in the same place afterwards, so nothing restarts.
 */
@Composable
fun OpeningAnimation(play: Boolean, sound: Boolean, content: @Composable () -> Unit) {
    val context = LocalContext.current
    val reduce = remember { reducedMotion(context) }
    val chomp = remember { Chomp(context, play && sound && !reduce) }
    DisposableEffect(Unit) { onDispose { chomp.release() } }

    val logo = remember { Animatable(0f) }          // 0 hidden, 1 shown (also drives the scale .9 -> 1)
    val bite = remember { Animatable(0f) }          // 0 jaws open, 1 shut
    val shake = remember { Animatable(0f) }         // keyframe index along the shake path
    val appScale = remember { Animatable(if (play && !reduce) 1.04f else 1f) }
    val splashAlpha = remember { Animatable(1f) }
    var splash by remember { mutableStateOf(play) }
    var jaws by remember { mutableStateOf(play && !reduce) }

    LaunchedEffect(Unit) {
        if (!play) return@LaunchedEffect
        if (reduce) {
            logo.snapTo(1f)
            delay(600)
            splashAlpha.animateTo(0f, tween(300))
            splash = false
            return@LaunchedEffect
        }
        logo.animateTo(1f, tween(Intro.LOGO_IN, easing = Intro.EASE_LOGO))
        val lead = max(0, Intro.SOUND_IMPACT - Intro.CLOSE).toLong()
        delay(Intro.LOGO_HOLD - lead)
        chomp.play()
        delay(lead)
        bite.animateTo(1f, tween(Intro.CLOSE, easing = Intro.EASE_CLOSE))
        splash = false                                  // swapped while the screen is covered
        shake.animateTo(5f, tween(Intro.SHAKE, easing = CubicBezierEasing(0f, 0f, .58f, 1f)))
        delay(Intro.HOLD_CLOSED.toLong())
        val scaling = async { appScale.animateTo(1f, tween(Intro.OPEN + 120, easing = Intro.EASE_OPEN)) }
        bite.animateTo(0f, tween(Intro.OPEN, easing = Intro.EASE_OPEN))
        jaws = false
        scaling.await()
    }

    val shakePath = listOf(Offset(0f, 0f), Offset(-6f, 3f), Offset(5f, -3f), Offset(-3f, 2f), Offset(2f, -1f), Offset(0f, 0f))
    val density = LocalDensity.current
    Box(Modifier.fillMaxSize().background(Intro.forest).graphicsLayer {
        val s = shake.value.coerceIn(0f, 5f)
        val i = s.toInt().coerceAtMost(4)
        val f = s - i
        val a = shakePath[i]; val b = shakePath[i + 1]
        translationX = with(density) { (a.x + (b.x - a.x) * f).dp.toPx() }
        translationY = with(density) { (a.y + (b.y - a.y) * f).dp.toPx() }
    }) {
        Box(Modifier.fillMaxSize().graphicsLayer { scaleX = appScale.value; scaleY = appScale.value }) { content() }
        if (splash) {
            Box(Modifier.fillMaxSize().graphicsLayer { alpha = splashAlpha.value }.background(Intro.forest), contentAlignment = Alignment.Center) {
                Image(painterResource(R.drawable.wildthing_crown), contentDescription = "WildThing",
                    modifier = Modifier.size(150.dp)
                        .graphicsLayer { alpha = logo.value; val sc = .9f + .1f * logo.value; scaleX = sc; scaleY = sc }
                        .shadow(28.dp, RoundedCornerShape(34.dp), ambientColor = Intro.scratch, spotColor = Intro.scratch)
                        .clip(RoundedCornerShape(34.dp)))
            }
        }
        if (jaws) Jaws(bite.value)
    }
}

/** Both jaws, [closed] from 0 (open, off-screen) to 1 (shut, covering everything). */
@Composable
private fun Jaws(closed: Float) {
    Canvas(Modifier.fillMaxSize()) {
            val w = size.width; val h = size.height
            val p = w / Intro.TEETH_PER_WIDTH
            val t = p * Intro.TOOTH_RATIO
            val open = 1f - closed
            val angle = Intro.OPEN_ANGLE * open
            val shift = -t * Intro.OFFSCREEN_SHIFT * open
            val pivot = Offset(0f, h / 2f)
            withTransform({ translate(left = shift); rotate(-angle, pivot) }) { jaw(w, h, p, t, top = true) }
            withTransform({ translate(left = shift); rotate(angle, pivot) }) {
                scale(1f, -1f, pivot) { jaw(w, h, p, t, top = false) }          // the lower jaw is the upper one mirrored
            }
    }
}

/** One jaw, drawn as the upper one: from the top edge down to the tooth tips just past the middle. */
private fun DrawScope.jaw(w: Float, h: Float, p: Float, t: Float, top: Boolean) {
    val len = ceil(w * 1.15f)
    val half = h / 2f
    val base = half - t / 2f
    val tip = half + t / 2f
    val gum = max(14.dp.toPx(), t * .5f)
    drawRect(Intro.mouth, Offset.Zero, Size(len, tip))
    drawRect(Brush.verticalGradient(listOf(Intro.body, Intro.body2), 0f, base), Offset.Zero, Size(len, base))
    for (k in 0 until 3) {
        val sx = len * (.25f + .22f * k); val sy = base * (.30f + .12f * k)
        val path = Path().apply { moveTo(sx, sy); relativeQuadraticTo(p * .5f, -p * .1f, p * .9f, p * .35f) }
        drawPath(path, Intro.scratch.copy(alpha = .16f), style = Stroke(3.dp.toPx(), cap = StrokeCap.Round))
    }
    drawRect(Intro.gum, Offset(0f, base - gum), Size(len, gum))
    drawRect(Color.Black.copy(alpha = .25f), Offset(0f, base - gum), Size(len, 3.dp.toPx()))
    val phase = if (top) .5f else 0f                  // lower teeth sit between the upper ones
    val n = ceil(len / p).toInt() + 2
    val edge = Stroke(1.5.dp.toPx(), join = StrokeJoin.Round)
    for (i in -1 until n) {
        val x = p * (i + phase)
        val tooth = Path().apply {
            moveTo(x - p / 2f, base)
            quadraticTo(x - p * .10f, base + t * .62f, x, tip)
            quadraticTo(x + p * .10f, base + t * .62f, x + p / 2f, base)
            close()
        }
        drawPath(tooth, Intro.tooth)
        drawPath(tooth, Intro.toothEdge, style = edge)
    }
}
