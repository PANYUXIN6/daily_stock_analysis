# -*- coding: utf-8 -*-
"""
===================================
Report placeholder fallback tests
===================================

Tests for the shared price-position placeholder helper.
"""

import sys
import unittest
from unittest.mock import MagicMock

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.analyzer import (
    _is_value_placeholder,
)


class TestIsValuePlaceholder(unittest.TestCase):
    """Tests for _is_value_placeholder."""

    def test_none_is_placeholder(self) -> None:
        self.assertTrue(_is_value_placeholder(None))

    def test_zero_is_placeholder(self) -> None:
        self.assertTrue(_is_value_placeholder(0))
        self.assertTrue(_is_value_placeholder(0.0))

    def test_empty_string_is_placeholder(self) -> None:
        self.assertTrue(_is_value_placeholder(""))
        self.assertTrue(_is_value_placeholder("   "))

    def test_na_variants_are_placeholder(self) -> None:
        self.assertTrue(_is_value_placeholder("N/A"))
        self.assertTrue(_is_value_placeholder("n/a"))
        self.assertTrue(_is_value_placeholder("NA"))
        self.assertTrue(_is_value_placeholder("na"))

    def test_data_missing_is_placeholder(self) -> None:
        self.assertTrue(_is_value_placeholder("数据缺失"))
        self.assertTrue(_is_value_placeholder("数据缺失，无法判断"))
        self.assertTrue(_is_value_placeholder("未知"))

    def test_valid_values_not_placeholder(self) -> None:
        self.assertFalse(_is_value_placeholder(0.5))
        self.assertFalse(_is_value_placeholder("50%"))
        self.assertFalse(_is_value_placeholder("67.5%"))
        self.assertFalse(_is_value_placeholder(25.6))
        self.assertFalse(_is_value_placeholder("健康"))
