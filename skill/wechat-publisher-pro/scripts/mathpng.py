"""
LaTeX -> inline PNG data-URI rendering for WeChat.

WeChat's editor cannot render MathML, KaTeX, or inline SVG -- SVG is stripped on
save and JavaScript is removed outright.  A base64 PNG in an ``<img src="...">``
is the only formula representation that survives the paste-save-publish cycle,
because WeChat re-uploads the image to its own CDN on paste.

matplotlib's ``mathtext`` engine does the typesetting.  It implements a solid
subset of LaTeX (fractions, roots, sums, integrals, greek, sub/superscripts,
matrices) without needing a TeX installation, which matters because most users
will not have one.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re

# A colour that matches body text in every shipped theme; formulae look wrong
# when they are pure black next to #333 body copy.
DEFAULT_COLOR = "#24292f"

# Greedy-but-bounded whitespace trim inside math (TeX ignores spacing anyway).
_WS = re.compile(r"\s+")

# The handful of macros mathtext does not implement but authors reach for most.
# Rewriting them beats failing the whole formula.
_COMPAT = [
    (r"\\displaystyle", ""),
    (r"\\text\s*\{([^{}]*)\}", r"\\mathrm{\1}"),
    (r"\\mbox\s*\{([^{}]*)\}", r"\\mathrm{\1}"),
    (r"\\operatorname\s*\{([^{}]*)\}", r"\\mathrm{\1}"),
    (r"\\dfrac", r"\\frac"),
    (r"\\tfrac", r"\\frac"),
    (r"\\leqslant", r"\\leq"),
    (r"\\geqslant", r"\\geq"),
    (r"\\varnothing", r"\\emptyset"),
    (r"\\therefore", r"\\Rightarrow"),
    (r"\\because", r"\\Leftarrow"),
    (r"\\land", r"\\wedge"),
    (r"\\lor", r"\\vee"),
    (r"\\ne", r"\\neq"),
    (r"\\;|\\,|\\!|\\quad|\\qquad", r"\\ "),
]

# Best-effort LaTeX -> Unicode for `--math unicode` (no matplotlib available).
_UNICODE_MAP = {
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\varepsilon": "ε", r"\zeta": "ζ", r"\eta": "η",
    r"\theta": "θ", r"\iota": "ι", r"\kappa": "κ", r"\lambda": "λ",
    r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ", r"\pi": "π", r"\rho": "ρ",
    r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ", r"\phi": "φ",
    r"\varphi": "φ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ", r"\Phi": "Φ",
    r"\Psi": "Ψ", r"\Omega": "Ω",
    r"\times": "×", r"\div": "÷", r"\pm": "±", r"\mp": "∓",
    r"\cdot": "·", r"\ast": "∗", r"\star": "⋆",
    r"\leq": "≤", r"\geq": "≥", r"\neq": "≠", r"\approx": "≈",
    r"\equiv": "≡", r"\sim": "∼", r"\propto": "∝",
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇",
    r"\sum": "∑", r"\prod": "∏", r"\int": "∫", r"\oint": "∮",
    r"\sqrt": "√", r"\in": "∈", r"\notin": "∉", r"\subset": "⊂",
    r"\subseteq": "⊆", r"\supset": "⊃", r"\supseteq": "⊇",
    r"\cup": "∪", r"\cap": "∩", r"\emptyset": "∅", r"\varnothing": "∅",
    r"\forall": "∀", r"\exists": "∃", r"\neg": "¬", r"\land": "∧",
    r"\lor": "∨", r"\rightarrow": "→", r"\leftarrow": "←",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\leftrightarrow": "↔",
    r"\to": "→", r"\mapsto": "↦", r"\ldots": "…", r"\cdots": "⋯",
    r"\quad": " ", r"\qquad": "  ",
}

_SUP = str.maketrans("0123456789+-=()nijklm",
                     "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱʲᵏˡᵐ")
_SUB = str.maketrans("0123456789+-=()ijklmn",
                     "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ᵢⱼₖₗₘₙ")


class MathRenderer:
    """Renders LaTeX to base64 PNGs, memoising on (latex, fontsize, color).

    A single article often repeats the same symbol a dozen times; the cache
    turns that into one matplotlib call plus cheap string reuse.
    """

    def __init__(self, fontsize: int = 18, dpi: int = 200, color: str = DEFAULT_COLOR):
        self.fontsize = fontsize
        self.dpi = dpi
        self.color = color
        self._cache: dict[str, str] = {}
        self._available: bool | None = None
        self._mathtext = None
        self.failures: list[str] = []

    # -- capability probe -------------------------------------------------
    @property
    def available(self) -> bool:
        if self._available is None:
            try:
                import matplotlib
                matplotlib.use("Agg", force=True)
                from matplotlib import mathtext
                self._mathtext = mathtext
                self._available = True
            except Exception:
                self._available = False
        return self._available

    # -- normalisation ----------------------------------------------------
    @staticmethod
    def prepare(latex: str) -> str:
        """Apply compatibility rewrites so common macros do not hard-fail."""
        out = latex.strip()
        for pattern, repl in _COMPAT:
            out = re.sub(pattern, repl, out)
        out = _WS.sub(" ", out).strip()
        # mathtext rejects bare `$`; escape any we missed.
        return out

    # -- renderers --------------------------------------------------------
    def _render_png(self, latex: str, display: bool) -> str | None:
        """Return a ``data:image/png;base64,...`` URI, or None on failure."""
        # mathtext has no text/display distinction to switch on, and it rejects
        # `\displaystyle` outright -- so display math is distinguished purely by
        # how the pipeline places the resulting image, not by the TeX source.
        body = self.prepare(latex)
        source = "$%s$" % body
        key = hashlib.sha1(
            ("%s|%s|%s" % (source, self.fontsize, self.color)).encode("utf-8")
        ).hexdigest()
        if key in self._cache:
            return self._cache[key]
        try:
            buf = io.BytesIO()
            self._mathtext.math_to_image(
                source,
                buf,
                prop=None,
                dpi=self.dpi,
                format="png",
                color=self.color,
            )
            png = buf.getvalue()
            if not png.startswith(b"\x89PNG"):
                raise ValueError("mathtext produced a non-PNG payload")
            uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            self._cache[key] = uri
            return uri
        except Exception as exc:  # mathtext raises bare ValueError/KeyError
            self.failures.append("%s (%s)" % (latex, exc))
            return None

    def render(self, latex: str, display: bool = False) -> dict:
        """Render to a descriptor dict used by the pipeline.

        ``{"uri": ..., "mode": "png"}`` on success; ``{"text": ..., "mode":
        "unicode"|"raw"}`` when the formula cannot be drawn.
        """
        if self.available:
            uri = self._render_png(latex, display)
            if uri:
                return {"uri": uri, "mode": "png", "display": display}
        text = to_unicode(latex)
        return {"text": text, "mode": "unicode" if text != latex else "raw",
                "display": display}

    def render_png_uri(self, latex: str, display: bool = False):
        """Compatibility shim returning just the URI or None."""
        if not self.available:
            return None
        return self._render_png(latex, display)


def to_unicode(latex: str) -> str:
    """Best-effort LaTeX -> Unicode, used when PNG rendering is unavailable.

    This is a fallback, not a substitute: it handles single symbols, simple
    sub/superscripts and fractions of the form ``\\frac{a}{b}`` -> ``a/b``.
    Anything it cannot translate is returned wrapped in backticks so the reader
    at least sees the source rather than a broken picture.
    """
    s = latex.strip()

    # \frac{a}{b} -> (a)/(b), recursively simplified
    for _ in range(3):
        new = re.sub(
            r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
            lambda m: _wrap_frac(to_unicode(m.group(1)), to_unicode(m.group(2))),
            s,
        )
        if new == s:
            break
        s = new

    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", lambda m: "√(" + to_unicode(m.group(1)) + ")", s)

    # Superscripts / subscripts on simple single-token bases
    s = re.sub(r"\^\{([^{}]{1,6})\}", lambda m: _map_script(m.group(1), _SUP), s)
    s = re.sub(r"\^([0-9n+\-])", lambda m: _map_script(m.group(1), _SUP), s)
    s = re.sub(r"_\{([^{}]{1,6})\}", lambda m: _map_script(m.group(1), _SUB), s)
    s = re.sub(r"_([0-9+\-])", lambda m: _map_script(m.group(1), _SUB), s)

    for macro in sorted(_UNICODE_MAP, key=len, reverse=True):
        s = s.replace(macro, _UNICODE_MAP[macro])

    # Drop leftover grouping braces and spacing macros
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\\left|\\right", "", s)
    s = re.sub(r"\\\\", " ", s)
    # Any surviving control sequence is untranslatable -- show it verbatim.
    s = re.sub(r"\\[A-Za-z]+", lambda m: "`" + m.group(0) + "`", s)
    return s.strip()


def _wrap_frac(num: str, den: str) -> str:
    """``a/b`` for simple parts, ``(a+b)/(c-d)`` when parentheses are needed."""
    if re.search(r"[+\-±∓×÷]| ", num):
        num = "(" + num + ")"
    if re.search(r"[+\-±∓×÷]| ", den):
        den = "(" + den + ")"
    return "%s/%s" % (num, den)


def _map_script(inner: str, table) -> str:
    mapped = inner.translate(table)
    # If any character had no Unicode equivalent, fall back to a caret form.
    if any(c not in "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎" for c in mapped):
        return "^" + ("(" + inner + ")" if len(inner) > 1 else inner)
    return mapped
