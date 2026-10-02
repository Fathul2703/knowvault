# Prosedur Pemulihan Bencana dan Cadangan Data

Prosedur ini menjelaskan cara memulihkan layanan bila pusat data utama tidak dapat digunakan,
misalnya karena gangguan listrik yang panjang atau kerusakan perangkat keras.

## Sasaran pemulihan

Sasaran waktu pemulihan (RTO) adalah empat jam: layanan inti harus kembali berjalan di wilayah
cadangan paling lambat empat jam setelah bencana dinyatakan. Sasaran titik pemulihan (RPO)
adalah lima belas menit, artinya data yang boleh hilang paling banyak transaksi lima belas menit
terakhir.

## Cadangan data

Basis data mereplikasi transaksi ke wilayah cadangan secara terus-menerus. Selain itu, salinan
lengkap dibuat setiap pukul dua dini hari dan disimpan selama tiga puluh lima hari. Berkas yang
diunggah pelanggan disalin ke penyimpanan objek di wilayah cadangan dalam waktu satu jam.

## Langkah pemulihan

Komandan insiden menyatakan bencana setelah berkonsultasi dengan kepala teknik. Langkah pertama
adalah mempromosikan replika basis data di wilayah cadangan menjadi basis data utama. Setelah itu
lalu lintas dialihkan dengan mengubah catatan DNS, yang memerlukan waktu sampai sepuluh menit
untuk menyebar.

## Uji coba

Prosedur ini diuji dua kali setahun dengan simulasi pemadaman wilayah utama pada hari kerja.
Hasil setiap uji coba dicatat, termasuk waktu yang benar-benar dibutuhkan untuk setiap langkah,
dan prosedur diperbarui bila ada langkah yang ternyata tidak jelas.
