from uuid import uuid4

import pytest

from src.infrastructure.moderation.text_filter import SimpleTextModerationFilter


@pytest.mark.asyncio
async def test_moderation_filter_blocks_links_and_stopwords():
    flt = SimpleTextModerationFilter()
    ok_link, rule_link, _ = await flt.check_text(
        uuid4(), "Отличная игра, заходи на https://spam.test"
    )
    ok_word, rule_word, _ = await flt.check_text(
        uuid4(), "Лучший промокод только у нас в профиле"
    )
    ok_good, rule_good, _ = await flt.check_text(
        uuid4(), "Отличный сюжет и плавная боевая система."
    )

    assert not ok_link and rule_link == "url_spam_detected"
    assert not ok_word and rule_word.startswith("stop_word:")
    assert ok_good and rule_good == "passed_all_checks"