import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import time

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Maaş Bütçesi", page_icon="💰", layout="centered")

# --- MAAŞ GÜNÜ ---
MAAS_GUNU = 19 

# --- GOOGLE SHEETS BAĞLANTISI (HİBRİT SİSTEM) ---
@st.cache_resource
def baglanti_kur():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. YÖNTEM: Streamlit Cloud'daki Gizli Kasa'ya bak
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    # 2. YÖNTEM: Bilgisayardaki dosyaya bak (Local)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        
    client = gspread.authorize(creds)
    sheet = client.open("ButceVerileri").sheet1 
    return sheet

# --- YARDIMCI FONKSİYON: AY İSİMLERİ ---
def turkce_tarih_yaz(tarih_obj):
    aylar = {1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
             7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"}
    return f"{tarih_obj.day} {aylar[tarih_obj.month]} {tarih_obj.year}"

# --- VERİLERİ ÇEK ---
def verileri_getir():
    sheet = baglanti_kur()
    veriler = sheet.get_all_records()
    df = pd.DataFrame(veriler)
    
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
    if not df.empty and df['Tarih_Obj'].min() is not pd.NaT:
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
            
        etiket = f"{turkce_tarih_yaz(iter_date)} - {turkce_tarih_yaz(son_date)}"
        donemler.append({"label": etiket, "start": iter_date, "end": son_date})
        iter_date = next_iter
    return donemler[::-1]

# --- ARAYÜZ BAŞLANGIÇ ---
st.title("📅 Maaş Bütçesi (Online)")

try:
    df_raw, sheet = verileri_getir()
    
    # Yan Menü
    st.sidebar.header("⏳ Zaman Makinesi")
    tum_donemler = donem_listesi_olustur(df_raw)
    secilen_donem_index = st.sidebar.selectbox("Dönem Seçiniz:", range(len(tum_donemler)), format_func=lambda x: tum_donemler[x]["label"])
    secilen_bilgi = tum_donemler[secilen_donem_index]
    baslangic, bitis = secilen_bilgi["start"], secilen_bilgi["end"]
    
    if not df_raw.empty:
        df = df_raw.loc[(df_raw['Tarih_Obj'] >= baslangic) & (df_raw['Tarih_Obj'] <= bitis)]
    else:
        df = pd.DataFrame()

    st.caption(f"Dönem: **{secilen_bilgi['label']}**")
    toplam = df["Tutar"].sum() if not df.empty else 0
    st.metric(label="Dönem Harcaması", value=f"{toplam} TL")

except Exception as e:
    st.error(f"Hata: {e}")
    st.stop()

aciklama_col = 'Aciklama' if not df.empty and 'Aciklama' in df.columns else 'Açıklama'
tab1, tab2, tab3 = st.tabs(["➕ Ekle", "📊 Analiz", "✏️ İşlemler"])

with tab1:
    bugun = datetime.now()
    if not (baslangic <= bugun <= bitis):
        st.warning(f"⚠️ Geçmiş dönemdesin. Kayıt BUGÜNE ({turkce_tarih_yaz(bugun)}) işlenir.")
    with st.form("ekle", clear_on_submit=True):
        tutar = st.number_input("Tutar", min_value=0.0, step=10.0)
        kat = st.selectbox("Kategori", ["Yemek", "Ulaşım", "Market", "Fatura", "Eğlence", "Giyim", "Diğer"])
        acik = st.text_input("Açıklama")
        if st.form_submit_button("KAYDET"):
            if tutar > 0:
                sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), kat, tutar, acik])
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
        idx = df.index[liste.index(secilen)]
        row_num = idx + 2
        
        with st.form("duzenle"):
            row_data = df.loc[idx]
            nTutar = st.number_input("Tutar", value=float(row_data["Tutar"]))
            kats = ["Yemek", "Ulaşım", "Market", "Fatura", "Eğlence", "Giyim", "Diğer"]
            nKat = st.selectbox("Kategori", kats, index=kats.index(row_data["Kategori"]) if row_data["Kategori"] in kats else 6)
            nAcik = st.text_input("Açıklama", value=str(row_data[aciklama_col]))
            if st.form_submit_button("GÜNCELLE"):
                sheet.update_cell(row_num, 2, nKat)
                sheet.update_cell(row_num, 3, nTutar)
                sheet.update_cell(row_num, 4, nAcik)
                st.success("Güncellendi!")
                time.sleep(1)
                st.rerun()
        if st.button("SİL 🗑️", type="primary"):
            sheet.delete_rows(row_num)
            st.success("Silindi!")
            time.sleep(1)
            st.rerun()