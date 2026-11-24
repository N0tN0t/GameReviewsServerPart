import hashlib
import re
from typing import Any
from uuid import UUID

URL_PATTERN = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
STOP_WORDS = {"казино", "ставки", "промокод", "бесплатные деньги", "купить аккаунт"}


class SimpleTextModerationFilter:
    def __init__(self, review_repo: Any | None = None) -> None:
        self._review_repo = review_repo

    @staticmethod
    def compute_hash(text: str) -> str:
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    async def check_text(self, user_id: UUID, text: str) -> tuple[bool, str, str]:
        content_hash = self.compute_hash(text)
        lowered = text.lower()

        if URL_PATTERN.search(text):
            return False, "url_spam_detected", content_hash

        for word in STOP_WORDS:
            if word in lowered:
                return False, f"stop_word:{word}", content_hash

        if self._review_repo is not None:
            is_dup = await self._review_repo.has_duplicate_hash_recent(content_hash)
            if is_dup:
                return False, "duplicate_text_24h", content_hash

        return True, "passed_all_checks", content_hash
