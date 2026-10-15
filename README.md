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

## Kurulum

```bash
# Bağımlılıkları yükle
python -m pip install -r requirements.txt

# Odaklı testleri çalıştır
python -m unittest discover -s tests -v
```

## Kullanım

### Web Paneli (Önerilen)

```bash
# Web panelini başlat
python app.py
```

Tarayıcıda http://127.0.0.1:5000 adresini açın. Windows'ta başlatma sırasında
5000 portunda çalışan bu projeye ait eski `app.py` örneği varsa kapatılıp yenisi
başlatılır. Portu başka bir uygulama kullanıyorsa o uygulama kapatılmaz ve
başlatma açık bir hata mesajıyla durur. Eski örnekte çalışan bir görev varsa
yeniden başlatma görevi kesebilir.

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
