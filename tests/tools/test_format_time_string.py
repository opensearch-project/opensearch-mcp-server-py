# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the time-string compatibility layer."""

import pytest
from tools.analysis.data_fetching_helper import format_time_string


@pytest.mark.parametrize(
    'value,expected',
    [
        # Default 'yyyy-MM-dd HH:mm:ss' (documented format).
        ('2021-03-10 04:30:00', '2021-03-10T04:30:00.000Z'),
        # Trailing Z.
        ('2021-03-10 04:30:00Z', '2021-03-10T04:30:00.000Z'),
        # ISO 8601 with Z.
        ('2021-03-10T04:30:00Z', '2021-03-10T04:30:00.000Z'),
        # ISO 8601 with explicit UTC offset (no Z).
        ('2021-03-10T12:30:00+08:00', '2021-03-10T04:30:00.000Z'),
        # ISO 8601 without timezone — treated as UTC.
        ('2021-03-10T04:30:00', '2021-03-10T04:30:00.000Z'),
        # Unix epoch seconds — string of digits.
        ('1615350600', '2021-03-10T04:30:00.000Z'),
        # Unix epoch milliseconds — auto-detected by magnitude.
        ('1615350600000', '2021-03-10T04:30:00.000Z'),
        # Fractional epoch seconds.
        ('1615350600.5', '2021-03-10T04:30:00.000Z'),
    ],
)
def test_format_time_string_accepts_supported_formats(value, expected):
    assert format_time_string(value) == expected


def test_format_time_string_rejects_garbage():
    with pytest.raises(RuntimeError, match='Invalid time format'):
        format_time_string('not a time')
