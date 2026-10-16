@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if errorlevel 1 (
        echo HATA: Python bulunamadi.
        echo Yapilacak: Python 3.10 veya daha yeni bir surumu kurun ve kurulumda
        echo "Add Python to PATH" secenegini isaretleyin. Sonra bu dosyayi yeniden acin.
        echo https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo Sanal ortam hazirlaniyor...
    py -3 -m venv .venv
    if errorlevel 1 goto :venv_error
)

".venv\Scripts\python.exe" -c "import flask, selenium, webdriver_manager" >nul 2>nul
if errorlevel 1 (
    echo Gerekli paketler kuruluyor...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :package_error
)

echo Uygulama baslatiliyor. Kapatmak icin bu pencereyi kapatin.
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :app_error
exit /b 0

:venv_error
echo.
echo HATA: Sanal ortam olusturulamadi.
echo Yapilacak: Python 3 kurulumunu onarin, proje klasorune yazma izniniz
echo oldugunu kontrol edin ve Baslat.bat dosyasini yeniden calistirin.
pause
exit /b 1

:package_error
echo.
echo HATA: Gerekli paketler indirilemedi veya kurulamadi.
echo Yapilacak: Internet baglantinizi kontrol edin. Guvenlik duvari veya proxy
echo pip indirmelerini engelliyorsa izin verin; sonra Baslat.bat dosyasini yeniden acin.
echo Ayrintili hata yukaridaki satirlarda gorunur.
pause
exit /b 1

:app_error
echo.
echo HATA: Uygulama baslatilamadi.
echo Yapilacak: Yukaridaki hata mesajini kontrol edin. 5000 portu baska bir
echo uygulama tarafindan kullaniliyorsa o uygulamayi kapatip yeniden deneyin.
echo Bu klasorde yazma izni oldugunu ve Chrome'un kurulu oldugunu da kontrol edin.
pause
exit /b 1
