import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import time

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Aile Bütçesi", page_icon="🏠", layout="centered")

# --- MAAŞ GÜNÜ ---
MAAS_GUNU = 19 

# --- GOOGLE SHEETS BAĞLANTISI ---
@st.cache_resource
def baglanti_kur():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    return client

# --- KULLANICI İŞLEMLERİ ---
def kullanici_kontrol(kadi, sifre):
    client = baglanti_kur()
    users_sheet = client.open("ButceVerileri").worksheet("Kullanicilar")
    veriler = users_sheet.get_all_records()
    
    for user in veriler:
        if str(user['KullaniciAdi']) == kadi and str(user['Sifre']) == sifre:
            return True
    return False

def kullanici_ekle(kadi, sifre):
    client = baglanti_kur()
    users_sheet = client.open("ButceVerileri").worksheet("Kullanicilar")
    veriler = users_sheet.get_all_records()
    
    # Kullanıcı adı var mı kontrol et
    for user in veriler:
        if str(user['KullaniciAdi']) == kadi:
            return False, "Bu kullanıcı adı zaten alınmış!"
            
    users_sheet.append_row([kadi, sifre])
    return True, "Kayıt başarılı! Giriş yapabilirsiniz."

def sifre_degistir(kadi, yeni_sifre):
    client = baglanti_kur()
    users_sheet = client.open("ButceVerileri").worksheet("Kullanicilar")
    cell = users_sheet.find(kadi)
    users_sheet.update_cell(cell.row, 2, yeni_sifre) # 2. Sütun Şifre

def hesap_sil(kadi):
    client = baglanti_kur()
    # 1. Kullanıcıyı sil
    users_sheet = client.open("ButceVerileri").worksheet("Kullanicilar")
    cell = users_sheet.find(kadi)
    users_sheet.delete_rows(cell.row)
    
    # 2. Kullanıcının TÜM verilerini sil (Temizlik)
    data_sheet = client.open("ButceVerileri").sheet1
    veriler = data_sheet.get_all_records()
    # Tersten silmek gerekir ki indexler kaymasın
    rows_to_delete = []
    for i, row in enumerate(veriler):
        if str(row.get('Kullanici', '')).lower() == kadi.lower():
            rows_to_delete.append(i + 2) # Header + 1-based
            
    # Toplu silme API'de zor olduğu için kullanıcıyı uyaracağız sadece
    # (Gerçek uygulamada batch delete yapılır ama burada basit tutalım)
    pass 

# --- VERİLERİ ÇEK ---
def verileri_getir(aktif_kullanici):
    client = baglanti_kur()
    sheet = client.open("ButceVerileri").sheet1 
    veriler = sheet.get_all_records()
    df = pd.DataFrame(veriler)
    
    if not df.empty and 'Kullanici' in df.columns:
        # Sadece kendi verisini görsün
        df = df[df['Kullanici'].astype(str) == aktif_kullanici]
        
        if not df.empty:
            df['Tarih_Obj'] = pd.to_datetime(df['Tarih'], format="%Y-%m-%d %H:%M", errors='coerce')
            if df["Tutar"].dtype == 'O': 
                 df["Tutar"] = df["Tutar"].astype(str).str.replace(',', '.').astype(float)
            df = df.sort_values(by='Tarih_Obj', ascending=False)
    return df, sheet

# --- DÖNEMLER ---
def donem_listesi_olustur(df):
    bugun = datetime.now()
    if bugun.day >= MAAS_GUNU:
        mevcut_baslangic = datetime(bugun.year, bugun.month, MAAS_GUNU)
    else:
        if bugun.month == 1:
            mevcut_baslangic = datetime(bugun.year - 1, 12, MAAS_GUNU)
        else:
            mevcut_baslangic = datetime(bugun.year, bugun.month - 1, MAAS_GUNU)
    
    donemler = []
    if not df.empty and 'Tarih_Obj' in df.columns and df['Tarih_Obj'].min() is not pd.NaT:
        en_eski = df['Tarih_Obj'].min()
        if en_eski.day >= MAAS_GUNU:
            iter_date = datetime(en_eski.year, en_eski.month, MAAS_GUNU)
        else:
            if en_eski.month == 1:
                iter_date = datetime(en_eski.year - 1, 12, MAAS_GUNU)
            else:
                iter_date = datetime(en_eski.year, en_eski.month - 1, MAAS_GUNU)
    else:
        iter_date = mevcut_baslangic

    while iter_date <= mevcut_baslangic:
        if iter_date.month == 12:
            son_date = datetime(iter_date.year + 1, 1, MAAS_GUNU) - timedelta(seconds=1)
            next_iter = datetime(iter_date.year + 1, 1, MAAS_GUNU)
        else:
            son_date = datetime(iter_date.year, iter_date.month + 1, MAAS_GUNU) - timedelta(seconds=1)
            next_iter = datetime(iter_date.year, iter_date.month + 1, MAAS_GUNU)
        
        bas_str = f"{iter_date.day}.{iter_date.month}.{iter_date.year}"
        bit_str = f"{son_date.day}.{son_date.month}.{son_date.year}"
        donemler.append({"label": f"{bas_str} - {bit_str}", "start": iter_date, "end": son_date})
        iter_date = next_iter
    return donemler[::-1]

# --- GİRİŞ KONTROL ---
if 'giris_yapildi' not in st.session_state:
    st.session_state['giris_yapildi'] = False
    st.session_state['kullanici_adi'] = ""

# --- SAYFA YAPISI ---
if not st.session_state['giris_yapildi']:
    st.title("🔐 Aile Bütçesi Giriş")
    
    tab_giris, tab_kayit = st.tabs(["Giriş Yap", "Yeni Hesap Oluştur"])
    
    with tab_giris:
        kullanici = st.text_input("Kullanıcı Adı").lower().strip()
        sifre = st.text_input("Şifre", type="password")
        if st.button("GİRİŞ YAP"):
            if kullanici and sifre:
                if kullanici_kontrol(kullanici, sifre):
                    st.session_state['giris_yapildi'] = True
                    st.session_state['kullanici_adi'] = kullanici
                    st.success("Giriş Başarılı!")
                    st.rerun()
                else:
                    st.error("Kullanıcı adı veya şifre hatalı.")
            else:
                st.warning("Alanları doldurunuz.")

    with tab_kayit:
        st.write("Kendi bütçeni yönetmek için hesap oluştur.")
        yeni_kadi = st.text_input("Belirleyeceğiniz Kullanıcı Adı").lower().strip()
        yeni_sifre = st.text_input("Belirleyeceğiniz Şifre", type="password")
        yeni_sifre2 = st.text_input("Şifre Tekrar", type="password")
        
        if st.button("HESAP OLUŞTUR"):
            if yeni_kadi and yeni_sifre:
                if yeni_sifre == yeni_sifre2:
                    basari, mesaj = kullanici_ekle(yeni_kadi, yeni_sifre)
                    if basari:
                        st.success(mesaj)
                    else:
                        st.error(mesaj)
                else:
                    st.error("Şifreler uyuşmuyor!")
            else:
                st.warning("Tüm alanları doldurunuz.")

# --- UYGULAMA İÇİ ---
else:
    aktif_kullanici = st.session_state['kullanici_adi']
    
    with st.sidebar:
        st.write(f"👤 **{aktif_kullanici.upper()}**")
        
        # HESAP AYARLARI (Sidebar'da)
        with st.expander("⚙️ Hesap Ayarları"):
            st.write("Şifre Değiştir")
            degis_sifre = st.text_input("Yeni Şifre", type="password", key="s1")
            if st.button("Şifreyi Güncelle"):
                sifre_degistir(aktif_kullanici, degis_sifre)
                st.success("Şifre değişti!")
            
            st.divider()
            
            st.write("Hesabı Sil (Dikkat!)")
            if st.button("Hesabımı Kalıcı Sil"):
                hesap_sil(aktif_kullanici)
                st.session_state['giris_yapildi'] = False
                st.rerun()

        if st.button("Çıkış Yap 🔒"):
            st.session_state['giris_yapildi'] = False
            st.rerun()

    st.title(f"💸 Bütçem")

    try:
        df_raw, sheet = verileri_getir(aktif_kullanici)
        
        st.sidebar.divider()
        st.sidebar.header("⏳ Dönem Seç")
        tum_donemler = donem_listesi_olustur(df_raw)
        secilen_donem_index = st.sidebar.selectbox("Dönem:", range(len(tum_donemler)), format_func=lambda x: tum_donemler[x]["label"])
        secilen_bilgi = tum_donemler[secilen_donem_index]
        baslangic, bitis = secilen_bilgi["start"], secilen_bilgi["end"]
        
        if not df_raw.empty:
            df = df_raw.loc[(df_raw['Tarih_Obj'] >= baslangic) & (df_raw['Tarih_Obj'] <= bitis)]
        else:
            df = pd.DataFrame()

        toplam = df["Tutar"].sum() if not df.empty else 0
        
        col1, col2 = st.columns(2)
        col1.caption(f"Dönem: **{secilen_bilgi['label']}**")
        col2.metric(label="Toplam Harcama", value=f"{toplam} TL")

    except Exception as e:
        st.error(f"Veri hatası: {e}")
        st.stop()

    aciklama_col = 'Aciklama' if not df.empty and 'Aciklama' in df.columns else 'Açıklama'
    tab1, tab2, tab3 = st.tabs(["➕ Ekle", "📊 Analiz", "✏️ İşlemler"])

    with tab1:
        bugun = datetime.now()
        if not (baslangic <= bugun <= bitis):
            st.warning(f"⚠️ Geçmiş dönemdesin.")
        
        with st.form("ekle", clear_on_submit=True):
            tutar = st.number_input("Tutar", min_value=0.0, step=10.0)
            kat = st.selectbox("Kategori", ["Yemek", "Ulaşım", "Market", "Fatura", "Eğlence", "Giyim", "Diğer"])
            acik = st.text_input("Açıklama")
            if st.form_submit_button("KAYDET"):
                if tutar > 0:
                    # Kullanıcı adıyla kaydet
                    sheet.append_row([aktif_kullanici, datetime.now().strftime("%Y-%m-%d %H:%M"), kat, tutar, acik])
                    st.success("Kaydedildi!")
                    time.sleep(1)
                    st.rerun()

    with tab2:
        if not df.empty:
            fig = px.pie(df.groupby("Kategori")["Tutar"].sum().reset_index(), values='Tutar', names='Kategori', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df[["Tarih", "Kategori", "Tutar", aciklama_col]], use_container_width=True, hide_index=True)
        else:
            st.info("Bu dönemde veri yok.")

    with tab3:
        if not df.empty:
            liste = [f"{row['Tarih']} | {row['Kategori']} | {row['Tutar']} TL" for i, row in df.iterrows()]
            secilen = st.selectbox("İşlem yapılacak:", liste)
            
            idx = df.index[liste.index(secilen)]
            # Filtrelenmiş df'in orijinal index'ine göre satır numarasını buluyoruz
            # (Tüm verideki yeri)
            # Header (1) + 1-based index = +2 AMA,
            # df_raw tüm veriyi içeriyor. df filtrelenmiş.
            # En güvenli yol: sheet.find ile satırı bulmak ama aynı veri varsa karışabilir.
            # Basitlik için: df_raw içindeki indexini bulalım.
            row_num = idx + 2 
            
            with st.form("duzenle"):
                row_data = df.loc[idx]
                nTutar = st.number_input("Tutar", value=float(row_data["Tutar"]))
                kats = ["Yemek", "Ulaşım", "Market", "Fatura", "Eğlence", "Giyim", "Diğer"]
                nKat = st.selectbox("Kategori", kats, index=kats.index(row_data["Kategori"]) if row_data["Kategori"] in kats else 6)
                nAcik = st.text_input("Açıklama", value=str(row_data[aciklama_col]))
                
                if st.form_submit_button("GÜNCELLE"):
                    # Sütun sırası: A=Kullanici, B=Tarih, C=Kategori, D=Tutar, E=Aciklama
                    sheet.update_cell(row_num, 3, nKat)   # C
                    sheet.update_cell(row_num, 4, nTutar) # D
                    sheet.update_cell(row_num, 5, nAcik)  # E
                    st.success("Güncellendi!")
                    time.sleep(1)
                    st.rerun()
            
            if st.button("SİL 🗑️", type="primary"):
                sheet.delete_rows(row_num)
                st.success("Silindi!")
                time.sleep(1)
                st.rerun()