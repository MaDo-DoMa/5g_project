# PoC: Edge vs Cloud — pomiar latencji i przepustowości

**Temat pracy:** *Edge Computing and Application-Aware Traffic Steering in 5G Networks*

Prosty PoC porównujący dwa warianty rozmieszczenia aplikacji: **Edge** (serwer blisko klienta,
np. drugi komputer w sieci LAN/kampusowej lub serwer brzegowy operatora) oraz **Cloud**
(serwer w chmurze publicznej / za WAN). Klient mierzy latencję i przepustowość pobierania
paczki danych (domyślnie **1 MB**), a wyniki dopisuje do `results.csv`, z którego generowane
są wykresy PNG.

## Architektura

```
+---------------------+   rapid access (LAN/5G edge)   +---------------------+
|      client.py      | <----------------------------> |  server.py  (EDGE)  |
|   (twoja maszyna,   |                                |  np. drugi komputer |
|   laptop / 5G modem)|   slow path (Internet/WAN)     +---------------------+
|                     |                                +---------------------+
|                     | <----------------------------> |  server.py  (CLOUD) |
+---------------------+                                |  np. VPS w chmurze  |
                                                       +---------------------+
```

## Pliki

| Plik | Rola |
|---|---|
| `server.py` | bezstanowy serwer TCP; po triggerze odsyła paczkę 1 MB (bajty zerowe) i zamyka połączenie |
| `client.py` | klient pomiarowy; 50 zapytań na środowisko, dopisuje wyniki do `results.csv` |
| `plot.py` | wykresy: boxplot latencji + słupkowy wykres średniej przepustowości |
| `results.csv` | wyniki pomiarów (tworzy go `client.py`) |

## Wymagania

- Python 3.8+ — dla `server.py` i `client.py` wystarczy **wyłącznie biblioteka standardowa**,
- żeby wygenerować wykresy: `pip install pandas matplotlib`.

## Instrukcja uruchomienia (krok po kroku)

### 1. Zainstaluj zależności

```bash
pip install pandas matplotlib
```

### 2. Uruchom serwer EDGE (np. drugi komputer w LAN)

Na początku `server.py` ustaw parametry (`SERVER_IP`, `SERVER_PORT`, `PAYLOAD_MB`), potem:

```bash
python server.py
```

Windows poprosi o zgodę Zapory dla Pythona w sieciach prywatnych — zaakceptuj.

### 3. Uruchom serwer CLOUD (np. VPS w chmurze)

```bash
scp server.py user@<IP_VPS>:~/
ssh user@<IP_VPS>
nohup python3 server.py > server.log 2>&1 &
```

Pamiętaj o otwarciu portu TCP 5001 w zaporze / Security Group VPS
(np. `sudo ufw allow 5001/tcp` albo reguła inbound w konsoli chmury).

### 4. Wykonaj pomiar (z maszyny klienckiej)

```bash
python client.py <IP_EDGE> <IP_CLOUD>
```

Flagi opcjonalne:

| Flaga | Domyślnie | Opis |
|---|---|---|
| `--requests N` | 50 | liczba zapytań na każde środowisko |
| `--edge-port P` | 5001 | port serwera Edge |
| `--cloud-port P` | 5001 | port serwera Cloud |
| `--size-mb MB` | 1 | oczekiwany rozmiar paczki (kontrola zgodności) |

Metodologia: każde zapytanie to **nowe połączenie TCP** (jak typowe żądanie HTTP);
zapytania **Edge i Cloud są przeplatane** (iteracja = 1×Edge + 1×Cloud), co eliminuje
wpływ dryftu warunków sieciowych w czasie. Nieudane zapytania są ponawiane (3 próby);
po trzech porażkach do CSV trafia pusty wiersz (pandas automatycznie go ignoruje).

### 5. Wygeneruj wykresy i statystyki

```bash
python plot.py
```

Wynik: `latency_boxplot.png` (boxplot latencji Edge vs Cloud, z punktami pomiarów — jitter),
`throughput_bars.png` (średnia przepustowość ± odchylenie standardowe) oraz podsumowanie
statystyczne w konsoli (średnia, mediana, std = jitter, p75/p95).

### 6. Szybki test na jednym komputerze (bez sieci)

Skopiuj `server.py` do `server_cloud.py`, zmień w nim `SERVER_PORT` na `5002` i uruchom
obie instancje. Następnie:

```bash
python client.py 127.0.0.1 127.0.0.1 --cloud-port 5002
```

Uwaga: wartości przez loopback nie są reprezentatywne dla sieci (latencja < 1 ms,
przepustowość ograniczona przez CPU) — służą tylko do sprawdzenia poprawności skryptów.

## Format `results.csv`

```csv
timestamp,server_type,latency_ms,throughput_mbps
2026-10-23T14:00:01,Edge,1.412,913.55
2026-10-23T14:00:01,Cloud,84.170,402.11
```

Plik jest **appendowany** — przed rozpoczęciem nowej serii pomiarów usuń go lub zmień nazwę,
żeby nie mieszać populacji danych.

## Interpretacja wyników (notatki do pracy)

- `latency_ms` — czas od wysłania żądania (trigger) do **pierwszych** odebranych bajtów;
  obejmuje RTT sieci + czas obsługi żądania po stronie serwera,
- `throughput_mbps` = `payload_bity / czas_pobierania` — liczone od pierwszego bajtu do EOF,
  więc nie zawiera wpływu na ustanowienie połączenia (to sprawdzane osobno przez latencję),
- rozrzut latencji na boxplotcie (IQR, odchylenie std) — to **jitter**, kluczowy dla
  zastosowań czasu rzeczywistego (wideokonferencje, XR/cloud gaming); Edge zwykle daje
  mniejszą nie tylko średnią, ale właśnie **mniejszy rozrzut**,
- świeże połączenie na każde zapytanie — jawnie modeluje przypadek HTTP-like; przez co
  wynik przepustowości obejmuje fazę slow-start TCP (dotyczy głównie długości RTT Cloud).

## Rozwiązywanie problemów

- `python` nie działa → na Windows spróbuj `py` albo zainstaluj Pythona z opcją "Add to PATH",
- widać timeouts w client → sprawdź: czy serwer działa (`netstat -ano | findstr 5001`),
  czy zapora/Security Group przepuszcza TCP 5001, czy IP jest poprawne (nie WAN IP za NAT-em bez port-forwardingu),
- serwer ma zatrzymać się po wylogowaniu z VPS → użyj `nohup ... &` (jak wyżej) lub `tmux`/`screen`.

---

# Wariant 5G: UPF Router z Traffic Steering (DPI) — topologia localhost

Rozbudowa PoC o architekturę **klient–serwer z węzłem sterującym 5G Core**:
cały ruch UE przechodzi przez router UPF (port **5000**), który na podstawie
flagi L7 (`APP_TYPE=...`) w uplinku decyduje, czy skierować sesję do serwera
**Edge** (port **5002**, opóźnienie symulowane **5 ms**) czy **Cloud**
(port **5001**, opóźnienie symulowane **50 ms**). Węzły końcowe odsyłają
bufor **1 MB** (`sendall`) i zamykają połączenie (krótkotrwała sesja
HTTP/REST).

## Topologia

```
                          +---------------------------------------+
                          |              127.0.0.1                |
                          |                                       |
 +----------+   TCP/5000  |  +-----------+          +----------+  |
 |    UE    | ------------> | UPF (DPI) | =======> |   Edge   |  |
 |ue_client |               +-----------+  5 ms    | (5002)   |  |
 +----------+                   |                      +----------+  |
                                | eMBB_VIDEO            +----------+  |
                                ======================> |  Cloud   |  |
                                       50 ms           | (5001)   |  |
                                                       +----------+  |
                          +---------------------------------------+
```

| Plik | Rola | Port |
|---|---|---|
| `edge.py` | serwer Edge (MEC) — `sleep(5 ms)` → 1 MB → FIN | 5002 |
| `cloud.py` | serwer Cloud (DC) — `sleep(50 ms)` → 1 MB → FIN | 5001 |
| `upf_router.py` | transparentne proxy + DPI (`APP_TYPE`), steering UL Classifier | 5000 |
| `ue_client.py` | symulator UE / sonda pomiarowa — 50 żądań na profil | → 5000 |
| `data_viz.py` | pandas + matplotlib — boxplot latencji, słupkowy throughput | - |

Flagi L7: `APP_TYPE=URLLC_SENSOR` → Edge, `APP_TYPE=eMBB_VIDEO` → Cloud
(traffic nieznany → Cloud, bezpieczny default).

## Uruchomienie

```bash
# terminal 1, 2, 3 (kolejność dowolna):
python edge.py
python cloud.py
python upf_router.py

# terminal 4:
python ue_client.py            # 50 zapytań na profil -> telemetry.csv
.venv\Scripts\python data_viz.py   # albo: python data_viz.py -> latency_plot.png, throughput_plot.png
```

Wymagania: `python edge|cloud|upf_router|ue_client` — tylko biblioteka
standardowa; `data_viz.py` wymaga `pip install pandas matplotlib` (lub
środowiska `.venv`, jeśli używasz venv z repo).

## Metryki UE (`telemetry.csv`)

| Kolumna | Znaczenie |
|---|---|
| `timestamp` | ISO z sekundową rozdzielczością |
| `profile_type` | `URLLC_Sensor` / `eMBB_Video` |
| `latency_ms` | czas od `sendall` żądania do **pierwszego** bajtu odpowiedzi (`time.perf_counter`) |
| `throughput_mbps` | (rozmiar payloadu w megabitach) / (czas wysłania → ostatni bajt 1 MB) |

Interpretacja: rozrzut pudełka (IQR, std) latencji dla `URLLC_Sensor` to
**jitter** — kluczowe kryterium akceptacji URLLC; eMBB "kupuje" przepustowość
większą stabilnością okna transmisji, ale płaci RTT do centrum danych.

Uwaga metodologiczna: wyniki loopback nie są reprezentatywne dla sieci
fizycznej — służą do walidacji mechanizmu steering i demonstracji rozdzielenia
ścieżek URLLC/eMBB.
