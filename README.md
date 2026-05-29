# Sistem Streaming UAV Lokal

Service ini sekarang murni lokal dan tidak memakai Docker.

Flow runtime:

```text
RTSP camera
-> FFmpeg
-> HLS di ./hls
-> FastAPI serve /hls dan /player

saat mission aktif
-> FFmpeg juga menulis MP4 ke ./records
```

Komponen yang tetap dipakai:
- websocket telemetry client
- mission event handling
- process manager FFmpeg
- graceful shutdown

Komponen yang sudah dihapus:
- Docker
- Docker Compose
- MediaMTX
- RTSP republish
- remote streaming

## Struktur Folder

```text
service-rec-drone-mission/
├── app.py
├── app/
│   ├── main.py
│   ├── http_server.py
│   ├── config/
│   │   ├── constants.py
│   │   └── settings.py
│   ├── mission/
│   │   └── mission_events.py
│   ├── streaming/
│   │   ├── ffmpeg_manager.py
│   │   └── pipeline.py
│   ├── telemetry/
│   │   ├── models.py
│   │   └── parser.py
│   ├── utils/
│   │   ├── logger.py
│   │   ├── process.py
│   │   ├── retry.py
│   │   └── time.py
│   └── websocket/
│       ├── client.py
│       ├── handlers.py
│       └── reconnect.py
├── scripts/
│   ├── start.sh
│   └── stop.sh
├── hls/
├── records/
├── logs/
├── run/
├── requirements.txt
├── .env
└── .env.example
```

## Cara Jalan

Butuh:
- `python3`
- `ffmpeg`

Catatan:
- `./scripts/start.sh` akan otomatis load variabel dari file `.env`
- `./scripts/start.sh` akan otomatis membuat `.venv` jika belum ada
- `./scripts/start.sh` juga akan otomatis install dependency Python dari `requirements.txt` jika belum terpasang
- `ffmpeg` tetap harus sudah terinstall di komputer dan tersedia di `PATH`
- `./scripts/start.sh` sekarang jalan di foreground, cocok untuk run biasa atau dipanggil oleh `systemd`

Install dependency Python manual jika diperlukan:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Jalankan service:

```bash
./scripts/start.sh
```

Mode jalannya:
- manual: jalankan `./scripts/start.sh`, lalu stop dengan `Ctrl+C`
- systemd: panggil script ini sebagai `ExecStart`, jangan di-background-kan

Stop service:

```bash
./scripts/stop.sh
```

`stop.sh` sekarang hanya reminder, karena service tidak lagi pakai PID file/background mode.

Kalau startup gagal sebelum logger aplikasi aktif, jalankan langsung:

```bash
./scripts/start.sh
```

Kalau service berhasil boot, log utama ada di:

```bash
logs/app.log
logs/ffmpeg.stdout.log
logs/ffmpeg.stderr.log
```

## URL Lokal

- Player: `http://127.0.0.1:8088/player`
- Playlist HLS: `http://127.0.0.1:8088/hls/uav/<drone_id>/index.m3u8`
- Health: `http://127.0.0.1:8088/health`

Penting:
- URL HLS sekarang memakai `uav_id` di path.
- Jika `drone_id` efektif adalah `1`, akses live stream menjadi:
  `http://127.0.0.1:8088/hls/uav/1/index.m3u8`
- `drone_id` efektif diambil dari `device-context`.
- Jika `device-context` gagal, fallback ke `SUBSCRIBE_UAV_ID`.

## API Contract

Base URL lokal default:

```text
http://127.0.0.1:8088
```

### `GET /health`

Fungsi:
- cek status service lokal
- lihat state runtime saat ini
- lihat URL HLS aktif

Response contoh:

```json
{
  "status": "ok",
  "runtime_state": "STREAMING",
  "hls_url": "http://127.0.0.1:8088/hls/uav/1/index.m3u8",
  "playlist_exists": true,
  "playlist_size": 342
}
```

Field:
- `status`: status endpoint lokal, saat ini selalu `"ok"` jika request berhasil
- `runtime_state`: salah satu dari `IDLE`, `CONNECTED`, `STREAMING`, `RECORDING`, `DISCONNECTED`
- `hls_url`: URL HLS aktif yang harus dipakai frontend
- `playlist_exists`: apakah file playlist HLS sudah ada di disk
- `playlist_size`: ukuran file playlist dalam byte

### `GET /stream-info`

Fungsi:
- memberikan kontrak ringan untuk frontend
- memberi tahu `drone_id` aktif dan URL HLS final

Response contoh:

```json
{
  "drone_id": "1",
  "hls_url": "http://127.0.0.1:8088/hls/uav/1/index.m3u8",
  "player_url": "http://127.0.0.1:8088/player"
}
```

Field:
- `drone_id`: UAV ID efektif yang dipakai service
- `hls_url`: URL playlist HLS final
- `player_url`: URL player lokal bawaan

Catatan:
- frontend sebaiknya baca `hls_url` dari endpoint ini, bukan hardcode path sendiri

### `GET /player`

Fungsi:
- player lokal bawaan untuk verifikasi cepat

Response:
- `text/html`

Catatan:
- player akan memanggil `/stream-info`
- lalu player memutar `hls_url` yang dikembalikan endpoint itu

### `GET /hls/uav/{drone_id}/index.m3u8`

Fungsi:
- playlist HLS live utama

Response:
- content type HLS playlist
- isi file berasal dari output FFmpeg di disk

Contoh:

```text
GET /hls/uav/1/index.m3u8
```

Catatan:
- endpoint ini hanya valid jika `drone_id` cocok dengan `drone_id` aktif service
- source of truth untuk URL final tetap `/stream-info`

### `GET /hls/uav/{drone_id}/{segment}`

Fungsi:
- mengambil segment HLS `.ts`

Contoh:

```text
GET /hls/uav/1/segment_000001.ts
```

Catatan:
- file ini dipakai player setelah membaca `index.m3u8`
- segment akan berganti terus selama live stream berjalan

### `GET /records/...`

Fungsi:
- expose file hasil recording mission

Contoh path:

```text
/records/drone_1/2026/05/mission_123.mp4
/records/drone_1/2026/05/mission_123.json
```

Catatan:
- path final mengikuti `drone_id`, tahun, bulan, dan `history_id`
- file `.mp4` adalah hasil recording mission
- file `.json` adalah metadata sederhana mission recording

## Logika Runtime

State runtime sengaja sederhana:

- websocket putus atau vehicle `connected=false` -> FFmpeg stop
- websocket aktif + vehicle connected + bukan mission -> HLS only
- mission start -> FFmpeg restart ke mode `HLS + MP4`
- mission stop -> FFmpeg kembali ke mode `HLS only`

Mission dikendalikan oleh event websocket yang sudah ada:
- `vehicle_state`
- `mission_event`

Jika `mission_event` membawa `history_id`, nilai itu dipakai untuk nama file MP4. Jika tidak ada, fallback ke timestamp lokal.

## Output File

HLS live:

```text
./hls/uav/<drone_id>/index.m3u8
./hls/uav/<drone_id>/segment_000001.ts
...
```

Recording mission:

```text
./records/drone_<id>/<year>/<month>/mission_<history_id>.mp4
./records/drone_<id>/<year>/<month>/mission_<history_id>.json
```

File `.json` berisi metadata sederhana:
- `history_id`
- `drone_id`
- `output_file`
- `started_at_epoch`
- `finished_at_epoch`

## Variabel Penting

Contoh ada di [.env.example](/Users/macbook/Workdir/Office/Projects/drone/service-rec-drone-mission/.env.example:1).

Yang paling penting:
- `BASE_URL`
- `TOKEN`
- `SUBSCRIBE_UAV_ID`
- `RTSP_URL`
- `FFMPEG_CODEC`
- `HLS_TIME_SECONDS`
- `HLS_LIST_SIZE`
- `SERVER_PORT`
- `PUBLIC_BASE_URL`

Keterangan praktis:
- `SUBSCRIBE_UAV_ID=1`
  artinya service subscribe telemetry untuk UAV `1`.
- Jika backend `device-context` berhasil, `drone_id` dari backend dipakai untuk URL HLS dan penamaan folder recording.
- Jika `device-context` gagal, fallback ke `SUBSCRIBE_UAV_ID`.
- Dengan config default di atas, URL yang dibuka frontend tetap:
  `http://127.0.0.1:8088/hls/uav/<drone_id>/index.m3u8`
- Player bawaan ada di:
  `http://127.0.0.1:8088/player`

Contoh:
- jika `SUBSCRIBE_UAV_ID=1` dan `device-context` fallback ke ID itu, stream live ada di:
  `http://127.0.0.1:8088/hls/uav/1/index.m3u8`
- file record akan masuk ke folder seperti:
  `./records/drone_1/2026/05/mission_<history_id>.mp4`
  jika `device-context` fallback ke ID `1`

## Catatan FFmpeg

Default yang paling ringan untuk Raspberry Pi dan macOS:

```env
FFMPEG_CODEC=copy
```

Kalau source RTSP bukan H.264 yang cocok untuk HLS, baru ganti ke:

```env
FFMPEG_CODEC=libx264
```

Mode encode saat ini memakai konfigurasi low-latency:
- `ultrafast`
- `zerolatency`
- GOP pendek
- rolling HLS segment

## File Inti

- [app/streaming/pipeline.py](/Users/macbook/Workdir/Office/Projects/drone/service-rec-drone-mission/app/streaming/pipeline.py:1): keputusan mode `disconnected / idle / mission`
- [app/streaming/ffmpeg_manager.py](/Users/macbook/Workdir/Office/Projects/drone/service-rec-drone-mission/app/streaming/ffmpeg_manager.py:1): build command FFmpeg dan restart tunggal
- [app/http_server.py](/Users/macbook/Workdir/Office/Projects/drone/service-rec-drone-mission/app/http_server.py:1): FastAPI untuk `/hls`, `/records`, `/player`, `/health`
- [app/websocket/client.py](/Users/macbook/Workdir/Office/Projects/drone/service-rec-drone-mission/app/websocket/client.py:1): koneksi websocket dan reconnect

Player `/player` di-render langsung dari FastAPI, jadi tidak ada folder `static/` terpisah.

## Verifikasi Cepat

1. Jalankan `./scripts/start.sh`
2. Buka `/player`
3. Pastikan `vehicle_state.connected=true`
4. Saat mission mulai, cek file MP4 muncul di `records/`
5. Saat mission selesai, file MP4 berhenti bertambah dan `.json` metadata ditulis
