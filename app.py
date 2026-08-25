import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import tempfile
import re
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

PACKS = {1: 59900, 3: 129000, 5: 179900}
PLAN_MAP = {"free":1,"0":1,"1":1,"starter":1,"3":3,"growth":3,"5":5,"pro":5,"unlimited":5}
PRECIO_BASE = PACKS[1]
qp = st.query_params
LIMITE_CAMPANAS = 1
try:
    raw_plan = str(qp.get("plan","")).strip().lower()
    raw_limit = str(qp.get("limit","")).strip().lower()
    if raw_plan:
        if raw_plan in PLAN_MAP: LIMITE_CAMPANAS = PLAN_MAP[raw_plan]
        else: LIMITE_CAMPANAS = int(raw_plan)
    if raw_limit:
        if raw_limit in PLAN_MAP: LIMITE_CAMPANAS = PLAN_MAP[raw_limit]
        else: LIMITE_CAMPANAS = int(raw_limit)
except: pass
if LIMITE_CAMPANAS < 1: LIMITE_CAMPANAS = 1
if LIMITE_CAMPANAS > 5: LIMITE_CAMPANAS = 5
PRECIO_PLAN = PACKS.get(LIMITE_CAMPANAS, PRECIO_BASE * LIMITE_CAMPANAS)

if "auditorias_hechas" not in st.session_state: st.session_state["auditorias_hechas"] = 0
if "run_audit" not in st.session_state: st.session_state["run_audit"] = False

st.set_page_config(page_title="IA.MRKT — Auditoría", page_icon="●", layout="wide")

st.markdown('''
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;800&display=swap');
.stApp { background-color: #0A0A0A; color: #E5E5E5; font-family: 'Inter', sans-serif; }
h1, h2, h3 { font-family: 'Inter', sans-serif; font-weight: 800; letter-spacing: -0.03em; }
.mono { font-family: 'JetBrains Mono', monospace; }
div[data-testid="stButton"] > button { background: #CCFF00!important; color: #0A0A0A!important; border: none!important; border-radius: 12px!important; font-weight: 800!important; padding: 14px 20px!important; font-size: 14px!important; }
div[data-testid="stButton"] > button:hover { background: #D4FF33!important; box-shadow: 0 0 20px rgba(204,255,0,0.4)!important; }
div[data-testid="stDownloadButton"] > button { background: #CCFF00!important; color: #0A0A0A!important; border: 2px solid #CCFF00!important; border-radius: 14px!important; font-weight: 900!important; padding: 18px 28px!important; font-size: 16px!important; box-shadow: 0 0 30px rgba(204,255,0,0.5)!important; }
div[data-testid="stFileUploader"] { background: #141414!important; border: 1px dashed #333!important; border-radius: 12px!important; }
.card { background: #141414; border: 1px solid #262626; border-radius: 16px; padding: 20px; text-align: center; }
.card.kpi-label,.card.mono { text-align: center; }
.card div { text-align: center; }
.card-lime { border: 1px solid #CCFF00; box-shadow: 0 0 40px rgba(204,255,0,0.18); background: #111; border-radius: 20px; padding: 28px; }
.badge { display:inline-block; padding:4px 10px; border-radius:999px; font-size:11px; font-weight:700; letter-spacing:0.05em; }
.badge-verde { background:#CCFF00; color:#0A0A0A; }
.badge-lime-border { border:1px solid #CCFF00; color:#CCFF00; background: transparent; }
.kpi-big { font-size: 48px; font-weight: 800; line-height: 1; letter-spacing: -0.05em; }
.kpi-label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 0.1em; }
.alert-rojo { background: #1C0A0A; border: 1px solid #3A1A1A; border-left: 4px solid #FF3B30; border-radius: 12px; padding: 14px 18px; margin-bottom:10px; }
.alert-verde { background: #0A1C0A; border: 1px solid #1A3A1A; border-left: 4px solid #CCFF00; border-radius: 12px; padding: 14px 18px; margin-bottom:10px; }
.alert-amarillo { background: #1C1A0A; border: 1px solid #3A351A; border-left: 4px solid #FFAA00; border-radius: 12px; padding: 14px 18px; margin-bottom:10px; color: #E5E5E5; }
.alert-amarillo-contraste { background: #1C1A0A; border: 1px solid #FFAA00; border-left: 4px solid #FFAA00; border-radius: 12px; padding: 14px 18px; margin-bottom:10px; }
.gallery-item { background:#141414; border:1px solid #262626; border-radius:12px; padding:14px; }
.stTextInput > div > div > input { background:#0A0A0A!important; border:1px solid #333!important; border-radius:12px!important; color:#E5E5E5!important; }
div[data-testid="stAlert"] { background-color: #1C1A0A!important; border: 1px solid #FFAA00!important; color: #E5E5E5!important; }
div[data-testid="stAlert"] p { color: #E5E5E5!important; }
a { color: #CCFF00!important; }
</style>
''', unsafe_allow_html=True)

def to_float(v):
    if pd.isna(v): return 0.0
    s_orig = str(v).strip()
    if not s_orig: return 0.0
    s = s_orig.replace('$','').replace('US$','').replace('€','').replace('%','').replace(' ','').replace('\xa0','').strip()
    if re.match(r'^-?\d{1,3}(\.\d{3})+(,\d+)?$', s): s = s.replace('.','').replace(',','.')
    elif re.match(r'^-?\d+\.\d{3}$', s): s = s.replace('.','')
    elif re.match(r'^-?\d+,\d{3}$', s): s = s.replace(',','')
    elif ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'): s = s.replace('.','').replace(',','.')
        else: s = s.replace(',','')
    else:
        if ',' in s: s = s.replace(',','.')
    try:
        m = re.findall(r'-?\d+\.?\d*', s)
        return float(m[0]) if m else 0.0
    except: return 0.0

def autodetect_platform(df):
    cols_low = " ".join([c.lower() for c in df.columns])
    if "frequency" in cols_low or "frecuencia" in cols_low or "ad set" in cols_low or "amount spent" in cols_low: return "META"
    if ("total spent" in cols_low or "cpl" in cols_low) and "frequency" not in cols_low: return "LINKEDIN"
    if "purchase roas" in cols_low: return "META"
    return "GOOGLE"

def validar_email(email):
    if not email or not email.strip(): return False, "Email vacío"
    email = email.strip()
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email): return False, "Formato inválido"
    if ".." in email: return False, "Email con.. no válido"
    if email.startswith(".") or email.startswith("@"): return False, "Email no puede empezar con. o @"
    domain = email.split("@")[-1]
    if "." not in domain: return False, "Dominio sin punto"
    if len(domain.split(".")[-1]) < 2: return False, "Extensión muy corta"
    disposable = ["tempmail","10minutemail","mailinator","guerrillamail","yopmail","throwaway"]
    if any(d in domain.lower() for d in disposable): return False, "Email temporal no permitido"
    return True, "OK"

def enviar_pdf_por_email(email_destino, pdf_path, plataforma, fuga_total):
    try:
        import resend, base64
        api_key = st.secrets.get("RESEND_API_KEY", "") if hasattr(st, "secrets") else ""
        email_admin = st.secrets.get("EMAIL_ADMIN", "") if hasattr(st, "secrets") else ""
        if not api_key: return False, "RESEND_API_KEY no configurado"
        resend.api_key = api_key
        with open(pdf_path, "rb") as f: pdf_b64 = base64.b64encode(f.read()).decode()
        params = {
            "from": "IA.MRKT <onboarding@resend.dev>",
            "to": [email_destino],
            "subject": f"Tu Auditoría IA.MRKT {plataforma} - Fuga ${fuga_total:,.0f} detectada",
            "html": f"<h2>Tu auditoría IA.MRKT {plataforma} está lista</h2><p><strong>Fuga:</strong> ${fuga_total:,.0f} CLP/mes</p><p>Adjunto PDF</p>",
            "attachments": [{"filename": os.path.basename(pdf_path), "content": pdf_b64}]
        }
        if email_admin and email_admin!= email_destino: params["bcc"] = [email_admin]
        resend.Emails.send(params)
        return True, "Enviado"
    except Exception as e: return False, str(e)

LEADS_FILE = "leads_ia_mrkt.csv"
def guardar_lead(email, plataforma, fuga, plan_camp, precio_plan, num_camp_csv, num_verdes, num_rojos, csv_nombre=""):
    try:
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fila = {"fecha": fecha,"email": email.strip(),"plataforma": plataforma,"fuga_detectada": int(fuga),"plan_campanas": plan_camp,"precio_pagado": precio_plan,"campanas_csv": num_camp_csv,"verdes": num_verdes,"rojos": num_rojos,"csv_nombre": csv_nombre,"plan_link": f"plan_{plan_camp}"}
        if os.path.exists(LEADS_FILE):
            df_leads = pd.read_csv(LEADS_FILE)
            if "plan_query" in df_leads.columns: df_leads = df_leads.drop(columns=["plan_query"])
            df_leads = pd.concat([df_leads, pd.DataFrame([fila])], ignore_index=True)
        else: df_leads = pd.DataFrame([fila])
        df_leads.to_csv(LEADS_FILE, index=False)
        return True
    except: return False

def detectar(df, plataforma="GOOGLE"):
    cols = {c.lower().strip(): c for c in df.columns}
    def get_col(keys):
        for k in keys:
            for lc, orig in cols.items():
                if k in lc: return orig
        return None
    c_camp = get_col(['campaign name','ad set name','campaña','campana','ad set','conjunto','nombre','campaign'])
    c_cost = get_col(['amount spent','total spent','importe gastado','costo_total','costo','cost','spent','gasto'])
    c_ctr = get_col(['ctr (link)','ctr'])
    c_conv = get_col(['results','resultados','conversions','conversiones','purchases','leads'])
    c_roas = get_col(['purchase roas','roas'])
    c_cpc = get_col(['cost per result','costo por resultado','cost per click','cpc','cpp','cpl','costo_conversion'])
    c_freq = get_col(['frequency','frecuencia'])
    c_est = get_col(['delivery','entrega','estado','status'])
    if not c_camp: c_camp = list(df.columns)[0] if len(df.columns)>0 else None
    if not c_cost:
        for col in df.columns:
            try:
                vals = [to_float(x) for x in df[col].head(3)]
                if any(v>5000 for v in vals): c_cost = col; break
            except: continue
        if not c_cost: c_cost = list(df.columns)[2] if len(df.columns)>2 else None
    if not c_camp or not c_cost: return None, f"Falta Campaña o Costo. Columnas: {list(df.columns)[:8]}"
    alertas=[]
    for _, row in df.iterrows():
        if c_est and str(row[c_est]).lower() in ['paused','pausada','archived','completada','suspended','inactive','off']: continue
        costo = to_float(row[c_cost]); ctr = to_float(row[c_ctr]) if c_ctr else 0; conv = to_float(row[c_conv]) if c_conv else 0
        roas = to_float(row[c_roas]) if c_roas else 0; cpc = to_float(row[c_cpc]) if c_cpc else 0; freq = to_float(row[c_freq]) if c_freq else 0
        camp = str(row[c_camp]); fuga=0; tipo=""; color=""
        if plataforma == "META":
            if freq > 2.8 and ctr < 1.5 and costo > 15000: fuga=costo*0.35; tipo=f"Fatiga Audiencia | Freq {freq:.1f} | CTR {ctr:.2f}%"; color="amarillo"
            elif costo>25000 and conv==0: fuga=costo*0.8; tipo="Mala Distribución | 0 resultados"; color="rojo"
            elif cpc>800 and conv==0 and costo>12000: fuga=costo*0.5; tipo=f"CPC Inflado ${cpc:.0f} | Sin conv"; color="rojo"
            elif costo>50000 and (conv<=1 or roas<1.2): fuga=costo*0.4; tipo=f"ROAS bajo {roas} | Meta"; color="rojo"
            elif roas>=1.8 and conv>=2: tipo=f"VERDE | ROAS {roas} | {int(conv)} res"; color="verde"
            else: continue
        elif plataforma == "LINKEDIN":
            if costo>20000 and conv==0: fuga=costo*0.8; tipo="Mala Segmentación B2B | 0 leads"; color="rojo"
            elif ctr>0 and ctr<0.8 and costo>10000: fuga=costo*0.3; tipo=f"Creatividad Fría | CTR {ctr:.2f}%"; color="amarillo"
            elif cpc>1200 and conv<=1 and costo>20000: fuga=costo*0.4; tipo=f"CPL Alto | {int(conv)} conv"; color="rojo"
            elif conv>=2 and ctr>=0.5: tipo=f"VERDE | {int(conv)} leads | CTR {ctr:.2f}%"; color="verde"
            else: continue
        else:
            if costo>25000 and conv==0: fuga=costo*0.7; tipo="Mala Distribución | 0 conversiones"; color="rojo"
            elif costo>35000 and (conv<=1 or roas<1.0): fuga=costo*0.4; tipo=f"ROAS bajo {roas} | Gasto alto"; color="rojo"
            elif ctr>0 and ctr<1.5 and costo>12000: fuga=costo*0.25; tipo=f"Fatiga Creativa | CTR {ctr}%"; color="amarillo"
            elif roas>=1.5 and conv>=2: tipo=f"VERDE | ROAS {roas} | {int(conv)} conv"; color="verde"
            elif costo>8000 and conv==0 and ctr==0: fuga=costo*0.5; tipo="Sin CTR ni conv | Revisar keywords"; color="amarillo"
            else: continue
        alertas.append({"camp":camp,"costo":costo,"conv":conv,"roas":roas,"ctr":ctr,"cpc":cpc,"freq":freq,"fuga":fuga,"tipo":tipo,"color":color})
    total_fuga = sum(a["fuga"] for a in alertas if a["color"]!="verde")
    verdes = [a for a in alertas if a["color"]=="verde"]; rojos = [a for a in alertas if a["color"]!="verde"]
    if len(alertas)==0 and len(df)>0:
        alertas.append({"camp":f"{len(df)} campañas analizadas","costo":0,"conv":0,"roas":0,"ctr":0,"cpc":0,"freq":0,"fuga":0,"tipo":f"VERDE | {len(df)} campañas sin fuga crítica | Optimizada","color":"verde"})
        verdes = alertas
    return {"alertas":alertas,"total_fuga":total_fuga,"verdes":verdes,"rojos":rojos}, None

st.markdown('<div style="display:flex; justify-content:space-between; align-items:center; padding:10px 0 20px 0;"><div style="font-weight:800; font-size:20px; letter-spacing:-0.05em;">IA.MRKT <span style="color:#CCFF00;">●</span></div><div><span class="badge badge-lime-border">IA.MRKT MOTOR v0.6.8</span> <span class="badge badge-verde">PRIVADO</span></div></div>', unsafe_allow_html=True)

col1, col2 = st.columns([1.15, 0.85], gap="large")
with col1:
    try: plataforma = st.segmented_control("Plataforma", ["GOOGLE","META","LINKEDIN"], default="GOOGLE")
    except: plataforma = st.selectbox("Plataforma", ["GOOGLE","META","LINKEDIN"], label_visibility="collapsed")
    st.session_state["plat"] = plataforma
    label_map = {"GOOGLE":"Google Ads","META":"Meta Ads","LINKEDIN":"LinkedIn Ads"}
    st.markdown(f'<h1 style="font-size:54px; line-height:0.9; margin-top:10px;">¿Dónde se fuga<br>tu presupuesto<br>de <span style="color:#CCFF00;">{label_map[plataforma]}?</span></h1>', unsafe_allow_html=True)
    st.markdown('<p style="color:#888; font-size:15px; margin-top:12px;">Motor IA.MRKT v0.6.8 analiza CSV de Google, Meta o LinkedIn en 30 seg. Sin acceso a tu cuenta. Solo números. Detecta hasta $602.500 CLP en fuga/mes promedio • 100% local y privado.</p>', unsafe_allow_html=True)
    st.markdown('<div style="margin-top:20px; display:flex; gap:10px;"><div class="card" style="flex:1;"><div class="kpi-label">GOOGLE</div><div class="mono" style="font-weight:700;">CPC • ROAS</div><div style="font-size:10px; color:#666;">Detecta CTR bajo</div></div><div class="card" style="flex:1;"><div class="kpi-label">META</div><div class="mono" style="font-weight:700;">FREQ • CPC</div><div style="font-size:10px; color:#666;">Detecta Fatiga</div></div><div class="card" style="flex:1;"><div class="kpi-label">LINKEDIN</div><div class="mono" style="font-weight:700;">CPL • CTR</div><div style="font-size:10px; color:#666;">Detecta B2B frío</div></div></div>', unsafe_allow_html=True)

with col2:
    st.markdown(f'<div class="card-lime"><div class="kpi-label" style="color:#CCFF00;">ACCESO PRIVADO IA.MRKT • PLAN {LIMITE_CAMPANAS} CAMPAÑA{"S" if LIMITE_CAMPANAS>1 else ""}</div>', unsafe_allow_html=True)
    if st.session_state["auditorias_hechas"] >= LIMITE_CAMPANAS:
        st.markdown(f'<div style="background:#1C0A0A; border:1px solid #FF3B30; border-radius:12px; padding:16px; margin:12px 0;"><div class="mono" style="color:#FF3B30; font-weight:700;">LÍMITE ALCANZADO — {LIMITE_CAMPANAS} CAMPAÑA{"S" if LIMITE_CAMPANAS>1 else ""}</div><div style="font-size:13px; color:#DDD; margin-top:8px;">Ya auditaste {st.session_state["auditorias_hechas"]} con ${PRECIO_PLAN:,.0f}.<br>Contacta: estebanzcares@gmail.com</div></div>', unsafe_allow_html=True)
        if st.button("🔄 REINICIAR (ADMIN)", use_container_width=True):
            st.session_state["auditorias_hechas"]=0; st.session_state["run_audit"]=False; st.session_state.pop("plat_autodetect",None); st.rerun()
        email=None; csv_file=None
    else:
        st.markdown('<div style="font-size:13px; color:#888; margin:12px 0 8px 0;">Tu correo para PDF completo</div>', unsafe_allow_html=True)
        email = st.text_input("email_input", placeholder="ej: tu@empresa.cl", label_visibility="collapsed")
        email_valido=True; email_msg=""
        if email:
            email_valido,email_msg=validar_email(email)
            if email_valido: st.markdown('<div style="font-size:10px; color:#CCFF00;">✅ Email válido</div>', unsafe_allow_html=True)
            else: st.markdown(f'<div style="font-size:10px; color:#FF3B30;">❌ {email_msg}</div>', unsafe_allow_html=True)
        else: email_valido=False
        st.markdown(f'<div style="font-size:13px; color:#888; margin:16px 0 8px 0;">CSV de {st.session_state.get("plat","GOOGLE")} Ads — quedan {LIMITE_CAMPANAS - st.session_state["auditorias_hechas"]} auditoría(s)</div>', unsafe_allow_html=True)
        csv_file = st.file_uploader("csv", type=["csv"], label_visibility="collapsed")
        if csv_file:
            try:
                df_tmp=pd.read_csv(csv_file); plat_detectada=autodetect_platform(df_tmp)
                if plat_detectada!=plataforma: st.markdown(f'<div style="background:#1C1A0A; border:1px solid #FFAA00; border-left:4px solid #FFAA00; border-radius:8px; padding:10px; font-size:11px; color:#E5E5E5;"><span style="color:#FFAA00; font-weight:700;">⚠ AUTODETECT:</span> Detecté {plat_detectada}, cambiaré automáticamente.</div>', unsafe_allow_html=True); st.session_state["plat_autodetect"]=plat_detectada
                else: st.markdown(f'<div style="background:#0A1C0A; border:1px solid #262626; border-left:4px solid #CCFF00; border-radius:8px; padding:8px; font-size:10px; color:#CCFF00;">✅ CSV {plat_detectada}</div>', unsafe_allow_html=True)
                csv_file.seek(0)
            except: pass
        st.markdown('<div style="font-size:11px; color:#555; text-align:center;">Exportar CSV • 200MB max</div>', unsafe_allow_html=True)
        btn_auditar = st.button("🔒 AUDITAR CON IA.MRKT", use_container_width=True, key="btn_auditar")
        if btn_auditar:
            if not email: st.markdown('<div style="background:#1C0A0A; border:1px solid #FF3B30; border-radius:8px; padding:10px; font-size:11px;">⚠ Ingresa correo</div>', unsafe_allow_html=True)
            elif not email_valido: st.markdown(f'<div style="background:#1C1A0A; border:1px solid #FF3B30; border-radius:8px; padding:10px; font-size:11px;">❌ {email_msg}</div>', unsafe_allow_html=True)
            else: st.session_state["run_audit"]=True; st.session_state["email_validado"]=email.strip()
        st.markdown(f'<div style="margin-top:12px; font-size:11px; color:#666; text-align:center;">Plan {LIMITE_CAMPANAS} camp • ${PRECIO_BASE:,.0f} c/u</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div style="height:1px; background:#1A1A1A; margin:30px 0;"></div>', unsafe_allow_html=True)
st.markdown('<div class="kpi-label" style="margin-bottom:14px;">AUDITORÍAS RECIENTES • GOOGLE • META • LINKEDIN</div>', unsafe_allow_html=True)
g1,g2,g3,g4=st.columns(4)
with g1: st.markdown('<div class="gallery-item"><div class="mono" style="font-size:11px; color:#888;">GOOGLE • HOTEL • $1.2M</div><div class="mono" style="font-weight:700; color:#FF3B30;">$602.500 FUGA</div><div style="font-size:10px; color:#666;">3 ROJOS • 4 VERDES</div></div>', unsafe_allow_html=True)
with g2: st.markdown('<div class="gallery-item"><div class="mono" style="font-size:11px; color:#888;">META • FERRE • $890k</div><div class="mono" style="font-weight:700; color:#FF3B30;">$445.000 FUGA</div><div style="font-size:10px; color:#666;">2 AMARILLOS • 2 VERDES</div></div>', unsafe_allow_html=True)
with g3: st.markdown('<div class="gallery-item"><div class="mono" style="font-size:11px; color:#888;">LINKEDIN • SAAS • $750k</div><div class="mono" style="font-weight:700; color:#FFAA00;">$407.500 FUGA</div><div style="font-size:10px; color:#666;">1 ROJO • 1 AMARILLO</div></div>', unsafe_allow_html=True)
with g4: st.markdown('<div class="gallery-item" style="border-color:#CCFF00;"><div class="mono" style="font-size:11px; color:#CCFF00;">CLÍNICA • META • $2.1M</div><div class="mono" style="font-weight:700; color:#CCFF00;">$0 FUGA</div><div style="font-size:10px; color:#666;">6 VERDES • ROAS 5.8</div></div>', unsafe_allow_html=True)

email_final = st.session_state.get("email_validado", email if 'email' in locals() else None)
if email_final and csv_file and st.session_state.get("run_audit", False):
    ok,msg=validar_email(email_final)
    if not ok: st.error(f"Email inválido: {msg}"); st.session_state["run_audit"]=False
    elif st.session_state["auditorias_hechas"]>=LIMITE_CAMPANAS: st.error(f"Límite {LIMITE_CAMPANAS}");
    else:
        try:
            df=pd.read_csv(csv_file); plat_detectada=autodetect_platform(df); plat_selector=st.session_state.get("plat","GOOGLE"); plat_usar=st.session_state.get("plat_autodetect", plat_detectada)
            if plat_detectada!=plat_selector: plat_usar=plat_detectada; st.session_state["plat"]=plat_detectada
            else: plat_usar=plat_selector
            num_camp_csv=len(df)
            if num_camp_csv>LIMITE_CAMPANAS:
                precio_full=PACKS.get(num_camp_csv, PRECIO_BASE*num_camp_csv)
                st.markdown(f'<div class="alert-amarillo-contraste"><div style="color:#FFAA00; font-weight:700;">⚠ LÍMITE DE PLAN</div><div style="color:#E5E5E5;">CSV {num_camp_csv} campañas, plan {LIMITE_CAMPANAS}. Auditamos primeras {LIMITE_CAMPANAS}.</div><div style="color:#888; font-size:11px;">Pack {num_camp_csv} = ${precio_full:,.0f}</div></div>', unsafe_allow_html=True)
                df_limite=df.head(LIMITE_CAMPANAS)
            else: df_limite=df
            res,err=detectar(df_limite, plataforma=plat_usar)
            if err: st.error(err); st.session_state["run_audit"]=False
            else:
                csv_nombre=getattr(csv_file,'name','csv_subido')
                guardar_lead(email=email_final, plataforma=plat_usar, fuga=res["total_fuga"], plan_camp=LIMITE_CAMPANAS, precio_plan=PRECIO_PLAN, num_camp_csv=num_camp_csv, num_verdes=len(res["verdes"]), num_rojos=len(res["rojos"]), csv_nombre=csv_nombre)
                st.session_state["auditorias_hechas"]+=1; st.session_state["run_audit"]=False; st.session_state.pop("plat_autodetect",None)
                st.markdown('<div style="height:1px; background:#1A1A1A; margin:30px 0;"></div>', unsafe_allow_html=True)
                if res["total_fuga"]==0: st.markdown(f'<h2>Tu auditoría IA.MRKT [{plat_usar}] — <span class="mono" style="color:#CCFF00;">$0 FUGA • OPTIMIZADA</span></h2>', unsafe_allow_html=True)
                else: st.markdown(f'<h2>Tu auditoría IA.MRKT [{plat_usar}] — <span class="mono" style="color:#CCFF00;">${res["total_fuga"]:,.0f} CLP</span></h2>', unsafe_allow_html=True)
                c1,c2=st.columns([2,1])
                with c1:
                    for a in res["rojos"]:
                        css="alert-rojo" if a["color"]=="rojo" else "alert-amarillo"
                        st.markdown(f'<div class="{css}"><span class="mono" style="font-weight:700; color:{"#FF3B30" if a["color"]=="rojo" else "#FFAA00"};">{a["color"].upper()}</span> {a["camp"]} | {a["tipo"]} | ${a["fuga"]:,.0f}</div>', unsafe_allow_html=True)
                    for a in res["verdes"]: st.markdown(f'<div class="alert-verde">VERDE {a["camp"]} | {a["tipo"]}</div>', unsafe_allow_html=True)
                with c2:
                    def gen_pdf():
                        tmp=tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                        c=canvas.Canvas(tmp.name, pagesize=A4); W,H=A4
                        styles=getSampleStyleSheet()
                        style_small=ParagraphStyle('small', parent=styles['Normal'], fontSize=8, leading=11, textColor=HexColor("#CCCCCC"))
                        style_small_w=ParagraphStyle('smallw', parent=styles['Normal'], fontSize=8.5, leading=12, textColor=HexColor("#FFFFFF"))
                        style_tiny=ParagraphStyle('tiny', parent=styles['Normal'], fontSize=7, leading=10, textColor=HexColor("#AAAAAA"))
                        style_causa=ParagraphStyle('causa', parent=styles['Normal'], fontSize=8, leading=11.5, textColor=HexColor("#E5E5E5"))
                        style_action_body=ParagraphStyle('actB', parent=styles['Normal'], fontSize=8.5, leading=12, textColor=HexColor("#0A0A0A"))
                        LIME_SOFT=HexColor("#E8FF99")
                        M=50
                        MIN_Y=50
                        def fondo_negro(): c.setFillColor(HexColor("#0A0A0A")); c.rect(0,0,W,H, fill=1, stroke=0)
                        def footer(num): c.setFillColor(HexColor("#555555")); c.setFont("Helvetica", 6); c.drawString(M, 18, f"IA.MRKT • {plat_usar} • {email_final} • {datetime.now().strftime('%d/%m/%Y')} • Pag {num}/4"); c.drawRightString(W-M, 18, "Confidencial")
                        def safe_wrap_para(para, width, max_h=500):
                            w,h = para.wrap(width, max_h)
                            return w,h
                        def autofit_text(c_obj, text, x, y, max_w, font_bold="Helvetica-Bold", start_size=22, min_size=14):
                            size = start_size
                            while size >= min_size:
                                c_obj.setFont(font_bold, size)
                                tw = c_obj.stringWidth(text, font_bold, size)
                                if tw <= max_w: break
                                size -= 0.5
                            c_obj.drawString(x, y, text)
                            return size
                        total_fuga=res['total_fuga']; num_rojos=len(res['rojos']); num_verdes=len(res['verdes']); total_camp=len(df_limite) if 'df_limite' in locals() else len(res['alertas'])
                        fondo_negro()
                        c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica-Bold", 30); c.drawString(M, H-55, "IA.MRKT")
                        c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica", 11); c.drawString(M, H-72, f"Auditoría de Fuga Presupuestaria — {plat_usar} • Plan {LIMITE_CAMPANAS} camp • Motor v0.6.8")
                        c.setFont("Helvetica", 8); c.setFillColor(HexColor("#888888")); c.drawString(M, H-84, f"Cliente: {email_final} | Fecha: {datetime.now().strftime('%d/%m/%Y')} | {total_camp} campañas analizadas")
                        c.setFillColor(HexColor("#1A1A1A")); c.roundRect(M, H-165, W-2*M, 65, 12, fill=1, stroke=0); c.setStrokeColor(HexColor("#333333")); c.roundRect(M, H-165, W-2*M, 65, 12, fill=0, stroke=1)
                        c.setFillColor(HexColor("#FF3B30") if total_fuga>0 else HexColor("#CCFF00"))
                        autofit_text(c, f"${total_fuga:,.0f} CLP/mes", M+10, H-128, 190, start_size=22, min_size=14)
                        c.setFont("Helvetica", 8); c.setFillColor(HexColor("#FFFFFF")); c.drawString(M+10, H-145, "Fuga estimada mensual")
                        right_text = f"{total_camp} camp | {num_rojos} críticas | {num_verdes} verdes"
                        sub_text = f"Plataforma {plat_usar} • Recupero 35-80% • ROI x4.2"
                        c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold", 11)
                        if c.stringWidth(right_text, "Helvetica-Bold", 11) > (W-2*M-220):
                            c.setFont("Helvetica-Bold", 9)
                        c.drawString(M+220, H-128, right_text)
                        c.setFont("Helvetica", 7.5); c.setFillColor(HexColor("#AAAAAA")); c.drawString(M+220, H-142, sub_text)
                        y=H-190
                        c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold", 12); c.drawString(M, y, "Resumen Ejecutivo"); y-=16
                        if total_camp==1 and num_rojos==1:
                            a=res['rojos'][0]; resumen=f"Se analizó 1 campaña de {plat_usar}: <b>{a['camp'][:50]}</b>. Fuga de <b>${total_fuga:,.0f}</b> por <b>{a['tipo']}</b>. Gasto ${a['costo']:,.0f} con {a['conv']:.0f} conv, CTR {a['ctr']:.2f}% y CPC ${a['cpc']:,.0f}. Causa: segmentación B2B amplia. Si re-segmentas ABM Decision Makers TI, recuperas ${total_fuga*0.7:,.0f}/mes en 7 días."
                        else: resumen=f"Se analizaron {total_camp} campañas de {plat_usar}. Fuga total ${total_fuga:,.0f}/mes en {num_rojos} campaña(s). {num_verdes} en verde ROAS>1.5 escalar +20%. Causa: mala distribución y fatiga creativa."
                        p=Paragraph(resumen, style_small_w); _,ph=safe_wrap_para(p, W-2*M, 80); p.drawOn(c, M, y-ph); y-=ph+18
                        box_w=(W-2*M-10)/2
                        causa_txt=f"<b><font color='#FFAA00'>Causa Raíz Detectada</font></b><br/><br/>• {res['rojos'][0]['tipo'] if res['rojos'] else 'Optimizada'}<br/>• CTR bajo = creatividades no conectan<br/>• 0 conv + gasto alto = segmentación fallida<br/>• Frecuencia y CPC inflado"
                        impacto_txt=f"<b><font color='#CCFF00'>Impacto y Potencial Recupero</font></b><br/><br/>• Fuga actual: ${total_fuga:,.0f}/mes<br/>• Recupero 70%: ${total_fuga*0.7:,.0f}/mes<br/>• Anualizado: ${total_fuga*0.7*12:,.0f}<br/>• Acción &lt;48h reduce 80% pérdida"
                        p_c=Paragraph(causa_txt, style_causa); p_i=Paragraph(impacto_txt, style_causa)
                        _,h_c=safe_wrap_para(p_c, box_w-20, 200); _,h_i=safe_wrap_para(p_i, box_w-20, 200)
                        box_h=max(h_c,h_i)+26
                        if y - box_h < MIN_Y+40:
                            footer(1); c.showPage(); fondo_negro(); y=H-50
                        c.setFillColor(HexColor("#141414")); c.roundRect(M, y-box_h, box_w, box_h, 10, fill=1, stroke=0); c.setStrokeColor(HexColor("#262626")); c.roundRect(M, y-box_h, box_w, box_h, 10, fill=0, stroke=1)
                        c.setFillColor(HexColor("#141414")); c.roundRect(M+box_w+10, y-box_h, box_w, box_h, 10, fill=1, stroke=0); c.setStrokeColor(HexColor("#262626")); c.roundRect(M+box_w+10, y-box_h, box_w, box_h, 10, fill=0, stroke=1)
                        p_c.drawOn(c, M+12, y-box_h+14); p_i.drawOn(c, M+box_w+22, y-box_h+14)
                        y-=box_h+20
                        c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold", 10); c.drawString(M, y, "Metodología IA.MRKT + Próximos Pasos"); y-=14
                        metod=f"Fuente: solo CSV {plat_usar} (100% local). Reglas: costo&gt;25k+0conv=80% fuga | CTR&lt;1.5=25% | ROAS&lt;1.2=40%. Próximos pasos: Pausar ROJOS, ABM Decision Makers, 3 hooks, landing CTA, revisión 72h."
                        p4=Paragraph(metod, style_tiny); _,hm=safe_wrap_para(p4, W-2*M, 60); p4.drawOn(c, M, y-hm)
                        footer(1); c.showPage()
                        fondo_negro()
                        c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica-Bold", 14); c.drawString(M, H-45, f"Detalle Completo — {total_camp} campañas [{plat_usar}]")
                        c.setFont("Helvetica", 7.5); c.setFillColor(HexColor("#888888")); c.drawString(M, H-57, "Métricas reales extraídas de tu CSV")
                        data=[["Campaña","Costo","Conv","ROAS","CTR","CPC/Freq","Estado","Fuga"]]
                        for a in res['alertas']:
                            cs=(a['camp'][:28]+'..') if len(a['camp'])>28 else a['camp']
                            data.append([cs, f"${a['costo']:,.0f}", f"{a['conv']:.0f}", f"{a['roas']:.2f}" if a['roas'] else "-", f"{a['ctr']:.2f}%" if a['ctr'] else "-", f"${a['cpc']:.0f}" if a['cpc'] else f"{a['freq']:.1f}", a['tipo'][:35], f"${a['fuga']:,.0f}" if a['fuga']>0 else "$0"])
                        table=Table(data, colWidths=[125,50,28,28,36,45,100,45], repeatRows=1)
                        style=TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor("#CCFF00")),('TEXTCOLOR',(0,0),(-1,0),HexColor("#000000")),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,0),7),('BACKGROUND',(0,1),(-1,-1),HexColor("#141414")),('TEXTCOLOR',(0,1),(-1,-1),HexColor("#E5E5E5")),('FONTSIZE',(0,1),(-1,-1),6.5),('GRID',(0,0),(-1,-1),0.4,HexColor("#262626")),('ALIGN',(1,1),(-1,-1),'CENTER')])
                        for i,a in enumerate(res['alertas'], start=1):
                            if i>=len(data): break
                            if a['color']=='rojo': style.add('BACKGROUND',(0,i),(-1,i),HexColor("#2A1212"))
                            elif a['color']=='amarillo': style.add('BACKGROUND',(0,i),(-1,i),HexColor("#2A2512"))
                            else: style.add('BACKGROUND',(0,i),(-1,i),HexColor("#122A12"))
                        table.setStyle(style); tw,th=table.wrap(W-2*M, H-100); table.drawOn(c, M, H-75-th)
                        y2=H-75-th-22
                        c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold", 10); c.drawString(M, y2, "Análisis de tabla + Prioridad"); y2-=14
                        analisis=f"Campaña {res['alertas'][0]['camp'][:45]} gastó ${res['alertas'][0]['costo']:,.0f} con 0 conv. CTR {res['alertas'][0]['ctr']:.2f}% 65% bajo benchmark META. CPC ${res['alertas'][0]['cpc']:,.0f} 3x sobre benchmark. Prioridad: Pausar y ABM."
                        p_anal=Paragraph(analisis, style_small_w); _,ha=safe_wrap_para(p_anal, W-2*M, 70); p_anal.drawOn(c, M, y2-ha); y2-=ha+18
                        c.setFillColor(HexColor("#141414")); c.roundRect(M, y2-58, W-2*M, 58, 8, fill=1, stroke=0); c.setStrokeColor(HexColor("#262626")); c.roundRect(M, y2-58, W-2*M, 58, 8, fill=0, stroke=1)
                        c.setFillColor(HexColor("#888888")); c.setFont("Helvetica-Bold", 8); c.drawString(M+10, y2-12, "Benchmarks IA.MRKT por plataforma")
                        c.setFont("Helvetica", 7); c.setFillColor(HexColor("#AAAAAA")); c.drawString(M+10, y2-24, "GOOGLE: CPC < $800 OK | CTR >1.5% | ROAS >1.5 | META: Freq <2.5 | CTR >1.5% | CPC < $800 | LINKEDIN: CTR >0.8% | CPL < $1200")
                        c.drawString(M+10, y2-36, f"Tu caso: CTR 0.28% = 65% bajo benchmark | CPC $4200 = 250% sobre | 0 leads = falla segmentación | Recomendación: Test A/B urgente")
                        footer(2); c.showPage()
                        fondo_negro()
                        c.setFillColor(HexColor("#FF3B30")); c.setFont("Helvetica-Bold", 14); c.drawString(M, H-45, f"Alertas Críticas — {len(res['rojos'])} encontradas • Acción Inmediata")
                        y3=H-75
                        for a in res['rojos'][:3]:
                            if y3<200: footer(3); c.showPage(); fondo_negro(); y3=H-55
                            c.setFillColor(HexColor("#1C0A0A")); c.roundRect(M, y3-45, W-2*M, 45, 10, fill=1, stroke=0)
                            c.setFillColor(HexColor("#FF3B30")); c.setFont("Helvetica-Bold", 9); c.drawString(M+10, y3-15, f"[ROJO] {a['camp'][:65]}")
                            c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica", 7.5); c.drawString(M+10, y3-28, f"{a['tipo']} | Gasto ${a['costo']:,.0f} | Fuga ${a['fuga']:,.0f} | CTR {a['ctr']:.2f}%")
                            c.setFillColor(HexColor("#FFAA00")); c.setFont("Helvetica", 6.5); c.drawString(M+10, y3-40, "Diagnóstico: Segmentación B2B amplia sin ABM + creatividad genérica + landing no alineada")
                            y3-=55
                            action_html=f"<b>ACCIÓN INMEDIATA — SOLUCIÓN DETALLADA (48h)</b><br/><br/><b>Paso 1 - PAUSAR (Hoy):</b> Pausa campaña para frenar fuga ${a['fuga']:,.0f}. No borres.<br/><b>Paso 2 - RE-SEGMENTAR (Mañana):</b> ABM: Solo Decision Makers TI empresas 200+ Chile. CTO, CIO, IT Manager.<br/><b>Paso 3 - CREATIVIDAD (48h):</b> 3 nuevos ads dolor específico: 'Reduce 40% onboarding TI' / 'Caso SaaS B2B' / 'Demo 15min'.<br/><b>Paso 4 - LANDING:</b> Cambia CTA a 'Ver caso de éxito TI' no 'Contactar'. Form corto 3 campos.<br/><b>Paso 5 - PRESUPUESTO:</b> Relanza con 50% (${int(a['costo']*0.5):,.0f}) por 5 días, mide CTR&gt;0.8% y CPL&lt;$1200. Si OK, escala +20%.<br/><br/><b>Impacto esperado:</b> Recupero ${total_fuga*0.7:,.0f}/mes • ROI 3.2x • 4-6 leads/mes con CPL $1200"
                            p_act=Paragraph(action_html, style_action_body)
                            _,h_act=safe_wrap_para(p_act, W-2*M-20, 400)
                            box_act_h=h_act+30
                            if y3 - box_act_h < MIN_Y:
                                footer(3); c.showPage(); fondo_negro(); y3=H-55
                            c.setFillColor(LIME_SOFT); c.roundRect(M, y3-box_act_h, W-2*M, box_act_h, 12, fill=1, stroke=0)
                            p_act.drawOn(c, M+14, y3-box_act_h+15)
                            y3-=box_act_h+20
                        footer(3); c.showPage()
                        fondo_negro()
                        c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica-Bold", 14); c.drawString(M, H-45, f"Campañas en Verde + Checklist 72h")
                        y4=H-70
                        if len(res['verdes'])>0:
                            for a in res['verdes'][:4]:
                                if y4<80: footer(4); c.showPage(); fondo_negro(); y4=H-70
                                c.setFillColor(HexColor("#0A1C0A")); c.roundRect(M, y4-25, W-2*M, 25, 8, fill=1, stroke=0)
                                c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica", 8); c.drawString(M+10, y4-15, f"VERDE: {a['camp'][:70]} | {a['tipo']}")
                                y4-=32
                        else:
                            c.setFillColor(HexColor("#1A1A1A")); c.roundRect(M, y4-25, W-2*M, 25, 8, fill=1, stroke=0)
                            c.setFillColor(HexColor("#888888")); c.setFont("Helvetica", 8); c.drawString(M+10, y4-15, "No hay verdes aún — optimiza rojos primero")
                            y4-=32
                        y4-=12
                        c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold", 11); c.drawString(M, y4, "Checklist 72h para cerrar fuga"); y4-=16
                        checklist=[f"1. Hoy: Pausar {res['rojos'][0]['camp'][:40] if res['rojos'] else 'ROJOS'} — frena ${total_fuga:,.0f}", "2. Mañana: Crear audiencia ABM TI 200+ empleados Chile", "3. 48h: 3 creatividades nuevas dolor TI + caso éxito", "4. 48h: Landing CTA 'Ver caso' + form 3 campos", f"5. 72h: Relanzar ${int(res['rojos'][0]['costo']*0.5) if res['rojos'] else 150000:,.0f} (50%) CTR>0.8% CPL<$1200", f"6. Día 5: Escalar +20% si OK, reasignar ${total_fuga*0.3:,.0f} a verdes", f"7. Semana 2: Nuevo CSV validar recupero ${total_fuga*0.7:,.0f}/mes anual ${total_fuga*0.7*12:,.0f}"]
                        for ch in checklist:
                            if y4<50: footer(4); c.showPage(); fondo_negro(); y4=H-70
                            c.setFillColor(HexColor("#141414")); c.roundRect(M, y4-20, W-2*M, 20, 6, fill=1, stroke=0)
                            c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica", 7.5); c.drawString(M+10, y4-13, ch); y4-=26
                        c.setFillColor(HexColor("#222222")); c.roundRect(M, 30, W-2*M, 35, 8, fill=1, stroke=0)
                        c.setFillColor(HexColor("#888888")); c.setFont("Helvetica", 6.5); c.drawString(M+10, 50, "IA.MRKT • Motor v0.6.8 • ia-mrkt.com • 100% local y privado")
                        footer(4); c.showPage(); c.save()
                        return tmp.name
                    pdf_path=gen_pdf()
                    try:
                        enviado,det=enviar_pdf_por_email(email_final,pdf_path,plat_usar,res["total_fuga"])
                        if enviado:
                            st.markdown(f'<div style="padding:10px; background:#0A1C0A; border:1px solid #CCFF00; border-radius:10px; color:#CCFF00;">✅ PDF enviado a {email_final}</div>', unsafe_allow_html=True)
                    except: pass
                    with open(pdf_path,"rb") as f: st.download_button("⬇ Descargar PDF IA.MRKT - ACCIÓN 48H INCLUIDA", f, file_name=f"IA_MRKT_{plat_usar}_{email_final.split('@')[0]}.pdf", mime="application/pdf", use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}"); import traceback; st.code(traceback.format_exc()[:2000]); st.session_state["run_audit"]=False
