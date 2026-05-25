from __future__ import annotations

from pathlib import Path

from app.services.llm.base import LLMParseError, LLMProvider, LLMUnavailable, parse_llm_json

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


class LLMService:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    @property
    def available(self) -> bool:
        return getattr(self.provider, "available", False)

    def classify_dish(self, name: str) -> dict:
        prompt = _load_prompt("classify_dish.txt").format(name=name)
        try:
            return parse_llm_json(self.provider.generate(prompt, temperature=0.4))
        except (LLMUnavailable, LLMParseError):
            return parse_llm_json(self.provider.generate(prompt, temperature=0.6))

    def generate_new_dishes(
        self,
        *,
        cuisine_prefs,
        spicy,
        dislikes,
        ingredients,
        cuisine_histogram,
        cooked_this_week,
        meal_label: str = "正餐",
    ) -> list[dict]:
        prompt = _load_prompt("new_dish.txt").format(
            cuisine_prefs=", ".join(cuisine_prefs) or "(无)",
            spicy=spicy,
            dislikes=", ".join(dislikes) or "(无)",
            ingredients=", ".join(ingredients),
            cuisine_histogram=", ".join(f"{k}:{v}" for k, v in cuisine_histogram.items())
            or "(空)",
            cooked_this_week=", ".join(cooked_this_week) or "(无)",
            meal_label=meal_label,
        )
        data = parse_llm_json(self.provider.generate(prompt, temperature=0.7))
        return list(data.get("dishes", []))
