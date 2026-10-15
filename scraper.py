import csv
import hashlib
import logging
import os
import re
import time
import unicodedata
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager


logger = logging.getLogger(__name__)

MAX_GENERATED_SEARCH_QUERIES = 20
MAX_STAGNANT_SCROLLS = 3
MAX_SCROLL_ATTEMPTS = 50
RESULT_CHANGE_TIMEOUT = 5

CITY_NAMES = {
    "istanbul": "Istanbul",
    "ankara": "Ankara",
    "izmir": "Izmir",
    "bursa": "Bursa",
    "antalya": "Antalya",
    "konya": "Konya",
    "adana": "Adana",
    "mersin": "Mersin",
    "gaziantep": "Gaziantep",
    "sanliurfa": "Şanlıurfa",
    "kocaeli": "Kocaeli",
    "tekirdag": "Tekirdağ",
    "kayseri": "Kayseri",
}

CONTACT_HEADERS = [
    'Name Prefix', 'First Name', 'Middle Name', 'Last Name', 'Name Suffix',
    'Phonetic First Name', 'Phonetic Middle Name', 'Phonetic Last Name', 'Nickname',
    'File As', 'E-mail 1 - Label', 'E-mail 1 - Value',
    'Phone 1 - Label', 'Phone 1 - Value',
    'Address 1 - Label', 'Address 1 - Country', 'Address 1 - Street',
    'Address 1 - Extended Address', 'Address 1 - City', 'Address 1 - Region',
    'Address 1 - Postal Code', 'Address 1 - PO Box',
    'Organization Name', 'Organization Title', 'Organization Department',
    'Birthday', 'Event 1 - Label', 'Event 1 - Value',
    'Relation 1 - Label', 'Relation 1 - Value',
    'Website 1 - Label', 'Website 1 - Value',
    'Custom Field 1 - Label', 'Custom Field 1 - Value', 'Notes', 'Labels'
]


def normalize_mobile_phone(value):
    """Return a Turkish mobile phone in Google Contacts format, or None."""
    digits = re.sub(r'\D', '', value)
    if digits.startswith('0090'):
        digits = digits[4:]
    elif digits.startswith('90') and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith('0') and len(digits) == 11:
        digits = digits[1:]
    if re.fullmatch(r'5\d{9}', digits):
        return f'+90{digits}'
    return None


def normalize_location_key(value):
    folded = value.casefold().replace('ı', 'i')
    return ''.join(
        character for character in unicodedata.normalize('NFKD', folded)
        if not unicodedata.combining(character)
    )


def extract_category_label(card_text, business_name=None):
    """Extract a category only when Maps separates it from adjacent card text."""
    for line in card_text.splitlines():
        parts = re.split(r'\s*[·•]\s*', line.strip())
        if len(parts) < 2:
            continue
        for part in parts:
            candidate = part.strip()
            if not candidate:
                continue
            if (business_name
                    and normalize_location_key(candidate)
                    == normalize_location_key(business_name)):
                continue
            if (any(character.isdigit() for character in candidate)
                    and not any(character.isalpha() for character in candidate)):
                continue
            return candidate
    return None


def build_search_queries(search_keywords, expand=False):
    """Keep original terms first, then add a bounded set of useful variants."""
    originals = []
    seen = set()
    for keyword in search_keywords:
        cleaned = keyword.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            originals.append(cleaned)
            seen.add(key)

    if not expand:
        return originals

    generated = []
    generated_keys = set()

    def add_variant(query):
        key = query.casefold()
        if (len(generated) < MAX_GENERATED_SEARCH_QUERIES
                and key not in seen and key not in generated_keys):
            generated.append(query)
            generated_keys.add(key)

    for index, first in enumerate(originals):
        for second in originals[index + 1:]:
            add_variant(f"{first} {second}")

    variants_by_term = {
        "mobilya": (
            "mobilya üreticisi",
            "mobilya imalatı",
            "özel üretim mobilya",
            "mobilya atölyesi"
        ),
        "mutfak": (
            "mutfak dolabı imalatı",
            "özel ölçü mutfak dolabı"
        ),
        "dolap": ("dolap imalatı", "özel ölçü dolap"),
        "marangoz": ("marangoz atölyesi", "özel üretim marangoz"),
        "mdf": ("MDF kesim", "MDF ebatlama"),
        "cnc": ("CNC ahşap kesim",),
        "ebatlama": ("MDF ebatlama",)
    }
    for keyword in originals:
        normalized = normalize_location_key(keyword)
        for term, variants in variants_by_term.items():
            if term in normalized:
                for variant in variants:
                    add_variant(variant)

    return originals + generated[:MAX_GENERATED_SEARCH_QUERIES]


class GoogleMapsScraper:
    def __init__(
        self,
        search_query: str,
        max_results: int = 50,
        cumulative_file: str = None,
        city: str = None,
        region: str = None,
        on_result=None,
        on_event=None
    ):
        self.search_query = search_query
        self.max_results = max_results
        self.results = []
        # Kümülatif dosya adı belirtilmediyse zaman damgalı oluştur
        self.output_file = cumulative_file if cumulative_file else f"google_contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        parsed_location = self.parse_location(search_query)
        self.city = (
            CITY_NAMES.get(normalize_location_key(city), city)
            if city else parsed_location[0]
        )
        self.region = region.capitalize() if region is not None else parsed_location[1]
        self.on_result = on_result
        self.on_event = on_event
        self.observed_keys = set()
        self.existing_phones = self.load_existing_phones()

    def emit_event(self, message, level="INFO"):
        if self.on_event is not None:
            self.on_event({
                "message": message,
                "level": level,
                "observed_at": datetime.now().isoformat()
            })

    def parse_location(self, search_query):
        """Arama kelimesinden şehir ve ilçe bilgisini çıkar"""
        words = search_query.split()
        city = ""
        region = ""

        for index, word in enumerate(words):
            city_key = normalize_location_key(word)
            if city_key in CITY_NAMES:
                city = CITY_NAMES[city_key]
                if index > 0:
                    region = words[index - 1].capitalize()
                break

        return city, region

    def load_existing_phones(self):
        """Mevcut CSV dosyasından telefon numaralarını yükle"""
        existing = set()
        if os.path.exists(self.output_file):
            if os.path.getsize(self.output_file) == 0:
                return existing
            with open(self.output_file, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or 'Phone 1 - Value' not in reader.fieldnames:
                    raise ValueError(
                        f"CSV başlığında 'Phone 1 - Value' sütunu yok: {self.output_file}"
                    )
                for row in reader:
                    phone = normalize_mobile_phone(row.get('Phone 1 - Value') or '')
                    if phone:
                        existing.add(phone)
        return existing

    def scrape(self):
        self.emit_event("Chrome WebDriver başlatılıyor.")
        # Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Background çalışması için
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # Tarayıcıyı başlat (webdriver-manager ile otomatik driver yükleme)
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        try:
            # Google Maps'e git
            self.emit_event("https://www.google.com/maps açılıyor.")
            driver.get("https://www.google.com/maps")
            time.sleep(3)

            # Arama kutusunu bul ve arama yap (birden fazla selector denemesi)
            search_box = None
            selectors = [
                'input[aria-label="Ara Google Maps"]',
                'input[name="q"]',
                '#searchboxinput',
                'input[aria-label*="Search"]'
            ]

            for selector in selectors:
                try:
                    search_box = driver.find_element(By.CSS_SELECTOR, selector)
                    if search_box:
                        break
                except Exception:
                    continue

            if not search_box:
                raise Exception("Arama kutusu bulunamadı")

            self.emit_event(f'Sorgu gönderiliyor: "{self.search_query}"')
            search_box.send_keys(self.search_query)
            search_box.send_keys(Keys.RETURN)

            # Sonuçların yüklenmesini bekle
            self.emit_event("Google Maps sonuçları bekleniyor.")
            time.sleep(3)
            self.emit_event("Sonuç kartları taranmaya başladı.")

            # Sonuçları topla
            collected_count = 0
            stagnant_scrolls = 0
            scroll_attempts = 0
            seen_result_count = 0
            no_mobile_count = 0
            duplicate_phone_count = 0
            end_reason = "scroll_limit"

            while (collected_count < self.max_results
                   and scroll_attempts < MAX_SCROLL_ATTEMPTS):
                # Mevcut sonuçları extract et
                new_results = self.extract_results(driver)
                iteration_observations = 0
                for result in new_results:
                    if self._process_observed_result(result):
                        iteration_observations += 1
                        seen_result_count += 1
                        if result.get("collection_status") == "no_mobile":
                            no_mobile_count += 1
                        elif result.get("collection_status") == "duplicate_phone":
                            duplicate_phone_count += 1

                if iteration_observations:
                    self.emit_event(
                        f"Sayfada {len(new_results)} kart; "
                        f"bu turda {iteration_observations} yeni kart; "
                        f"toplam {seen_result_count} farklı kart görüldü."
                    )
                collected_count = len(self.results)
                if collected_count >= self.max_results:
                    end_reason = "result_limit"
                    break

                previous_signature = self._result_signature(new_results)
                scroll_state = self.scroll_results_panel(driver)
                scroll_attempts += 1
                self.emit_event(
                    "Google Maps sonuç paneli kaydırıldı "
                    f"({scroll_state['container']}; tur {scroll_attempts}/"
                    f"{MAX_SCROLL_ATTEMPTS})."
                )
                if self.wait_for_result_change(driver, previous_signature):
                    stagnant_scrolls = 0
                    continue

                stagnant_scrolls += 1
                self.emit_event(
                    f"Kaydırma sonrası yeni kart görünmedi "
                    f"({stagnant_scrolls}/{MAX_STAGNANT_SCROLLS}).",
                    "WARN"
                )
                if stagnant_scrolls >= MAX_STAGNANT_SCROLLS:
                    end_reason = "no_new_cards"
                    break

        finally:
            # Tarayıcıyı kapat
            driver.quit()

        # CSV'ye kaydet
        self.emit_event(
            f"CSV'ye {len(self.results)} benzersiz telefonlu kayıt yazılıyor."
        )
        self.save_to_csv()
        self.emit_event(
            f'Sorgu tamamlandı: "{self.search_query}" — '
            f"{seen_result_count} kart incelendi, {len(self.results)} kayıt eklendi; "
            f"{no_mobile_count} telefonsuz, {duplicate_phone_count} tekrar telefon; "
            f"bitirme nedeni: {end_reason}."
        )
        return len(self.results)

    @staticmethod
    def _result_signature(results):
        return tuple(
            (result.get("place_url") or "", result.get("name") or "",
             result.get("card_text") or "")
            for result in results
        )

    @staticmethod
    def scroll_results_panel(driver):
        """Scroll Maps' feed (or a scrollable card ancestor) before page fallback."""
        state = driver.execute_script("""
            const feed = document.querySelector('div[role="feed"]');
            const cards = document.querySelectorAll(
                'div[role="article"], div[class*="section-result"], a[href*="/maps/place/"]'
            );
            let target = feed;
            if (!target) {
                let node = cards.length ? cards[0].parentElement : null;
                while (node && node !== document.body) {
                    const style = window.getComputedStyle(node);
                    if (node.scrollHeight > node.clientHeight + 2 &&
                        /(auto|scroll)/.test(style.overflowY)) {
                        target = node;
                        break;
                    }
                    node = node.parentElement;
                }
            }
            if (target) {
                const before = target.scrollTop;
                target.scrollTop = Math.min(
                    target.scrollHeight,
                    before + Math.max(target.clientHeight * 0.8, 700)
                );
                return {
                    container: feed ? 'results-feed' : 'results-card-container',
                    scrollTop: target.scrollTop,
                    maxScrollTop: Math.max(0, target.scrollHeight - target.clientHeight)
                };
            }
            window.scrollBy(0, Math.max(window.innerHeight * 0.8, 700));
            return {container: 'window-fallback', scrollTop: window.scrollY, maxScrollTop: 0};
        """)
        if not isinstance(state, dict):
            raise RuntimeError("Google Maps sonuç paneli kaydırma durumu okunamadı")
        return state

    def wait_for_result_change(self, driver, previous_signature):
        try:
            WebDriverWait(
                driver, RESULT_CHANGE_TIMEOUT, poll_frequency=0.5
            ).until(
                lambda current_driver: self._result_signature(
                    self.extract_results(current_driver)
                ) != previous_signature
            )
            return True
        except TimeoutException:
            return False

    def _process_observed_result(self, result):
        identity = result.get('place_url') or (
            f"{result['name']}\n{result['card_text']}"
        )
        observation_key = hashlib.sha256(
            identity.casefold().encode('utf-8')
        ).hexdigest()
        if observation_key in self.observed_keys:
            return False
        self.observed_keys.add(observation_key)

        phone = result.get('phone')
        if not phone:
            result['collection_status'] = 'no_mobile'
        elif phone in self.existing_phones:
            result['collection_status'] = 'duplicate_phone'
        elif len(self.results) >= self.max_results:
            result['collection_status'] = 'limit_reached'
        else:
            result['collection_status'] = 'saved'
            self.results.append(result)
            self.existing_phones.add(phone)

        if self.on_result is not None:
            self.on_result({
                **result,
                'search_query': self.search_query,
                'observed_at': datetime.now().isoformat()
            })
        return True

    def extract_results(self, driver):
        results = []

        result_cards = driver.find_elements(By.CSS_SELECTOR, 'div[role="article"]')
        if not result_cards:
            result_cards = driver.find_elements(By.CSS_SELECTOR, 'div[class*="section-result"]')
        if not result_cards:
            result_cards = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]')

        for card in result_cards:
            try:
                name = None
                for selector in (
                    'h3',
                    'div[class*="fontHeadline"]',
                    'div[class*="title"]',
                    'span[class*="fontHeadline"]'
                ):
                    try:
                        name = card.find_element(By.CSS_SELECTOR, selector).text
                        if name:
                            break
                    except Exception:
                        continue

                phone_matches = re.findall(
                    r'(?<!\d)(?:(?:\+|00)?90[\s().-]*)?0?5(?:[\s().-]*\d){9}(?!\d)',
                    card.text
                )
                phone = next(
                    (normalized for match in phone_matches
                     if (normalized := normalize_mobile_phone(match))),
                    None
                )
                card_text = card.text.strip()
                if not name and card_text:
                    name = next(
                        (line.strip() for line in card_text.splitlines()
                         if line.strip()),
                        None
                    )
                if name:
                    card_text = card.text.strip()
                    place_url = None
                    try:
                        place_url = card.get_attribute('href')
                        if not place_url:
                            place_url = card.find_element(
                                By.CSS_SELECTOR, 'a[href*="/maps/place/"]'
                            ).get_attribute('href')
                    except Exception:
                        logger.debug("Maps kartında yer bağlantısı bulunamadı",
                                     exc_info=True)
                    results.append({
                        'name': name.strip(),
                        'phone': phone,
                        'card_text': card_text[:1200],
                        'category_label': extract_category_label(
                            card_text, name.strip()
                        ),
                        'place_url': place_url,
                        'sponsored': bool(re.search(
                            r'\b(?:sponsored|sponsorlu)\b',
                            card_text,
                            re.IGNORECASE
                        ))
                    })
            except Exception:
                logger.exception("Google Maps kartı okunamadı")

        return results

    def save_to_csv(self):
        self.existing_phones = self.load_existing_phones()
        unique_results = []
        for result in self.results:
            phone = normalize_mobile_phone(result.get('phone') or '')
            if not phone or phone in self.existing_phones:
                continue
            result['phone'] = phone
            self.existing_phones.add(phone)
            unique_results.append(result)
        self.results = unique_results

        file_exists = os.path.exists(self.output_file)
        write_header = not file_exists or os.path.getsize(self.output_file) == 0

        with open(self.output_file, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(CONTACT_HEADERS)

            for result in self.results:
                row = [''] * len(CONTACT_HEADERS)
                row[1] = result['name']
                row[12] = 'Mobile'
                row[13] = result['phone']
                row[15] = 'Turkey'
                row[18] = self.city
                row[19] = self.region
                if result.get('category_label'):
                    row[34] = (
                        f"Google Maps kategorisi: {result['category_label']}"
                    )
                row[35] = 'Maps'
                writer.writerow(row)

        logger.info("%s sonuç %s dosyasına eklendi.", len(self.results), self.output_file)
