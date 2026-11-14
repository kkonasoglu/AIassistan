"""Testler gerçek konuşma modelini yüklemesin (yüzlerce MB, yavaş): ayar, uygulama içe aktarılmadan önce verilir."""
import os

os.environ["OFIS_STT_PRELOAD"] = "false"
os.environ["OFIS_WEB_SEARCH"] = "false"   # testler gerçek internete çıkmasın (web testleri kendisi açar)
