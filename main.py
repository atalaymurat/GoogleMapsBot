from scraper import GoogleMapsScraper


def main():
    searches = [
        {
            "keyword": "mutfak imalat",
            "district": "tuzla",
            "city": "istanbul",
            "max_results": 15,
        },
        {
            "keyword": "mobilya imalat",
            "district": "kadikoy",
            "city": "istanbul",
            "max_results": 15,
        },
        {
            "keyword": "mobilya imalat",
            "district": "uskudar",
            "city": "istanbul",
            "max_results": 15,
        },
    ]
    cumulative_file = "google_contacts_cumulative.csv"

    for search in searches:
        query = f"{search['keyword']} {search['district']} {search['city']}"
        print(f"\n{'=' * 60}")
        print(f"Arama: {query}")
        print(f"{'=' * 60}")

        scraper = GoogleMapsScraper(
            query,
            search['max_results'],
            cumulative_file,
            city=search['city'],
            region=search['district']
        )
        result_count = scraper.scrape()
        print(f"Arama tamamlandı: {result_count} yeni kayıt")

    print(f"\n{'=' * 60}")
    print(f"Tüm aramalar tamamlandı! Sonuçlar: {cumulative_file}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
