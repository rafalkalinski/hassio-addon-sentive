# Sentive OPS — dodatek do Home Assistant

Witaj w ekosystemie **Sentive OPS** — profesjonalnej platformie zarządzania instalacjami Home Assistant. Ten dodatek łączy Twój dom z zespołem Sentive, umożliwiając zdalny monitoring, diagnostykę oraz automatyczne naprawy bez konieczności jakiejkolwiek konfiguracji z Twojej strony.

---

## Co to jest Sentive OPS?

**Sentive OPS** to platforma floty zarządzania instalacjami Home Assistant, stworzona przez firmę [Sentive](https://sentive.it). Obejmuje trzy produkty:

- **The Sentive Pulse** — stały monitoring stanu Twojej instalacji. Zespół Sentive wie o problemach, zanim Ty je zauważysz.
- **The Sentive Brain** — diagnostyka oparta na sztucznej inteligencji. Analizujemy logi i zdarzenia, żeby znaleźć przyczynę awarii.
- **The Sentive Fix** — automatyczne naprawy. Za Twoją zgodą wdrażamy poprawki zdalnie, bez potrzeby wizyty serwisowej.

---

## Co robi ten dodatek?

Dodatek **Sentive OPS** wykonuje trzy zadania:

1. **Rejestruje** Twój Home Assistant w systemie Sentive OPS — jednorazowo, przez panel dodatku (formularz z kodem zaproszenia).
2. **Utrzymuje bezpieczne połączenie** z platformą Sentive, dzięki czemu nasz zespół może monitorować Twoją instalację bez wchodzenia do sieci domowej.
3. **Umożliwia wydawanie certyfikatów urządzeń** — jeśli chcesz mieć dostęp do panelu Sentive OPS z telefonu lub komputera, tutaj wygenerujesz potrzebne poświadczenia.

Po skonfigurowaniu w pasku bocznym Home Assistant pojawi się panel **Sentive OPS**, z którego możesz zarządzać urządzeniami.

---

## Instalacja

### Krok 1 — Dodaj repozytorium

1. W Home Assistant przejdź do **Ustawienia → Dodatki → Sklep z dodatkami**.
2. Kliknij menu z trzema kropkami (prawy górny róg) i wybierz **Repozytoria**.
3. Wpisz adres: `https://github.com/rafalkalinski/hassio-addon-sentive` i kliknij **Dodaj**.

### Krok 2 — Zainstaluj dodatek

4. Odśwież stronę sklepu.
5. Znajdź **Sentive OPS** na liście i kliknij **Zainstaluj**.

### Krok 3 — Uruchom dodatek

6. Przejdź do zakładki **Informacje** i kliknij **Uruchom**.

### Krok 4 — Zarejestruj przez panel

7. W pasku bocznym Home Assistant kliknij **Sentive OPS**.
8. Wpisz **kod zaproszenia** otrzymany od zespołu Sentive w formularzu i kliknij **Zarejestruj**.

> Kod zaproszenia jest jednorazowy i ważny przez 15 minut. Jeśli wygasł, skontaktuj się z nami.

### Krok 5 — Ustaw PIN

9. Po pomyślnej rejestracji zostaniesz poproszony o ustawienie 4-cyfrowego PINu — zabezpiecza on dostęp do panelu.

### Krok 6 — Zrestartuj Home Assistant

10. Rejestracja automatycznie aktualizuje `configuration.yaml` (dodaje `trusted_proxies` i `external_url`). **Zrestartuj Home Assistant**, aby zastosować te zmiany.

Gotowe! Twoja instalacja jest teraz monitorowana przez Sentive OPS.

---

## Konfiguracja

Dodatek nie wymaga żadnej konfiguracji w zakładce **Konfiguracja**. Kod zaproszenia podajesz bezpośrednio w panelu po uruchomieniu.

---

## Co dzieje się po rejestracji?

- Dodatek automatycznie rejestruje Twój Home Assistant w Sentive OPS.
- Otwiera bezpieczne, szyfrowane połączenie z naszymi serwerami.
- W pliku `configuration.yaml` zostają dodane wpisy `trusted_proxies` i `external_url` — wymagane do poprawnego działania tunelu.
- W pasku bocznym HA pojawia się panel **Sentive OPS**.
- Zespół Sentive może teraz monitorować Twoją instalację, reagować na awarie i — za Twoją zgodą — wdrażać poprawki.

---

## Pomoc i kontakt

Masz pytania lub coś nie działa? Napisz do nas:

**kontakt@sentive.it**
