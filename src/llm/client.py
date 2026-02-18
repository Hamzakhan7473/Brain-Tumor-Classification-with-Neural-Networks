"""
Multimodal LLM client — supports latest Gemini (2.0 Flash default) and selectable models (Challenge 3).
"""
import io
import os
from typing import Optional

# Default to newest generally-available Gemini
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

# All Gemini provider ids use the same Google backend; model_id selects the version
GEMINI_PROVIDER_IDS = frozenset({
    "gemini", "gemini_2_flash", "gemini_2_flash_lite", "gemini_2_pro",
    "gemini_15_flash", "gemini_15_pro",
})


def get_llm_client(provider: str = "gemini", model_id: Optional[str] = None):
    """Return a client for the given provider. Uses model_id if provided, else default for provider."""
    if provider in GEMINI_PROVIDER_IDS or provider.startswith("gemini"):
        import google.generativeai as genai
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_id or DEFAULT_GEMINI_MODEL)
        return model
    raise ValueError(f"Unknown provider: {provider}")


def generate_with_image(client, image_bytes_or_path, prompt: str, **kwargs):
    """Send image + text prompt to the LLM and return response text."""
    if hasattr(client, "generate_content"):
        import PIL.Image
        if isinstance(image_bytes_or_path, str):
            img = PIL.Image.open(image_bytes_or_path)
        elif isinstance(image_bytes_or_path, bytes):
            img = PIL.Image.open(io.BytesIO(image_bytes_or_path))
        else:
            img = image_bytes_or_path
        response = client.generate_content([prompt, img], generation_config=kwargs)
        return response.text if response else ""
    return ""
