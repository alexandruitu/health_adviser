"""
Health Adviser — AI-powered health data assessment using Claude API.
"""
import json
import os
from pathlib import Path
from typing import Optional

import anthropic
from fastapi.responses import StreamingResponse

BIOMARKERS_CONFIG_PATH = Path(__file__).parent.parent / "biomarkers_config.json"


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            cfg = json.loads(BIOMARKERS_CONFIG_PATH.read_text())
            key = cfg.get("anthropic_api_key")
        except Exception:
            pass
    if not key:
        raise ValueError(
            "Anthropic API key not configured. Set ANTHROPIC_API_KEY env var "
            "or add 'anthropic_api_key' to biomarkers_config.json"
        )
    return key


SYSTEM_PROMPT = """You are Health Adviser, an expert health analytics assistant embedded in a personal health dashboard.
You are a certified sports medicine physician, exercise physiologist, and longevity science expert.

Your role is to analyze the user's health data and provide:
1. A clear, concise assessment of what the numbers mean
2. Trends worth noting (improving, declining, stable)
3. Actionable insights and recommendations
4. Comparisons to population norms where relevant
5. Potential correlations between metrics

Guidelines:
- Be direct and specific — reference actual numbers from the data
- Use a warm but professional tone
- Highlight both positive findings and areas for improvement
- If data is sparse or missing, note it and explain what it limits
- For exercise data, consider training load, recovery balance, and periodization
- For body composition, consider trends rather than single measurements
- For heart metrics, explain what HRV, resting HR trends indicate about autonomic health
- For sleep, assess architecture (deep/REM/core ratios) and consistency
- For biomarkers, flag anything outside normal ranges and explain clinical significance
- Keep the response focused and scannable — use short paragraphs, not walls of text
- Use markdown formatting: **bold** for key findings, bullet points for recommendations
- Do NOT use emojis
- Respond in 200-400 words unless the data warrants more detail"""


def _sse_stream(client, system: str, messages: list, max_tokens: int = 1024):
    """Shared SSE streaming helper."""
    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def stream_assessment(tab: str, date_range: dict, data: dict):
    """Stream the initial health assessment from Claude API."""
    client = anthropic.Anthropic(api_key=_get_api_key())
    user_msg = (
        f"Analyze my {tab} health data for the period "
        f"{date_range.get('start', '?')} to {date_range.get('end', '?')}.\n\n"
        f"Here is the data:\n```json\n{json.dumps(data, indent=2, default=str)}\n```"
    )
    return _sse_stream(client, SYSTEM_PROMPT, [{"role": "user", "content": user_msg}])


def stream_followup(conversation: list, data: dict, tab: str, date_range: dict):
    """Stream a follow-up response given the full conversation history.

    `conversation` is a list of {role, content} dicts — the entire thread so far,
    starting with the initial assessment exchange and including any follow-ups.
    The original data context is injected into the system prompt so Claude retains
    full awareness of the user's metrics throughout the conversation.
    """
    client = anthropic.Anthropic(api_key=_get_api_key())

    # Enrich system prompt with data context so follow-up answers stay grounded
    system = (
        SYSTEM_PROMPT
        + f"\n\n---\nThe user is viewing the **{tab}** tab, "
        f"data from {date_range.get('start', '?')} to {date_range.get('end', '?')}. "
        f"Full data context for reference:\n```json\n"
        f"{json.dumps(data, indent=2, default=str)}\n```"
    )
    return _sse_stream(client, system, conversation, max_tokens=768)
