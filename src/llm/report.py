"""
Comprehensive report: model prediction, insights, historical cases, next steps (Challenge 5).
"""
from typing import Optional
from .client import get_llm_client, generate_with_image


def build_report(image_path_or_bytes, prediction: str, confidence: float, provider: str = "gemini", model_id: Optional[str] = None):
    """Generate a structured report with prediction, insights, analogous cases, and next steps."""
    prompt = (
        "You are a medical imaging report assistant. Given this brain MRI scan and the following "
        "AI classification result, generate a concise clinical-style report with these sections:\n"
        "1. **Prediction summary**: Restate the prediction and confidence.\n"
        "2. **Additional insights**: Brief observations about the image (in non-diagnostic language).\n"
        "3. **Historical/analogous cases**: One or two short, anonymized analogies (e.g. 'similar appearance to cases that...').\n"
        "4. **Next steps for patient and doctors**: Suggested follow-up (e.g. further imaging, specialist referral).\n"
        "Use clear headings and plain language. Do not make a definitive diagnosis.\n\n"
        f"Model prediction: {prediction} (confidence: {confidence:.2%})."
    )
    client = get_llm_client(provider=provider, model_id=model_id)
    return generate_with_image(client, image_path_or_bytes, prompt)
