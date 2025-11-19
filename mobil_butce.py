import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import time

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Aile Bütçesi", page_icon="🏠", layout="centered")

# --- KULLANICI VE ŞİFRELER (Burası Resepsiyon) ---
# Buraya kardeşlerinin adını ve şifresini ekleyebilirsin
KULLANICILAR = {
    "mustafa": "1234",
    "kardes1": "abcd",
    "kardes2": "0000"
}

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
    sheet = client.open("ButceVerileri").sheet1 
    return sheet

# --- VERİLERİ ÇEK VE KULLANICIYA GÖRE FİLTRELE ---
def verileri_getir(aktif_kullanici):
    sheet = baglanti_kur()
    veriler = sheet.get_all_records()
    df = pd.DataFrame(veriler)
    
    if not df.empty:
        # Sadece giriş yapan kullanıcının verilerini al! (İşte sihir burada)
        if 'Kullanici' in df.columns:
            df = df[df['Kullanici'] == aktif_kullanici]
        
        if not df.empty:
            df['Tarih_Obj'] = pd.to_datetime(df['Tarih'], format="%Y-%m-%d %H:%M", errors='coerce')
            if df["Tutar"].dtype == 'O': 
                 df["Tutar"] = df["Tutar"].astype(str).str.replace(',', '.').astype(float)
            df = df.sort_values(by='Tarih_Obj', ascending=False)
        
    return df, sheet

# --- DÖNEM LİSTESİ ---
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
            
        aylar = {1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"}
        bas_str = f"{iter_date.day} {aylar[iter_date.month]} {iter_date.year}"
        bit_str = f"{son_date.day} {aylar[son_date.month]} {son_date.year}"
        
        etiket = f"{bas_str} - {bit_str}"
        donemler.append({"label": etiket, "start": iter_date, "end": son_date})
        iter_date = next_iter
    return donemler[::-1]

# --- GİRİŞ KONTROL MEKANİZMASI ---
if 'giris_yapildi' not in st.session_state:
    st.session_state['giris_yapildi'] = False
    st.session_state['kullanici_adi'] = ""

# --- EĞER GİRİŞ YAPILMADIYSA LOGIN EKRANI GÖSTER ---
if not st.session_state['giris_yapildi']:
    st.title("🔐 Giriş Yap")
    kullanici = st.text_input("Kullanıcı Adı").lower() # Küçük harfe çevir
    sifre = st.text_input("Şifre", type="password")
    
    if st.button("GİRİŞ"):
        if kullanici in KULLANICILAR and KULLANICILAR[kullanici] == sifre:
            st.session_state['giris_yapildi'] = True
            st.session_state['kullanici_adi'] = kullanici
            st.success("Giriş Başarılı!")
            st.rerun()
        else:
            st.error("Hatalı kullanıcı adı veya şifre!")

# --- GİRİŞ YAPILDIYSA UYGULAMAYI GÖSTER ---
else:
    aktif_kullanici = st.session_state['kullanici_adi']
    
    # Çıkış Butonu (Yan Menüde)
    if st.sidebar.button("Çıkış Yap 🔒"):
        st.session_state['giris_yapildi'] = False
        st.rerun()

    st.sidebar.write(f"👤 Hoşgeldin, **{aktif_kullanici.upper()}**")
    st.title(f"💸 Bütçem ({aktif_kullanici.capitalize()})")

    try:
        df_raw, sheet = verileri_getir(aktif_kullanici)
        
        # Zaman Makinesi
        st.sidebar.header("⏳ Dönem Seç")
        tum_donemler = donem_listesi_olustur(df_raw)
        secilen_donem_index = st.sidebar.selectbox("Dönem:", range(len(tum_donemler)), format_func=lambda x: tum_donemler[x]["label"])
        secilen_bilgi = tum_donemler[secilen_donem_index]
        baslangic, bitis = secilen_bilgi["start"], secilen_bilgi["end"]
        
        if not df_raw.empty:
            df = df_raw.loc[(df_raw['Tarih_Obj'] >= baslangic) & (df_raw['Tarih_Obj'] <= bitis)]
        else:
            df = pd.DataFrame()

        st.caption(f"Dönem: **{secilen_bilgi['label']}**")
        toplam = df["Tutar"].sum() if not df.empty else 0
        st.metric(label="Harcanan", value=f"{toplam} TL")

    except Exception as e:
        st.error(f"Hata: {e}")
        st.stop()

    aciklama_col = 'Aciklama' if not df.empty and 'Aciklama' in df.columns else 'Açıklama'
    tab1, tab2, tab3 = st.tabs(["➕ Ekle", "📊 Analiz", "✏️ İşlemler"])

    with tab1:
        bugun = datetime.now()
        if not (baslangic <= bugun <= bitis):
            st.warning(f"⚠️ Geçmiş dönemdesin. Kayıt BUGÜNE işlenir.")
        
        with st.form("ekle", clear_on_submit=True):
            tutar = st.number_input("Tutar", min_value=0.0, step=10.0)
            kat = st.selectbox("Kategori", ["Yemek", "Ulaşım", "Market", "Fatura", "Eğlence", "Giyim", "Diğer"])
            acik = st.text_input("Açıklama")
            if st.form_submit_button("KAYDET"):
                if tutar > 0:
                    # DİKKAT: Veriyi kaydederken en başa kullanıcı adını da ekliyoruz!
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
            st.write("Veri yok.")

    with tab3:
        if not df.empty:
            liste = [f"{row['Tarih']} | {row['Kategori']} | {row['Tutar']} TL" for i, row in df.iterrows()]
            secilen = st.selectbox("Seç:", liste)
            
            # Orijinal indexi bul (DİKKAT: Pandas indexi ile Sheet satırı farklı olabilir çünkü filtreledik)
            # Bu yüzden 'Tarih' ve 'Aciklama' ve 'Tutar' eşleşmesine göre bulmak en güvenlisidir.
            # Ama basitlik için şimdilik index üzerinden gidelim, hata payı düşüktür.
            idx = df.index[liste.index(secilen)]
            
            # Google Sheets'teki satır numarasını bulmak için +2 (Header + 1-based index)
            # Ama filtreleme olduğu için bu kısım risklidir. En doğrusu tüm veriyi çekip indexlemektir.
            # Filtrelenmiş df_raw'daki index, orijinal verideki sırayı korur.
            row_num = idx + 2 
            
            with st.form("duzenle"):
                row_data = df.loc[idx]
                nTutar = st.number_input("Tutar", value=float(row_data["Tutar"]))
                kats = ["Yemek", "Ulaşım", "Market", "Fatura", "Eğlence", "Giyim", "Diğer"]
                nKat = st.selectbox("Kategori", kats, index=kats.index(row_data["Kategori"]) if row_data["Kategori"] in kats else 6)
                nAcik = st.text_input("Açıklama", value=str(row_data[aciklama_col]))
                
                if st.form_submit_button("GÜNCELLE"):
                    # Güncelleme yaparken sütunlar kaydı (A=Kullanici, B=Tarih, C=Kategori...)
                    sheet.update_cell(row_num, 3, nKat)   # C Sütunu (Kategori)
                    sheet.update_cell(row_num, 4, nTutar) # D Sütunu (Tutar)
                    sheet.update_cell(row_num, 5, nAcik)  # E Sütunu (Açıklama)
                    st.success("Güncellendi!")
                    time.sleep(1)
                    st.rerun()
            
            if st.button("SİL 🗑️", type="primary"):
                sheet.delete_rows(row_num)
                st.success("Silindi!")
                time.sleep(1)
                st.rerun()