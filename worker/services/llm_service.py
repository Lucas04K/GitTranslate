import requests
import logging
from core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        self.host = settings.ollama_host
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout
        self.api_url = f"{self.host}/api/generate"

    def translate_latex(self, text: str) -> str:
        """
        Sendet den Text an Ollama und nutzt das offizielle TranslateGemma Prompt-Format,
        kombiniert mit strikten LaTeX-Regeln.
        """
        if not text.strip():
            return text

        # Wir bauen den exakten Prompt nach der offiziellen Dokumentation auf
        # und betten unsere LaTeX-Regeln nahtlos ein.
        full_prompt = (
            "You are a professional German (de) to English (en) translator. "
            "Your goal is to accurately convey the meaning and nuances of the original German text "
            "while adhering to English grammar, vocabulary, and cultural sensitivities.\n\n"
            "CRITICAL LATEX RULES:\n"
            "- NEVER modify, translate, or remove any LaTeX commands (e.g., \\section{}, \\maketitle, \\textbf{}).\n"
            "- DO NOT use Markdown formatting (like ** or ##). Keep all LaTeX tags exactly as they are.\n"
            "- If the text is purely a LaTeX command (like \\maketitle), return it exactly as it is.\n\n"
            "Produce only the English translation, without any additional explanations or commentary. "
            "Please translate the following German text into English:\n\n\n"
            f"{text}"
        )

        # Da TranslateGemma "a single user message" erwartet,
        # packen wir alles in den 'prompt' und lassen 'system' weg.
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False
        }

        try:
            logger.info(f"Sende Textblock an Ollama (Modell: {self.model})...")
            response = requests.post(self.api_url, json=payload, timeout=self.timeout)
            response.raise_for_status()

            result = response.json()
            translated_text = result.get("response", "").strip()
            return translated_text

        except requests.exceptions.Timeout:
            logger.error(f"Ollama Timeout! Das Modell hat nicht innerhalb von {self.timeout} Sekunden geantwortet.")
            raise RuntimeError(f"LLM Timeout nach {self.timeout}s")
        except requests.exceptions.ConnectionError:
            logger.error(f"Verbindung zu Ollama fehlgeschlagen. Läuft der Dienst auf {self.host}?")
            raise RuntimeError("Ollama Connection Error")
        except requests.exceptions.RequestException as e:
            logger.error(f"Unerwarteter Fehler bei der Kommunikation mit Ollama: {e}")
            raise RuntimeError(f"Ollama API Error: {e}")