"""
Generate natural-language explanations of a brain MRI scan using a multimodal LLM.
"""
from typing import Optional
from .client import get_llm_client, generate_with_image


def explain_image(image_path_or_bytes, model_prediction: str, provider: str = "gemini", model_id: Optional[str] = None):
    """Generate a short explanation of the scan given the model's prediction."""
    prompt = (
        "You are a medical imaging assistant. Based on this brain MRI scan and the following "
        "classification result from an AI model, provide a brief, clear explanation in plain language "
        "for a clinician. Do not diagnose; only describe what the image might show and how it relates "
        "to the prediction.\n\nModel prediction: " + model_prediction
    )
    client = get_llm_client(provider=provider, model_id=model_id)
    return generate_with_image(client, image_path_or_bytes, prompt)
