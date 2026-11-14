"""Örnek (KURGUSAL) kayıtları bilgi bankasına yükler, sohbeti denemek için.
    .venv\\Scripts\\python.exe -m scripts.seed_example

Kayıtlar bu dosyanın içindedir; hiçbir dokümana ihtiyaç yoktur. Aynı başlıklı kayıt
varsa atlanır. Adım 4'te admin ekranı gelince bu betiğe gerek kalmaz.
"""
import sys

from app.services import knowledge

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXAMPLES = [
    ("KNK-101: Konnektör servisine bağlanılamıyor",
     'Belirti: Programda "Konnektör servisine bağlanılamıyor" uyarısı çıkar, fatura gönderilemez.\n'
     "Çözüm adımları:\n"
     "Önce Iplerin doğru olup olmadığını kontrol edin:\n"
     "1. Bilgisayar > Disk > Windows > system32 > drivers > etc > host dosyasını metin belgesi ile açın.\n"
     "2. Bilgisayarın arama kısmına cmd yazın ve yönetici olarak başlatın.\n"
     "3. ipconfig yazın ve IPv4 yazan yerdeki numaralar ile host dosyasının içinde yazan ip'nin aynı olup "
     "olmadığına bakın, aynı değilse değiştirin.\n"
     "4. Aynı ip'yi kendi bilgisayarınızdaki host dosyasına da yapıştırın. Sonra önce merkez bilgisayardan "
     "konnektör uygulamasını, sonra kendi bilgisayarınızda çalıştırın.\n"
     "5. Hesap planlarından durumu test edin."),
    ("KNK-204: Kullanıcı adı veya şifre hatalı",
     'Belirti: Entegratör girişinde "Kimlik doğrulama başarısız" mesajı alınır.\n'
     "Çözüm adımları:\n"
     "1. Ayarlar > Entegratör Bilgileri ekranına girin.\n"
     "2. Kullanıcı adı ve şifreyi entegratör portalındaki bilgilerle karşılaştırın.\n"
     '3. Şifre yakın zamanda değiştirildiyse yeni şifreyi girip "Bağlantıyı Test Et" düğmesine basın.\n'
     "4. Test başarılıysa kaydedin ve programı yeniden açın."),
    ("KNK-310: Fatura XML şema doğrulaması başarısız",
     'Belirti: Fatura gönderilirken "Şema doğrulama hatası" alınır.\n'
     "Çözüm adımları:\n"
     "1. Hata detayında belirtilen alanı not edin (genellikle vergi numarası veya birim kodu).\n"
     "2. Müşteri kartında vergi numarasının 10 veya 11 haneli olduğunu kontrol edin.\n"
     "3. Ürün kartında birim kodunun geçerli bir UN/ECE kodu olduğunu doğrulayın (örneğin ADET için C62).\n"
     "4. Faturayı düzeltip yeniden gönderin."),
    ("e-İmza (mali mühür) PIN kodu istemiyor veya imzalama başlamıyor",
     "Çözüm adımları:\n"
     "1. USB e-İmza cihazının takılı olduğundan emin olun, farklı bir USB portunu deneyin.\n"
     "2. Cihazın sürücü yazılımının (akıllı kart yazılımı) kurulu olduğunu kontrol edin.\n"
     "3. Görev çubuğunda akıllı kart okuyucu hizmetinin çalıştığını doğrulayın.\n"
     "4. Tarayıcıda veya programda imza eklentisini güncelleyin.\n"
     "5. Yine olmuyorsa bilgisayarı yeniden başlatıp cihazı bir kez daha takın."),
    ("e-İmza sertifikasının süresi dolmuş",
     'Belirti: "Sertifika geçerlilik süresi dolmuş" uyarısı.\n'
     "Çözüm: Sertifika sağlayıcınızdan yenileme talep edin. Yenileme tamamlanınca yeni sertifikayı "
     "programa tekrar tanıtmak için Ayarlar > e-İmza > Sertifika Seç yolunu izleyin."),
    ('Fatura "Gönderildi" görünüyor ama alıcıya ulaşmadı',
     "Çözüm adımları:\n"
     "1. Fatura durum sorgulama ekranından faturanın GİB durumunu kontrol edin.\n"
     '2. Alıcının e-Fatura mükellefi olup olmadığını "Mükellef Sorgula" ile doğrulayın.\n'
     "3. Alıcı e-Fatura mükellefi değilse faturayı e-Arşiv olarak kesmeniz gerekir.\n"
     '4. Durum "Hata" ise hata kodunu not edip ilgili çözüm başlığına bakın.'),
]

if __name__ == "__main__":
    added = skipped = 0
    for title, solution in EXAMPLES:
        if knowledge.title_exists(title):
            skipped += 1
            continue
        knowledge.add(title, solution, author="örnek-veri")
        added += 1
        print("Eklendi:", title)
    print(f"\n{added} kayıt eklendi, {skipped} zaten vardı.")
