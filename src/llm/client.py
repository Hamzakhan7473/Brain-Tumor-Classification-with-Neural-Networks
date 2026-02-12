"""
Multimodal LLM client (Gemini 1.5 Flash by default; extensible for Challenge 3).
"""
import io
import os
from typing import Optional

# Lazy import to avoid requiring API key at import time
_gemini_client = None


def get_llm_client(provider: str = "gemini", model_id: Optional[str] = None):
    """Return a client for the given provider. Challenge 3: selectable LLM."""
    if provider == "gemini":
        import google.generativeai as genai
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_id or "gemini-1.5-flash")
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
