from sentiment import polarity


def test_polarity_mapping():
    assert polarity("POSITIVE") == 1
    assert polarity("NEGATIVE") == -1
    assert polarity("NEUTRAL") == 0
    assert polarity("") == 0
    assert polarity(None) == 0


def test_neutral_threshold_is_configurable():
    from config import settings

    assert 0.5 <= settings.SENTIMENT_NEUTRAL_THRESHOLD <= 1.0
