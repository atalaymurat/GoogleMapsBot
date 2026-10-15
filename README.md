# Google Maps Scraper - Web Paneli

Google Maps üzerinde işletme arayıp iletişim bilgilerini Google Contacts formatında toplayan web tabanlı araç.

## Özellikler

- ✅ Sadece mobile numaraları (5 ile başlayan) filtreler
- ✅ Numaraları +905xxxxxxxxx formatında kaydeder
- ✅ Bölgesel arama desteği (şehir/ilçe belirtebilirsiniz)
- ✅ Duplicate kontrolü (aynı numarayı tekrar kaydetmez)
- ✅ Google Contacts formatında CSV çıktısı
- ✅ Kümülatif dosya (tüm aramalar tek bir dosyada toplanır)
- ✅ "Maps" label'ı eklenir
- ✅ **Web yönetim paneli (Flask)**
- ✅ **Background task işleme**
- ✅ **Otomatik ilçe/mahalle araması**
- ✅ **Gerçek zamanlı ilerleme takibi**
- ✅ **Canlı sonuç akışı ve sponsorlu etiketi gözlemi**

## Kurulum ve çalıştırma

Aşağıdaki adımlar Windows PowerShell içindir. Bilgisayarınızda Python 3 ve
Google Chrome kurulu olmalıdır. İlk aramada Selenium, Chrome için gereken
WebDriver'ı internet üzerinden otomatik indirir.

### 1. Projeyi bilgisayarınıza alın

Git kuruluysa PowerShell'de:

```powershell
git clone https://github.com/atalaymurat/GoogleMapsBot.git
cd GoogleMapsBot
```

Alternatif olarak GitHub deposundaki **Code > Download ZIP** seçeneğiyle
projeyi indirip ZIP dosyasını çıkartın; ardından PowerShell'de proje klasörüne
geçin.

### 2. Python kurulumunu kontrol edin

```powershell
py --version
```

Python sürüm numarası görüntülenmelidir. `py` komutu bulunamazsa Python 3'ü
kurup terminali yeniden açın.

### 3. Sanal ortam oluşturup etkinleştirin

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Etkinleştirme engellenirse yalnızca mevcut PowerShell oturumu için şu komutu
çalıştırıp 3. adımdaki etkinleştirme komutunu yeniden deneyin:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 4. Gerekli paketleri yükleyin

```powershell
py -m pip install -r requirements.txt
```

### 5. Web panelini başlatın

```powershell
py app.py
```

Terminal penceresini açık bırakın ve tarayıcıda
http://127.0.0.1:5000 adresini açın. Uygulama yalnızca bu bilgisayarda
erişilebilir şekilde çalışır.

### 6. Arama görevi oluşturun

Panelden şehir seçin, isterseniz ilçeleri belirleyin ve bir veya daha fazla
arama kelimesi girin. Sonuç sayısını ve çıktı CSV dosyasının adını seçip görevi
başlatın. Görev ilerlemesini panelden takip edebilirsiniz. İlk çalıştırmada
Chrome/WebDriver başlatılır; tarama sırasında internet bağlantısı gereklidir.
Görev geçmişi ve CSV dosyaları Windows'ta
`%LOCALAPPDATA%\GoogleMapsBot` klasörüne kaydedilir. İlk açılışta proje
klasöründeki görev geçmişi, anahtar kelime geçmişi ve varsayılan kümülatif CSV
bu konuma kopyalanır; panelden CSV'yi indirebilirsiniz.

### 7. Uygulamayı durdurun

Çalıştırıldığı PowerShell penceresine dönüp `Ctrl+C` tuşlarına basın. Daha sonra
yeniden başlatmak için proje klasöründe sanal ortamı etkinleştirip
`py app.py` komutunu çalıştırın.

> Not: 5000 portu başka bir uygulama tarafından kullanılıyorsa uygulama açık
> hata vererek başlatılmaz; o uygulamayı kapatıp tekrar deneyin. 5000 portunda
> çalışan bu projeye ait eski `app.py` örneği başlatma sırasında kapatılıp
> yenisi çalıştırılır; eski örnekte devam eden bir görev kesilebilir.

Testleri çalıştırmak için proje klasöründe:

```powershell
py -m unittest discover -s tests -v
```

### Komut satırından çalıştırma (isteğe bağlı)

Web paneli yerine:

```powershell
py main.py
```

Arama kelimelerini `main.py` dosyasından düzenleyebilirsiniz.

## Kullanım ayrıntıları

**Web Paneli Özellikleri:**
- Şehir seçimi (İstanbul, Ankara, İzmir vb.)
- İlçe seçimi (opsiyonel - seçilmezse tüm ilçeler aranır)
- Şehir ve ilçe bilgileri arama metninden tahmin edilmez; görev seçimiyle CSV'ye yazılır
- Telefon numaraları aynı çıktı CSV'sinde biçim farkları normalize edilerek tekrar eklenmez
- Birden fazla arama kelimesi girebilirsiniz
- Kontrollü sorgu varyasyonları seçeneği, girilen kelime çiftlerini ve mobilya sektörüne uygun sorguları ayrı ayrı dener; en fazla 20 ek terim üretir ve ilçelerle çarpılan toplam sorgu sayısını panelde gösterir
- Maksimum sonuç sayısı ayarlanabilir (varsayılan: 50)
- Görevleri gerçek zamanlı takip edebilirsiniz
- İlerleme çubuğu ve durum raporları
- Terminal benzeri görev akışı iki saniyede bir güncellenir; gönderilen sorgular, tarama aşamaları, incelenen kartlar ve hata/bitirme durumları gösterilir
- Görülen işletme kartlarının Google Maps metni açılıp incelenebilir; telefon bulunmayan ve listede zaten olan kayıtlar da görüntülenir, yalnızca yeni ve geçerli cep telefonları CSV'ye eklenir
- Google Maps kartında kategori etiketi açıkça görünüyorsa görev geçmişine ve paneldeki kategori özetine kaydedilir; Google Contacts CSV'sinin standart `Notes` alanına da eklenir. Etiket bulunamazsa ad veya sorgudan tahmin edilmez
- Sponsorlu etiketi açıkça görülen kartlar işaretlenir; etiket görülmemesi organik olduğunu kanıtlamaz
- Sonuç taraması Google Maps `role="feed"` sonuç panelini kaydırır; yeni kart gelmiyorsa üç ardışık denemeden sonra durur. Terminalde her sorgu için incelenen kartlar, yeni kayıtlar, telefonsuz/tekrar telefon sayıları ve bitirme nedeni görünür

### Komut Satırı

```bash
# Botu çalıştır
python main.py
```

`main.py` dosyasında arama kelimelerini düzenleyebilirsiniz.

## API Endpoints

Web paneli arka planda şu API'leri kullanır:

- `POST /api/tasks` - Yeni görev oluştur
- `GET /api/tasks/<id>` - Görev durumu
- `GET /api/tasks` - Tüm görevler
- `GET /api/districts/<city>` - İlçe listesi
- `GET /api/cities` - Şehir listesi
- `GET /api/keywords-history` - Kullanılmış anahtar kelimeler
- `GET /api/export?filename=google_contacts_cumulative.csv` - CSV dosyasını indir

Görev durumları `pending`, `running`, `completed`, `completed_with_errors` veya
`failed` olabilir. Kısmi arama hataları görev ayrıntılarında gösterilir. Uygulama
yeniden başladığında bekleyen görevler kuyruğa alınır; çalışma sırasında kesilmiş
görevler hata durumuyla işaretlenir.

Web panelinin dışa aktarma bağlantısı, görevde seçilmiş çıktı dosyasını indirir.
Dosya adı olarak yalnızca `.csv` dosya adlarına izin verilir; sunucu yerel
makinede `127.0.0.1` adresinde çalışır.
Desteklenen sekiz şehir için ilçe arama listeleri şehirle eşleştirilmiştir.

## Örnek API Kullanımı

```bash
# Yeni görev oluştur
curl -X POST http://localhost:5000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "city": "istanbul",
    "search_keywords": ["mobilya imalat", "mutfak"],
    "expand_search_queries": true,
    "max_results": 50,
    "cumulative_file": "google_contacts_cumulative.csv"
  }'

# Görev durumu
curl http://localhost:5000/api/tasks/task_1

# Tüm görevler
curl http://localhost:5000/api/tasks
```

`expand_search_queries` isteğe bağlıdır ve varsayılanı `false` değeridir. `true`
olduğunda verilen terimler korunur; terim çiftleri ve bilinen mobilya
imalat/atölye aramaları en fazla 20 ek sorgu olarak eklenir. Her ek sorgu her
seçili ilçe için ayrı çalıştırılır; tüm sorgulardaki telefonlar aynı CSV'ye
tekilleştirilerek yazılır.

## CSV Formatı

Google Contacts import formatında:
- **Phone 1 - Label**: Mobile
- **Phone 1 - Value**: +905xxxxxxxxx
- **Address 1 - City**: Şehir (örn: Istanbul)
- **Address 1 - Region**: İlçe (örn: Kadiköy)
- **Address 1 - Country**: Turkey
- **Labels**: Maps

## Dosya Yapısı

```
GoogleMapsBot/
├── app.py                 # Flask web uygulaması
├── scraper.py             # Scraper sınıfı
├── main.py                # Komut satırı arayüzü
├── requirements.txt       # Python bağımlılıkları
├── templates/
│   └── index.html        # Web paneli arayüzü
├── PROGRESS.md           # İlerleme takibi
└── README.md             # Bu dosya
```

## Notlar

- Google Maps scraping'i TOS kapsamında olabilir, kişisel kullanım için tasarlanmıştır
- ReCAPTCHA veya rate limiting ile karşılaşılabilir
- Google Maps DOM yapısı değişebilir, selector'lar güncellenmesi gerekebilir
- Background modda çalışır, tarayıcı penceresi açılmaz

## Lisans

Kişisel kullanım için.
