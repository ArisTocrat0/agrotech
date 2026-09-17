"""Static UI contract tests that do not require a browser or network socket."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT/'web/app.js').read_text(encoding='utf-8')
        cls.app += (ROOT/'web/settings.js').read_text(encoding='utf-8')
        cls.review = (ROOT/'web/review.js').read_text(encoding='utf-8')
        cls.i18n = (ROOT/'web/i18n.js').read_text(encoding='utf-8')

    def test_agronomist_navigation_and_kpis(self):
        for text in ['Обзор','Анализы','Проверка','Отчёты','Настройки',
                     'Обнаружено моделью','Подтверждено сорняков','Продолжить проверку']:
            self.assertIn(text, self.app)

    def test_review_traverses_images(self):
        self.assertIn('pendingTarget(results,reviewImage,reviewDetection)', self.review)
        self.assertIn('Все объекты этого анализа проверены.', self.review)
        self.assertIn('show-all-boxes', self.review)

    def test_new_translated_strings_have_en_and_kk(self):
        for text in ['Обзор','Анализы','Проверка','Отчёты','Настройки',
                     'Следующий непроверенный','Показать все рамки']:
            pattern = re.escape(f'"{text}"') + r'\s*:\s*\{[^}]*en\s*:[^}]*kk\s*:'
            self.assertRegex(self.i18n, pattern)

    def test_polling_is_conditional(self):
        self.assertNotIn('setInterval(refreshTraining', self.app)
        self.assertNotIn('setInterval(refreshSetup', self.app)
        self.assertIn("if(trainingState.status==='running')", self.app)


if __name__ == '__main__':
    unittest.main(verbosity=2)
