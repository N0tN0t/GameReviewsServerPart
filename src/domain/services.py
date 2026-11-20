from dataclasses import dataclass
from statistics import mean, stdev
from typing import Sequence


@dataclass(frozen=True)
class RatingAggregationResult:
    raw_average: float
    bayesian_rating: float
    valid_count: int


def calculate_bayesian_rating(
    valid_ratings: Sequence[int],
    global_mean: float,
    confidence_threshold: int = 30,
) -> RatingAggregationResult:
    v = len(valid_ratings)
    if v == 0:
        return RatingAggregationResult(
            raw_average=0.0,
            bayesian_rating=round(global_mean, 2),
            valid_count=0,
        )

    raw_avg = sum(valid_ratings) / v
    weight_local = v / (v + confidence_threshold)
    weight_prior = confidence_threshold / (v + confidence_threshold)
    bayesian = weight_local * raw_avg + weight_prior * global_mean

    return RatingAggregationResult(
        raw_average=round(raw_avg, 2),
        bayesian_rating=round(bayesian, 2),
        valid_count=v,
    )


def detect_review_bombing(
    window_ratings: Sequence[int],
    baseline_hourly_rate: float,
    historical_ratings: Sequence[int],
    min_window_volume: int = 20,
    rate_multiplier: float = 5.0,
    extreme_share_threshold: float = 0.75,
) -> bool:
    volume = len(window_ratings)
    effective_baseline = max(baseline_hourly_rate, 1.0)

    if volume < min_window_volume or volume <= effective_baseline * rate_multiplier:
        return False

    extreme_count = sum(1 for r in window_ratings if r in (1, 10))
    if (extreme_count / volume) < extreme_share_threshold:
        return False

    if len(historical_ratings) < 10:
        return True

    hist_mean = mean(historical_ratings)
    hist_std = max(stdev(historical_ratings), 0.5)
    window_mean = mean(window_ratings)

    return abs(window_mean - hist_mean) > 2.5 * hist_std
