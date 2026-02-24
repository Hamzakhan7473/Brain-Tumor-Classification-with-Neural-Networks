"""
HealthTech MRI Report UI: 2024-style dashboard — glassmorphism, gradients, dark mode.
Research-backed: empathetic design, clear data viz, accessibility (WCAG), minimal cognitive load.
"""
import streamlit as st

# Light theme (default)
ACCENT = "#0d9488"
ACCENT_LIGHT = "rgba(13, 148, 136, 0.12)"
TEXT = "#1e293b"
TEXT_MUTED = "#64748b"
BG = "#fafbfc"
CARD_BG = "#ffffff"

# Dark theme (accessibility: contrast ≥ 4.5:1)
ACCENT_DARK = "#2dd4bf"
TEXT_DARK = "#e2e8f0"
TEXT_MUTED_DARK = "#94a3b8"
BG_DARK = "#0f172a"
CARD_BG_DARK = "#1e293b"
BORDER_DARK = "rgba(255,255,255,0.08)"


def inject_apple_css(dark: bool = False):
    """Inject global CSS. Set dark=True for dark mode (reduces eye strain, modern look)."""
    if dark:
        bg, card_bg, text, text_muted, accent, accent_light = (
            BG_DARK, CARD_BG_DARK, TEXT_DARK, TEXT_MUTED_DARK, ACCENT_DARK, "rgba(45, 212, 191, 0.15)"
        )
        border = BORDER_DARK
        shadow = "0 4px 24px rgba(0,0,0,0.3)"
        input_bg = "#334155"
    else:
        bg, card_bg, text, text_muted, accent, accent_light = (
            BG, CARD_BG, TEXT, TEXT_MUTED, ACCENT, ACCENT_LIGHT
        )
        border = "rgba(0,0,0,0.06)"
        shadow = "0 4px 24px rgba(0,0,0,0.06)"
        input_bg = "#f8fafc"

    st.markdown(
        f"""
        <style>
        /* 2024 HealthTech: Plus Jakarta Sans, glassmorphism-lite, gradients */
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
        
        html, body, [class*="css"] {{
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
            background: {bg} !important;
            color: {text} !important;
            transition: background 0.3s ease, color 0.3s ease;
        }}
        
        .block-container {{
            padding-top: 2rem !important;
            padding-bottom: 3rem !important;
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        h1, h2, h3 {{
            font-weight: 600 !important;
            letter-spacing: -0.02em !important;
            color: {text} !important;
        }}
        h1 {{ font-size: 2.5rem !important; }}
        h2 {{ font-size: 1.5rem !important; }}
        h3 {{ font-size: 1.25rem !important; }}
        
        /* Glassmorphism-lite cards: subtle blur + soft shadow */
        .apple-card {{
            background: {card_bg};
            border-radius: 20px;
            padding: 1.5rem 1.75rem;
            margin: 1rem 0;
            box-shadow: {shadow};
            border: 1px solid {border};
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        .apple-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.08);
        }}
        
        .apple-card-header {{
            font-size: 1.05rem;
            font-weight: 600;
            color: {text};
            margin-bottom: 0.75rem;
            letter-spacing: -0.01em;
        }}
        
        /* Hero — gradient accent, bento-style */
        .apple-hero {{
            text-align: center;
            padding: 3rem 1.5rem 2.5rem;
            margin-bottom: 1.5rem;
            background: linear-gradient(180deg, {accent_light} 0%, transparent 70%);
            border-radius: 24px;
            border: 1px solid {border};
        }}
        .ondex-badge {{
            display: inline-block;
            font-size: 0.7rem;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: {accent};
            margin-bottom: 0.75rem;
            padding: 0.35rem 0.85rem;
            background: {accent_light};
            border-radius: 999px;
        }}
        .apple-hero h1 {{
            font-size: 2.5rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            margin-bottom: 0.5rem;
            color: {text} !important;
        }}
        .apple-hero p {{
            font-size: 1.1rem;
            color: {text_muted};
            font-weight: 400;
            max-width: 540px;
            margin: 0 auto;
            line-height: 1.6;
        }}
        
        [data-testid="stFileUploader"] {{
            background: {card_bg} !important;
            border-radius: 20px !important;
            padding: 2.5rem !important;
            border: 2px dashed {accent_light} !important;
            transition: all 0.25s ease;
            box-shadow: {shadow};
        }}
        [data-testid="stFileUploader"]:hover {{
            border-color: {accent} !important;
            background: {input_bg} !important;
            transform: scale(1.01);
        }}
        
        .stButton > button {{
            border-radius: 12px !important;
            font-weight: 600 !important;
            padding: 0.6rem 1.35rem !important;
            border: none !important;
            background: {accent} !important;
            color: #fff !important;
            transition: all 0.2s ease !important;
        }}
        .stButton > button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 14px rgba(13, 148, 136, 0.4);
            border: none !important;
            background: #0f766e !important;
            color: #fff !important;
        }}
        
        [data-testid="stSidebar"] {{
            background: {card_bg} !important;
            border-right: 1px solid {border} !important;
        }}
        [data-testid="stSidebar"] .block-container {{ padding-top: 1.5rem !important; }}
        
        [data-testid="stAlert"] {{
            border-radius: 14px !important;
            border: 1px solid {border} !important;
            box-shadow: {shadow} !important;
        }}
        
        [data-testid="stChatInput"], [data-testid="stChatMessage"] {{
            border-radius: 14px !important;
            border: 1px solid {border} !important;
        }}
        
        .apple-pill {{
            display: inline-block;
            background: {accent_light};
            color: {text};
            padding: 0.35rem 0.85rem;
            border-radius: 999px;
            font-size: 0.88rem;
            font-weight: 500;
            margin: 0.2rem 0.2rem 0.2rem 0;
            transition: transform 0.15s ease;
        }}
        .apple-pill:hover {{ transform: scale(1.02); }}
        .apple-pill strong {{ color: {accent}; }}
        
        .apple-divider {{
            height: 1px;
            background: linear-gradient(90deg, transparent, {border}, transparent);
            margin: 2rem 0;
        }}
        
        .apple-caption {{
            font-size: 0.85rem;
            color: {text_muted};
            margin-top: 0.5rem;
        }}

        /* ——— Report dashboard (bento-style panels) ——— */
        .report-topbar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.75rem 0 1.25rem;
            margin-bottom: 1rem;
            border-bottom: 1px solid {border};
            flex-wrap: wrap;
            gap: 0.75rem;
        }}
        .report-topbar-left {{ display: flex; align-items: center; gap: 1rem; }}
        .report-topbar-right {{ display: flex; align-items: center; gap: 0.75rem; }}
        .report-title {{ font-size: 1.35rem; font-weight: 700; color: {text}; margin: 0; letter-spacing: -0.02em; }}
        .report-search {{
            min-width: 240px;
            padding: 0.55rem 1rem;
            border-radius: 12px;
            border: 1px solid {border};
            font-size: 0.9rem;
            color: {text_muted};
            background: {input_bg};
            transition: border-color 0.2s, box-shadow 0.2s;
        }}
        .report-search:focus {{ outline: none; border-color: {accent}; box-shadow: 0 0 0 3px {accent_light}; }}
        .report-patient-card {{
            background: {card_bg};
            border-radius: 16px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1rem;
            border: 1px solid {border};
            box-shadow: {shadow};
            transition: transform 0.2s ease;
        }}
        .report-patient-card:hover {{ transform: translateY(-1px); }}
        .report-patient-card .patient-name {{ font-weight: 600; color: {text}; font-size: 1.05rem; }}
        .report-patient-card .patient-meta {{ font-size: 0.85rem; color: {text_muted}; margin-top: 0.25rem; }}

        .findings-card, .similar-cases-card {{
            background: {card_bg};
            border-radius: 16px;
            padding: 1.25rem 1.5rem;
            margin: 1rem 0;
            border: 1px solid {border};
            box-shadow: {shadow};
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        .findings-card:hover, .similar-cases-card:hover {{ transform: translateY(-1px); box-shadow: 0 8px 28px rgba(0,0,0,0.08); }}
        .findings-card h4, .similar-cases-card h4 {{ margin: 0 0 0.75rem 0; font-size: 1rem; font-weight: 600; color: {text}; }}
        .finding-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.65rem 0;
            border-bottom: 1px solid {border};
            font-size: 0.9rem;
            transition: background 0.15s ease;
        }}
        .finding-row:last-child {{ border-bottom: none; }}
        .finding-row:hover {{ background: {accent_light}; border-radius: 8px; margin: 0 -0.5rem; padding-left: 0.5rem; padding-right: 0.5rem; }}
        .finding-label {{ color: {text}; font-weight: 500; }}
        .finding-value {{ color: {text}; }}
        .status-pill {{
            display: inline-block;
            padding: 0.28rem 0.7rem;
            border-radius: 999px;
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            transition: transform 0.15s ease;
        }}
        .status-pill:hover {{ transform: scale(1.05); }}
        .status-normal {{ background: #dcfce7; color: #166534; }}
        .status-follow {{ background: #fef3c7; color: #92400e; }}
        .status-refer {{ background: #fee2e2; color: #991b1b; }}
        .status-review {{ background: #e0e7ff; color: #3730a3; }}

        .recommendations-card {{
            background: linear-gradient(135deg, {accent_light} 0%, {card_bg} 50%);
            border-radius: 16px;
            padding: 1.25rem 1.5rem;
            margin: 1rem 0;
            border: 1px solid {border};
            box-shadow: {shadow};
            transition: transform 0.2s ease;
        }}
        .recommendations-card:hover {{ transform: translateY(-1px); }}
        .recommendations-card h4 {{ margin: 0 0 0.75rem 0; font-size: 1rem; font-weight: 600; color: {text}; }}
        .recommendation-item {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.45rem 0;
            font-size: 0.9rem;
            color: {text};
            transition: padding-left 0.2s ease;
        }}
        .recommendation-item:hover {{ padding-left: 4px; }}
        .recommendation-item::before {{ content: "↑"; color: {accent}; font-weight: 700; }}
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


# ——— HealthTech dashboard components (doctor report view) ———

def report_topbar(title: str = "MRI Report", show_search: bool = True):
    """Top bar: title, search placeholder, Export/Recent area (buttons rendered by caller)."""
    search_html = (
        '<input type="text" class="report-search" placeholder="Search reports, tumor types…" readonly />'
        if show_search else ""
    )
    st.markdown(
        f'<div class="report-topbar">'
        f'<div class="report-topbar-left"><h2 class="report-title">{title}</h2>{search_html}</div>'
        f'<div class="report-topbar-right" id="report-topbar-actions"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def report_patient_card(patient_name: str = "Current scan", meta: str = "Uploaded now"):
    """Patient/scan context card (e.g. 'John Smith - age: 45' or 'Scan - Feb 2026')."""
    st.markdown(
        f'<div class="report-patient-card">'
        f'<div class="patient-name">{patient_name}</div>'
        f'<div class="patient-meta">{meta}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def findings_row_html(label: str, value: str, status: str) -> str:
    """One finding row: label, value, status pill (normal/follow/refer/review)."""
    status_class = f"status-{status}" if status in ("normal", "follow", "refer", "review") else "status-review"
    return (
        f'<div class="finding-row">'
        f'<span class="finding-label">{label}</span>'
        f'<span class="finding-value">{value}</span>'
        f'<span class="status-pill {status_class}">{status.upper()}</span>'
        f'</div>'
    )


def findings_card_html(title: str, rows: list[tuple[str, str, str]]) -> str:
    """Full findings card HTML. rows = [(label, value, status), ...]."""
    body = "".join(findings_row_html(l, v, s) for l, v, s in rows)
    return f'<div class="findings-card"><h4>{title}</h4><div>{body}</div></div>'


def recommendations_card_html(title: str, items: list[str]) -> str:
    """Recommended next steps card. items = list of short strings."""
    body = "".join(f'<div class="recommendation-item">{item}</div>' for item in items)
    return f'<div class="recommendations-card"><h4>{title}</h4><div>{body}</div></div>'


def similar_cases_card_html(title: str, body_html: str) -> str:
    """Similar cases / reference card (chart or text inside)."""
    return f'<div class="similar-cases-card"><h4>{title}</h4><div>{body_html}</div></div>'
