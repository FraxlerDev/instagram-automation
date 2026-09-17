import unittest

from bot.text import contains_any_word, words


class TextTests(unittest.TestCase):
    def test_normalizes_case_and_punctuation(self):
        self.assertEqual(words("ГАЙД!"), ["гайд"])

    def test_matches_inflected_keyword(self):
        accepted = frozenset({"гайд", "гайду"})
        self.assertTrue(contains_any_word("Можна мені гайду?", accepted))

    def test_does_not_match_substring(self):
        self.assertFalse(contains_any_word("гайдамак", frozenset({"гайд"})))

    def test_confirmation_in_sentence(self):
        self.assertTrue(contains_any_word("Готово, дякую", frozenset({"готово"})))


if __name__ == "__main__":
    unittest.main()
