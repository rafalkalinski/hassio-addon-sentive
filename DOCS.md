# Sentive OPS — Dokumentacja

## Pierwsze uruchomienie

Po zainstalowaniu dodatku wykonaj kilka prostych kroków:

1. Uruchom dodatek.
2. Otwórz panel Sentive OPS (zakładka **Sentive OPS** w bocznym menu Home Assistant).
3. W formularzu rejestracji wpisz **kod zaproszenia** otrzymany od zespołu Sentive i kliknij **Zarejestruj**.
4. Po pomyślnej rejestracji ustaw **4-cyfrowy PIN** — będzie chronił dostęp do panelu.
5. **Zrestartuj Home Assistant** — rejestracja aktualizuje plik `configuration.yaml` (dodaje `trusted_proxies` i `external_url`). Restart jest wymagany, aby zmiany zostały zastosowane.

To wszystko — Twój Home Assistant jest teraz połączony z platformą Sentive OPS.

---

## Panel Sentive OPS

Panel składa się z dwóch zakładek:

### Status

Wyświetla informacje o połączeniu Twojego Home Assistant z platformą Sentive OPS — m.in. czy połączenie jest aktywne i podstawowe dane Twojej instalacji.

### Urządzenia

Tutaj zarządzasz dostępem do swojego Home Assistant z telefonu lub komputera. Możesz dodawać urządzenia, odnawiać im dostęp lub go cofać.

---

## Dostęp z telefonu / komputera

W zakładce **Urządzenia** możesz dodać dowolne urządzenie mobilne lub komputer:

1. Kliknij **Dodaj urządzenie** i nadaj mu nazwę (np. „iPhone Rafała").
2. Na ekranie pojawi się kod QR.
3. Zeskanuj kod QR na telefonie lub postępuj zgodnie z instrukcją wyświetloną dla komputera.
4. Urządzenie otrzyma certyfikat dostępowy umożliwiający połączenie z Twoim Home Assistant przez platformę Sentive OPS.

Jeśli urządzenie nie jest już używane, możesz cofnąć mu dostęp w dowolnym momencie, klikając **Odwołaj**.

---

## PIN

PIN chroni panel Sentive OPS przed niepowołanym dostępem. Ustawiasz go raz — po pierwszej rejestracji.

Jeśli zapomnisz PIN-u, skontaktuj się z zespołem Sentive: **kontakt@sentive.it** — zresetujemy go zdalnie.

---

## Problemy i kontakt

Jeśli dodatek nie uruchamia się lub wyświetla błąd, napisz do nas: **kontakt@sentive.it**.

Opisz krótko, co widzisz na ekranie lub w logach dodatku — postaramy się pomóc jak najszybciej.
