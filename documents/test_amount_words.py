from decimal import Decimal
from django.test import SimpleTestCase
from core.exceptions import FinancialValidationError
from documents.genoclab_layout import amount_in_words_fr, _amount_notice, _money


class AmountInWordsTests(SimpleTestCase):
    def test_complete_monetary_phrases(self):
        cases = (
            ('11900.50', 'onze mille neuf cents dinars algériens et cinquante centimes'),
            ('11900.60', 'onze mille neuf cents dinars algériens et soixante centimes'),
            ('11900', 'onze mille neuf cents dinars algériens'),
            ('0', 'zéro dinar algérien'),
            ('0.01', 'zéro dinar algérien et un centime'),
            ('0.50', 'zéro dinar algérien et cinquante centimes'),
            ('1', 'un dinar algérien'),
            ('1.01', 'un dinar algérien et un centime'),
            ('1.02', 'un dinar algérien et deux centimes'),
            ('2.01', 'deux dinars algériens et un centime'),
            ('21.21', 'vingt et un dinars algériens et vingt et un centimes'),
            ('71.71', 'soixante et onze dinars algériens et soixante et onze centimes'),
            ('80.80', 'quatre-vingts dinars algériens et quatre-vingts centimes'),
            ('81.81', 'quatre-vingt-un dinars algériens et quatre-vingt-un centimes'),
            ('90.90', 'quatre-vingt-dix dinars algériens et quatre-vingt-dix centimes'),
            ('91.91', 'quatre-vingt-onze dinars algériens et quatre-vingt-onze centimes'),
            ('99.99', 'quatre-vingt-dix-neuf dinars algériens et quatre-vingt-dix-neuf centimes'),
            ('200', 'deux cents dinars algériens'),
            ('201', 'deux cent un dinars algériens'),
            ('1000.05', 'mille dinars algériens et cinq centimes'),
            ('80000', 'quatre-vingt mille dinars algériens'),
            ('200000', 'deux cent mille dinars algériens'),
            ('1000000', 'un million de dinars algériens'),
            ('2000000.01', 'deux millions de dinars algériens et un centime'),
            ('1000001', 'un million un dinars algériens'),
            ('80000000', 'quatre-vingts millions de dinars algériens'),
            ('200000000', 'deux cents millions de dinars algériens'),
            ('1000000000', 'un milliard de dinars algériens'),
            ('-11900.50', 'moins onze mille neuf cents dinars algériens et cinquante centimes'),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(amount_in_words_fr(value), expected)
                self.assertNotRegex(expected, r'[0-9/]')

    def test_rounding_matches_numeric_amounts(self):
        cases = (
            ('1.995', 'deux dinars algériens', '2,00 DA'),
            ('11900.505', 'onze mille neuf cents dinars algériens et cinquante et un centimes', '11 900,51 DA'),
            ('0.005', 'zéro dinar algérien et un centime', '0,01 DA'),
            ('0.004', 'zéro dinar algérien', '0,00 DA'),
            ('999999.995', 'un million de dinars algériens', '1 000 000,00 DA'),
        )
        for value, words, numeric in cases:
            with self.subTest(value=value):
                self.assertEqual(amount_in_words_fr(value), words)
                self.assertEqual(_money(value), numeric)
        self.assertEqual(amount_in_words_fr('-0.004'), 'zéro dinar algérien')

    def test_supported_numeric_types(self):
        expected = 'mille dinars algériens et cinquante centimes'
        for value in ('1000.50', Decimal('1000.50'), 1000.5):
            self.assertEqual(amount_in_words_fr(value), expected)
        self.assertEqual(amount_in_words_fr(1000), 'mille dinars algériens')

    def test_every_centime_is_written_without_digits_or_fractions(self):
        for cents in range(100):
            with self.subTest(cents=cents):
                value = Decimal('11900') + Decimal(cents) / 100
                words = amount_in_words_fr(value)
                self.assertNotRegex(words, r'[0-9/]')
                self.assertTrue(words.startswith('onze mille neuf cents dinars algériens'))
                if cents:
                    self.assertTrue(words.endswith('centime' if cents == 1 else 'centimes'))
                else:
                    self.assertNotIn('centime', words)

    def test_invalid_and_out_of_range_values_do_not_create_partial_phrases(self):
        for value in (None, '', 'invalid', 'NaN', 'Infinity', '-Infinity', 'sNaN', True,
                      10**12, -(10**12), '999999999999.995', '-999999999999.995'):
            with self.subTest(value=value):
                self.assertEqual(amount_in_words_fr(value), '')
                with self.assertRaises(FinancialValidationError):
                    _amount_notice('', value, 'invoice')
        self.assertTrue(amount_in_words_fr('999999999999.99').endswith('quatre-vingt-dix-neuf centimes'))


class AmountNoticeTests(SimpleTestCase):
    def test_default_notice_for_quotes_and_invoices(self):
        words = 'onze mille neuf cents dinars algériens et cinquante centimes'
        for kind, introduction in (('quote', 'Arrêté le présent devis'),
                                   ('invoice', 'Arrêtée la présente facture')):
            self.assertEqual(_amount_notice('', '11900.50', kind),
                introduction + ' à la somme de ' + words + ' (11 900,50 DA).')

    def test_legacy_currency_suffixes_do_not_duplicate_or_misplace_units(self):
        for suffix in ('dinars', 'dinars algériens', 'Dinars Algériens', 'DZD', 'DA',
                       'dinar algérien', 'de dinars algériens'):
            for marker in ('{amount_words}', '____________________'):
                with self.subTest(suffix=suffix, marker=marker):
                    template = 'Arrêtée la présente facture à la somme de ' + marker + ' ' + suffix + ' ({amount}).'
                    text = _amount_notice(template, '11900.50', 'quote')
                    self.assertEqual(text, 'Arrêté le présent devis à la somme de '
                        'onze mille neuf cents dinars algériens et cinquante centimes (11 900,50 DA).')

    def test_custom_notices_always_include_full_words(self):
        for template in ('Montant : {amount_words}.', 'Montant : {amount}.', 'Montant arrêté.'):
            text = _amount_notice(template, '1.01', 'invoice')
            self.assertIn('un dinar algérien et un centime', text)
            self.assertNotIn('{amount', text)
            self.assertNotIn('/100', text)
        self.assertEqual(_amount_notice('Montant : {amount_words}.', '1000000', 'invoice'),
                         'Montant : un million de dinars algériens.')
