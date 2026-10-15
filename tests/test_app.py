import io
import json
import os
import queue
import tempfile
import unittest
from unittest.mock import patch

import app as app_module


class TaskApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.original_tasks = app_module.tasks
        self.original_queue = app_module.task_queue
        self.original_counter = app_module.task_counter
        app_module.tasks = {}
        app_module.task_queue = queue.Queue()
        app_module.task_counter = 0
        self.persistence_patches = (
            patch.object(app_module, "save_tasks_history"),
            patch.object(app_module, "save_keywords_history"),
        )
        for persistence_patch in self.persistence_patches:
            persistence_patch.start()

    def tearDown(self):
        for persistence_patch in self.persistence_patches:
            persistence_patch.stop()
        app_module.tasks = self.original_tasks
        app_module.task_queue = self.original_queue
        app_module.task_counter = self.original_counter

    def test_dashboard_contains_live_monitor_and_summary_cards(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Arama geri bildirimi".encode(), response.data)
        self.assertIn("GOOGLE MAPS SCRAPER / LIVE OUTPUT".encode(), response.data)
        self.assertIn("Sponsorlu etiketi görülen".encode(), response.data)
        self.assertIn("Kaydedilen işletme kategori etiketleri".encode(), response.data)

    def test_rejects_invalid_task_payloads_without_queueing(self):
        invalid_payloads = [
            None,
            {"city": "unknown", "search_keywords": ["wood"]},
            {"city": "istanbul", "search_keywords": [" "]},
            {"city": "istanbul", "search_keywords": ["wood"], "max_results": True},
            {"city": "istanbul", "search_keywords": ["wood"], "max_results": 101},
            {
                "city": "istanbul",
                "search_keywords": ["wood"],
                "cumulative_file": "..\\outside.csv",
            },
            {
                "city": "istanbul",
                "search_keywords": ["wood"],
                "cumulative_file": "C:outside.csv",
            },
            {
                "city": "istanbul",
                "search_keywords": ["wood"],
                "districts": ["not-a-district"],
            },
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post("/api/tasks", json=payload)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(app_module.task_queue.qsize(), 0)
        self.assertEqual(app_module.tasks, {})

    def test_accepts_valid_task_and_deduplicates_inputs(self):
        response = self.client.post("/api/tasks", json={
            "city": "İSTANBUL",
            "search_keywords": ["mobilya", " mobilya "],
            "districts": ["Üsküdar", "uskudar"],
            "max_results": 50,
        })
        self.assertEqual(response.status_code, 200)
        task = app_module.tasks["task_1"]
        self.assertEqual(task["data"]["city"], "istanbul")
        self.assertEqual(task["data"]["search_keywords"], ["mobilya"])
        self.assertEqual(task["data"]["districts"], ["uskudar"])
        self.assertEqual(app_module.task_queue.qsize(), 1)

    def test_expands_search_terms_into_separate_bounded_queries(self):
        response = self.client.post("/api/tasks", json={
            "city": "kocaeli",
            "districts": ["gebze"],
            "search_keywords": ["mobilya", "mutfak"],
            "expand_search_queries": True,
        })

        self.assertEqual(response.status_code, 200)
        task_data = app_module.tasks["task_1"]["data"]
        self.assertEqual(
            task_data["search_keywords"], ["mobilya", "mutfak"]
        )
        self.assertEqual(task_data["search_queries"][:2], ["mobilya", "mutfak"])
        self.assertIn("mobilya mutfak", task_data["search_queries"])
        self.assertLessEqual(
            response.get_json()["generated_query_count"], 20
        )
        self.assertEqual(
            response.get_json()["search_query_count"],
            len(task_data["search_queries"])
        )

    def test_rejects_non_boolean_search_variation_option(self):
        response = self.client.post("/api/tasks", json={
            "city": "istanbul",
            "search_keywords": ["mobilya"],
            "expand_search_queries": "yes"
        })
        self.assertEqual(response.status_code, 400)

    def test_kocaeli_districts_are_valid_and_do_not_include_corlu(self):
        response = self.client.get("/api/districts/kocaeli")
        districts = response.get_json()["districts"]
        self.assertEqual(len(districts), 12)
        self.assertEqual(len({district.casefold() for district in districts}), 12)
        self.assertIn("dilovasi", districts)
        self.assertIn("darica", districts)
        self.assertIn("korfez", districts)
        self.assertNotIn("corlu", districts)

    def test_city_district_lists_have_expected_unique_district_counts(self):
        expected_counts = {
            "istanbul": 39,
            "ankara": 25,
            "izmir": 30,
            "kocaeli": 12,
            "tekirdag": 11,
            "antalya": 19,
            "bursa": 17,
            "kayseri": 16,
        }
        self.assertEqual(set(app_module.TURKEY_DISTRICTS), set(expected_counts))
        for city, expected_count in expected_counts.items():
            with self.subTest(city=city):
                districts = app_module.TURKEY_DISTRICTS[city]
                self.assertEqual(len(districts), expected_count)
                self.assertEqual(
                    len({district.casefold() for district in districts}),
                    expected_count
                )

    def test_export_sends_csv_as_attachment_and_rejects_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = "export_test.csv"
            with open(
                os.path.join(directory, filename), "w", encoding="utf-8"
            ) as file:
                file.write("Name,Phone\n")
            with patch.object(app_module, "APP_DATA_DIR", directory):
                response = self.client.get(
                    "/api/export", query_string={"filename": filename}
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("attachment", response.headers["Content-Disposition"])
                self.assertEqual(response.data, b"Name,Phone\r\n")
                response.close()
                self.assertEqual(
                    self.client.get(
                        "/api/export", query_string={"filename": "..\\secret.csv"}
                    ).status_code,
                    400
                )
                self.assertEqual(
                    self.client.get(
                        "/api/export", query_string={"filename": "C:secret.csv"}
                    ).status_code,
                    400
                )

    def test_task_apis_include_live_result_snapshot(self):
        app_module.tasks["task_live"] = {
            "id": "task_live",
            "status": "running",
            "data": {"city": "kocaeli", "search_keywords": ["mobilya"]},
            "live_results": [{
                "name": "İşletme",
                "phone": "+905321234567",
                "sponsored": False
            }],
            "live_result_count": 1,
            "sponsored_count": 0,
            "category_counts": {"Mobilya İmalatçısı": 1},
            "uncategorized_category_count": 2,
            "terminal_events": [{
                "id": "task_live-log-1",
                "level": "INFO",
                "message": "Sorgu gönderiliyor"
            }]
        }

        list_response = self.client.get("/api/tasks")
        detail_response = self.client.get("/api/tasks/task_live")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            list_response.get_json()[0]["live_results"][0]["phone"],
            "+905321234567"
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(
            detail_response.get_json()["live_result_count"], 1
        )
        self.assertEqual(
            detail_response.get_json()["category_counts"],
            {"Mobilya İmalatçısı": 1}
        )
        self.assertEqual(
            detail_response.get_json()["uncategorized_category_count"], 2
        )
        self.assertEqual(
            detail_response.get_json()["terminal_events"][0]["message"],
            "Sorgu gönderiliyor"
        )


class TaskWorkerTests(unittest.TestCase):
    def run_worker(
        self, scraper_side_effect, districts, city="istanbul",
        search_queries=None
    ):
        task_data = {
            "city": city,
            "search_keywords": ["mobilya"],
            "districts": districts,
            "max_results": 10,
            "cumulative_file": "unused.csv",
        }
        if search_queries is not None:
            task_data["search_queries"] = search_queries
        test_queue = queue.Queue()
        test_queue.put(("task_test", task_data))
        test_queue.put((None, None))
        original_tasks = app_module.tasks
        original_queue = app_module.task_queue
        app_module.tasks = {
            "task_test": {"id": "task_test", "status": "pending"}
        }
        app_module.task_queue = test_queue
        try:
            with patch.object(app_module, "save_tasks_history"), \
                    patch.object(app_module.time, "sleep"), \
                    patch.object(app_module.logger, "exception"), \
                    patch.object(app_module, "GoogleMapsScraper",
                                 side_effect=scraper_side_effect) as scraper_mock:
                app_module.task_worker()
            return app_module.tasks["task_test"], scraper_mock.call_args_list
        finally:
            app_module.tasks = original_tasks
            app_module.task_queue = original_queue

    def test_reports_all_searches_failed_as_failed(self):
        task, scraper_calls = self.run_worker(
            RuntimeError("browser unavailable"), ["gebze"], city="kocaeli"
        )
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["completed_searches"], 1)
        self.assertEqual(task["failed_searches"], 1)
        self.assertIn("browser unavailable", task["error"])
        self.assertEqual(scraper_calls[0].kwargs["city"], "kocaeli")
        self.assertEqual(scraper_calls[0].kwargs["region"], "gebze")

    def test_reports_partial_search_failures(self):
        class SuccessfulScraper:
            def scrape(self):
                return 2

        def make_scraper(**kwargs):
            if kwargs["search_query"].startswith("mobilya derince"):
                raise RuntimeError("temporary failure")
            return SuccessfulScraper()

        task, _ = self.run_worker(make_scraper, ["tuzla", "derince"])
        self.assertEqual(task["status"], "completed_with_errors")
        self.assertEqual(task["completed_searches"], 2)
        self.assertEqual(task["failed_searches"], 1)
        self.assertEqual(task["total_results"], 2)
        self.assertEqual(len(task["errors"]), 1)

    def test_worker_runs_each_planned_variation_as_its_own_search(self):
        queries = []

        class SuccessfulScraper:
            def __init__(self, search_query, **_kwargs):
                queries.append(search_query)

            def scrape(self):
                return 1

        task, _ = self.run_worker(
            SuccessfulScraper,
            ["gebze"],
            city="kocaeli",
            search_queries=["mobilya", "mobilya üreticisi"]
        )

        self.assertEqual(queries, [
            "mobilya gebze kocaeli",
            "mobilya üreticisi gebze kocaeli"
        ])
        self.assertEqual(task["total_searches"], 2)
        self.assertEqual(task["completed_searches"], 2)

    def test_reports_live_results_and_sponsored_count(self):
        class SuccessfulScraper:
            def __init__(self, on_result, on_event, **kwargs):
                on_event({
                    "message": "Sonuç taraması başladı",
                    "level": "INFO"
                })
                on_result({
                    "name": "Sponsorlu İşletme",
                    "phone": "+905321234567",
                    "category_label": "Mobilya Üreticisi",
                    "card_text": "Sponsorlu İşletme\n0532 123 45 67",
                    "place_url": None,
                    "collection_status": "saved",
                    "sponsored": True,
                    "search_query": kwargs["search_query"],
                    "observed_at": "2026-10-15T12:00:00"
                })

            def scrape(self):
                return 1

        task, _ = self.run_worker(
            SuccessfulScraper, ["gebze"], city="kocaeli"
        )
        self.assertEqual(task["live_result_count"], 1)
        self.assertEqual(task["sponsored_count"], 1)
        self.assertEqual(task["live_results"][0]["name"], "Sponsorlu İşletme")
        self.assertTrue(task["live_results"][0]["sponsored"])
        self.assertEqual(
            task["live_results"][0]["category_label"], "Mobilya Üreticisi"
        )
        self.assertEqual(
            task["category_counts"], {"Mobilya Üreticisi": 1}
        )
        self.assertGreaterEqual(task["observed_count"], 1)
        self.assertTrue(any(
            "Sonuç taraması başladı" in event["message"]
            for event in task["terminal_events"]
        ))


class StartupInstanceTests(unittest.TestCase):
    def test_skips_shutdown_when_port_is_free(self):
        with patch.object(app_module, "_get_port_listener_pid", return_value=None), \
                patch.object(app_module.os, "kill") as kill:
            app_module.close_existing_instance()
        kill.assert_not_called()

    def test_closes_matching_running_instance(self):
        with patch.object(
            app_module, "_get_port_listener_pid", side_effect=[123, None]
        ), patch.object(
            app_module, "_is_this_app_instance", return_value=True
        ), patch.object(app_module, "_terminate_process_tree") as terminate:
            app_module.close_existing_instance()
        terminate.assert_called_once_with(123)

    def test_does_not_kill_an_unrelated_process_on_port(self):
        with patch.object(
            app_module, "_get_port_listener_pid", return_value=123
        ), patch.object(
            app_module, "_is_this_app_instance", return_value=False
        ), patch.object(app_module, "_terminate_process_tree") as terminate:
            with self.assertRaisesRegex(RuntimeError, "başka bir uygulama"):
                app_module.close_existing_instance()
        terminate.assert_not_called()

    def test_identifies_app_by_city_api_and_page_title(self):
        cities_response = io.BytesIO(json.dumps(
            {'cities': list(app_module.TURKEY_DISTRICTS)}
        ).encode())
        page_response = io.BytesIO(
            b"<title>Google Maps Scraper - Y\xc3\xb6netim Paneli</title>"
        )
        with patch.object(
            app_module.urllib.request, "urlopen",
            side_effect=[cities_response, page_response]
        ):
            self.assertTrue(app_module._is_this_app_instance())

        cities_response = io.BytesIO(json.dumps(
            {'cities': list(app_module.TURKEY_DISTRICTS)}
        ).encode())
        page_response = io.BytesIO(b"<title>Different application</title>")
        with patch.object(
            app_module.urllib.request, "urlopen",
            side_effect=[cities_response, page_response]
        ):
            self.assertFalse(app_module._is_this_app_instance())


if __name__ == "__main__":
    unittest.main()
