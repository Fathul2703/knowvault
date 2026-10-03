# Kode Status Pengiriman Barang

Setiap paket yang dikirim dari gudang memiliki kode status. Pelanggan dapat melihat kode ini di
halaman pelacakan.

## Daftar kode

Kode T10 berarti paket sedang dikemas di gudang. Kode T20 berarti paket sudah diserahkan kepada
kurir. Kode T30 berarti paket dalam perjalanan menuju kota tujuan. Kode T40 berarti paket sudah
diterima oleh pelanggan dan ditandatangani.

## Keterlambatan

Bila sebuah paket berstatus T30 lebih dari lima hari, sistem membuat tiket otomatis untuk tim
logistik. Tim logistik menghubungi kurir dan memberi kabar kepada pelanggan dalam satu hari kerja.

## Paket kembali

Paket yang tidak dapat diantar dikembalikan ke gudang dan statusnya kembali ke T10 setelah
diperiksa. Biaya pengiriman ulang ditanggung pelanggan bila alamat yang diberikan salah.
