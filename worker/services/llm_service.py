import requests
import logging
from core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        self.api_url = settings.llm_api_url
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout
        self.source_lang = settings.source_lang
        self.target_lang = settings.target_lang

    def _build_prompt(self, text: str) -> str:
        return (
            f"You are a professional {self.source_lang} to {self.target_lang} translator "
            f"specializing in academic LaTeX documents.\n\n"

            f"TRANSLATE:\n"
            f"- All regular paragraph text.\n"
            f"- Text arguments of heading and display commands:\n"
            f"  \\chapter{{...}}, \\section{{...}}, \\subsection{{...}}, \\subsubsection{{...}},\n"
            f"  \\paragraph{{...}}, \\caption{{...}}, \\title{{...}}, \\footnote{{...}},\n"
            f"  \\emph{{...}}, \\textbf{{...}}, \\textit{{...}}, \\text{{...}}\n\n"

            f"NEVER MODIFY:\n"
            f"- LaTeX command names themselves (\\chapter stays \\chapter, etc.).\n"
            f"- Math content: $...$, \\(...\\), \\[...\\], \\begin{{equation}} ... \\end{{equation}},\n"
            f"  and all other math environments (align, gather, multline, etc.).\n"
            f"- References and labels: \\ref{{...}}, \\cite{{...}}, \\label{{...}}, "
            f"\\autoref{{...}}, \\eqref{{...}}, \\pageref{{...}}.\n"
            f"- File inclusions: \\input{{...}}, \\include{{...}}, \\includegraphics{{...}}.\n"
            f"- Code blocks: \\begin{{lstlisting}}, \\begin{{verbatim}}.\n"
            f"- URLs: \\url{{...}}, the URL part of \\href{{URL}}{{text}} (translate only the text part).\n"
            f"- Do NOT add Markdown formatting (**, ##, etc.).\n\n"

            f"If the chunk contains ONLY structural commands with no translatable text "
            f"(e.g. \\maketitle, \\tableofcontents), return it exactly as-is.\n\n"

            f"Examples:\n"
            f"  IN:  \\chapter{{Einleitung}}\n"
            f"  OUT: \\chapter{{Introduction}}\n\n"
            f"  IN:  \\section{{Grundlagen der maschinellen Übersetzung}}\n"
            f"  OUT: \\section{{Fundamentals of Machine Translation}}\n\n"
            f"  IN:  Die Methode wird in Abschnitt~\\ref{{sec:method}} beschrieben.\n"
            f"  OUT: The method is described in Section~\\ref{{sec:method}}.\n\n"

            f"Produce ONLY the {self.target_lang} translation — no explanations, no commentary.\n\n"
            f"Text to translate:\n\n{text}"
        )

    def _call_ollama(self, prompt: str) -> str:
        url = f"{self.api_url}/api/generate"
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("response", "").strip()

    def translate_latex(self, text: str) -> str:
        if not text.strip():
            return text

        prompt = self._build_prompt(text)

        try:
            logger.info(f"Sending chunk to Ollama (model: {self.model})...")
            return self._call_ollama(prompt)

        except requests.exceptions.Timeout:
            logger.error(f"LLM timeout after {self.timeout}s.")
            raise RuntimeError(f"LLM Timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection to LLM failed at {self.api_url}.")
            raise RuntimeError("LLM Connection Error")
        except requests.exceptions.RequestException as e:
            logger.error(f"Unexpected LLM API error: {e}")
            raise RuntimeError(f"LLM API Error: {e}")
