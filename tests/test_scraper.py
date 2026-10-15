import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scraper import (
    CONTACT_HEADERS,
    GoogleMapsScraper,
    build_search_queries,
    extract_category_label,
    normalize_mobile_phone,
)


class GoogleMapsScraperTests(unittest.TestCase):
    def test_normalizes_only_turkish_mobile_numbers(self):
        cases = {
            "0532 123 45 67": "+905321234567",
            "+90 (532) 123-45-67": "+905321234567",
            "0090 532 123 45 67": "+905321234567",
            "5321234567": "+905321234567",
            "0212 123 45 67": None,
            "532123456": None,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_mobile_phone(raw), expected)

    def test_extracts_explicit_category_from_maps_card_text(self):
        self.assertEqual(
            extract_category_label(
                "İşletme\nİşletme\n5,0 · Mobilya İmalatçısı · 1436. Sk. No:13",
                "İşletme"
            ),
            "Mobilya İmalatçısı"
        )
        self.assertIsNone(
            extract_category_label(
                "İşletme\n1436. Sk. No:13\nKapalı ⋅ Açılış zamanı: Cum 09:00",
                "İşletme"
            )
        )

    def test_builds_bounded_query_variations_without_losing_originals(self):
        originals = ["mobilya", "mutfak"]
        self.assertEqual(build_search_queries(originals), originals)

        expanded = build_search_queries(originals, expand=True)
        self.assertEqual(expanded[:2], originals)
        self.assertIn("mobilya mutfak", expanded)
        self.assertIn("mobilya üreticisi", expanded)
        self.assertIn("mutfak dolabı imalatı", expanded)
        self.assertEqual(
            len({query.casefold() for query in expanded}),
            len(expanded)
        )

    def test_scroll_targets_maps_results_feed_before_window_fallback(self):
        class Driver:
            script = None

            def execute_script(self, script):
                self.script = script
                return {
                    "container": "results-feed",
                    "scrollTop": 700,
                    "maxScrollTop": 1400
                }

        driver = Driver()
        scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
        state = scraper.scroll_results_panel(driver)

        self.assertEqual(state["container"], "results-feed")
        self.assertIn("div[role=\"feed\"]", driver.script)
        self.assertIn("target.scrollTop", driver.script)
        self.assertIn("window.scrollBy", driver.script)

    def test_waits_for_a_changed_business_card_signature(self):
        class Driver:
            pass

        scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
        scraper.extract_results = lambda _driver: [{
            "name": "Yeni işletme",
            "card_text": "Yeni işletme"
        }]
        with patch("scraper.WebDriverWait") as wait:
            wait.return_value.until.side_effect = lambda condition: condition(Driver())
            self.assertTrue(scraper.wait_for_result_change(Driver(), ()))
        wait.assert_called_once()

    def test_parses_all_supported_cities(self):
        for city in ("istanbul", "ankara", "izmir", "bursa", "antalya",
                     "konya", "adana", "mersin", "gaziantep", "şanlıurfa",
                     "kocaeli", "tekirdag", "kayseri"):
            with self.subTest(city=city), tempfile.TemporaryDirectory() as directory:
                output = os.path.join(directory, "contacts.csv")
                scraper = GoogleMapsScraper(
                    f"mobilya gebze {city}", cumulative_file=output
                )
                self.assertEqual(scraper.city, {
                    "tekirdag": "Tekirdağ"
                }.get(city, city.capitalize()))
                self.assertEqual(scraper.region, "Gebze")

    def test_parses_accented_turkish_city_names(self):
        with tempfile.TemporaryDirectory() as directory:
            scraper = GoogleMapsScraper(
                "mobilya Çorlu Tekirdağ",
                cumulative_file=os.path.join(directory, "contacts.csv")
            )
            self.assertEqual(scraper.city, "Tekirdağ")
            self.assertEqual(scraper.region, "Çorlu")

    def test_explicit_search_location_overrides_query_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            scraper = GoogleMapsScraper(
                "mobilya gebze istanbul",
                cumulative_file=os.path.join(directory, "contacts.csv"),
                city="kocaeli",
                region="gebze"
            )
            self.assertEqual(scraper.city, "Kocaeli")
            self.assertEqual(scraper.region, "Gebze")

    def test_reads_phone_by_header_and_deduplicates_by_normalized_number(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "contacts.csv")
            with open(output, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(CONTACT_HEADERS)
                row = [""] * len(CONTACT_HEADERS)
                row[13] = "0532 123 45 67"
                writer.writerow(row)

            scraper = GoogleMapsScraper("mobilya kocaeli", cumulative_file=output)
            self.assertIn("+905321234567", scraper.existing_phones)

    def test_extracts_phone_without_accepting_landline_or_partial_values(self):
        class Card:
            text = "İşletme 0212 111 22 33; cep telefonu 0532 123 45 67"

            def find_element(self, *args):
                selector = args[1]
                if selector == "h3":
                    return type("NameElement", (), {"text": "Örnek İşletme"})()
                raise LookupError(selector)

        class Driver:
            def find_elements(self, *args):
                selector = args[1]
                if selector == 'div[role="article"]':
                    return [Card()]
                return []

        scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
        self.assertEqual(
            scraper.extract_results(Driver()),
            [{
                'name': 'Örnek İşletme',
                'phone': '+905321234567',
                'card_text': Card.text,
                'category_label': None,
                'place_url': None,
                'sponsored': False
            }]
        )

    def test_extracts_mobile_with_international_00_prefix(self):
        class Card:
            text = "İşletme telefonu 0090 532 123 45 67"

            def find_element(self, *args):
                if args[1] == "h3":
                    return type("NameElement", (), {"text": "İşletme"})()
                raise LookupError(args[1])

        class Driver:
            def find_elements(self, *args):
                return [Card()] if args[1] == 'div[role="article"]' else []

        scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
        self.assertEqual(
            scraper.extract_results(Driver()),
            [{
                'name': 'İşletme',
                'phone': '+905321234567',
                'card_text': Card.text,
                'category_label': None,
                'place_url': None,
                'sponsored': False
            }]
        )

    def test_detects_explicit_sponsored_listing_label(self):
        class Card:
            text = "Sponsorlu İşletme 0532 123 45 67"

            def find_element(self, *args):
                if args[1] == "h3":
                    return type("NameElement", (), {"text": "İşletme"})()
                raise LookupError(args[1])

        class Driver:
            def find_elements(self, *args):
                return [Card()] if args[1] == 'div[role="article"]' else []

        scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
        result = scraper.extract_results(Driver())[0]
        self.assertTrue(result['sponsored'])
        self.assertEqual(result['category_label'], None)

    def test_does_not_treat_business_text_mentioning_ads_as_sponsored(self):
        class Card:
            text = "Reklam Ajansı 0532 123 45 67"

            def find_element(self, *args):
                if args[1] == "h3":
                    return type("NameElement", (), {"text": "Reklam Ajansı"})()
                raise LookupError(args[1])

        class Driver:
            def find_elements(self, *args):
                return [Card()] if args[1] == 'div[role="article"]' else []

        scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
        result = scraper.extract_results(Driver())[0]
        self.assertFalse(result['sponsored'])

    def test_extracts_business_card_without_mobile_for_search_insights(self):
        class Card:
            text = "Koltuk Döşeme\nDöşemeci\n4,8 yıldız\nKadıköy"

            def find_element(self, *args):
                if args[1] == "h3":
                    return type("NameElement", (), {"text": "Koltuk Döşeme"})()
                raise LookupError(args[1])

        class Driver:
            def find_elements(self, *args):
                return [Card()] if args[1] == 'div[role="article"]' else []

        scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
        result = scraper.extract_results(Driver())[0]
        self.assertEqual(result['name'], "Koltuk Döşeme")
        self.assertIsNone(result['phone'])
        self.assertIn("4,8 yıldız", result['card_text'])

    def test_publishes_new_duplicate_and_missing_phone_observations(self):
        observations = []
        scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
        scraper.observed_keys = set()
        scraper.existing_phones = {"+905321234567"}
        scraper.results = []
        scraper.max_results = 10
        scraper.search_query = "mobilya gebze kocaeli"
        scraper.on_result = observations.append

        cards = [
            {
                "name": "Mevcut kayıt",
                "phone": "+905321234567",
                "card_text": "Mevcut kayıt +905321234567",
                "place_url": "https://maps.test/place/1",
                "sponsored": False
            },
            {
                "name": "Telefon yok",
                "phone": None,
                "card_text": "Telefon yok, mobilya imalat",
                "place_url": "https://maps.test/place/2",
                "sponsored": False
            },
            {
                "name": "Yeni kayıt",
                "phone": "+905551234567",
                "card_text": "Yeni kayıt +905551234567",
                "place_url": "https://maps.test/place/3",
                "sponsored": False
            }
        ]

        self.assertTrue(scraper._process_observed_result(cards[0]))
        self.assertFalse(scraper._process_observed_result(cards[0]))
        self.assertTrue(scraper._process_observed_result(cards[1]))
        self.assertTrue(scraper._process_observed_result(cards[2]))
        self.assertEqual(
            [item["collection_status"] for item in observations],
            ["duplicate_phone", "no_mobile", "saved"]
        )
        self.assertEqual(len(scraper.results), 1)

    def test_writes_template_compatible_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "contacts.csv")
            scraper = GoogleMapsScraper(
                "mobilya gebze kocaeli", cumulative_file=output
            )
            scraper.results = [{
                "name": "Örnek İşletme",
                "phone": "+905321234567",
                "category_label": "Mobilya İmalatçısı"
            }]
            scraper.save_to_csv()

            with open(output, newline="", encoding="utf-8-sig") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Phone 1 - Value"], "+905321234567")
            self.assertEqual(rows[0]["Address 1 - City"], "Kocaeli")
            self.assertEqual(rows[0]["Address 1 - Region"], "Gebze")
            self.assertEqual(
                rows[0]["Notes"],
                "Google Maps kategorisi: Mobilya İmalatçısı"
            )
            self.assertEqual(rows[0]["Labels"], "Maps")

    def test_save_rechecks_phone_uniqueness_for_stale_scraper_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "contacts.csv")
            stale_scraper = GoogleMapsScraper(
                "mobilya gebze kocaeli", cumulative_file=output
            )
            first_scraper = GoogleMapsScraper(
                "mobilya gebze kocaeli", cumulative_file=output
            )
            result = {"name": "Aynı İşletme", "phone": "+905321234567"}
            first_scraper.results = [result.copy()]
            stale_scraper.results = [
                result.copy(),
                {"name": "Aynı İşletme", "phone": "0532 123 45 67"}
            ]

            first_scraper.save_to_csv()
            stale_scraper.save_to_csv()

            with open(output, newline="", encoding="utf-8-sig") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(stale_scraper.results, [])

    def test_rejects_existing_csv_without_contacts_phone_header(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "contacts.csv")
            with open(output, "w", encoding="utf-8") as file:
                file.write("wrong,header\n")
            with self.assertRaisesRegex(ValueError, "Phone 1 - Value"):
                GoogleMapsScraper("mobilya kocaeli", cumulative_file=output)

    def test_accepts_empty_existing_csv_and_writes_header(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "contacts.csv")
            Path(output).touch()
            scraper = GoogleMapsScraper("mobilya gebze kocaeli", cumulative_file=output)
            scraper.results = [{"name": "İşletme", "phone": "+905321234567"}]
            scraper.save_to_csv()
            with open(output, newline="", encoding="utf-8-sig") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Phone 1 - Value"], "+905321234567")


if __name__ == "__main__":
    unittest.main()
