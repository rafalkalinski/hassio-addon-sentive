# Sentive OPS Add-on for Home Assistant

Connect your Home Assistant instance to the Sentive OPS fleet management platform.

## Features

- Automatic registration via invite code (one-shot bootstrap)
- Persistent `cloudflared` tunnel for secure remote access
- Ingress UI panel with PIN gate
- Device certificate management (issue, revoke, renew mTLS certs for mobile/desktop clients)

## Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**.
2. Click the three-dot menu and select **Repositories**.
3. Add the repository URL: `https://github.com/rafalkalinski/hassio-addon-sentive`
4. Find **Sentive OPS** in the store and click **Install**.

## Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `invite_code` | Invite code provided by Sentive OPS | (required) |
| `ops_bootstrap_url` | Bootstrap server URL | `https://bootstrap-dev.sentive.it` |
| `ops_api_url` | Sentive OPS API URL | `https://api-dev.sentive.it` |

## First-Run Steps

1. Set your `invite_code` in the add-on configuration.
2. Start the add-on.
3. Open the **Sentive OPS** panel in the HA sidebar.
4. Set a 4-digit PIN when prompted — this protects the ingress panel.
5. The add-on registers automatically and starts the cloudflared tunnel.

## Support

For issues, visit the [GitHub repository](https://github.com/rafalkalinski/hassio-addon-sentive).

---

# Sentive OPS — dodatek do Home Assistant

Podłącz swój Home Assistant do platformy zarządzania flotą Sentive OPS.

## Funkcje

- Automatyczna rejestracja przez kod zaproszenia (jednorazowy bootstrap)
- Stały tunel `cloudflared` dla bezpiecznego zdalnego dostępu
- Panel UI z bramką PIN w ingress HA
- Zarządzanie certyfikatami urządzeń (wydawanie, odwoływanie, odnawianie certyfikatów mTLS dla telefonów i komputerów)

## Instalacja

1. W Home Assistant przejdź do **Ustawienia → Dodatki → Sklep z dodatkami**.
2. Kliknij menu z trzema kropkami i wybierz **Repozytoria**.
3. Dodaj adres repozytorium: `https://github.com/rafalkalinski/hassio-addon-sentive`
4. Znajdź **Sentive OPS** w sklepie i kliknij **Zainstaluj**.

## Konfiguracja

| Opcja | Opis | Domyślna wartość |
|-------|------|------------------|
| `invite_code` | Kod zaproszenia otrzymany od operatora Sentive OPS | (wymagane) |
| `ops_bootstrap_url` | Adres serwera bootstrap | `https://bootstrap-dev.sentive.it` |
| `ops_api_url` | Adres API Sentive OPS | `https://api-dev.sentive.it` |

## Pierwsze uruchomienie

1. Wpisz `invite_code` w konfiguracji dodatku.
2. Uruchom dodatek.
3. Otwórz panel **Sentive OPS** w pasku bocznym HA.
4. Ustaw 4-cyfrowy PIN — zabezpiecza dostęp do panelu.
5. Dodatek zarejestruje się automatycznie i uruchomi tunel cloudflared.

## Rozwiązywanie problemów

| Objaw | Przyczyna | Rozwiązanie |
|-------|-----------|-------------|
| Dodatek nie startuje | Nieprawidłowy lub już użyty kod zaproszenia | Pobierz nowy kod od operatora Sentive OPS |
| Panel pusty / błąd 502 | Serwer Flask nie wystartował | Sprawdź logi dodatku |
| Tunel nie łączy się | Nieprawidłowy token tunelu | Usuń `/data/registered` i uruchom ponownie |
| Panel PIN zapętla się | Uszkodzony plik `pin.json` | Usuń `/data/pin.json` i uruchom ponownie |
| Lista certyfikatów pusta | Wygasła sesja JWT | Usuń `/data/registered` i zarejestruj ponownie |

## Wsparcie

W razie problemów otwórz zgłoszenie w [repozytorium GitHub](https://github.com/rafalkalinski/hassio-addon-sentive).
