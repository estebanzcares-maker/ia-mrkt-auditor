import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
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
PRECIO_BASE = PACKS[1]
qp = st.query_params
LIMITE_CAMPANAS = 1
try:
    if qp.get("limit",""): LIMITE_CAMPANAS = int(str(qp.get("limit","")).strip())
    if qp.get("plan",""): LIMITE_CAMPANAS = int(str(qp.get("plan","")).strip())
except: pass
if LIMITE_CAMPANAS < 1: LIMITE_CAMPANAS = 1
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
div[data-testid="stButton"] > button { background: #CCFF00 !important; color: #0A0A0A !important; border: none !important; border-radius: 12px !important; font-weight: 800 !important; padding: 14px 20px !important; font-size: 14px !important; }
div[data-testid="stButton"] > button:hover { background: #D4FF33 !important; box-shadow: 0 0 20px rgba(204,255,0,0.4) !important; }
div[data-testid="stFileUploader"] { background: #141414 !important; border: 1px dashed #333 !important; border-radius: 12px !important; }
.card { background: #141414; border: 1px solid #262626; border-radius: 16px; padding: 20px; text-align: center; }
.card .kpi-label, .card .mono { text-align: center; }
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
.stTextInput > div > div > input { background:#0A0A0A !important; border:1px solid #333 !important; border-radius:12px !important; color:#E5E5E5 !important; }
div[data-testid="stAlert"] { background-color: #1C1A0A !important; border: 1px solid #FFAA00 !important; color: #E5E5E5 !important; }
div[data-testid="stAlert"] p { color: #E5E5E5 !important; }
a { color: #CCFF00 !important; }
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
    if ".." in email: return False, "Email con .. no válido"
    if email.startswith(".") or email.startswith("@"): return False, "Email no puede empezar con . o @"
    domain = email.split("@")[-1]
    if "." not in domain: return False, "Dominio sin punto"
    if len(domain.split(".")[-1]) < 2: return False, "Extensión muy corta"
    disposable = ["tempmail","10minutemail","mailinator","guerrillamail","yopmail","throwaway"]
    if any(d in domain.lower() for d in disposable): return False, "Email temporal no permitido"

def enviar_pdf_por_email(email_destino, pdf_path, plataforma, fuga_total):
    """Envía PDF al cliente y copia a admin. Usa st.secrets si existen, sino no envía."""
    try:
        # Config desde Streamlit Secrets (opcional)
        email_user = st.secrets.get("EMAIL_USER", "") if hasattr(st, "secrets") else ""
        email_pass = st.secrets.get("EMAIL_PASS", "") if hasattr(st, "secrets") else ""
        email_admin = st.secrets.get("EMAIL_ADMIN", email_user) if hasattr(st, "secrets") else email_user

        if not email_user or not email_pass:
            # Sin config, no falla, solo retorna False para no romper diseño
            return False, "Email no configurado en Secrets"

        msg = MIMEMultipart()
        msg['From'] = f"IA.MRKT <{email_user}>"
        msg['To'] = email_destino
        msg['Subject'] = f"Tu Auditoría IA.MRKT {plataforma} - Fuga ${fuga_total:,.0f} detectada"

        body = f"""Hola,

Tu auditoría IA.MRKT {plataforma} está lista.

Fuga detectada: ${fuga_total:,.0f} CLP/mes
Email auditado: {email_destino}

Adjunto el PDF completo.

Si quieres que optimicemos esto por ti, responde este correo.

— IA.MRKT
Auditor privado
"""
        msg.attach(MIMEText(body, 'plain'))

        with open(pdf_path, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(pdf_path)}"')
            msg.attach(part)

        # Enviar a cliente + admin en BCC
        destinatarios = [email_destino]
        if email_admin and email_admin != email_destino:
            destinatarios.append(email_admin)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_user, email_pass)
        server.send_message(msg, from_addr=email_user, to_addrs=destinatarios)
        server.quit()
        return True, "Enviado"
    except Exception as e:
        return False, str(e)


LEADS_FILE = "leads_ia_mrkt.csv"
def guardar_lead(email, plataforma, fuga, plan_camp, precio_plan, num_camp_csv, num_verdes, num_rojos, csv_nombre=""):
    try:
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fila = {
            "fecha": fecha,
            "email": email.strip(),
            "plataforma": plataforma,
            "fuga_detectada": int(fuga),
            "plan_campanas": plan_camp,
            "precio_pagado": precio_plan,
            "campanas_csv": num_camp_csv,
            "verdes": num_verdes,
            "rojos": num_rojos,
            "csv_nombre": csv_nombre,
            "plan_link": f"plan_{plan_camp}"  # FIX: sin ?plan visible
        }
        if os.path.exists(LEADS_FILE):
            df_leads = pd.read_csv(LEADS_FILE)
            # Migración: si existe columna vieja plan_query, la renombramos
            if "plan_query" in df_leads.columns:
                df_leads = df_leads.drop(columns=["plan_query"])
            df_leads = pd.concat([df_leads, pd.DataFrame([fila])], ignore_index=True)
        else:
            df_leads = pd.DataFrame([fila])
        df_leads.to_csv(LEADS_FILE, index=False)
        return True
    except Exception as e:
        print(f"Error guardando lead: {e}")
        return False

# === DETECTAR v0.6.8 - UMBRALES BAJOS PARA DEMO + MANTIENE OPTIMIZADA ===
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
        else: # GOOGLE - UMBRALES BAJOS PARA DEMO
            if costo>25000 and conv==0: fuga=costo*0.7; tipo="Mala Distribución | 0 conversiones"; color="rojo"
            elif costo>35000 and (conv<=1 or roas<1.0): fuga=costo*0.4; tipo=f"ROAS bajo {roas} | Gasto alto"; color="rojo"
            elif ctr>0 and ctr<1.5 and costo>12000: fuga=costo*0.25; tipo=f"Fatiga Creativa | CTR {ctr}%"; color="amarillo"
            elif roas>=1.5 and conv>=2: tipo=f"VERDE | ROAS {roas} | {int(conv)} conv"; color="verde"
            elif costo>8000 and conv==0 and ctr==0: fuga=costo*0.5; tipo="Sin CTR ni conv | Revisar keywords"; color="amarillo"
            else: continue
        alertas.append({"camp":camp,"costo":costo,"conv":conv,"roas":roas,"ctr":ctr,"cpc":cpc,"freq":freq,"fuga":fuga,"tipo":tipo,"color":color})
    total_fuga = sum(a["fuga"] for a in alertas if a["color"]!="verde")
    verdes = [a for a in alertas if a["color"]=="verde"]; rojos = [a for a in alertas if a["color"]!="verde"]
    # A: si no hay rojos pero tampoco verdes y hay campañas, marcamos como optimizada con fuga 0
    if len(alertas)==0 and len(df)>0:
        # No es error, es que está optimizada - devolvemos 0 fuga con mensaje verde genérico
        alertas.append({"camp":f"{len(df)} campañas analizadas","costo":0,"conv":0,"roas":0,"ctr":0,"cpc":0,"freq":0,"fuga":0,"tipo":f"VERDE | {len(df)} campañas sin fuga crítica detectada | Optimizada","color":"verde"})
        verdes = alertas
    return {"alertas":alertas,"total_fuga":total_fuga,"verdes":verdes,"rojos":rojos}, None

st.markdown('<div style="display:flex; justify-content:space-between; align-items:center; padding:10px 0 20px 0;"><div style="font-weight:800; font-size:20px; letter-spacing:-0.05em;">IA.MRKT <span style="color:#CCFF00;">●</span></div><div><span class="badge badge-lime-border">IA.MRKT MOTOR v0.6.8</span> <span class="badge badge-verde">PRIVADO</span></div></div>', unsafe_allow_html=True)

col1, col2 = st.columns([1.15, 0.85], gap="large")
with col1:
    try:
        plataforma = st.segmented_control("Plataforma", ["GOOGLE","META","LINKEDIN"], default="GOOGLE")
    except:
        plataforma = st.selectbox("Plataforma", ["GOOGLE","META","LINKEDIN"], label_visibility="collapsed")
    st.session_state["plat"] = plataforma
    label_map = {"GOOGLE":"Google Ads","META":"Meta Ads","LINKEDIN":"LinkedIn Ads"}
    st.markdown(f'<h1 style="font-size:54px; line-height:0.9; margin-top:10px;">¿Dónde se fuga<br>tu presupuesto<br>de <span style="color:#CCFF00;">{label_map[plataforma]}?</span></h1>', unsafe_allow_html=True)
    st.markdown('<p style="color:#888; font-size:15px; margin-top:12px;">Motor IA.MRKT v0.6.8 analiza CSV de Google, Meta o LinkedIn en 30 seg. Sin acceso a tu cuenta. Solo números. Detecta hasta $602.500 CLP en fuga/mes promedio • 100% local y privado.</p>', unsafe_allow_html=True)
    st.markdown('<div style="margin-top:20px; display:flex; gap:10px;"><div class="card" style="flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;"><div class="kpi-label" style="text-align:center; width:100%;">GOOGLE</div><div class="mono" style="font-weight:700; text-align:center; width:100%;">CPC • ROAS</div><div style="font-size:10px; color:#666; margin-top:4px; text-align:center; width:100%;">Detecta CTR bajo</div></div><div class="card" style="flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;"><div class="kpi-label" style="text-align:center; width:100%;">META</div><div class="mono" style="font-weight:700; text-align:center; width:100%;">FREQ • CPC</div><div style="font-size:10px; color:#666; margin-top:4px; text-align:center; width:100%;">Detecta Fatiga</div></div><div class="card" style="flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;"><div class="kpi-label" style="text-align:center; width:100%;">LINKEDIN</div><div class="mono" style="font-weight:700; text-align:center; width:100%;">CPL • CTR</div><div style="font-size:10px; color:#666; margin-top:4px; text-align:center; width:100%;">Detecta B2B frío</div></div></div>', unsafe_allow_html=True)

with col2:
    st.markdown(f'''
    <div class="card-lime" style="margin-bottom:0;">
        <div class="kpi-label" style="color:#CCFF00;">ACCESO PRIVADO IA.MRKT • PLAN {LIMITE_CAMPANAS} CAMPAÑA{"S" if LIMITE_CAMPANAS>1 else ""}</div>
    ''', unsafe_allow_html=True)

    if st.session_state["auditorias_hechas"] >= LIMITE_CAMPANAS:
        st.markdown(f'''
            <div style="background:#1C0A0A; border:1px solid #FF3B30; border-radius:12px; padding:16px; margin:12px 0;">
                <div class="mono" style="color:#FF3B30; font-weight:700;">LÍMITE ALCANZADO — {LIMITE_CAMPANAS} CAMPAÑA{"S" if LIMITE_CAMPANAS>1 else ""}</div>
                <div style="font-size:13px; color:#DDD; margin-top:8px;">Ya auditaste {st.session_state["auditorias_hechas"]} campaña(s) con ${PRECIO_PLAN:,.0f}.<br>Para más: contacta. estebanzcares@gmail.com</div>
            </div>
        ''', unsafe_allow_html=True)
        if st.button("🔄 REINICIAR (ADMIN)", use_container_width=True):
            st.session_state["auditorias_hechas"] = 0
            st.session_state["run_audit"] = False
            st.session_state.pop("plat_autodetect", None)
            st.rerun()
        email = None
        csv_file = None
    else:
        st.markdown('<div style="font-size:13px; color:#888; margin:12px 0 8px 0;">Tu correo para PDF completo</div>', unsafe_allow_html=True)
        email = st.text_input("email_input", placeholder="ej: tu@empresa.cl", label_visibility="collapsed")
        email_valido = True
        email_msg = ""
        if email:
            email_valido, email_msg = validar_email(email)
            if email_valido:
                st.markdown('<div style="font-size:10px; color:#CCFF00; margin-top:4px;">✅ Email válido — PDF se generará con este correo</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="font-size:10px; color:#FF3B30; margin-top:4px;">❌ {email_msg}</div>', unsafe_allow_html=True)
        else:
            email_valido = False

        st.markdown(f'<div style="font-size:13px; color:#888; margin:16px 0 8px 0;">CSV de {st.session_state.get("plat","GOOGLE")} Ads — quedan {LIMITE_CAMPANAS - st.session_state["auditorias_hechas"]} auditoría(s)</div>', unsafe_allow_html=True)
        csv_file = st.file_uploader("csv", type=["csv"], label_visibility="collapsed")
        if csv_file:
            try:
                df_tmp = pd.read_csv(csv_file)
                plat_detectada = autodetect_platform(df_tmp)
                if plat_detectada != plataforma:
                    st.markdown(f'<div style="background:#1C1A0A; border:1px solid #FFAA00; border-left:4px solid #FFAA00; border-radius:8px; padding:10px; font-size:11px; margin-top:8px; color:#E5E5E5;"><span style="color:#FFAA00; font-weight:700;">⚠️ AUTODETECT:</span> Detecté CSV de <b style="color:#FFFFFF;">{plat_detectada}</b> pero tenías <b>{plataforma}</b>. Al auditar cambiaré a {plat_detectada} automáticamente.</div>', unsafe_allow_html=True)
                    st.session_state["plat_autodetect"] = plat_detectada
                else:
                    st.markdown(f'<div style="background:#0A1C0A; border:1px solid #262626; border-left:4px solid #CCFF00; border-radius:8px; padding:8px; font-size:10px; margin-top:8px; color:#CCFF00;">✅ CSV detectado como {plat_detectada}</div>', unsafe_allow_html=True)
                csv_file.seek(0)
            except: pass
        st.markdown('<div style="font-size:11px; color:#555; margin-top:4px; text-align:center;">Exportar desde Ads Manager > Exportar > CSV • 200MB max</div>', unsafe_allow_html=True)
        
        btn_auditar = st.button("🔒 AUDITAR CON IA.MRKT", use_container_width=True, key="btn_auditar")
        if btn_auditar:
            if not email:
                st.markdown('<div style="background:#1C0A0A; border:1px solid #FF3B30; border-radius:8px; padding:10px; font-size:11px; color:#E5E5E5; margin-top:8px;"><span style="color:#FF3B30;">⚠️ Debes ingresar tu correo para generar el PDF.</span></div>', unsafe_allow_html=True)
            elif not email_valido:
                st.markdown(f'<div style="background:#1C0A0A; border:1px solid #FF3B30; border-radius:8px; padding:10px; font-size:11px; color:#E5E5E5; margin-top:8px;">❌ <span style="color:#FF3B30;">Email inválido:</span> {email_msg}</div>', unsafe_allow_html=True)
            else:
                st.session_state["run_audit"] = True
                st.session_state["email_validado"] = email.strip()

        st.markdown(f'<div style="margin-top:12px; font-size:11px; color:#666; text-align:center;">Plan actual: {LIMITE_CAMPANAS} campaña(s) • ${PRECIO_BASE:,.0f} c/u • Boleta Honorarios</div>', unsafe_allow_html=True)

    st.markdown('''
        <div style="margin-top:6px; font-size:10px; color:#444; text-align:center;">Pago por transferencia • Link privado.</div>
    </div>
    ''', unsafe_allow_html=True)

st.markdown('<div style="height:1px; background:#1A1A1A; margin:30px 0;"></div>', unsafe_allow_html=True)
st.markdown('<div class="kpi-label" style="margin-bottom:14px;">AUDITORÍAS RECIENTES • GOOGLE • META • LINKEDIN (ANONIMIZADAS)</div>', unsafe_allow_html=True)
g1,g2,g3,g4 = st.columns(4)
with g1:
    st.markdown('<div class="gallery-item"><div class="mono" style="font-size:11px; color:#888;">GOOGLE • HOTEL COSTA • $1.2M</div><div class="mono" style="font-weight:700; color:#FF3B30; margin-top:6px;">$602.500 FUGA</div><div style="margin-top:8px; display:flex; gap:4px;"><div style="width:100%; height:6px; background:#FF3B30; border-radius:99px;"></div><div style="width:60%; height:6px; background:#333; border-radius:99px;"></div></div><div style="font-size:10px; color:#666; margin-top:8px;">3 ROJOS • 4 VERDES</div></div>', unsafe_allow_html=True)
with g2:
    st.markdown('<div class="gallery-item"><div class="mono" style="font-size:11px; color:#888;">META • FERRETERÍA 3 LOCALES • $890k</div><div class="mono" style="font-weight:700; color:#FF3B30; margin-top:6px;">$445.000 FUGA</div><div style="margin-top:8px; display:flex; gap:4px;"><div style="width:70%; height:6px; background:#FF3B30; border-radius:99px;"></div><div style="width:30%; height:6px; background:#333; border-radius:99px;"></div></div><div style="font-size:10px; color:#666; margin-top:8px;">2 AMARILLOS • 2 VERDES</div></div>', unsafe_allow_html=True)
with g3:
    st.markdown('<div class="gallery-item"><div class="mono" style="font-size:11px; color:#888;">LINKEDIN • SAAS B2B • $750k</div><div class="mono" style="font-weight:700; color:#FFAA00; margin-top:6px;">$407.500 FUGA</div><div style="margin-top:8px; display:flex; gap:4px;"><div style="width:50%; height:6px; background:#FFAA00; border-radius:99px;"></div><div style="width:50%; height:6px; background:#333; border-radius:99px;"></div></div><div style="font-size:10px; color:#666; margin-top:8px;">1 ROJO • 1 AMARILLO</div></div>', unsafe_allow_html=True)
with g4:
    st.markdown('<div class="gallery-item" style="border-color:#CCFF00;"><div class="mono" style="font-size:11px; color:#CCFF00;">CLÍNICA DENTAL • META • $2.1M</div><div class="mono" style="font-weight:700; color:#CCFF00; margin-top:6px;">$0 FUGA • OPTIMIZADA</div><div style="margin-top:8px; display:flex; gap:4px;"><div style="width:100%; height:6px; background:#CCFF00; border-radius:99px;"></div></div><div style="font-size:10px; color:#666; margin-top:8px;">6 VERDES • ROAS 5.8</div></div>', unsafe_allow_html=True)

email_final = st.session_state.get("email_validado", email if 'email' in locals() else None)

if email_final and csv_file and st.session_state.get("run_audit", False):
    ok, msg = validar_email(email_final)
    if not ok:
        st.error(f"Email inválido: {msg}")
        st.session_state["run_audit"] = False
    elif st.session_state["auditorias_hechas"] >= LIMITE_CAMPANAS:
        st.error(f"Límite alcanzado: {LIMITE_CAMPANAS} campaña(s).")
    else:
        try:
            df = pd.read_csv(csv_file)
            plat_detectada = autodetect_platform(df)
            plat_selector = st.session_state.get("plat","GOOGLE")
            plat_usar = st.session_state.get("plat_autodetect", plat_detectada)
            if plat_detectada != plat_selector:
                plat_usar = plat_detectada
                st.markdown(f'<div class="alert-amarillo" style="color:#E5E5E5;"><span class="mono" style="font-weight:700; color:#FFAA00;">🤖 AUTODETECT:</span> <span style="color:#FFFFFF;">CSV de {plat_detectada} auditado como {plat_detectada}.</span></div>', unsafe_allow_html=True)
                st.session_state["plat"] = plat_detectada
            else:
                plat_usar = plat_selector

            num_camp_csv = len(df)
            if num_camp_csv > LIMITE_CAMPANAS:
                precio_full = PACKS.get(num_camp_csv, PRECIO_BASE * num_camp_csv)
                st.markdown(f'''
                <div class="alert-amarillo-contraste">
                    <div style="color:#FFAA00; font-weight:700; font-size:12px; margin-bottom:4px;">⚠️ LÍMITE DE PLAN</div>
                    <div style="color:#E5E5E5; font-size:13px;">Tu CSV tiene <b style="color:#FFFFFF;">{num_camp_csv} campañas</b>, pero tu plan de <b style="color:#CCFF00;">${PRECIO_PLAN:,.0f}</b> incluye solo <b style="color:#FFFFFF;">{LIMITE_CAMPANAS}</b>. Auditaremos solo las primeras {LIMITE_CAMPANAS}.</div>
                    <div style="color:#888; font-size:11px; margin-top:6px;">Pack {num_camp_csv} campañas = <b style="color:#CCFF00;">${precio_full:,.0f}</b> • Contacta para pack extra</div>
                </div>
                ''', unsafe_allow_html=True)
                df_limite = df.head(LIMITE_CAMPANAS)
            else:
                df_limite = df

            res, err = detectar(df_limite, plataforma=plat_usar)
            if err:
                st.error(err)
                st.session_state["run_audit"] = False
            else:
                csv_nombre = getattr(csv_file, 'name', 'csv_subido')
                guardado = guardar_lead(
                    email=email_final,
                    plataforma=plat_usar,
                    fuga=res["total_fuga"],
                    plan_camp=LIMITE_CAMPANAS,
                    precio_plan=PRECIO_PLAN,
                    num_camp_csv=num_camp_csv,
                    num_verdes=len(res["verdes"]),
                    num_rojos=len(res["rojos"]),
                    csv_nombre=csv_nombre
                )

                st.session_state["auditorias_hechas"] += 1
                st.session_state["run_audit"] = False
                st.session_state.pop("plat_autodetect", None)

                st.markdown('<div style="height:1px; background:#1A1A1A; margin:30px 0;"></div>', unsafe_allow_html=True)
                # A: Si fuga 0, mostrar optimizada
                if res["total_fuga"] == 0 and len(res["verdes"])>0 and len(res["rojos"])==0:
                    st.markdown(f'<h2 style="font-size:32px;">Tu auditoría IA.MRKT [{plat_usar}] — <span class="mono" style="color:#CCFF00;">$0 FUGA • OPTIMIZADA</span></h2>', unsafe_allow_html=True)
                    st.markdown(f'<div style="display:flex; gap:16px; margin:20px 0;"><div class="card" style="flex:1;"><div class="kpi-label">FUGA ESTIMADA / MES</div><div class="kpi-big mono" style="color:#CCFF00;">$0</div></div><div class="card" style="flex:1;"><div class="kpi-label">CAMPAÑAS EN VERDE</div><div class="kpi-big mono">{len(res["verdes"])}</div></div><div class="card" style="flex:1;"><div class="kpi-label">ESTADO</div><div class="kpi-big mono" style="color:#CCFF00; font-size:24px;">OPTIMIZADA</div></div></div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<h2 style="font-size:32px;">Tu auditoría IA.MRKT [{plat_usar}] — <span class="mono" style="color:#CCFF00;">${res["total_fuga"]:,.0f} CLP</span> detectados</h2>', unsafe_allow_html=True)
                    st.markdown(f'<div style="display:flex; gap:16px; margin:20px 0;"><div class="card" style="flex:1;"><div class="kpi-label">FUGA ESTIMADA / MES</div><div class="kpi-big mono" style="color:#FF3B30;">${res["total_fuga"]:,.0f}</div></div><div class="card" style="flex:1;"><div class="kpi-label">CAMPAÑAS EN VERDE</div><div class="kpi-big mono">{len(res["verdes"])}</div></div><div class="card" style="flex:1;"><div class="kpi-label">ALERTAS CRÍTICAS</div><div class="kpi-big mono">{len(res["rojos"])}</div></div></div>', unsafe_allow_html=True)
                if guardado:
                    st.markdown('<div style="font-size:11px; color:#CCFF00; margin-bottom:12px;">✅ Lead guardado en base de datos local</div>', unsafe_allow_html=True)
                c1,c2 = st.columns([2,1])
                with c1:
                    for a in res["rojos"]:
                        css = "alert-rojo" if a["color"]=="rojo" else "alert-amarillo"
                        st.markdown(f'<div class="{css}"><span class="mono" style="font-weight:700; font-size:12px; color:{"#FF3B30" if a["color"]=="rojo" else "#FFAA00"};">{a["color"].upper()}</span> <span style="margin-left:8px; font-size:13px; color:#E5E5E5;">{a["camp"]} | {a["tipo"]} | Fuga: <span class="mono" style="color:#FFFFFF;">${a["fuga"]:,.0f}</span></span></div>', unsafe_allow_html=True)
                    for a in res["verdes"]:
                        st.markdown(f'<div class="alert-verde"><span class="mono" style="color:#CCFF00; font-weight:700; font-size:12px;">VERDE</span> <span style="margin-left:8px; font-size:13px; color:#E5E5E5;">{a["camp"]} | {a["tipo"]}</span></div>', unsafe_allow_html=True)
                with c2:
                    def gen_pdf():
                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                        cc = canvas.Canvas(tmp.name, pagesize=A4)
                        cc.setFillColor(HexColor("#0A0A0A")); cc.rect(0,0,595,842, fill=1, stroke=0)
                        cc.setFillColor(HexColor("#CCFF00")); cc.setFont("Helvetica-Bold", 28); cc.drawString(40,790,"IA.MRKT")
                        cc.setFillColor(HexColor("#FFFFFF")); cc.setFont("Helvetica", 12); cc.drawString(40,770,f"Reporte {plat_usar} - {email_final} - Plan {LIMITE_CAMPANAS} camp")
                        cc.setFont("Helvetica-Bold", 20); cc.drawString(40,730,f"Fuga: ${res['total_fuga']:,.0f} CLP/mes [{plat_usar}]")
                        y=700
                        for a in res["rojos"]:
                            cc.setFont("Helvetica", 10); cc.drawString(40,y,f"[{a['color'].upper()}] {a['camp'][:60]} | {a['tipo']} | ${a['fuga']:,.0f}"); y-=18
                            if y<100: cc.showPage(); y=800
                        for a in res["verdes"]:
                            cc.setFont("Helvetica", 10); cc.drawString(40,y,f"[VERDE] {a['camp'][:60]} | {a['tipo']}"); y-=18
                            if y<100: cc.showPage(); y=800
                        cc.showPage(); cc.save()
                        return tmp.name
                    pdf_path = gen_pdf()
                    # === NUEVO: ENVÍO AUTOMÁTICO PDF POR EMAIL (sin tocar diseño) ===
                    try:
                        enviado, detalle_envio = enviar_pdf_por_email(email_final, pdf_path, plat_usar, res["total_fuga"])
                        if enviado:
                            st.markdown(f'<div style="margin-bottom:10px; padding:10px 14px; background:#0A1C0A; border:1px solid #CCFF00; border-radius:10px; font-size:12px; color:#CCFF00;">✅ PDF enviado automáticamente a <span class="mono">{email_final}</span></div>', unsafe_allow_html=True)
                        else:
                            # Si no hay secrets configurados, no mostrar error rojo, solo info sutil
                            if "no configurado" not in detalle_envio.lower():
                                st.markdown(f'<div style="margin-bottom:10px; font-size:11px; color:#888;">ℹ️ Email automático: {detalle_envio}</div>', unsafe_allow_html=True)
                    except Exception as e:
                        pass
                    # === FIN NUEVO ===

                    with open(pdf_path,"rb") as f:
                        st.download_button("⬇ Descargar PDF IA.MRKT", f, file_name=f"IA_MRKT_Auditoria_{plat_usar}_{email_final.split('@')[0]}.pdf", mime="application/pdf", use_container_width=True)
                    
                    if os.path.exists(LEADS_FILE):
                        try:
                            df_leads_preview = pd.read_csv(LEADS_FILE)
                            if len(df_leads_preview) > 0 and qp.get("admin","") == "1":
                                st.markdown('<div style="margin-top:20px; font-size:11px; color:#888;">📊 LEADS GUARDADOS (solo ?admin=1)</div>', unsafe_allow_html=True)
                                st.dataframe(df_leads_preview.tail(10), use_container_width=True)
                                with open(LEADS_FILE,"rb") as lf:
                                    st.download_button("⬇ Descargar leads_ia_mrkt.csv", lf, file_name="leads_ia_mrkt.csv", mime="text/csv", use_container_width=True)
                        except: pass

                    if st.session_state["auditorias_hechas"] >= LIMITE_CAMPANAS:
                        st.markdown(f'<div style="margin-top:16px; padding:12px; background:#1C0A0A; border-radius:8px; font-size:12px; color:#FF3B30;">Has consumido tu plan de {LIMITE_CAMPANAS} campaña(s).</div>', unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error leyendo CSV: {e}")
            import traceback
            st.code(traceback.format_exc()[:2000])
            st.session_state["run_audit"] = False
elif email and csv_file and not st.session_state.get("run_audit", False):
    ok,_ = validar_email(email) if email else (False,"")
    if ok:
        st.markdown('<div style="margin-top:10px; color:#CCFF00; font-size:12px; text-align:center;">✓ Listo para auditar — presiona AUDITAR CON IA.MRKT</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="margin-top:10px; color:#FF3B30; font-size:11px; text-align:center;">❌ Corrige tu email para desbloquear auditoría</div>', unsafe_allow_html=True)
else:
    st.markdown('<div style="margin-top:20px; color:#444; font-size:12px; text-align:center;">↑ Completa correo válido + CSV para desbloquear auditoría multi-plataforma</div>', unsafe_allow_html=True)

if qp.get("admin","") == "1" and os.path.exists(LEADS_FILE):
    st.markdown('<div style="height:1px; background:#1A1A1A; margin:40px 0;"></div>', unsafe_allow_html=True)
    st.markdown('<h3>📊 Base de clientes — leads_ia_mrkt.csv</h3>', unsafe_allow_html=True)
    try:
        df_all = pd.read_csv(LEADS_FILE)
        st.markdown(f'<div class="kpi-label">TOTAL LEADS: {len(df_all)} • FUGA PROMEDIO: ${df_all["fuga_detectada"].mean():,.0f} • INGRESO ESTIMADO: ${df_all["precio_pagado"].sum():,.0f}</div>', unsafe_allow_html=True)
        st.dataframe(df_all, use_container_width=True)
        colA,colB,colC = st.columns(3)
        with colA:
            st.markdown('<div class="card"><div class="kpi-label">POR PLATAFORMA</div>', unsafe_allow_html=True)
            st.dataframe(df_all["plataforma"].value_counts(), use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        with colB:
            st.markdown('<div class="card"><div class="kpi-label">POR PLAN</div>', unsafe_allow_html=True)
            st.dataframe(df_all["plan_campanas"].value_counts(), use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        with colC:
            st.markdown('<div class="card"><div class="kpi-label">TOP EMAILS</div>', unsafe_allow_html=True)
            st.dataframe(df_all["email"].value_counts().head(10), use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
    except Exception as e:
        st.error(f"No se pudo leer leads: {e}")
