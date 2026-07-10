from __future__ import annotations

from anti_geo.audit.models import ParaphrasePair

DEFAULT_QUERY_PAIRS: list[ParaphrasePair] = [
    ParaphrasePair(
        "product",
        "What are the best moisturizers for dry skin?",
        "Which moisturizers work best for dry skin?",
    ),
    ParaphrasePair(
        "product",
        "What is the best ergonomic office chair?",
        "Which office chair has the best ergonomics?",
    ),
    ParaphrasePair(
        "travel",
        "What are the best things to do in Los Angeles?",
        "Top attractions and activities in LA?",
    ),
    ParaphrasePair(
        "health",
        "What are evidence-based treatments for seasonal allergies?",
        "How can I treat seasonal allergies based on medical evidence?",
    ),
    ParaphrasePair(
        "technology",
        "What is the best password manager for small businesses?",
        "Which password manager should small businesses use?",
    ),
    ParaphrasePair(
        "finance",
        "What are the best index funds for long-term investing?",
        "Which index funds are recommended for long-term investors?",
    ),
]


def get_query_pairs(name: str = "default") -> list[ParaphrasePair]:
    if name == "default":
        return list(DEFAULT_QUERY_PAIRS)
    raise ValueError(f"Unknown query set: {name}")
