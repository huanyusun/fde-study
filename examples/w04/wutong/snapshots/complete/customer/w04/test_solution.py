"""Wutong's learner-owned tests; independent expected money and source handling."""
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('solution',Path(__file__).with_name('solution.py'))
solution=importlib.util.module_from_spec(spec);spec.loader.exec_module(solution)


class BookshopTests(unittest.TestCase):
    def test_decimal_money(self):
        self.assertEqual(solution.cents('19.99'),1999)
        self.assertEqual(solution.cents('0.01'),1)
        with self.assertRaises(ValueError):solution.cents('0.001')

    def test_calendar(self):
        self.assertEqual(solution.date_value('16/03/2025'),'2025-03-16')
        self.assertEqual(solution.date_value('2025年3月16日'),'2025-03-16')
        with self.assertRaises(ValueError):solution.date_value('2026-02-30')


if __name__=='__main__':unittest.main()
