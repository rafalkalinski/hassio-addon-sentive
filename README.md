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

1. **Rejestruje** Twój Home Assistant w systemie Sentive OPS — jednorazowo, przy pierwszym uruchomieniu.
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

### Krok 3 — Wpisz kod zaproszenia

6. Przejdź do zakładki **Konfiguracja** dodatku.
7. W polu `invite_code` wpisz kod, który otrzymałeś od zespołu Sentive.

> Kod zaproszenia jest jednorazowy i ważny przez 15 minut. Jeśli wygasł, skontaktuj się z nami.

### Krok 4 — Uruchom dodatek

8. Wróć do zakładki **Informacje** i kliknij **Uruchom**.
9. Poczekaj chwilę — w logach zobaczysz komunikat o pomyślnej rejestracji.

### Krok 5 — Ustaw PIN

10. W pasku bocznym Home Assistant kliknij **Sentive OPS**.
11. Przy pierwszym wejściu zostaniesz poproszony o ustawienie 4-cyfrowego PINu — zabezpiecza on dostęp do panelu.

Gotowe! Twoja instalacja jest teraz monitorowana przez Sentive OPS.

---

## Konfiguracja

W konfiguracji dodatku jest tylko jedno pole do uzupełnienia:

| Opcja | Opis |
|-------|------|
| `invite_code` | Kod zaproszenia otrzymany od zespołu Sentive — **wymagane** |

Nic więcej nie musisz konfigurować.

---

## Co dzieje się po konfiguracji?

- Dodatek automatycznie rejestruje Twój Home Assistant w Sentive OPS.
- Otwiera bezpieczne, szyfrowane połączenie z naszymi serwerami.
- W pasku bocznym HA pojawia się panel **Sentive OPS**.
- Zespół Sentive może teraz monitorować Twoją instalację, reagować na awarie i — za Twoją zgodą — wdrażać poprawki.

---

## Pomoc i kontakt

Masz pytania lub coś nie działa? Napisz do nas:

**kontakt@sentive.it**
