import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Passthrough environments — chunks consisting entirely of these are skipped.
# ---------------------------------------------------------------------------

_PASSTHROUGH_ENVS = (
    r'equation\*?|align\*?|alignat\*?|flalign\*?|gather\*?|multline\*?|'
    r'eqnarray\*?|displaymath|math|'
    r'lstlisting|verbatim|Verbatim|minted|'
    r'tikzpicture|pgfpicture|forest|circuitikz|'
    r'filecontents\*?'
)

# Matches only if the *entire* chunk is one passthrough environment
# (with optional trailing whitespace). Uses a backreference (\1) to ensure
# \begin{env} and \end{env} refer to the same environment name.
_FULL_ENV_RE = re.compile(
    r'^\s*\\begin\{(' + _PASSTHROUGH_ENVS + r')\}'
    r'.*?'
    r'\\end\{\1\}\s*$',
    re.DOTALL,
)

# Display math \[ ... \]
_DISPLAY_MATH_RE = re.compile(r'^\s*\\\[.*\\\]\s*$', re.DOTALL)

# Commands whose arguments are never translatable prose.
_STRUCTURAL_LINE_RE = re.compile(
    r'^\s*\\(?:'
    r'newpage|clearpage|cleardoublepage|'
    r'pagenumbering|setcounter|addtocounter|stepcounter|refstepcounter|'
    r'pagestyle|thispagestyle|'
    r'vspace\*?|hspace\*?|vfill|hfill|bigskip|medskip|smallskip|'
    r'centering|raggedright|raggedleft|noindent|linebreak|pagebreak|'
    r'hypersetup|geometry|newgeometry|restoregeometry|'
    r'bibliographystyle|'
    r'label|ref|cite|autoref|eqref|pageref|cref|Cref|'
    r'input|include|includeonly|includegraphics'
    r')(?:\*)?(?:\[.*?\])?(?:\{[^{}]*\})*\s*$'
)

# ---------------------------------------------------------------------------
# Placeholder protection for inline elements
# ---------------------------------------------------------------------------

# Unicode brackets used as placeholder delimiters — never appear in LaTeX.
_PH_L, _PH_R = "\u27e6", "\u27e7"   # ⟦ ⟧

# Order matters: longer / more specific patterns first to avoid partial matches.
_PROTECT_PATTERNS = [
    # Display math  \[...\]
    re.compile(r'\\\[.*?\\\]', re.DOTALL),
    # Inline math  $...$  (not $$)
    re.compile(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', re.DOTALL),
    # Reference commands (incl. optional arguments)
    re.compile(r'\\(?:auto|page|eq|c|C)?ref\{[^}]*\}'),
    # Citations (with optional argument)
    re.compile(r'\\cite(?:\[[^\]]*\])?\{[^}]*\}'),
    # Labels
    re.compile(r'\\label\{[^}]*\}'),
    # File includes (with optional argument)
    re.compile(r'\\(?:input|include|includegraphics)(?:\[[^\]]*\])?\{[^}]*\}'),
    # URLs
    re.compile(r'\\url\{[^}]*\}'),
]


def _is_structural_only(chunk: str) -> bool:
    """Return True if every non-blank, non-comment line is a known structural command."""
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('%'):
            continue
        if not _STRUCTURAL_LINE_RE.match(stripped):
            return False
    return True


class LatexParser:
    def is_passthrough_chunk(self, chunk: str) -> bool:
        """
        Returns True if the chunk should NOT be sent to the LLM.
        Matches chunks that consist *entirely* of a single math/code environment,
        a display-math block, or structural-only commands with no translatable text.
        """
        stripped = chunk.strip()
        if not stripped:
            return True
        if _FULL_ENV_RE.match(stripped):
            return True
        if _DISPLAY_MATH_RE.match(stripped):
            return True
        if _is_structural_only(stripped):
            return True
        return False

    def protect(self, text: str) -> Tuple[str, dict]:
        """
        Replace inline math, references, labels, and file commands with
        numbered placeholders (⟦0⟧, ⟦1⟧, …) so the LLM cannot modify them.
        Returns the protected text and a store dict for restoration.
        """
        store = {}
        counter = 0

        def _replace(m):
            nonlocal counter
            key = f"{_PH_L}{counter}{_PH_R}"
            store[key] = m.group(0)
            counter += 1
            return key

        for pattern in _PROTECT_PATTERNS:
            text = pattern.sub(_replace, text)

        return text, store

    def restore(self, text: str, store: dict) -> str:
        """Restore placeholders back to original LaTeX fragments."""
        # Build index: number → original, for regex fallback
        index: dict[int, str] = {}
        for key, original in store.items():
            text = text.replace(key, original)
            # Extract the number from ⟦N⟧
            num_str = key.lstrip(_PH_L).rstrip(_PH_R)
            if num_str.isdigit():
                index[int(num_str)] = original

        # Fallback: LLM may replace Unicode ⟦N⟧ with [N] — only replace
        # if the number matches a known placeholder to avoid collisions
        if index:
            def _fallback(m):
                n = int(m.group(1))
                return index[n] if n in index else m.group(0)
            text = re.sub(r'\[(\d+)\]', _fallback, text)

        return text

    def parse_and_chunk(self, tex_content: str) -> dict:
        """
        Splits a LaTeX document into preamble, body chunks, and postamble.
        Chunks are split on blank lines so each paragraph/block is atomic.
        Whitespace separators are kept as their own list entries for lossless reconstruction.
        """
        match = re.search(r'(.*?\\begin\{document\})(.*?)(\\end\{document\}.*)', tex_content, re.DOTALL)

        if match:
            preamble = match.group(1)
            body = match.group(2)
            postamble = match.group(3)
            logger.info("Main document detected (preamble found).")
        else:
            preamble = ""
            body = tex_content
            postamble = ""
            logger.info("Sub-document detected (no preamble).")

        # Split on blank lines; keep the separators so reconstruction is lossless.
        chunks = re.split(r'(\n\s*\n)', body)

        return {
            "preamble": preamble,
            "chunks": chunks,
            "postamble": postamble,
        }

    def reassemble(self, preamble: str, chunks: list[str], postamble: str) -> str:
        """Reconstructs the document from translated chunks."""
        return preamble + "".join(chunks) + postamble
