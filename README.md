# Edge vs Cloud — pomiar latencji i przepustowości w realnej sieci

**Temat pracy:** *Edge Computing and Application-Aware Traffic Steering in 5G Networks*

Koncepcja: **3 maszyny, realny ruch, zero symulowanych opóźnień.**
Kontroler na PC po kablu wysyła ping ICMP i test TCP (1 MB) do: (a) laptopa
połączonego po WiFi (węzeł Edge w LAN) oraz (b) zdalnego serwera VPS w Internecie
(węzeł Cloud). Wyniki trafiają do `measurements.csv`, wykresy generuje `plot_real.py`.

## Topologia (realna sieć)

```
 [laptop WiFi: EDGE]  --WiFi-->  [router]  <--LAN(kabel)--  [PC: KONTROLER]
                                                          (pinger + TCP probe)
                                                                  |
                                                     (Internet/WAN) v
                                                          [VPS: CLOUD]
```

| Maszyna | Rola | Uruchamia |
|---|---|---|
| Laptop po WiFi | węzeł **Edge** — responder TCP | `python server.py` |
| PC po kablu | **kontroler pomiarowy** (ICMP + TCP, przeplatane) | `python controller.py <IP_LAPTOP> <IP_VPS>` |
| Serwer VPS daleko | węzeł **Cloud** — responder TCP | `python server.py` |

| Plik | Rola |
|---|---|
| `pinger.py` | sonda ICMP — wrapper na systemowy `ping` (parsuje `time=`/`czas=`, odporny na lokalizację Windows); samodzielnie: `python pinger.py <ip> -n 20` |
| `controller.py` | kontroler: w każdej iteracji ICMP RTT + TCP latencja (trigger → 1. bajt) + throughput 1 MB, naprzemiennie dla obu celów |
| `server.py` | responder TCP — po triggerze odsyła 1 MB (bajty zerowe) i zamyka połączenie; ten sam skrypt na laptopie WiFi i na VPS |
| `plot_real.py` | wykresy: grouped boxplot ICMP vs TCP, słupkowy throughput, podsumowanie + overhead (`tcp_latency − icmp_rtt`) |

Wymagania: Python 3.8+; `server.py`, `pinger.py`, `controller.py` — wyłącznie
biblioteka standardowa. `plot_real.py` wymaga `pip install pandas matplotlib`.

### Format `measurements.csv`

```csv
timestamp,target,icmp_rtt_ms,tcp_latency_ms,throughput_mbps
2026-11-10T18:00:01,WiFi_Edge,3.20,4.11,312.55
2026-11-10T18:00:02,Remote_Cloud,28.00,30.42,88.17
```

Plik jest **appendowany** — przed nową serią pomiarów usuń go lub zmień nazwę,
żeby nie mieszać populacji danych.

### Interpretacja (notatki do pracy)

- `icmp_rtt_ms` — realne RTT ścieżki (warstwa sieciowa, bez serwisu),
- `tcp_latency_ms` = RTT + connect + obsługa żądania po stronie serwera,
- **overhead = `tcp_latency_ms − icmp_rtt_ms`** — izoluje narzut serwera/aplikacji
  (kluczowe porównanie: co daje umieszczenie aplikacji bliżej użytkownika przy tym
  samym ostatnim skoku WiFi),
- notka: ICMP w Windows bywa kwantowany do 1 ms — na szybkich ścieżkach LAN
  overhead może wyjść lekko ujemny; mierz go głównie dla ścieżki WAN (VPS),
- rozrzut latencji (IQR, odchylenie std) na boxplotcie — to **jitter**, kluczowy dla
  zastosowań czasu rzeczywistego; świeże połączenie na każde zapytanie jawnie
  modeluje przypadek HTTP-like, więc throughput obejmuje fazę slow-start TCP
  (dotyczy głównie długiej ścieżki do VPS).

### Przygotowanie maszyn (krok po kroku)

1. **Laptop WiFi**: `python server.py`; sprawdź jego IP (`ipconfig`) → to `<IP_LAPTOP>`;
   Windows: zgoda Zapory dla Pythona w sieci **prywatnej** (profil WiFi).
2. **VPS**:
   ```bash
   scp server.py user@<IP_VPS>:~/
   ssh user@<IP_VPS>
   nohup python3 server.py > server.log 2>&1 &
   ```
   Pamiętaj o otwarciu portu TCP 5001 w zaporze / Security Group VPS
   (np. `sudo ufw allow 5001/tcp` albo reguła inbound w konsoli chmury).
   Serwer ma przeżyć wylogowanie — właśnie za to odpowiada `nohup ... &`
   (alternatywnie `tmux`/`screen`).
3. **PC po kablu**: `python controller.py <IP_LAPTOP> <IP_VPS> --requests 50`,
   potem `python plot_real.py` → `real_latency_plot.png`, `real_throughput_plot.png`.

### Rozwiązywanie problemów

- `python` nie działa → na Windows spróbuj `py` albo zainstaluj Pythona z opcją "Add to PATH",
- timeouts w kontrolerze → sprawdź: czy responder działa na obu maszynach
  (`netstat -ano | findstr 5001`), czy zapora/Security Group przepuszcza TCP 5001,
  czy IP jest poprawne (VPS: adres publiczny; laptop WiFi: adres w sieci LAN),
- ping do laptopa działa, TCP nie → Zapora Windows na laptopie najczęściej blokuje
  przychodzący port; tymczasowo: `netsh advfirewall firewall add rule name="poc5001" dir=in action=allow protocol=TCP localport=5001`.
