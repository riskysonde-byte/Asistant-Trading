-- Jalankan SEKALI di Supabase: menu SQL Editor -> New query -> tempel semua isi file ini -> Run.

create table if not exists kv (
  kunci text primary key,
  nilai jsonb not null,
  diubah timestamptz default now()
);

create table if not exists sinyal (
  id text primary key,                 -- kode|tanggal|sumber
  dibuat timestamptz default now(),
  tanggal date not null,
  sumber text not null,
  kode text not null,
  gaya text,
  putusan text,
  keyakinan int,
  beli_dari numeric,
  beli_sampai numeric,
  tp numeric,
  sl numeric,
  rr numeric,
  status text not null default 'belum_masuk',
  harga_masuk numeric,
  tgl_masuk date,
  harga_keluar numeric,
  tgl_keluar date,
  hasil_pct numeric,
  hasil_r numeric,
  harga_terakhir numeric,
  diperbarui timestamptz default now()
);
create index if not exists sinyal_status_idx on sinyal (status);

create table if not exists skor_harian (
  id text primary key,                 -- kode|tanggal
  tanggal date not null,
  kode text not null,
  skor int not null,
  label text,
  harga numeric,
  ret5 numeric,
  ret10 numeric
);

-- Keamanan: kunci rahasia (service_role) tetap bisa baca-tulis, kunci publik (anon) tidak bisa apa-apa.
alter table kv enable row level security;
alter table sinyal enable row level security;
alter table skor_harian enable row level security;
