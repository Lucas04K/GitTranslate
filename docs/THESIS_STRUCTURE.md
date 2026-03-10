# Bachelor/Master Thesis — LaTeX Structure Guide for GitTranslate

## Recommended File Structure

```
thesis-de/                        ← source repo (German)
├── main.tex                      ← root document, \input{} calls only
├── preamble.tex                  ← \usepackage{}, custom commands, etc.
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
thesis-en/                        ← target repo (English, auto-generated)
└── (mirrors thesis-de exactly)
```

---

## main.tex Template

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

**GitTranslate behaviour on `main.tex`:**
- `\title{...}`, `\author{...}` → text inside braces is translated
- `\input{chapters/01_introduction}` → path is never modified
- `\maketitle`, `\tableofcontents` → passed through unchanged

---

## Chapter File Template

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

**What GitTranslate translates here:**
- `\chapter{Einleitung}` → `\chapter{Introduction}` ✓
- `\section{Motivation}` → `\section{Motivation}` ✓ (same in English)
- `\label{chap:introduction}` → **unchanged** (labels must stay consistent across repos)
- `\ref{sec:research_question}` → **unchanged** (references must match labels)
- Paragraph text → translated ✓

---

## Equations and Math

Equations are **automatically skipped** by GitTranslate — they are never sent to the LLM.

```latex
% This entire block is passed through unchanged:
\begin{equation}
    D = \sum_{i=1}^{n} (T_i \cdot t_{\text{infer}}) + t_{\text{overhead}}
    \label{eq:latency}
\end{equation}

% Inline math inside text IS processed (the surrounding text is translated):
Die Gesamtlatenz beträgt $D$ Sekunden, wobei $n$ die Anzahl der Token ist.
```

Supported math environments (all skipped): `equation`, `align`, `gather`, `multline`,
`alignat`, `flalign`, `eqnarray`, `displaymath`, and their starred variants.
Display math `\[...\]` is also skipped.

---

## Code Listings

Code blocks are **automatically skipped** — never sent to the LLM.

```latex
\begin{lstlisting}[language=Python, caption={Übersetzungsfunktion}]
def translate(text: str) -> str:
    return llm.call(text)
\end{lstlisting}
```

The `caption={}` text above **is** translated because it's part of surrounding text,
not inside the `lstlisting` environment itself.

---

## Figures and Tables

```latex
\begin{figure}[htbp]
    \centering
    \includegraphics{figures/architecture}
    \caption{Architektur des Systems}
    \label{fig:architecture}
\end{figure}
```

- `\caption{Architektur des Systems}` → `\caption{Architecture of the System}` ✓
- `\includegraphics{figures/architecture}` → **unchanged** (file path preserved) ✓
- `\label{fig:architecture}` → **unchanged** ✓

---

## Important Rules for Consistent Cross-References

Because both repos exist independently, `\label{}` identifiers **must be the same** in
both the German source and the English target. GitTranslate preserves them automatically.

If you rename a label in the source, the target is updated on the next sync.

**Do:**
```latex
\label{sec:methodology}   % stays the same in both repos
\ref{sec:methodology}     % never translated
```

**Avoid:** Labels with German words that you later want to change (they propagate as-is).

---

## preamble.tex

Keep `preamble.tex` free of German text — it typically contains only commands and
package settings which are not translated. If you do add comments in German, they
will be translated too (comments starting with `%` are treated as regular text chunks).

To prevent comment translation, put purely technical comments on the same line as code:

```latex
\usepackage[utf8]{inputenc}   % encoding — not translated (no blank line above/below)
```

---

## Workflow When Writing the Thesis

1. **Write each chapter in its own file** under `chapters/`.
2. **Push individual chapter files** — GitTranslate only re-translates changed files,
   so pushing `chapters/03_methodology.tex` triggers translation of that file only.
3. **Push `bibliography.bib`** — `.bib` files are copied to the target repo unchanged
   (only `.tex` files are translated).
4. **Figures** — `.pdf`, `.png`, `.jpg` etc. are copied unchanged.
5. **Check the translated chapter** in `thesis-en/` before submitting.
