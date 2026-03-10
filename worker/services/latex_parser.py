import re
import logging

logger = logging.getLogger(__name__)


class LatexParser:
    def parse_and_chunk(self, tex_content: str) -> dict:
        """
        Zerlegt ein LaTeX-Dokument in Preamble, übersetzbare Chunks (Absätze) und Postamble.
        """
        # Suche nach \begin{document} und \end{document}
        # re.DOTALL sorgt dafür, dass der Punkt (.) auch Zeilenumbrüche matcht
        match = re.search(r'(.*?\\begin\{document\})(.*?)(\\end\{document\}.*)', tex_content, re.DOTALL)

        if match:
            preamble = match.group(1)
            body = match.group(2)
            postamble = match.group(3)
            logger.info("Hauptdokument erkannt (Preamble gefunden).")
        else:
            # Falls es eine eingebundene Datei ist (z.B. chapter.tex ohne Präambel)
            preamble = ""
            body = tex_content
            postamble = ""
            logger.info("Sub-Dokument erkannt (Keine Preamble gefunden).")

        # Zerteile den Body in Absätze (doppelte Zeilenumbrüche).
        # WICHTIG: Die Klammern in r'(\n\s*\n)' sorgen dafür, dass die Trennzeichen
        # (die Zeilenumbrüche selbst) als eigene Listenelemente erhalten bleiben!
        # So können wir das Dokument später 1:1 mit originalem Spacing wieder zusammenbauen.
        chunks = re.split(r'(\n\s*\n)', body)

        return {
            "preamble": preamble,
            "chunks": chunks,
            "postamble": postamble
        }

    def reassemble(self, preamble: str, chunks: list[str], postamble: str) -> str:
        """
        Baut das Dokument aus den übersetzten Chunks wieder zusammen.
        """
        # Die chunks-Liste enthält abwechselnd Text und Whitespace/Zeilenumbrüche.
        # Wir fügen sie einfach wieder zu einem großen String zusammen.
        body_reconstructed = "".join(chunks)

        return preamble + body_reconstructed + postamble