# -*- coding: utf-8 -*-
"""
اپلیکیشن ارزیابی مواجهه شغلی با صدا
پشتیبانی از استانداردهای ایران/ACGIH، NIOSH و OSHA
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from io import BytesIO
import math

# تنظیمات صفحه و ظاهر
st.set_page_config(
    page_title="ارزیابی مواجهه با صدا",
    page_icon="🔊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Vazirmatn', sans-serif; direction: rtl; text-align: right; }
    .main { direction: rtl; text-align: right; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3em; }
    </style>
""", unsafe_allow_html=True)

st.title("🔊 ارزیابی مواجهه شغلی با صدا")
st.caption("محاسبه دوز، TWA و LEX,8h بر اساس استانداردهای ایران/ACGIH، NIOSH و OSHA — واحدها: dBA و ساعت")

# دیکشنری استانداردها
EXCHANGE_RATES = {
    "ایران / ACGIH TLV": {"rate": 3.0, "criterion": 85.0, "threshold": 80.0},
    "NIOSH REL":          {"rate": 3.0, "criterion": 85.0, "threshold": 80.0},
    "OSHA PEL":           {"rate": 5.0, "criterion": 90.0, "threshold": 90.0},
}

# توابع محاسباتی
def allowable_time(level_dba, rate, criterion):
    return 8.0 / (2.0 ** ((level_dba - criterion) / rate))

def compute_dose(exposures, rate, criterion):
    dose_sum = 0.0
    for e in exposures:
        L = e["level"]
        C = e["hours"]
        if C <= 0 or L < 0:
            continue
        T = allowable_time(L, rate, criterion)
        if T > 0:
            dose_sum += C / T
    return 100.0 * dose_sum

def twa_from_dose(dose_percent, rate, criterion):
    if dose_percent <= 0:
        return 0.0
    if rate == 3.0:
        return 10.0 * math.log10(dose_percent / 100.0) + criterion
    else:
        return 16.61 * math.log10(dose_percent / 100.0) + 90.0

def lex_8h(exposures):
    total = 0.0
    for e in exposures:
        L = e["level"]
        T = e["hours"]
        if T <= 0 or L <= 0:
            continue
        total += T * (10.0 ** (L / 10.0))
    if total <= 0:
        return 0.0
    return 10.0 * math.log10(total / 8.0)

def risk_level(dose_percent):
    if dose_percent < 50:
        return "🟢 کم", "#28a745"
    elif dose_percent < 85:
        return "🟡 قابل قبول (نظارت)", "#ffc107"
    elif dose_percent < 100:
        return "🟠 در آستانه خطر", "#fd7e14"
    elif dose_percent < 200:
        return "🔴 خطر بالا", "#dc3545"
    else:
        return "🟣 خطر بسیار بالا", "#6f42c1"

def nrr_derated(nrr, protector_type):
    factors = {"earmuff": 0.25, "foam": 0.50, "other": 0.70}
    f = factors.get(protector_type, 0.50)
    return nrr * (1.0 - f)

# نوار کناری
with st.sidebar:
    st.header("⚙️ تنظیمات ارزیابی")
    standard = st.selectbox("استاندارد مرجع", list(EXCHANGE_RATES.keys()), index=0)
    params = EXCHANGE_RATES[standard]
    st.info(f"**{standard}**\n\nحد مجاز: **{params['criterion']} dBA**\n\nنرخ تبادل: **{params['rate']} dB**")
    st.divider()
    input_mode = st.radio("روش ورود داده", ["دستی", "بارگذاری Excel"], index=0)

exposures = []

# ورودی داده‌ها
if input_mode == "دستی":
    st.subheader("📝 بازه‌های مواجهه")
    n = st.number_input("تعداد بازه‌ها", min_value=1, max_value=12, value=2, step=1)
    for i in range(int(n)):
        c1, c2 = st.columns(2)
        with c1:
            level = st.number_input(f"تراز صدا — بازه {i+1} (dBA)", min_value=0.0, max_value=140.0, value=85.0, step=1.0, key=f"L{i}")
        with c2:
            hours = st.number_input(f"مدت مواجهه — بازه {i+1} (ساعت)", min_value=0.0, max_value=24.0, value=4.0, step=0.5, key=f"H{i}")
        if hours > 0:
            exposures.append({"level": float(level), "hours": float(hours)})
else:
    st.subheader("📂 بارگذاری Excel")
    uploaded = st.file_uploader("فایل Excel با ستون‌های level_dba و hours", type=["xlsx", "xls"])
    if uploaded is not None:
        try:
            df_excel = pd.read_excel(uploaded)
            required_cols = {"level_dba", "hours"}
            if not required_cols.issubset(set(df_excel.columns)):
                st.error("فایل باید ستون‌های level_dba و hours داشته باشد.")
            else:
                for _, row in df_excel.iterrows():
                    try:
                        L = float(row["level_dba"])
                        H = float(row["hours"])
                        if 0 < H <= 24 and 0 <= L <= 140:
                            exposures.append({"level": L, "hours": H})
                    except (ValueError, TypeError):
                        continue
                st.success(f"✅ {len(exposures)} بازه معتبر خوانده شد.")
        except Exception as e:
            st.error(f"خطا: {e}")

if not exposures:
    st.warning("⚠️ حداقل یک بازه با مدت زمان بیشتر از صفر وارد کنید.")
    st.stop()

# محاسبات
dose = compute_dose(exposures, params["rate"], params["criterion"])
twa = twa_from_dose(dose, params["rate"], params["criterion"])
lex = lex_8h(exposures)
total_hours = sum(e["hours"] for e in exposures)
risk_label, risk_color = risk_level(dose)

# نمایش نتایج
st.divider()
st.subheader("📊 نتایج ارزیابی")

c1, c2, c3, c4 = st.columns(4)
c1.metric("دوز روزانه", f"{dose:.1f} %")
c2.metric("TWA (۸ ساعته)", f"{twa:.1f} dBA")
c3.metric("LEX,8h", f"{lex:.1f} dBA")
c4.metric("مجموع زمان", f"{total_hours:.1f} ساعت")

st.markdown(f"""
<div style="background:{risk_color}20; border-right:6px solid {risk_color}; padding:16px; border-radius:10px; margin:12px 0;">
<h3 style="margin:0; color:{risk_color};">سطح ریسک: {risk_label}</h3>
<p style="margin:4px 0 0 0;">دوز محاسبه‌شده <b>{dose:.1f}%</b> از حد مجاز است.</p>
</div>
""", unsafe_allow_html=True)

if dose >= 100:
    st.error("🚨 دوز بالای ۱۰۰٪. اقدام کنترلی فوری الزامی است.")
elif dose >= 85:
    st.warning("⚠️ دوز در آستانه حد مجاز. برنامه حفاظت شنوایی فعال شود.")
else:
    st.success("✅ دوز زیر حد مجاز است.")

# جدول
st.subheader("📋 تفصیل بازه‌ها")
rows = []
for i, e in enumerate(exposures, 1):
    T_allow = allowable_time(e["level"], params["rate"], params["criterion"])
    contrib = 100.0 * e["hours"] / T_allow if T_allow > 0 else 0.0
    rows.append({
        "بازه": i,
        "تراز (dBA)": f"{e['level']:.1f}",
        "مدت (ساعت)": f"{e['hours']:.1f}",
        "زمان مجاز (ساعت)": f"{T_allow:.2f}",
        "سهم از دوز (%)": f"{contrib:.1f}",
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# نمودارها
st.subheader("📈 نمودارها")
if len(exposures) > 1:
    labels = [f"بازه {i+1}" for i, e in enumerate(exposures)]
    contribs = []
    for e in exposures:
        T_allow = allowable_time(e["level"], params["rate"], params["criterion"])
        contribs.append(100.0 * e["hours"] / T_allow if T_allow > 0 else 0.0)
    fig_bar = go.Figure(data=[go.Bar(x=labels, y=contribs, marker_color="#1f77b4", text=[f"{v:.1f}%" for v in contribs], textposition="outside")])
    fig_bar.update_layout(title="سهم هر بازه در دوز روزانه", yaxis_title="سهم (%)", height=380)
    st.plotly_chart(fig_bar, use_container_width=True)

fig_gauge = go.Figure(go.Indicator(
    mode="gauge+number",
    value=dose,
    number={"suffix": "%"},
    title={"text": "دوز روزانه در برابر آستانه‌ها"},
    gauge={
        "axis": {"range": [0, 200]},
        "bar": {"color": risk_color},
        "steps": [
            {"range": [0, 50], "color": "#d4edda"},
            {"range": [50, 85], "color": "#fff3cd"},
            {"range": [85, 100], "color": "#ffe5b4"},
            {"range": [100, 200], "color": "#f8d7da"},
        ],
        "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": 100},
    },
))
fig_gauge.update_layout(height=320)
st.plotly_chart(fig_gauge, use_container_width=True)

# حفاظت شنوایی
if dose >= 85:
    st.subheader("🛡️ حفاظت شنوایی")
    nrr_input = st.number_input("NRR حفاظ", min_value=0.0, max_value=40.0, value=25.0, step=1.0)
    ptype = st.selectbox("نوع حفاظ", ["earmuff", "foam", "other"], index=0)
    nrr_der = nrr_derated(nrr_input, ptype)
    protected_twa = twa - nrr_der
    c1, c2 = st.columns(2)
    c1.metric("NRR کاهش‌یافته", f"{nrr_der:.1f} dB")
    c2.metric("TWA مؤثر با حفاظ", f"{max(protected_twa, 0):.1f} dBA")
    if protected_twa <= params["criterion"]:
        st.success(f"✅ با این حفاظ، TWA به {protected_twa:.1f} dBA کاهش می‌یابد.")
    else:
        st.error(f"❌ حتی با حفاظ، TWA ({protected_twa:.1f} dBA) بالای حد مجاز است.")

# خروجی اکسل
st.divider()
st.subheader("📥 خروجی گزارش")
output_rows = []
for i, e in enumerate(exposures, 1):
    T_allow = allowable_time(e["level"], params["rate"], params["criterion"])
    contrib = 100.0 * e["hours"] / T_allow if T_allow > 0 else 0.0
    output_rows.append({
        "بازه": i,
        "تراز (dBA)": round(e["level"], 1),
        "مدت (ساعت)": round(e["hours"], 1),
        "زمان مجاز (ساعت)": round(T_allow, 2),
        "سهم از دوز (%)": round(contrib, 1),
    })

df_out = pd.DataFrame(output_rows)
summary = pd.DataFrame([{
    "استاندارد": standard,
    "حد مجاز (dBA)": params["criterion"],
    "نرخ تبادل (dB)": params["rate"],
    "دوز (%)": round(dose, 1),
    "TWA (dBA)": round(twa, 1),
    "LEX,8h (dBA)": round(lex, 1),
    "سطح ریسک": risk_label,
}])

buffer = BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
    summary.to_excel(writer, sheet_name="خلاصه", index=False)
    df_out.to_excel(writer, sheet_name="تفصیل", index=False)

st.download_button(
    label="📊 دانلود گزارش Excel",
    data=buffer.getvalue(),
    file_name="noise_report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

st.caption("بر اساس OSHA 29 CFR 1910.95، NIOSH REL و ACGIH TLV.")
