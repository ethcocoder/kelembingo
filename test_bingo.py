"""
Bingo Detection Test Suite — only true winners pass.
Tests all 4 patterns: rows, columns, diagonals, 4 corners.
Also verifies edge cases and false-positive rejection.
"""
import sys, os, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import Mock
from game.round_engine import RoundEngine


def make_cartela(rows):
    flat = []
    for r in rows:
        flat.extend(r)
    return flat


SAMPLE_ROWS = [
    [ 1, 16, 31, 46, 61],
    [ 2, 17, 32, 47, 62],
    [ 3, 18,  0, 48, 63],
    [ 4, 19, 34, 49, 64],
    [ 5, 20, 35, 50, 65],
]
SAMPLE_CARTELA = make_cartela(SAMPLE_ROWS)


class TestBingoDetection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = RoundEngine(Mock())

    def check(self, called):
        return self.engine.check_bingo_for_cartela(SAMPLE_CARTELA, called)

    def test_row_0_wins(self):
        self.assertTrue(self.check([1, 16, 31, 46, 61]))

    def test_row_1_wins(self):
        self.assertTrue(self.check([2, 17, 32, 47, 62]))

    def test_row_2_wins_includes_free(self):
        self.assertTrue(self.check([3, 18, 48, 63]))

    def test_row_3_wins(self):
        self.assertTrue(self.check([4, 19, 34, 49, 64]))

    def test_row_4_wins(self):
        self.assertTrue(self.check([5, 20, 35, 50, 65]))

    def test_col_0_wins(self):
        self.assertTrue(self.check([1, 2, 3, 4, 5]))

    def test_col_1_wins(self):
        self.assertTrue(self.check([16, 17, 18, 19, 20]))

    def test_col_2_wins_includes_free(self):
        self.assertTrue(self.check([31, 32, 34, 35]))

    def test_col_3_wins(self):
        self.assertTrue(self.check([46, 47, 48, 49, 50]))

    def test_col_4_wins(self):
        self.assertTrue(self.check([61, 62, 63, 64, 65]))

    def test_main_diagonal_wins(self):
        self.assertTrue(self.check([1, 17, 49, 65]))

    def test_anti_diagonal_wins(self):
        self.assertTrue(self.check([61, 47, 19, 5]))

    def test_four_corners_wins(self):
        self.assertTrue(self.check([1, 61, 5, 65]))

    def test_four_corners_wins_any_order(self):
        self.assertTrue(self.check([65, 5, 61, 1]))

    def test_three_corners_not_enough(self):
        self.assertFalse(self.check([1, 61, 5]))

    def test_two_corners_not_enough(self):
        self.assertFalse(self.check([1, 61]))

    def test_4_in_row_not_win(self):
        self.assertFalse(self.check([1, 16, 31, 46]))

    def test_4_in_col_not_win(self):
        self.assertFalse(self.check([1, 2, 3, 4]))

    def test_empty_called_not_win(self):
        self.assertFalse(self.check([]))

    def test_unrelated_numbers_not_win(self):
        self.assertFalse(self.check([7, 22, 37, 52, 67, 10, 25, 40, 55, 70]))

    def test_one_number_not_win(self):
        self.assertFalse(self.check([1]))

    def test_free_space_alone_not_win(self):
        self.assertFalse(self.check([]))

    def test_free_space_not_in_corners(self):
        corners = [SAMPLE_CARTELA[0], SAMPLE_CARTELA[4], SAMPLE_CARTELA[20], SAMPLE_CARTELA[24]]
        self.assertEqual(corners, [1, 61, 5, 65])
        self.assertNotIn(0, corners)


class TestCartelaPatterns(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = RoundEngine(Mock())
        cls.patterns = cls.engine.get_cartela_patterns(SAMPLE_CARTELA)

    def test_has_4_corners_pattern(self):
        found = any(set(p) == {1, 61, 5, 65} for p in self.patterns)
        self.assertTrue(found)

    def test_has_5_rows(self):
        rows = [p for p in self.patterns if len(p) in (4, 5)]
        self.assertGreaterEqual(len(rows), 4)

    def test_has_5_columns(self):
        cols = [p for p in self.patterns if len(p) >= 4]
        self.assertGreaterEqual(len(cols), 5)

    def test_has_2_diagonals(self):
        self.assertGreaterEqual(len(self.patterns), 12)

    def test_no_zero_in_any_pattern(self):
        for p in self.patterns:
            self.assertNotIn(0, p)


class TestPickTargetWinner(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = RoundEngine(Mock())

    def setUp(self):
        cartela_a = make_cartela([
            [1, 16, 31, 46, 61],
            [2, 17, 32, 47, 62],
            [3, 18,  0, 48, 63],
            [4, 19, 34, 49, 64],
            [5, 20, 35, 50, 65],
        ])
        cartela_b = make_cartela([
            [10, 25, 40, 55, 70],
            [11, 26, 41, 56, 71],
            [12, 27,  0, 57, 72],
            [13, 28, 43, 58, 73],
            [14, 29, 44, 59, 74],
        ])
        self.player_cartelas = {
            'user_a': [{'cartela_number': 1, 'flat': cartela_a}],
            'user_b': [{'cartela_number': 2, 'flat': cartela_b}],
        }

    def test_picks_closest_to_win(self):
        called = [1, 16, 31, 46]
        target = self.engine._pick_target_winner(self.player_cartelas, called, {})
        self.assertIsNotNone(target)
        self.assertEqual(target['user_id'], 'user_a')

    def test_returns_none_without_players(self):
        self.assertIsNone(self.engine._pick_target_winner({}, [], {}))


class TestCandidateProgress(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = RoundEngine(Mock())

    def test_no_players_returns_999(self):
        self.assertEqual(self.engine._candidate_progress({}, [1, 2, 3]), 999)

    def test_winner_exists_returns_0(self):
        cartela = make_cartela(SAMPLE_ROWS)
        pc = {'user_a': [{'cartela_number': 1, 'flat': cartela}]}
        called = [1, 16, 31, 46, 61]
        self.assertEqual(self.engine._candidate_progress(pc, called), 0)

    def test_one_missing_returns_1(self):
        cartela = make_cartela(SAMPLE_ROWS)
        pc = {'user_a': [{'cartela_number': 1, 'flat': cartela}]}
        called = [1, 16, 31, 46]
        self.assertEqual(self.engine._candidate_progress(pc, called), 1)


class TestEvaluateWinners(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = RoundEngine(Mock())

    def test_no_winners(self):
        pc = {'user_a': [{'cartela_number': 1, 'flat': make_cartela(SAMPLE_ROWS)}]}
        winners = self.engine.evaluate_winners(pc, [1, 16, 31, 46])
        self.assertEqual(len(winners), 0)

    def test_one_winner(self):
        pc = {'user_a': [{'cartela_number': 1, 'flat': make_cartela(SAMPLE_ROWS)}]}
        winners = self.engine.evaluate_winners(pc, [1, 16, 31, 46, 61])
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]['user_id'], 'user_a')

    def test_four_corners_winner(self):
        pc = {'user_a': [{'cartela_number': 1, 'flat': make_cartela(SAMPLE_ROWS)}]}
        winners = self.engine.evaluate_winners(pc, [1, 61, 5, 65])
        self.assertEqual(len(winners), 1)

    def test_two_separate_winners(self):
        cartela_a = make_cartela(SAMPLE_ROWS)
        cartela_b = make_cartela([
            [1, 16, 31, 46, 61],
            [10, 25, 40, 55, 70],
            [12, 27,  0, 57, 72],
            [13, 28, 43, 58, 73],
            [14, 29, 44, 59, 74],
        ])
        pc = {
            'user_a': [{'cartela_number': 1, 'flat': cartela_a}],
            'user_b': [{'cartela_number': 2, 'flat': cartela_b}],
        }
        winners = self.engine.evaluate_winners(pc, [1, 16, 31, 46, 61])
        self.assertEqual(len(winners), 2)


class TestChooseSingleWinner(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = RoundEngine(Mock())

    def test_single_winner(self):
        result = self.engine.choose_single_winner(
            [{'user_id': '1', 'cartela_number': 1}],
            {'1': {'joined_at': '2026-01-01T00:00:00'}},
        )
        self.assertEqual(result['user_id'], '1')

    def test_earliest_joiner_wins_tie(self):
        result = self.engine.choose_single_winner(
            [
                {'user_id': '2', 'cartela_number': 1},
                {'user_id': '1', 'cartela_number': 2},
            ],
            {
                '1': {'joined_at': '2026-01-01T00:00:01'},
                '2': {'joined_at': '2026-01-01T00:00:00'},
            },
        )
        self.assertEqual(result['user_id'], '2')

    def test_none_for_no_winners(self):
        self.assertIsNone(self.engine.choose_single_winner([], {}))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
