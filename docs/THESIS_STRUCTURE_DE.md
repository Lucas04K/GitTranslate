# Bachelor-/Masterarbeit — LaTeX-Strukturleitfaden für GitTranslate

## Empfohlene Dateistruktur

```
thesis-de/                        ← Quell-Repo (Deutsch)
├── main.tex                      ← Wurzeldokument, nur \input{}-Aufrufe
├── preamble.tex                  ← \usepackage{}, eigene Befehle usw.
├── chapters/
│   ├── 01_introduction.tex
│   ├── 02_background.tex
│   ├── 03_methodology.tex
│   ├── 04_results.tex
│   └── 05_conclusion.tex
├── figures/
│   ├── architecture.pdf
│   └── results_plot.png
├── appendix/
│   └── appendix_a.tex
└── bibliography.bib
```

```
thesis-en/                        ← Ziel-Repo (Englisch, automatisch generiert)
└── (spiegelt thesis-de exakt wider)
```

---

## main.tex-Vorlage

```latex
\documentclass[12pt, a4paper]{scrreprt}
\input{preamble}

\begin{document}

\title{Automatische Übersetzung von LaTeX-Dokumenten}
\author{Max Mustermann}
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
```

**GitTranslate-Verhalten bei `main.tex`:**
- `\title{...}`, `\author{...}` → Text in geschweiften Klammern wird übersetzt
- `\input{chapters/01_introduction}` → Pfad wird nie verändert
- `\maketitle`, `\tableofcontents` → unverändert durchgereicht

---

## Kapitel-Vorlage

```latex
\chapter{Einleitung}
\label{chap:introduction}

Dies ist ein einführender Absatz, der das Thema vorstellt.
Die Forschungsfrage wird in Abschnitt~\ref{sec:research_question} definiert.

\section{Motivation}
\label{sec:motivation}

Die Motivation für diese Arbeit ergibt sich aus...

\section{Forschungsfrage}
\label{sec:research_question}

Die zentrale Frage dieser Arbeit lautet:
\begin{quote}
    Wie kann maschinelle Übersetzung für akademische LaTeX-Dokumente verbessert werden?
\end{quote}

\section{Struktur der Arbeit}

\begin{itemize}
    \item Kapitel~\ref{chap:background} gibt einen Überblick über den Stand der Technik.
    \item Kapitel~\ref{chap:methodology} beschreibt die verwendete Methodik.
\end{itemize}
```

**Was GitTranslate hier übersetzt:**
- `\chapter{Einleitung}` → `\chapter{Introduction}` ✓
- `\section{Motivation}` → `\section{Motivation}` ✓ (im Englischen gleich)
- `\label{chap:introduction}` → **unverändert** (Labels müssen in beiden Repos identisch bleiben)
- `\ref{sec:research_question}` → **unverändert** (Referenzen müssen zu Labels passen)
- Absatztext → übersetzt ✓

---

## Gleichungen und Mathematik

Gleichungen werden von GitTranslate **automatisch übersprungen** — sie werden nie an das LLM gesendet.

```latex
% Dieser gesamte Block wird unverändert durchgereicht:
\begin{equation}
    D = \sum_{i=1}^{n} (T_i \cdot t_{\text{infer}}) + t_{\text{overhead}}
    \label{eq:latency}
\end{equation}

% Inline-Mathematik innerhalb von Text WIRD verarbeitet (der umgebende Text wird übersetzt):
Die Gesamtlatenz beträgt $D$ Sekunden, wobei $n$ die Anzahl der Token ist.
```

Unterstützte Mathe-Umgebungen (alle übersprungen): `equation`, `align`, `gather`, `multline`,
`alignat`, `flalign`, `eqnarray`, `displaymath` sowie deren Stern-Varianten.
Abgesetzte Mathematik `\[...\]` wird ebenfalls übersprungen.

---

## Code-Listings

Code-Blöcke werden **automatisch übersprungen** — sie werden nie an das LLM gesendet.

```latex
\begin{lstlisting}[language=Python, caption={Übersetzungsfunktion}]
def translate(text: str) -> str:
    return llm.call(text)
\end{lstlisting}
```

Der `caption={}`-Text oben **wird** übersetzt, da er zum umgebenden Text gehört
und sich nicht innerhalb der `lstlisting`-Umgebung selbst befindet.

---

## Abbildungen und Tabellen

```latex
\begin{figure}[htbp]
    \centering
    \includegraphics{figures/architecture}
    \caption{Architektur des Systems}
    \label{fig:architecture}
\end{figure}
```

- `\caption{Architektur des Systems}` → `\caption{Architecture of the System}` ✓
- `\includegraphics{figures/architecture}` → **unverändert** (Dateipfad bleibt erhalten) ✓
- `\label{fig:architecture}` → **unverändert** ✓

---

## Wichtige Regeln für konsistente Querverweise

Da beide Repos unabhängig voneinander existieren, **müssen** `\label{}`-Bezeichner in
Quell- (Deutsch) und Ziel-Repo (Englisch) identisch sein. GitTranslate bewahrt sie automatisch.

Wird ein Label in der Quelle umbenannt, wird das Ziel beim nächsten Sync aktualisiert.

**Empfohlen:**
```latex
\label{sec:methodology}   % bleibt in beiden Repos gleich
\ref{sec:methodology}     % wird nie übersetzt
```

**Vermeiden:** Labels mit deutschen Wörtern, die später geändert werden sollen (sie werden unverändert übernommen).

---

## preamble.tex

`preamble.tex` sollte keinen deutschen Text enthalten — sie enthält typischerweise nur
Befehle und Paketeinstellungen, die nicht übersetzt werden. Werden dennoch deutsche
Kommentare eingefügt, werden auch diese übersetzt (Kommentare mit `%` werden als
normale Textblöcke behandelt).

Um die Übersetzung von Kommentaren zu verhindern, technische Kommentare direkt in
dieselbe Zeile wie den Code schreiben:

```latex
\usepackage[utf8]{inputenc}   % encoding — not translated (no blank line above/below)
```

---

## Arbeitsablauf beim Schreiben der Arbeit

1. **Jedes Kapitel in einer eigenen Datei** unter `chapters/` verfassen.
2. **Einzelne Kapitel-Dateien pushen** — GitTranslate übersetzt nur geänderte Dateien neu;
   ein Push von `chapters/03_methodology.tex` löst ausschließlich die Übersetzung dieser Datei aus.
3. **`bibliography.bib` pushen** — `.bib`-Dateien werden unverändert ins Ziel-Repo kopiert
   (nur `.tex`-Dateien werden übersetzt).
4. **Abbildungen** — `.pdf`, `.png`, `.jpg` usw. werden unverändert kopiert.
5. **Das übersetzte Kapitel** in `thesis-en/` vor der Abgabe prüfen.
