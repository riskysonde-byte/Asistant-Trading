### Panduan setel (sekali saja, sekitar 20 menit, semua gratis)

Tanpa langkah ini aplikasi tetap jalan. Bedanya: data hilang saat **Reboot app** dan notifikasi Telegram belum aktif.

#### A. Penyimpanan permanen (Supabase)
1. Buka **supabase.com**, daftar (bisa pakai akun GitHub), lalu **New project**. Isi nama bebas, pilih region **Singapore**, buat password database (simpan), tunggu sekitar 2 menit.
2. Menu kiri **SQL Editor** → **New query** → tempel seluruh isi file SQL di bawah → **Run**. Harus muncul "Success".
3. Buka **Project Settings → API Keys** (atau tombol **Connect**). Salin dua hal:
   - **Project URL**, bentuknya `https://xxxx.supabase.co`
   - **Secret key** (di Supabase lama bernama **service_role**). **Jangan** pakai kunci "anon/publishable".
4. Di Streamlit: **Manage app → Settings → Secrets**, tambahkan tiga baris ini lalu **Save**:
   ```
   SUPABASE_URL = "https://xxxx.supabase.co"
   SUPABASE_KEY = "kunci-secret-tadi"
   APP_PASSWORD = "password-pilihan-bos"
   ```
   `APP_PASSWORD` **wajib**. Tanpa password, penyimpanan Supabase sengaja tidak dinyalakan supaya data Bos tidak bisa dibuka orang lain yang tahu link aplikasinya.
5. **Reboot app**. Di tab ini harus tertulis **Penyimpanan: Supabase**.

#### B. Notifikasi Telegram
1. Di Telegram cari **@BotFather** → kirim `/newbot` → ikuti langkahnya → salin **token** (panjang, ada tanda `:`).
2. Buka chat dengan bot baru Bos, kirim `/start`.
3. Cari **chat ID**: buka di browser `https://api.telegram.org/bot<TOKEN>/getUpdates` (ganti `<TOKEN>` dengan token Bos), lalu cari tulisan `"chat":{"id":` diikuti angka. Itu chat ID Bos.
4. Tambahkan dua baris ke **Secrets Streamlit** (untuk tombol "Kirim pesan tes"):
   ```
   TELEGRAM_BOT_TOKEN = "token-tadi"
   TELEGRAM_CHAT_ID = "angka-chat-id"
   ```
5. Notifikasi otomatis dijalankan oleh GitHub, bukan oleh Streamlit. Di GitHub buka repo → **Settings → Secrets and variables → Actions → New repository secret**, lalu buat **empat** secret dengan nama dan isi yang sama persis:
   `SUPABASE_URL`, `SUPABASE_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
6. Buka tab **Actions** → **Pantau sinyal** → **Run workflow** → pilih `intraday` → **Run**. Dalam satu menit Bos akan melihat centang hijau. Pesan baru muncul di Telegram kalau memang ada kejadian (misalnya harga masuk zona beli).

#### Apa yang dikirim ke Telegram
- 📍 Harga masuk atau dekat **zona beli** sebuah sinyal (sekali sehari per sinyal)
- ✅ Sinyal **masuk**, 🎯 **TP kena**, 🛑 **SL kena**, ⌛ kedaluwarsa, ➖ tidak terisi
- ⚠️ Harga dekat SL, 🎯 dekat TP
- 🔔 **Alert harga** buatan Bos sendiri (form di atas)
- 🚨 IHSG turun lebih dari 1,5% hari itu
- 📊 Ringkasan harian pukul 17:20 WIB: jumlah sinyal, win rate, dan validasi skor bola

#### Jadwal dan batasnya
- Tiap 15 menit saat bursa buka (Senin–Jumat, 09:00–15:45 WIB). GitHub sering terlambat beberapa menit, jadi ini **bukan alarm detik per detik**.
- Harga dari Yahoo tertunda 10–15 menit. Notifikasi bisa datang setelah harga sebenarnya sudah lewat.
- Hari libur bursa tidak dikenali. Data basi tidak memicu notifikasi baru, tapi ringkasan sore tetap terkirim.
- GitHub Actions gratis untuk repo publik. Untuk repo privat ada jatah 2.000 menit per bulan; tugas ini memakai sekitar 600 menit.

#### Keamanan
- **Jangan** menempel token atau kunci di chat, screenshot, atau kode. Hanya di Secrets Streamlit dan Secrets GitHub.
- Kunci *secret/service_role* bisa membaca dan menulis semua data. Kalau bocor, buat ulang di Supabase (API Keys → roll/regenerate) lalu perbarui kedua Secrets.
- Token Telegram bocor? Kirim `/revoke` ke @BotFather.
