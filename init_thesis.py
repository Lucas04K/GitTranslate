#!/usr/bin/env python3
"""Generiert die empfohlene LaTeX-Thesis-Verzeichnisstruktur für GitTranslate.

Verwendung:
    python init_thesis.py                      # erstellt ./thesis-de/
    python init_thesis.py /pfad/zum/zielordner # erstellt dort
    python init_thesis.py --title "Mein Titel" --author "Max Mustermann"
"""

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

PREAMBLE = r"""\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[ngerman]{babel}
\usepackage{csquotes}
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{listings}
\usepackage{hyperref}
\usepackage{cleveref}
"""

MAIN_TEX = r"""\documentclass[12pt, a4paper]{scrreprt}
\input{preamble}

\begin{document}

\title{%(title)s}
\author{%(author)s}
\date{\today}
\maketitle

\tableofcontents
\listoffigures
\listoftables

\input{chapters/01_introduction}
\input{chapters/02_background}
\input{chapters/03_methodology}
\input{chapters/04_results}
\input{chapters/05_conclusion}

\appendix
\input{appendix/appendix_a}

\bibliographystyle{plain}
\bibliography{bibliography}

\end{document}
"""

CHAPTERS = {
    "01_introduction": (
        "Einleitung",
        "introduction",
        [("Motivation", "motivation"), ("Forschungsfrage", "research_question"), ("Struktur der Arbeit", "structure")],
    ),
    "02_background": (
        "Grundlagen",
        "background",
        [("Theoretischer Hintergrund", "theory"), ("Stand der Technik", "state_of_the_art")],
    ),
    "03_methodology": (
        "Methodik",
        "methodology",
        [("Forschungsdesign", "research_design"), ("Datenerhebung", "data_collection")],
    ),
    "04_results": (
        "Ergebnisse",
        "results",
        [("Quantitative Ergebnisse", "quantitative"), ("Qualitative Ergebnisse", "qualitative")],
    ),
    "05_conclusion": (
        "Fazit",
        "conclusion",
        [("Zusammenfassung", "summary"), ("Ausblick", "outlook")],
    ),
}

APPENDIX_A = r"""\chapter{Anhang A}
\label{chap:appendix_a}

% Zusätzliche Materialien hier einfügen.
"""

BIBLIOGRAPHY = r"""@misc{example2026,
  author = {Mustermann, Max},
  title  = {Beispielquelle},
  year   = {2026},
  note   = {Platzhalter -- durch echte Quellen ersetzen}
}
"""

GITTRANSLATE_IGNORE = """# Dateien, die nicht übersetzt werden sollen
preamble.tex
"""


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _build_chapter(filename: str) -> str:
    chapter_title, label, sections = CHAPTERS[filename]
    lines = [
        f"\\chapter{{{chapter_title}}}",
        f"\\label{{chap:{label}}}",
        "",
        f"% TODO: Inhalt für «{chapter_title}» verfassen.",
        "",
    ]
    for sec_title, sec_label in sections:
        lines += [
            f"\\section{{{sec_title}}}",
            f"\\label{{sec:{sec_label}}}",
            "",
            f"% TODO: Inhalt für «{sec_title}» verfassen.",
            "",
        ]
    return "\n".join(lines)


def create_thesis(target: Path, title: str, author: str) -> None:
    if target.exists() and any(target.iterdir()):
        print(f"Fehler: {target} existiert bereits und ist nicht leer.", file=sys.stderr)
        sys.exit(1)

    dirs = [target / d for d in ("chapters", "figures", "appendix")]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    (target / "main.tex").write_text(
        MAIN_TEX % {"title": title, "author": author}, encoding="utf-8"
    )
    (target / "preamble.tex").write_text(PREAMBLE, encoding="utf-8")
    (target / "bibliography.bib").write_text(BIBLIOGRAPHY, encoding="utf-8")
    (target / ".gittranslate-ignore").write_text(GITTRANSLATE_IGNORE, encoding="utf-8")

    for filename in CHAPTERS:
        (target / "chapters" / f"{filename}.tex").write_text(
            _build_chapter(filename), encoding="utf-8"
        )

    (target / "appendix" / "appendix_a.tex").write_text(APPENDIX_A, encoding="utf-8")
    (target / "figures" / ".gitkeep").write_text("", encoding="utf-8")

    print(f"Thesis-Struktur erstellt in: {target.resolve()}")
    print()
    print("Nächste Schritte:")
    print(f"  cd {target}")
    print("  git init && git add -A && git commit -m 'init thesis'")
    print("  # Repository bei GitHub/GitLab erstellen und pushen")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generiert die empfohlene LaTeX-Thesis-Struktur für GitTranslate."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="thesis-de",
        help="Zielverzeichnis (Standard: thesis-de)",
    )
    parser.add_argument("--title", default="Titel der Arbeit", help="Titel der Thesis")
    parser.add_argument("--author", default="Vorname Nachname", help="Name des Autors")

    args = parser.parse_args()
    create_thesis(Path(args.target), args.title, args.author)


if __name__ == "__main__":
    main()
