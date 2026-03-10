import re
import logging

logger = logging.getLogger(__name__)

# Environments that should NEVER be sent to the LLM — their content is not translatable text.
_PASSTHROUGH_ENV_RE = re.compile(
    r'\\begin\{'
    r'(equation\*?|align\*?|alignat\*?|flalign\*?|gather\*?|multline\*?|'
    r'eqnarray\*?|displaymath|math|'
    r'lstlisting|verbatim|Verbatim|minted|'
    r'tikzpicture|pgfpicture|forest|circuitikz|'
    r'filecontents\*?)'
    r'\}'
)

# Display math \[ ... \]
_DISPLAY_MATH_RE = re.compile(r'^\s*\\\[.*\\\]\s*$', re.DOTALL)

# Commands whose arguments are never translatable prose.
# A line matching this pattern carries no human-readable text.
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
        Matches chunks that consist entirely of math or code environments,
        display-math blocks, or structural-only commands with no translatable text.
        """
        stripped = chunk.strip()
        if not stripped:
            return True
        if _PASSTHROUGH_ENV_RE.search(stripped):
            return True
        if _DISPLAY_MATH_RE.match(stripped):
            return True
        if _is_structural_only(stripped):
            return True
        return False

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
