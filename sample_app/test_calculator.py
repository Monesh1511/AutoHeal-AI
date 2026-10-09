import pytest

from calculator import divide


def test_normal_division():
    assert divide(8, 2) == 4


def test_negative_division():
    assert divide(-8, 2) == -4


def test_zero_divisor_contract():
    with pytest.raises(ValueError, match="Divisor cannot be zero"):
        divide(8, 0)
