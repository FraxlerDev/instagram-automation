import tempfile
import unittest
from pathlib import Path

from bot.files import latin_slug, normalized_folder, unique_file_path, unique_pdf_path, validate_upload


class FileNamingTests(unittest.TestCase):
    def test_transliterates_ukrainian_pdf_name(self):
        self.assertEqual(
            latin_slug("Читалка — Твої книги завжди під рукою"),
            "chytalka-tvoi-knyhy-zavzhdy-pid-rukoiu",
        )

    def test_transliterates_nested_folders(self):
        self.assertEqual(normalized_folder("Курси/Швидке читання"), "kursy/shvydke-chytannia")
        self.assertNotIn("..", normalized_folder("../Безпечна папка"))

    def test_uses_english_name_and_avoids_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = unique_pdf_path(root, "Мої гайди", "Новий гайд.pdf")
            first.write_bytes(b"%PDF-one")
            second = unique_pdf_path(root, "Мої гайди", "Новий гайд.pdf")
            self.assertEqual(first.relative_to(root).as_posix(), "moi-haidy/novyi-haid.pdf")
            self.assertEqual(second.relative_to(root).as_posix(), "moi-haidy/novyi-haid-2.pdf")

    def test_preserves_supported_extension_and_transliterates_any_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = unique_file_path(Path(temp), "Відео/Уроки", "Моє відео.MP4")
            self.assertEqual(path.relative_to(temp).as_posix(), "video/uroky/moie-video.mp4")

    def test_validates_supported_file_signatures(self):
        valid_files = {
            "photo.jpg": b"\xff\xd8\xffdata",
            "photo.png": b"\x89PNG\r\n\x1a\ndata",
            "photo.webp": b"RIFF1234WEBPdata",
            "movie.mp4": b"\x00\x00\x00\x18ftypmp42",
            "movie.mov": b"\x00\x00\x00\x18ftypqt  ",
            "book.pdf": b"%PDF-1.7",
            "sheet.xlsx": b"PK\x03\x04data",
            "slides.pptx": b"PK\x03\x04data",
            "document.docx": b"PK\x03\x04data",
            "notes.txt": "Текст".encode(),
            "audio.mp3": b"ID3data",
            "audio.wav": b"RIFF1234WAVEdata",
            "archive.zip": b"PK\x03\x04data",
        }
        for filename, body in valid_files.items():
            with self.subTest(filename=filename):
                self.assertTrue(validate_upload(filename, body)[0])
        self.assertFalse(validate_upload("fake.pdf", b"not-a-pdf")[0])
        self.assertFalse(validate_upload("script.exe", b"MZ")[0])


if __name__ == "__main__":
    unittest.main()
