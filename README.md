# Sistem Streaming UAV Lokal

## Ringkasan

Repository ini berisi stack streaming UAV lokal yang memisahkan kontrol mission, telemetry, publish media, dan distribusi media ke modul yang jelas.

- Python menangani orkestrasi, telemetry websocket, state mission, dan supervisi proses.
- FFmpeg hanya mengambil sumber RTSP dari kamera/HM30 lalu mem-publish satu stream RTSP lokal ke MediaMTX.
- MediaMTX menangani fanout RTSP lokal, HLS, WebRTC opsional, `Control API`, `Metrics`, dan rekaman raw `fMP4`.
- Finalisasi rekaman mission ditangani Python dengan mengambil fragmen `.mp4` hasil MediaMTX lalu menyusunnya ke folder mission.

Perintah utama untuk menjalankan sistem:

```bash
./scripts/start.sh
```

Perintah tersebut akan menjalankan `mediamtx` dan aplikasi Python secara lokal melalui Docker Compose. Script akan memakai `docker compose` bila plugin Compose v2 tersedia, lalu fallback ke `docker-compose` untuk environment Linux yang masih memakai binary lama. Mode native juga didukung dengan menjalankan `python -m app.main` jika binary lokal `ffmpeg` dan `mediamtx` sudah tersedia.

Alternatif tanpa Docker:

```bash
./scripts/start-native.sh
```

Mode ini menjalankan aplikasi Python di background dan membiarkan aplikasi mengelola proses `mediamtx` dan `ffmpeg` secara native. Prasyaratnya:

- `python3`
- dependency Python dari `requirements.txt`
- binary `ffmpeg`
- binary `mediamtx`

Untuk menghentikan mode native:

```bash
./scripts/stop-native.sh
```

Untuk follow log mode native:

```bash
./scripts/logs-native.sh
```

Identitas stream selalu di-resolve dari `GET /device-context`. Path stream lokal di MediaMTX menggunakan `resolved_uav_id` dari response backend. Jika `device-context` sementara gagal diakses, aplikasi akan fallback ke `SUBSCRIBE_UAV_ID`.

## Catatan Platform

Desain ini ditujukan untuk berjalan di macOS maupun Linux.

- Mode yang direkomendasikan di kedua platform adalah `docker compose`.
- Mode native juga didukung jika `ffmpeg` dan `mediamtx` terpasang lokal.
- Karena sumber ingest sekarang fixed ke `RTSP_URL`, tidak ada lagi percabangan capture kamera spesifik platform di dalam aplikasi.
- Raspberry Pi diperlakukan sebagai target deployment Linux. Batasan utamanya ada di beban CPU jika codec diubah dari `copy` ke `libx264`.

## Kenapa Arsitektur Ini Dipakai

MediaMTX lebih tepat menangani recording dibanding FFmpeg karena recording berada di sisi downstream publish, bukan di tahap ingest. Dengan recording dipindahkan ke MediaMTX:

- konfigurasi tee-mux FFmpeg menjadi tidak perlu
- risiko double pipeline encode berkurang
- domain kegagalan lebih kecil
- RTSP, HLS, WebRTC, API, metrics, dan recording melihat state stream yang sama

FFmpeg jadi fokus pada satu pekerjaan: menjaga ingest sumber tetap stabil lalu mem-publish ke MediaMTX lokal.

Arsitektur ini juga lebih baik dibanding pendekatan monolitik sebelumnya karena auth HTTP, reconnect websocket, logika mission, publish RTSP, recording file, dan supervisi proses dipisahkan ke komponen yang eksplisit:

- supervisi transport di `app/streaming`
- keputusan mission di `app/mission`
- parsing dan routing telemetry di `app/telemetry` dan `app/websocket`
- konfigurasi deployment dan runtime di `app/config`

Pemisahan ini membuat crash recovery, kepemilikan tunggal proses FFmpeg, dan health checking lebih aman.

## Struktur Folder

```text
uav-streaming-system/
├── app/
│   ├── main.py
│   ├── websocket/
│   │   ├── client.py
│   │   ├── handlers.py
│   │   └── reconnect.py
│   ├── streaming/
│   │   ├── ffmpeg_manager.py
│   │   ├── mediamtx_manager.py
│   │   ├── recorder.py
│   │   ├── pipeline.py
│   │   └── healthcheck.py
│   ├── mission/
│   │   ├── mission_state.py
│   │   ├── mission_events.py
│   │   └── state_machine.py
│   ├── config/
│   │   ├── settings.py
│   │   ├── constants.py
│   │   └── mediamtx.yml
│   ├── telemetry/
│   │   ├── models.py
│   │   └── parser.py
│   └── utils/
│       ├── logger.py
│       ├── process.py
│       ├── retry.py
│       └── time.py
├── records/
├── hls/
├── logs/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── scripts/
│   ├── start.sh
│   ├── stop.sh
│   └── healthcheck.sh
├── requirements.txt
└── .env
```

## Tanggung Jawab Modul

### `app/main.py`

Bootstrap proses, penanganan signal, startup controller, startup websocket, dan graceful shutdown.

### `app/websocket`

- `client.py`: mengambil token WS, subscribe, loop reconnect, heartbeat ping, dan timeout handling
- `handlers.py`: merutekan `vehicle_state` dan `mission_event` ke controller
- `reconnect.py`: kebijakan backoff reconnect

### `app/streaming`

- `mediamtx_manager.py`: menjalankan MediaMTX pada mode native, melakukan health check `Control API`, menunggu readiness, dan restart bila managed mode aktif
- `ffmpeg_manager.py`: memiliki satu proses publisher FFmpeg dan membangun command RTSP ingest -> RTSP publish lokal ke MediaMTX
- `recorder.py`: melacak awal/akhir mission lalu mengambil fragmen raw recording MediaMTX ke `records/drone_<id>/<year>/<month>/mission_<history_id>/`
- `pipeline.py`: orkestrator utama yang mengonsumsi telemetry dan mission event, menjaga state machine tetap konsisten, lalu menyamakan desired state dengan proses yang benar-benar berjalan
- `healthcheck.py`: probe lokal sederhana untuk API dan metrics MediaMTX

### `app/mission`

- `mission_state.py`: model snapshot runtime
- `mission_events.py`: daftar event canonical untuk start/stop mission
- `state_machine.py`: transisi state yang thread-safe antara `IDLE`, `CONNECTED`, `STREAMING`, `RECORDING`, dan `DISCONNECTED`

### `app/config`

- `settings.py`: konfigurasi berbasis environment dan path runtime lokal
- `constants.py`: enum state runtime dan codec
- `mediamtx.yml`: konfigurasi server MediaMTX lokal

### `app/telemetry`

- `models.py`: model envelope untuk `vehicle_state` dan `mission_event`
- `parser.py`: parsing aman dari payload websocket

### `app/utils`

Helper bersama untuk logging, lifecycle subprocess, backoff, dan waktu.

## Logika State Machine

State runtime dibuat sesederhana mungkin:

- `DISCONNECTED`: websocket putus atau heartbeat UAV menunjukkan `connected=false`
- `CONNECTED`: koneksi sehat pertama setelah startup, tetapi idle publish belum benar-benar aktif
- `STREAMING`: websocket sehat, vehicle sehat, mission tidak aktif, dan idle publish aktif
- `RECORDING`: mission aktif dan sesi recorder sedang terbuka
- `IDLE`: baseline awal sebelum konektivitas terbentuk

Keputusan mission datang dari dua channel telemetry:

- `vehicle_state` menentukan konektivitas dan nilai `in_mission`
- `mission_event` menentukan batas lifecycle dan `history_id`

Controller akan melakukan reconcile setiap kali ada perubahan state. Artinya, tidak ada timer tersembunyi yang memutuskan apakah FFmpeg harus hidup atau mati; sumber kebenarannya tetap telemetry.

## Logika Orkestrasi Proses

Alur saat startup:

1. Membuat runtime directory
2. Resolve UAV ID dari `GET /device-context`, dengan fallback ke `SUBSCRIBE_UAV_ID`
3. Menjalankan atau mengecek MediaMTX
4. Menunggu `GET /v3/paths/list` di port `9997`
5. Menjalankan websocket client
6. Menunggu telemetry lalu masuk ke mode idle streaming saat vehicle terhubung

Alur saat mission mulai:

1. Menerima `vehicle_state.in_mission=true` atau `mission_event` seperti `takeoff`
2. Resolve `history_id` dari payload event atau `GET /mission/current`
3. Membuka sesi recorder
4. Menjaga RTSP publisher tetap hidup ke path MediaMTX yang sama
5. HLS dan WebRTC opsional otomatis tersedia dari MediaMTX pada path yang sama

Alur saat mission selesai:

1. Menerima `landed`, `mission_failed`, `mission_aborted`, atau `mission_completed`
2. Menutup sesi recorder
3. Mengambil fragmen raw `.mp4` MediaMTX ke folder target mission
4. Menjaga idle publish tetap hidup jika `IDLE_STREAM_ENABLED=true`

Alur saat disconnect:

1. WebSocket putus atau `vehicle_state.connected=false`
2. Menghentikan FFmpeg
3. Menjaga fragmen recording yang sudah sempat di-flush MediaMTX
4. Reconnect websocket dengan exponential backoff

## Konfigurasi MediaMTX

Konfigurasi saat ini ada di [app/config/mediamtx.yml](/Users/macbook/Workdir/Office/Projects/drone/service-rec-drone-mission/app/config/mediamtx.yml).

Pilihan desain:

- RTSP aktif di `8554`
- HLS aktif di `8888` dengan low-latency HLS
- WebRTC aktif di `8889`
- `Control API` aktif di `9997`
- `Metrics` aktif di `9998`
- logging terstruktur aktif
- recording aktif untuk semua path `uav/...`
- format recording menggunakan `fmp4` agar recorder bisa mengambil part `.mp4` native

### Bentuk Output HLS

Alur sumber live adalah:

1. Kamera/HM30 menyediakan RTSP pada `RTSP_URL`
2. FFmpeg meng-ingest RTSP tersebut
3. FFmpeg mem-publish ulang ke MediaMTX lokal pada:
   `rtsp://<mediamtx-host>:8554/uav/<resolved_uav_id>/live`
4. MediaMTX otomatis me-remux stream RTSP itu menjadi HLS
5. Frontend atau player membaca HLS dari:
   `http://<mediamtx-host>:8888/uav/<resolved_uav_id>/live/index.m3u8`

Contoh jika host lokal dan `resolved_uav_id=1`:

```text
http://127.0.0.1:8888/uav/1/live/index.m3u8
```

Perilaku penting:

- HLS dibuat oleh MediaMTX, bukan oleh FFmpeg
- HLS hanya tersedia jika FFmpeg sedang aktif mem-publish ke path RTSP yang sesuai
- Jika `IDLE_STREAM_ENABLED=true`, URL HLS bisa tetap hidup di luar window recording mission selama konektivitas vehicle sehat
- Jika UAV disconnect atau publisher berhenti, output HLS ikut berhenti update karena tidak ada lagi upstream stream aktif

### File HLS Lokal

MediaMTX menulis artifact HLS ke directory:

```text
/app/hls
```

Pada Docker Compose, directory itu di-mount dari folder repo:

```text
./hls
```

Artinya:

- playlist dan segment HLS dihasilkan lokal di disk
- file yang sama juga disajikan lewat HTTP pada port `8888`
- `./hls` adalah output runtime dan di-ignore oleh Git

Directory `./hls` diperlakukan sebagai area penyajian sementara, bukan arsip recording final. Arsip mission final tetap dipisahkan ke bawah `records/`.

### Pengaturan Low-Latency HLS

Pengaturan HLS saat ini di [app/config/mediamtx.yml](/Users/macbook/Workdir/Office/Projects/drone/service-rec-drone-mission/app/config/mediamtx.yml):

- `hlsVariant: lowLatency`
- `hlsSegmentCount: 4`
- `hlsSegmentDuration: 1s`
- `hlsPartDuration: 200ms`
- `hlsAlwaysRemux: yes`

Kenapa ini penting:

- segment pendek mengurangi waktu startup player
- part low-latency menurunkan delay live edge
- always-remux memastikan HLS siap segera setelah ada publisher aktif

### HLS dan Recording

HLS dan recording adalah dua output berbeda dari path input MediaMTX yang sama:

- HLS untuk pemutaran live di browser atau player
- recording untuk arsip mission dan review setelah penerbangan

Dalam stack ini:

- HLS disajikan dari `./hls`
- fragmen raw `fMP4` ditulis di `./records/_raw/...`
- arsip mission final disusun di:
  `records/drone_<drone_id>/<year>/<month>/mission_<history_id>/`

Jadi jika pertanyaannya adalah "nanti output HLS-nya gimana", jawaban praktisnya:

- output URL: `http://127.0.0.1:8888/uav/<resolved_uav_id>/live/index.m3u8`
- output di disk: dibuat di `./hls`
- dependensi sumber: hanya hidup selama MediaMTX lokal masih menerima RTSP publisher

### Control API dan Metrics

Port `9997` adalah `Control API` MediaMTX.

Dipakai untuk:

- health check aplikasi
- memeriksa apakah MediaMTX hidup
- melihat path dan publisher yang aktif

Contoh:

```text
GET http://127.0.0.1:9997/v3/paths/list
```

Port `9998` adalah endpoint `Metrics` MediaMTX.

Dipakai untuk:

- monitoring
- scraping Prometheus
- melihat traffic runtime dan jumlah stream

Contoh:

```text
GET http://127.0.0.1:9998/metrics
```

Untuk project ini:

- `9997` penting secara operasional
- `9998` opsional tetapi berguna untuk monitoring produksi

Konfigurasi ini mengikuti referensi resmi MediaMTX untuk file konfigurasi dan `Control API`:

- `api: yes` dan `GET /v3/paths/list` untuk health check
- `record: yes`, `recordPath`, `recordFormat: fmp4`
- `hlsVariant: lowLatency`, `hlsSegmentDuration`, `hlsPartDuration`

Sumber:

- https://mediamtx.org/docs/references/configuration-file
- https://mediamtx.org/docs/features/control-api

## Docker Compose

## Konfigurasi Docker Compose

File Compose ada di [docker/docker-compose.yml](/Users/macbook/Workdir/Office/Projects/drone/service-rec-drone-mission/docker/docker-compose.yml).

Service:

- `mediamtx`: image resmi MediaMTX, mengekspose RTSP/HLS/WebRTC/API/metrics, serta menyimpan recording dan aset HLS lewat volume mount
- `app`: orkestrator Python dengan FFmpeg terpasang, bergantung pada health MediaMTX

Port yang diekspos:

- `8554` RTSP
- `8888` HLS
- `8889` endpoint HTTP WebRTC
- `9997` `Control API`
- `9998` `Metrics`

Jika ingin membatasi port eksternal hanya ke empat port utama, `9998` bisa tidak diekspos ke host dan tetap dipakai internal.

## Contoh Pipeline FFmpeg

### 1. RTSP input -> MediaMTX, mode copy

```bash
ffmpeg -hide_banner -loglevel warning \
  -rtsp_transport tcp -fflags nobuffer -flags low_delay \
  -i rtsp://192.168.144.25:8554/main.264 \
  -map 0:v:0 -c:v copy -an \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/uav/1/live
```

### 2. RTSP input -> MediaMTX, re-encode H.264

```bash
ffmpeg -hide_banner -loglevel warning \
  -rtsp_transport tcp -fflags nobuffer -flags low_delay \
  -i rtsp://192.168.144.25:8554/main.264 \
  -map 0:v:0 -vf format=yuv420p \
  -c:v libx264 -preset veryfast -tune zerolatency \
  -profile:v baseline -level:v 3.1 \
  -g 30 -keyint_min 30 -sc_threshold 0 -bf 0 \
  -b:v 2500k -maxrate 3000k -bufsize 5000k -an \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/uav/1/live
```

## Menjalankan dan Deploy

Mode Docker:

```bash
./scripts/start.sh
./scripts/healthcheck.sh
./scripts/stop.sh
```

Mode native:

1. Pasang `ffmpeg` dan `mediamtx`
2. Set `MEDIAMTX_MANAGED=true` di `.env`
3. Jalankan `python -m app.main`

Endpoint penting setelah boot:

- RTSP: `rtsp://127.0.0.1:8554/uav/<drone_id>/live`
- HLS: `http://127.0.0.1:8888/uav/<drone_id>/live/index.m3u8`
- WebRTC WHEP: `http://127.0.0.1:8889/uav/<drone_id>/live/whep`
- API: `http://127.0.0.1:9997/v3/paths/list`
- Metrics: `http://127.0.0.1:9998/metrics`

## Cara Meminimalkan Latensi

Pada operasi live UAV, latensi biasanya didominasi oleh GOP cadence, buffering player, dan perpindahan protokol. Aturan praktisnya:

- gunakan `-c:v copy` jika stream HM30 sudah H.264 dan kompatibel dengan client
- jika perlu re-encode, pertahankan `-tune zerolatency`, `-bf 0`, GOP pendek, dan bitrate moderat
- pertahankan HLS low-latency dengan segment `1s` dan part `200ms`
- gunakan RTSP over TCP secara lokal antara FFmpeg dan MediaMTX agar perilakunya deterministik
- jadikan WebRTC opsional untuk operator yang butuh latency browser paling rendah
- hindari double encoding dan hindari tee output FFmpeg

## Catatan Optimasi Raspberry Pi

- Gunakan `FFMPEG_CODEC=copy` jika kamera sudah mengirim H.264
- Jika re-encode wajib, lebih baik turunkan resolusi sumber atau bitrate dari sisi kamera/encoder sebelum membebani CPU lokal
- Pertahankan `rtspTransports: [tcp]` untuk stabilitas kecuali jaringan lokal benar-benar bagus dan UDP memang dibutuhkan
- Jalankan aplikasi dan MediaMTX di host yang sama untuk menghindari hop tambahan
- Gunakan SSD atau media flash yang cepat jika recording kontinu diaktifkan
- Hardware encoder bisa ditambahkan nanti tanpa mengubah antarmuka orkestrasi
