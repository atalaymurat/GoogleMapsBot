from flask import Flask, request, jsonify, render_template, send_file
import threading
import queue
import time
import os
import json
import logging
import platform
import subprocess
import urllib.request
from datetime import datetime
from scraper import GoogleMapsScraper, build_search_queries
from scraper import normalize_location_key

app = Flask(__name__, template_folder='templates')
logger = logging.getLogger(__name__)
state_lock = threading.RLock()
APP_DIR = os.path.dirname(os.path.abspath(__file__))
# App data and generated CSV files stay beside app.py, regardless of the
# current working directory or the user's LOCALAPPDATA setting.
APP_DATA_DIR = APP_DIR

# Anahtar kelime geçmişi dosyası
KEYWORDS_FILE = os.path.join(APP_DATA_DIR, 'keywords_history.json')

# Görev geçmişi dosyası
TASKS_FILE = os.path.join(APP_DATA_DIR, 'tasks_history.json')

def load_tasks_history():
    """Görev geçmişini yükle"""
    if os.path.exists(TASKS_FILE):
        try:
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
                if not isinstance(history, dict):
                    raise ValueError("Görev geçmişi JSON nesnesi olmalı")
                return history
        except (OSError, json.JSONDecodeError, ValueError):
            logger.exception("Görev geçmişi yüklenemedi: %s", TASKS_FILE)
            raise
    return {}

def save_tasks_history():
    """Görev geçmişini kaydet"""
    temporary_file = f"{TASKS_FILE}.tmp"
    with state_lock:
        with open(temporary_file, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        os.replace(temporary_file, TASKS_FILE)

def load_keywords_history():
    """Anahtar kelime geçmişini yükle"""
    if os.path.exists(KEYWORDS_FILE):
        try:
            with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
                if not isinstance(history, list) or not all(
                    isinstance(item, str) for item in history
                ):
                    raise ValueError("Anahtar kelime geçmişi metin listesi olmalı")
                return history
        except (OSError, json.JSONDecodeError, ValueError):
            logger.exception("Anahtar kelime geçmişi yüklenemedi: %s", KEYWORDS_FILE)
            raise
    return []

def save_keywords_history(keywords):
    """Anahtar kelime geçmişini kaydet"""
    temporary_file = f"{KEYWORDS_FILE}.tmp"
    with state_lock:
        history = load_keywords_history()
        for keyword in keywords:
            if keyword not in history:
                history.append(keyword)
        with open(temporary_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        os.replace(temporary_file, KEYWORDS_FILE)

# İlçe listeleri: desteklenen şehirler için her ilçeyi bir kez içerir.
TURKEY_DISTRICTS = {
    "istanbul": [
        "adalar", "arnavutkoy", "atasehir", "avcilar", "bagcilar",
        "bahcelievler", "bakirkoy", "basaksehir", "bayrampasa", "besiktas",
        "beykoz", "beylikduzu", "beyoglu", "buyukcekmece", "catalca",
        "cekmekoy", "esenler", "esenyurt", "eyupsultan", "fatih",
        "gaziosmanpasa", "gungoren", "kadikoy", "kagithane", "kartal",
        "kucukcekmece", "maltepe", "pendik", "sancaktepe", "sariyer",
        "sile", "silivri", "sultanbeyli", "sultangazi", "sisli", "tuzla",
        "umraniye", "uskudar", "zeytinburnu"
    ],
    "ankara": [
        "akyurt", "altindag", "ayas", "bala", "beypazari",
        "camlidere", "cankaya", "cubuk", "elmadag", "etimesgut",
        "evren", "golbasi", "gudul", "haymana", "kahramankazan",
        "kalecik", "kecioren", "kizilcahamam", "mamak", "nallihan",
        "polatli", "pursaklar", "sincan", "sereflikochisar", "yenimahalle"
    ],
    "izmir": [
        "aliaga", "balcova", "bayindir", "bayrakli", "bergama",
        "beydag", "bornova", "buca", "cesme", "cigli", "dikili",
        "foca", "gaziemir", "guzelbahce", "karabaglar", "karaburun",
        "karsiyaka", "kemalpasa", "kinik", "kiraz", "konak",
        "menderes", "menemen", "narlidere", "odemis", "seferihisar",
        "selcuk", "tire", "torbali", "urla"
    ],
    "kocaeli": [
        "izmit", "gebze", "golcuk", "karamursel", "derince",
        "kandira", "basiskele", "kartepe", "cayirova", "dilovasi",
        "darica", "korfez"
    ],
    "tekirdag": [
        "suleymanpasa", "corlu", "cerkezkoy", "kapakli", "ergene",
        "malkara", "saray", "marmaraereglisi", "hayrabolu", "sarkoy",
        "muratli"
    ],
    "antalya": [
        "muratpasa", "kepez", "konyaalti", "aksu", "dosemealti",
        "serik", "manavgat", "alanya", "kas", "demre", "finike",
        "kumluca", "elmali", "korkuteli", "kemer", "gazipasa",
        "ibradi", "akseki", "gundogmus"
    ],
    "bursa": [
        "buyukorhan", "gemlik", "gursu", "harmancik", "inegol",
        "iznik", "karacabey", "keles", "kestel", "mudanya",
        "mustafakemalpasa", "nilufer", "orhaneli", "orhangazi",
        "osmangazi", "yenisehir", "yildirim"
    ],
    "kayseri": [
        "akkisla", "bunyan", "develi", "felahiye", "hacilar",
        "incesu", "kocasinan", "melikgazi", "ozvatan", "pinarbasi",
        "sarioglan", "sariz", "talas", "tomarza", "yahyali",
        "yesilhisar"
    ]
}


def _get_port_listener_pid(port):
    result = subprocess.run(
        ["netstat.exe", "-ano", "-p", "tcp"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5
    )
    for line in result.stdout.splitlines():
        fields = line.split()
        if (len(fields) >= 5 and fields[0].upper() == "TCP"
                and fields[1] == f"127.0.0.1:{port}"
                and fields[3].upper() == "LISTENING"):
            return int(fields[4])
    return None


def _is_this_app_instance():
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:5000/api/cities", timeout=2
        ) as response:
            city_data = json.load(response)
        with urllib.request.urlopen(
            "http://127.0.0.1:5000/", timeout=2
        ) as response:
            page = response.read().decode("utf-8")
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError
    ):
        return False

    return (
        city_data == {'cities': list(TURKEY_DISTRICTS)}
        and "<title>Google Maps Scraper - Yönetim Paneli</title>" in page
    )


def _terminate_process_tree(pid):
    subprocess.run(
        ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5
    )


def close_existing_instance():
    if platform.system() != "Windows":
        return

    pid = _get_port_listener_pid(5000)
    if pid is None:
        return
    if not _is_this_app_instance():
        raise RuntimeError(
            "127.0.0.1:5000 başka bir uygulama tarafından kullanılıyor; "
            "bu işlem güvenlik için kapatılmadı."
        )

    _terminate_process_tree(pid)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _get_port_listener_pid(5000) is None:
            print(f"Önceki uygulama örneği kapatıldı (PID {pid}).")
            return
        time.sleep(0.1)
    raise RuntimeError(
        f"Önceki uygulama örneği (PID {pid}) kapatılamadı; "
        "yeni sunucu başlatılmadı."
    )


if __name__ == '__main__':
    close_existing_instance()


# Görev kuyruğu ve durum takibi
task_queue = queue.Queue()
tasks = load_tasks_history()
task_counter = max(
    (int(task_id[5:]) for task_id in tasks
     if task_id.startswith('task_') and task_id[5:].isdigit()),
    default=0
)


def task_worker():
    """Background task worker"""
    while True:
        task_id, task_data = task_queue.get()
        if task_id is None:
            task_queue.task_done()
            break

        try:
            with state_lock:
                tasks[task_id].update({
                    'status': 'running',
                    'started_at': datetime.now().isoformat(),
                    'error': None,
                    'errors': [],
                    'live_results': [],
                    'live_result_count': 0,
                    'sponsored_count': 0,
                    'observed_count': 0,
                    'category_counts': {},
                    'uncategorized_category_count': 0,
                    'no_mobile_count': 0,
                    'duplicate_phone_count': 0,
                    'terminal_events': [],
                    'terminal_event_count': 0
                })

            def report_terminal(message, level="INFO"):
                with state_lock:
                    task = tasks[task_id]
                    events = task.setdefault('terminal_events', [])
                    task['terminal_event_count'] = (
                        task.get('terminal_event_count', 0) + 1
                    )
                    events.append({
                        'id': f"{task_id}-log-{task['terminal_event_count']}",
                        'timestamp': datetime.now().isoformat(),
                        'level': level,
                        'message': message
                    })
                    task['terminal_events'] = events[-250:]

            report_terminal("Görev kuyruğundan alındı; hazırlık başlıyor.")
            save_tasks_history()

            city = task_data['city'].lower()
            search_keywords = task_data.get(
                'search_queries', task_data['search_keywords']
            )
            cumulative_filename = task_data.get(
                'cumulative_file', 'google_contacts_cumulative.csv'
            )
            if (not isinstance(cumulative_filename, str)
                    or cumulative_filename != os.path.basename(cumulative_filename)
                    or not cumulative_filename.lower().endswith('.csv')):
                raise ValueError("Görev geçmişinde geçersiz CSV dosya adı")
            cumulative_file = os.path.join(APP_DATA_DIR, cumulative_filename)
            max_results = task_data.get('max_results', 50)
            generated_queries = [
                query for query in search_keywords
                if query.casefold() not in {
                    keyword.casefold()
                    for keyword in task_data['search_keywords']
                }
            ]
            report_terminal(
                f"{len(search_keywords)} arama terimi planlandı; "
                f"{len(generated_queries)} varyasyon sorgusu."
            )
            if generated_queries:
                report_terminal(
                    "Ek sorgular: " + " | ".join(generated_queries)
                )

            if task_data.get('districts'):
                districts = list(dict.fromkeys(task_data['districts']))
            else:
                districts = list(dict.fromkeys(TURKEY_DISTRICTS.get(city, [city])))

            total_results = 0
            completed_searches = 0
            failed_searches = 0
            total_searches = len(districts) * len(search_keywords)
            if total_searches == 0:
                raise ValueError("Görevde çalıştırılacak arama yok")

            with state_lock:
                tasks[task_id].update({
                    'total_searches': total_searches,
                    'completed_searches': 0,
                    'failed_searches': 0,
                    'total_results': 0
                })
            save_tasks_history()

            for district in districts:
                for keyword in search_keywords:
                    search_query = f"{keyword} {district} {city}"
                    report_terminal(f'Yeni sorgu: "{search_query}"')
                    with state_lock:
                        tasks[task_id]['current_search'] = search_query
                    save_tasks_history()

                    result_count = 0
                    search_error = False
                    try:
                        def report_live_result(result):
                            live_result = {
                                'name': result['name'],
                                'phone': result.get('phone'),
                                'card_text': result.get('card_text', ''),
                                'category_label': result.get('category_label'),
                                'place_url': result.get('place_url'),
                                'sponsored': result.get('sponsored', False),
                                'collection_status': result['collection_status'],
                                'search_query': result['search_query'],
                                'observed_at': result['observed_at']
                            }
                            with state_lock:
                                task = tasks[task_id]
                                task['observed_count'] = (
                                    task.get('observed_count', 0) + 1
                                )
                                live_result['observation_id'] = (
                                    f"{task_id}-{task['observed_count']}"
                                )
                                task.setdefault('live_results', []).append(live_result)
                                task['live_results'] = task['live_results'][-100:]
                                category_label = live_result['category_label']
                                if category_label:
                                    category_counts = task.setdefault(
                                        'category_counts', {}
                                    )
                                    normalized_category = normalize_location_key(
                                        category_label
                                    )
                                    stored_label = next(
                                        (
                                            label for label in category_counts
                                            if normalize_location_key(label)
                                            == normalized_category
                                        ),
                                        category_label
                                    )
                                    category_counts[stored_label] = (
                                        category_counts.get(stored_label, 0) + 1
                                    )
                                else:
                                    task['uncategorized_category_count'] = (
                                        task.get(
                                            'uncategorized_category_count', 0
                                        ) + 1
                                    )
                                status_labels = {
                                    'saved': 'KAYDEDİLDİ',
                                    'no_mobile': 'CEP TELEFONU YOK',
                                    'duplicate_phone': 'TEKRAR TELEFON',
                                    'limit_reached': 'SONUÇ LİMİTİ',
                                    'excluded_category': 'KATEGORİ ETİKETİ NEDENİYLE ATLANDI'
                                }
                                phone_info = live_result['phone'] or 'cep telefonu bulunamadı'
                                label = status_labels.get(
                                    live_result['collection_status'],
                                    live_result['collection_status'].upper()
                                )
                                report_terminal(
                                    f"[{label}] {live_result['name']} | {phone_info}"
                                    + (
                                        " | SPONSORLU ETİKETİ"
                                        if live_result['sponsored'] else ""
                                    ),
                                    (
                                        'SUCCESS'
                                        if live_result['collection_status'] == 'saved'
                                        else 'WARN'
                                    )
                                )
                                if live_result['card_text']:
                                    report_terminal(
                                        "Kart metni:\n"
                                        + live_result['card_text'][:600]
                                    )
                                if live_result['collection_status'] == 'saved':
                                    task['live_result_count'] = (
                                        task.get('live_result_count', 0) + 1
                                    )
                                elif live_result['collection_status'] == 'no_mobile':
                                    task['no_mobile_count'] = (
                                        task.get('no_mobile_count', 0) + 1
                                    )
                                elif live_result['collection_status'] == 'duplicate_phone':
                                    task['duplicate_phone_count'] = (
                                        task.get('duplicate_phone_count', 0) + 1
                                    )
                                if live_result['sponsored']:
                                    task['sponsored_count'] = (
                                        task.get('sponsored_count', 0) + 1
                                    )

                        scraper = GoogleMapsScraper(
                            search_query=search_query,
                            max_results=max_results,
                            cumulative_file=cumulative_file,
                            city=city,
                            region=district,
                            on_result=report_live_result,
                            on_event=lambda event: report_terminal(
                                event['message'], event.get('level', 'INFO')
                            ),
                            excluded_category_labels=task_data.get(
                                'excluded_category_labels', []
                            )
                        )
                        result_count = scraper.scrape()
                        total_results += result_count
                    except Exception as e:
                        search_error = True
                        failed_searches += 1
                        error_message = f"{search_query}: {e}"
                        with state_lock:
                            tasks[task_id].setdefault('errors', []).append(error_message)
                            tasks[task_id]['error'] = error_message
                        report_terminal(
                            f'Sorgu başarısız: "{search_query}" — {e}',
                            "ERROR"
                        )
                        logger.exception("Arama başarısız: %s", search_query)
                    finally:
                        completed_searches += 1
                        search_result = 'hata' if search_error else f'{result_count} sonuç'
                        with state_lock:
                            tasks[task_id].update({
                                'completed_searches': completed_searches,
                                'failed_searches': failed_searches,
                                'total_results': total_results,
                                'last_result': f"{search_query}: {search_result}"
                            })
                        if not search_error:
                            report_terminal(
                                f'Sorgu adımı bitti: "{search_query}" — '
                                f"{result_count} yeni telefonlu kayıt."
                            )
                        save_tasks_history()

                    if completed_searches < total_searches:
                        time.sleep(2)

            status = (
                'failed' if failed_searches == total_searches and total_searches
                else 'completed_with_errors' if failed_searches
                else 'completed'
            )
            with state_lock:
                tasks[task_id].update({
                    'status': status,
                    'completed_at': datetime.now().isoformat(),
                    'message': (
                        f"Tamamlandı: {total_results} sonuç; "
                        f"{failed_searches}/{total_searches} arama başarısız"
                    )
                })
            report_terminal(
                f"Görev tamamlandı: {total_results} kayıt, "
                f"{failed_searches}/{total_searches} sorgu hatalı.",
                "SUCCESS" if not failed_searches else "WARN"
            )
            save_tasks_history()

        except Exception as e:
            with state_lock:
                tasks[task_id].update({
                    'status': 'failed',
                    'error': str(e),
                    'completed_at': datetime.now().isoformat()
                })
            if 'report_terminal' in locals():
                report_terminal(f"Görev beklenmeyen hatayla durdu: {e}", "ERROR")
            save_tasks_history()
            logger.exception("Görev başarısız: %s", task_id)
        finally:
            task_queue.task_done()


# Background worker thread'ini başlat
worker_thread = threading.Thread(target=task_worker, daemon=True)
worker_thread.start()

interrupted_tasks = False
for saved_task_id, saved_task in tasks.items():
    if saved_task.get('status') == 'running':
        saved_task.update({
            'status': 'failed',
            'error': 'Uygulama yeniden başlatılırken görev kesildi.',
            'completed_at': datetime.now().isoformat()
        })
        interrupted_tasks = True
    elif saved_task.get('status') == 'pending':
        task_queue.put((saved_task_id, saved_task.get('data', {})))
if interrupted_tasks:
    save_tasks_history()


@app.route('/')
def index():
    """Ana sayfa"""
    return render_template('index.html')


@app.route('/api/tasks', methods=['POST'])
def create_task():
    """Yeni görev oluştur"""
    global task_counter
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'İstek gövdesi geçerli bir JSON nesnesi olmalı'}), 400

    city = data.get('city')
    if not isinstance(city, str) or normalize_location_key(city.strip()) not in TURKEY_DISTRICTS:
        return jsonify({'error': 'Geçerli bir şehir seçin'}), 400
    city = normalize_location_key(city.strip())

    raw_keywords = data.get('search_keywords')
    if not isinstance(raw_keywords, list) or not raw_keywords:
        return jsonify({'error': 'En az bir arama kelimesi gerekli'}), 400
    if not all(isinstance(keyword, str) and keyword.strip() for keyword in raw_keywords):
        return jsonify({'error': 'Arama kelimeleri boş olmayan metinler olmalı'}), 400
    search_keywords = list(dict.fromkeys(keyword.strip() for keyword in raw_keywords))

    expand_search_queries = data.get('expand_search_queries', False)
    if not isinstance(expand_search_queries, bool):
        return jsonify({
            'error': 'Arama kelimesi varyasyon seçeneği doğru/yanlış olmalı'
        }), 400
    search_queries = build_search_queries(
        search_keywords, expand=expand_search_queries
    )

    max_results = data.get('max_results', 50)
    if (isinstance(max_results, bool) or not isinstance(max_results, int)
            or not 10 <= max_results <= 100):
        return jsonify({'error': 'Maksimum sonuç sayısı 10 ile 100 arasında olmalı'}), 400

    cumulative_file = data.get('cumulative_file', 'google_contacts_cumulative.csv')
    if (not isinstance(cumulative_file, str) or not cumulative_file.strip()
            or cumulative_file != os.path.basename(cumulative_file)
            or '/' in cumulative_file or '\\' in cumulative_file
            or ':' in cumulative_file
            or not cumulative_file.lower().endswith('.csv')):
        return jsonify({'error': 'Çıktı dosyası yalnızca bir .csv dosya adı olmalı'}), 400
    cumulative_file = cumulative_file.strip()

    districts = data.get('districts')
    if districts is not None:
        if not isinstance(districts, list):
            return jsonify({'error': 'İlçeler liste biçiminde olmalı'}), 400
        city_districts = TURKEY_DISTRICTS[city]
        districts_by_casefold = {
            normalize_location_key(district): district for district in city_districts
        }
        if not all(
            isinstance(district, str)
            and normalize_location_key(district) in districts_by_casefold
            for district in districts
        ):
            return jsonify({'error': 'Seçilen ilçeler şehir için geçerli değil'}), 400
        districts = list(dict.fromkeys(
            districts_by_casefold[normalize_location_key(district)]
            for district in districts
        ))

    excluded_category_labels = data.get('excluded_category_labels', [])
    if (not isinstance(excluded_category_labels, list)
            or not all(
                isinstance(label, str) and label.strip()
                for label in excluded_category_labels
            )):
        return jsonify({
            'error': 'Hariç tutulacak kategori etiketleri metin listesi olmalı'
        }), 400
    excluded_category_labels = list(dict.fromkeys(
        label.strip() for label in excluded_category_labels
    ))

    task_data = {
        'city': city,
        'search_keywords': search_keywords,
        'search_queries': search_queries,
        'expand_search_queries': expand_search_queries,
        'cumulative_file': cumulative_file,
        'max_results': max_results,
        'districts': districts,
        'excluded_category_labels': excluded_category_labels
    }

    task_id = None
    try:
        save_keywords_history(search_keywords)
        with state_lock:
            task_counter += 1
            task_id = f"task_{task_counter}"
            tasks[task_id] = {
                'id': task_id,
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'data': task_data
            }
        save_tasks_history()
    except (OSError, ValueError) as error:
        if task_id is not None:
            with state_lock:
                tasks.pop(task_id, None)
        logger.exception("Yeni görev kaydedilemedi")
        return jsonify({
            'error': f"Görev dosyaya kaydedilemedi: {error}"
        }), 500

    task_queue.put((task_id, task_data))

    return jsonify({
        'task_id': task_id,
        'status': 'pending',
        'message': 'Görev kuyruğa eklendi',
        'search_query_count': len(search_queries),
        'generated_query_count': len(search_queries) - len(search_keywords)
    })


@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """Görev durumunu al"""
    with state_lock:
        task = dict(tasks[task_id]) if task_id in tasks else None
    if task is None:
        return jsonify({'error': 'Görev bulunamadı'}), 404
    return jsonify({
        'id': task['id'],
        'status': task['status'],
        'created_at': task.get('created_at'),
        'started_at': task.get('started_at'),
        'completed_at': task.get('completed_at'),
        'current_search': task.get('current_search'),
        'total_searches': task.get('total_searches'),
        'completed_searches': task.get('completed_searches'),
        'total_results': task.get('total_results'),
        'failed_searches': task.get('failed_searches'),
        'last_result': task.get('last_result'),
        'live_results': list(task.get('live_results', [])),
        'live_result_count': task.get('live_result_count', 0),
        'sponsored_count': task.get('sponsored_count', 0),
        'observed_count': task.get('observed_count', 0),
        'category_counts': dict(task.get('category_counts', {})),
        'uncategorized_category_count': task.get(
            'uncategorized_category_count', 0
        ),
        'no_mobile_count': task.get('no_mobile_count', 0),
        'duplicate_phone_count': task.get('duplicate_phone_count', 0),
        'terminal_events': list(task.get('terminal_events', [])),
        'terminal_event_count': task.get('terminal_event_count', 0),
        'error': task.get('error'),
        'errors': task.get('errors'),
        'message': task.get('message')
    })


@app.route('/api/tasks', methods=['GET'])
def list_tasks():
    """Tüm görevleri listele"""
    with state_lock:
        task_list = []
        for task in tasks.values():
            task_copy = dict(task)
            task_copy['live_results'] = list(task.get('live_results', []))
            task_copy['category_counts'] = dict(task.get('category_counts', {}))
            task_copy['terminal_events'] = list(task.get('terminal_events', []))
            task_list.append(task_copy)
    return jsonify(task_list)


@app.route('/api/districts/<city>', methods=['GET'])
def get_districts(city):
    """Şehrin ilçelerini al"""
    city_lower = city.lower()
    districts = TURKEY_DISTRICTS.get(city_lower, [])
    return jsonify({'city': city, 'districts': districts})


@app.route('/api/cities', methods=['GET'])
def get_cities():
    """Tüm şehirleri listele"""
    return jsonify({'cities': list(TURKEY_DISTRICTS.keys())})


@app.route('/api/keywords-history', methods=['GET'])
def get_keywords_history():
    """Anahtar kelime geçmişini al"""
    history = load_keywords_history()
    return jsonify({'keywords': history})


@app.route('/api/category-labels', methods=['GET'])
def get_category_labels():
    """Return category labels observed in saved task history."""
    labels = {}
    with state_lock:
        for task in tasks.values():
            for label in task.get('category_counts', {}):
                key = normalize_location_key(label)
                if key:
                    labels.setdefault(key, label)
    return jsonify({'labels': sorted(labels.values(), key=str.casefold)})


@app.route('/api/export', methods=['GET'])
def export_csv():
    """CSV dosyasını indir"""
    filename = request.args.get('filename', 'google_contacts_cumulative.csv')
    if (filename != os.path.basename(filename) or '/' in filename or '\\' in filename
            or ':' in filename
            or not filename.lower().endswith('.csv')):
        return jsonify({'error': 'Yalnızca geçerli bir CSV dosya adı indirilebilir'}), 400
    file_path = os.path.join(APP_DATA_DIR, filename)
    if not os.path.isfile(file_path):
        return jsonify({'error': 'Dosya bulunamadı'}), 404

    return send_file(
        file_path,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
