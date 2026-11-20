from src.domain.services import calculate_bayesian_rating, detect_review_bombing


def test_bayesian_cold_start_smoothing():
    res = calculate_bayesian_rating(
        valid_ratings=[10, 10], global_mean=7.20, confidence_threshold=30
    )
    assert res.raw_average == 10.0
    assert res.bayesian_rating == 7.38
    assert res.valid_count == 2


def test_bayesian_convergence_on_large_sample():
    res = calculate_bayesian_rating(
        valid_ratings=[9] * 1000, global_mean=7.0, confidence_threshold=30
    )
    assert res.bayesian_rating == 8.94


def test_detect_review_bombing_triggers_on_burst():
    window = [1] * 25
    historical = [8, 9, 8, 8, 9, 7, 8, 9, 8, 8]
    assert detect_review_bombing(window, baseline_hourly_rate=2.0, historical_ratings=historical)


def test_detect_review_bombing_ignores_low_volume():
    window = [1] * 10
    historical = [8, 9, 8, 8, 9, 7, 8, 9, 8, 8]
    assert not detect_review_bombing(
        window, baseline_hourly_rate=1.0, historical_ratings=historical
    )
