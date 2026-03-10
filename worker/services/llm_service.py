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
            f"You are a professional {self.source_lang} to {self.target_lang} translator. "
            f"Your goal is to accurately convey the meaning and nuances of the original {self.source_lang} text "
            f"while adhering to {self.target_lang} grammar, vocabulary, and cultural sensitivities.\n\n"
            "CRITICAL LATEX RULES:\n"
            "- NEVER modify, translate, or remove any LaTeX commands (e.g., \\section{}, \\maketitle, \\textbf{}).\n"
            "- DO NOT use Markdown formatting (like ** or ##). Keep all LaTeX tags exactly as they are.\n"
            "- If the text is purely a LaTeX command (like \\maketitle), return it exactly as it is.\n\n"
            f"Produce only the {self.target_lang} translation, without any additional explanations or commentary. "
            f"Please translate the following {self.source_lang} text into {self.target_lang}:\n\n\n"
            f"{text}"
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
