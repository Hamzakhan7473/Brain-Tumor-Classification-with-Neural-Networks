"""
Ondex-inspired HealthTech UI: minimal, clean, AI-driven healthcare aesthetic.
Ref: https://www.framer.com/marketplace/templates/ondex/
"""
import streamlit as st

# HealthTech accent (teal/slate)
ACCENT = "#0d9488"
ACCENT_LIGHT = "rgba(13, 148, 136, 0.12)"
TEXT = "#1e293b"
TEXT_MUTED = "#64748b"
BG = "#fafbfc"
CARD_BG = "#ffffff"


def inject_apple_css():
    """Inject global CSS for Ondex-style HealthTech UI (call once at top of page)."""
    st.markdown(
        f"""
        <style>
        /* Ondex-style: minimal, health-tech */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
            background-color: {BG} !important;
        }}
        
        .block-container {{
            padding-top: 2rem !important;
            padding-bottom: 3rem !important;
            max-width: 1100px;
            margin: 0 auto;
        }}
        
        h1, h2, h3 {{
            font-weight: 600 !important;
            letter-spacing: -0.02em !important;
            color: {TEXT} !important;
        }}
        h1 {{ font-size: 2.5rem !important; }}
        h2 {{ font-size: 1.5rem !important; }}
        h3 {{ font-size: 1.25rem !important; }}
        
        .apple-card {{
            background: {CARD_BG};
            border-radius: 16px;
            padding: 1.5rem 1.75rem;
            margin: 1rem 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            border: 1px solid rgba(0,0,0,0.06);
        }}
        
        .apple-card-header {{
            font-size: 1.05rem;
            font-weight: 600;
            color: {TEXT};
            margin-bottom: 0.75rem;
            letter-spacing: -0.01em;
        }}
        
        /* Hero — Ondex-style product led */
        .apple-hero {{
            text-align: center;
            padding: 2.5rem 1rem 2rem;
            margin-bottom: 1.5rem;
        }}
        .ondex-badge {{
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 500;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: {ACCENT};
            margin-bottom: 0.75rem;
        }}
        .apple-hero h1 {{
            font-size: 2.5rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            margin-bottom: 0.5rem;
            color: {TEXT} !important;
        }}
        .apple-hero p {{
            font-size: 1.1rem;
            color: {TEXT_MUTED};
            font-weight: 400;
            max-width: 520px;
            margin: 0 auto;
            line-height: 1.55;
        }}
        
        [data-testid="stFileUploader"] {{
            background: {CARD_BG} !important;
            border-radius: 14px !important;
            padding: 2rem !important;
            border: 2px dashed {ACCENT_LIGHT} !important;
            transition: border-color 0.2s, background 0.2s;
        }}
        [data-testid="stFileUploader"]:hover {{
            border-color: {ACCENT} !important;
            background: #f8fafc !important;
        }}
        
        .stButton > button {{
            border-radius: 10px !important;
            font-weight: 500 !important;
            padding: 0.55rem 1.2rem !important;
            border: none !important;
            background: {ACCENT} !important;
            color: #fff !important;
            transition: opacity 0.2s, transform 0.1s !important;
        }}
        .stButton > button:hover {{
            opacity: 0.92;
            transform: translateY(-1px);
            border: none !important;
            background: #0f766e !important;
            color: #fff !important;
        }}
        
        [data-testid="stSidebar"] {{
            background: {CARD_BG} !important;
            border-right: 1px solid rgba(0,0,0,0.06) !important;
        }}
        [data-testid="stSidebar"] .block-container {{ padding-top: 1.5rem !important; }}
        
        [data-testid="stAlert"] {{
            border-radius: 10px !important;
            border: none !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        }}
        
        [data-testid="stChatInput"] {{
            border-radius: 14px !important;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06) !important;
            border: 1px solid rgba(0,0,0,0.08) !important;
        }}
        
        [data-testid="stChatMessage"] {{
            border-radius: 14px !important;
            padding: 1rem 1.2rem !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        }}
        
        .apple-pill {{
            display: inline-block;
            background: {ACCENT_LIGHT};
            color: {TEXT};
            padding: 0.35rem 0.85rem;
            border-radius: 20px;
            font-size: 0.88rem;
            font-weight: 500;
            margin: 0.2rem 0.2rem 0.2rem 0;
        }}
        .apple-pill strong {{ color: {ACCENT}; }}
        
        .apple-divider {{
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(0,0,0,0.08), transparent);
            margin: 2rem 0;
        }}
        
        .apple-caption {{
            font-size: 0.85rem;
            color: {TEXT_MUTED};
            margin-top: 0.5rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str, badge: str = "AI-Powered HealthTech"):
    """Render an Ondex-style hero with optional badge."""
    badge_html = f'<span class="ondex-badge">{badge}</span>' if badge else ""
    st.markdown(
        f"""
        <div class="apple-hero">
            {badge_html}
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def card_header(title: str):
    """Render a card section header."""
    st.markdown(f'<div class="apple-card-header">{title}</div>', unsafe_allow_html=True)


def card_container():
    pass


def apple_card_markdown(html_content: str):
    """Render markdown inside a card-style block."""
    st.markdown(
        f'<div class="apple-card">{html_content}</div>',
        unsafe_allow_html=True,
    )
