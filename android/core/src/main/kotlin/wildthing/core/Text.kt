package wildthing.core

/** Text helpers that behave like the Python standard library calls the desktop version uses. */
object Html {
    // Python's html.unescape knows every HTML5 entity; these are the ones job postings actually use.
    private val NAMED = mapOf(
        "amp" to "&", "lt" to "<", "gt" to ">", "quot" to "\"", "apos" to "'", "nbsp" to " ",
        "rsquo" to "’", "lsquo" to "‘", "rdquo" to "”", "ldquo" to "“", "sbquo" to "‚",
        "bdquo" to "„", "mdash" to "—", "ndash" to "–", "hellip" to "…", "bull" to "•",
        "middot" to "·", "copy" to "©", "reg" to "®", "trade" to "™", "deg" to "°",
        "plusmn" to "±", "times" to "×", "divide" to "÷", "frac12" to "½", "frac14" to "¼",
        "frac34" to "¾", "cent" to "¢", "pound" to "£", "euro" to "€", "yen" to "¥",
        "sect" to "§", "para" to "¶", "laquo" to "«", "raquo" to "»", "iexcl" to "¡",
        "iquest" to "¿", "shy" to "­", "ensp" to " ", "emsp" to " ", "thinsp" to " ",
        "zwj" to "‍", "zwnj" to "‌", "lrm" to "‎", "rlm" to "‏", "dagger" to "†",
        "rarr" to "→", "larr" to "←", "check" to "✓", "starf" to "★", "hyphen" to "‐",
        "agrave" to "à", "aacute" to "á", "acirc" to "â", "atilde" to "ã", "auml" to "ä", "aring" to "å",
        "aelig" to "æ", "ccedil" to "ç", "egrave" to "è", "eacute" to "é", "ecirc" to "ê", "euml" to "ë",
        "igrave" to "ì", "iacute" to "í", "icirc" to "î", "iuml" to "ï", "ntilde" to "ñ", "ograve" to "ò",
        "oacute" to "ó", "ocirc" to "ô", "otilde" to "õ", "ouml" to "ö", "oslash" to "ø", "ugrave" to "ù",
        "uacute" to "ú", "ucirc" to "û", "uuml" to "ü", "yacute" to "ý", "szlig" to "ß",
        "Agrave" to "À", "Aacute" to "Á", "Eacute" to "É", "Ntilde" to "Ñ", "Ouml" to "Ö", "Uuml" to "Ü",
    )
    // Entities HTML allows without the closing semicolon.
    private val LEGACY = setOf("amp", "lt", "gt", "quot", "nbsp", "copy", "reg")
    // Python maps these numeric references (Windows-1252 range) to the characters browsers show.
    private val CP1252 = mapOf(
        0x80 to 0x20ac, 0x82 to 0x201a, 0x83 to 0x0192, 0x84 to 0x201e, 0x85 to 0x2026, 0x86 to 0x2020,
        0x87 to 0x2021, 0x88 to 0x02c6, 0x89 to 0x2030, 0x8a to 0x0160, 0x8b to 0x2039, 0x8c to 0x0152,
        0x8e to 0x017d, 0x91 to 0x2018, 0x92 to 0x2019, 0x93 to 0x201c, 0x94 to 0x201d, 0x95 to 0x2022,
        0x96 to 0x2013, 0x97 to 0x2014, 0x98 to 0x02dc, 0x99 to 0x2122, 0x9a to 0x0161, 0x9b to 0x203a,
        0x9c to 0x0153, 0x9e to 0x017e, 0x9f to 0x0178,
    )
    // Control characters and noncharacters Python drops from numeric references.
    private fun invalidCodepoint(c: Int) = c in 0x1..0x8 || c == 0xb || c in 0xe..0x1f || c in 0x7f..0x9f ||
        c in 0xfdd0..0xfdef || (c and 0xfffe) == 0xfffe

    private val REF = Regex("&(#[0-9]+;?|#[xX][0-9a-fA-F]+;?|[A-Za-z][A-Za-z0-9]*;?)")

    fun unescape(s: String): String {
        if ('&' !in s) return s
        return REF.replace(s) { m ->
            val body = m.groupValues[1]
            if (body.startsWith("#")) {
                val digits = body.trimEnd(';')
                val n = runCatching {
                    if (digits[1] == 'x' || digits[1] == 'X') digits.substring(2).toLong(16) else digits.substring(1).toLong()
                }.getOrNull() ?: return@replace m.value
                when {
                    n == 0L || n > 0x10FFFF || n in 0xD800L..0xDFFFL -> "�"
                    n.toInt() in CP1252 -> String(Character.toChars(CP1252.getValue(n.toInt())))
                    n == 0x0dL -> "\r"
                    invalidCodepoint(n.toInt()) -> ""
                    else -> String(Character.toChars(n.toInt()))
                }
            } else {
                val name = body.trimEnd(';')
                when {
                    body.endsWith(";") && name in NAMED -> NAMED.getValue(name)
                    !body.endsWith(";") && name in LEGACY -> NAMED.getValue(name)
                    else -> m.value
                }
            }
        }
    }

    private val BREAKS = pyI("<br\\s*/?>|</p>|</li>|</h\\d>")
    private val TAG = py("<[^>]+>")
    private val SPACES = py("[ \\t]+")
    private val BLANK_LINES = py("\\n\\s*\\n+")

    /** sources.strip_html: HTML from a job feed to plain text with line breaks. */
    fun strip(html: String?): String {
        var t = unescape(html ?: "")
        t = BREAKS.matcher(t).replaceAll("\n")
        t = TAG.matcher(t).replaceAll(" ")
        t = unescape(t)
        t = SPACES.matcher(t).replaceAll(" ")
        return BLANK_LINES.matcher(t).replaceAll("\n").pyStrip()
    }
}

/** Python's str.strip(): removes Unicode whitespace from both ends. */
fun String.pyStrip(): String = trim { Character.isWhitespace(it) || Character.isSpaceChar(it) }

/** Python's " ".join(s.split()): collapses every run of whitespace to one space. */
fun String.squeeze(): String = WHITESPACE.split(this).filter { it.isNotEmpty() }.joinToString(" ")

private val WHITESPACE = py("\\s+")

/** db.norm, db.dup_key and db.same_place: how the same job listed twice is recognised. */
object Dedupe {
    private val NON_ALNUM = Regex("[^a-z0-9 ]")
    private val SUFFIX = py("\\b(inc|llc|ltd|corp|corporation|co|company)\\b")

    fun norm(text: String?): String {
        val t = SUFFIX.matcher(NON_ALNUM.replace((text ?: "").lowercase(), " ")).replaceAll(" ")
        return t.squeeze()
    }

    /** Same title at the same company counts as the same posting. A posting with no company never matches. */
    fun dupKey(title: String?, company: String?): String =
        if (norm(company).isEmpty()) "" else norm(title) + "|" + norm(company)

    /** Locations agree when either is blank or their first part (the city) matches. */
    fun samePlace(a: String?, b: String?): Boolean {
        val ca = norm((a ?: "").split(",")[0])
        val cb = norm((b ?: "").split(",")[0])
        return ca.isEmpty() || cb.isEmpty() || ca == cb || ca in cb || cb in ca
    }
}

/** resume.read_resume for Word files: the text of each paragraph, one per line. */
object Docx {
    private val PARA = py("<w:p[ >].*?</w:p>", java.util.regex.Pattern.DOTALL)
    private val RUN = py("<w:t[^>]*>(.*?)</w:t>", java.util.regex.Pattern.DOTALL)

    fun documentXml(bytes: ByteArray): String? {
        java.util.zip.ZipInputStream(bytes.inputStream()).use { z ->
            while (true) {
                val e = z.nextEntry ?: return null
                if (e.name == "word/document.xml") return z.readBytes().toString(Charsets.UTF_8)
            }
        }
    }

    fun text(bytes: ByteArray): String {
        val xml = documentXml(bytes) ?: error("That does not look like a Word document.")
        val lines = mutableListOf<String>()
        val p = PARA.matcher(xml)
        while (p.find()) {
            val r = RUN.matcher(p.group())
            val sb = StringBuilder()
            while (r.find()) sb.append(r.group(1))
            val line = Html.unescape(sb.toString()).pyStrip()
            if (line.isNotEmpty()) lines += line
        }
        return lines.joinToString("\n")
    }
}
