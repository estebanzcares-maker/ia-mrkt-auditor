import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import tempfile, re, os, smtplib, base64
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

# === CSS EXACTO DE TU CAPTURA 1.png ===
st.markdown('''
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;800&display=swap');
.stApp { background-color: #0A0A0A; color: #E5E5E5; font-family: 'Inter', sans-serif; }
h1, h2, h3 { font-family: 'Inter', sans-serif; font-weight: 800; letter-spacing: -0.03em; }
.mono { font-family: 'JetBrains Mono', monospace; }
div[data-testid="stButton"] > button { background: #CCFF00!important; color: #0A0A0A!important; border: none!important; border-radius: 12px!important; font-weight: 800!important; padding: 14px 20px!important; font-size: 14px!important; }
div[data-testid="stButton"] > button:hover { background: #D4FF33!important; box-shadow: 0 0 20px rgba(204,255,0,0.4)!important; }
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
        import resend
        api_key = st.secrets.get("RESEND_API_KEY", "") if hasattr(st, "secrets") else ""
        if not api_key: return False, "RESEND_API_KEY no configurado"
        resend.api_key = api_key
        with open(pdf_path, "rb") as f: pdf_b64 = base64.b64encode(f.read()).decode()
        email_from = st.secrets.get("EMAIL_FROM", "onboarding@resend.dev") if hasattr(st, "secrets") else "onboarding@resend.dev"
        html_body = f"<h2>IA.MRKT — {plataforma}</h2><p>Fuga: <b>${fuga_total:,.0f} CLP/mes</b></p><p>PDF adjunto con tabla completa.</p>"
        params = {"from": email_from, "to": [email_destino], "subject": f"IA.MRKT — {plataforma} — ${fuga_total:,.0f}", "html": html_body, "attachments": [{"filename": f"IA_MRKT_{plataforma}.pdf", "content": pdf_b64}]}
        email_admin = st.secrets.get("EMAIL_ADMIN", "") if hasattr(st, "secrets") else ""
        if email_admin and email_admin!= email_destino: params["bcc"] = [email_admin]
        resend.Emails.send(params)
        return True, "Enviado"
    except Exception as e:
        return False, str(e)

LEADS_FILE = "leads_ia_mrkt.csv"
def guardar_lead(email, plataforma, fuga, plan_camp, precio_plan, num_camp_csv, num_verdes, num_rojos, csv_nombre=""):
    try:
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fila = {"fecha": fecha, "email": email.strip(), "plataforma": plataforma, "fuga_detectada": int(fuga), "plan_campanas": plan_camp, "precio_pagado": precio_plan, "campanas_csv": num_camp_csv, "verdes": num_verdes, "rojos": num_rojos, "csv_nombre": csv_nombre, "plan_link": f"plan_{plan_camp}"}
        if os.path.exists(LEADS_FILE):
            df_leads = pd.read_csv(LEADS_FILE)
            df_leads = pd.concat([df_leads, pd.DataFrame([fila])], ignore_index=True)
        else:
            df_leads = pd.DataFrame([fila])
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

# UI
st.markdown('<div style="display:flex; justify-content:space-between; align-items:center; padding:10px 0 20px 0;"><div style="font-weight:800; font-size:20px;">IA.MRKT <span style="color:#CCFF00;">●</span></div><div><span class="badge badge-lime-border">IA.MRKT MOTOR v0.7 PDF PULIDO</span> <span class="badge badge-verde">PRIVADO</span></div></div>', unsafe_allow_html=True)
col1, col2 = st.columns([1.15, 0.85], gap="large")
with col1:
    try: plataforma = st.segmented_control("Plataforma", ["GOOGLE","META","LINKEDIN"], default="GOOGLE")
    except: plataforma = st.selectbox("Plataforma", ["GOOGLE","META","LINKEDIN"], label_visibility="collapsed")
    st.session_state["plat"] = plataforma
    label_map = {"GOOGLE":"Google Ads","META":"Meta Ads","LINKEDIN":"LinkedIn Ads"}
    st.markdown(f'<h1 style="font-size:54px; line-height:0.9; margin-top:10px;">¿Dónde se fuga<br>tu presupuesto<br>de <span style="color:#CCFF00;">{label_map[plataforma]}?</span></h1>', unsafe_allow_html=True)
    st.markdown('<p style="color:#888; font-size:15px; margin-top:12px;">Motor IA.MRKT v0.7 PDF Pulido analiza CSV de Google, Meta o LinkedIn en 30 seg. Sin acceso a tu cuenta. Solo números. PDF con tabla completa + acciones.</p>', unsafe_allow_html=True)
with col2:
    st.markdown('<div style="background:#141414; border:1px solid #262626; border-radius:16px; padding:20px;">', unsafe_allow_html=True)
    st.markdown('<div class="kpi-label">CORREO PARA REPORTE PULIDO</div>', unsafe_allow_html=True)
    email = st.text_input("Email", label_visibility="collapsed", placeholder="tu@empresa.com")
    email_valido = False
    if email:
        ok, msg = validar_email(email)
        email_valido = ok
        if ok: st.markdown(f'<div style="background:#0A1C0A; border:1px solid #CCFF00; border-radius:8px; padding:8px; font-size:10px; margin-top:8px; color:#CCFF00;">✅ {msg}</div>', unsafe_allow_html=True)
        else: st.markdown(f'<div style="background:#1C0A0A; border:1px solid #FF3B30; border-radius:8px; padding:8px; font-size:10px; margin-top:8px; color:#FF3B30;">❌ {msg}</div>', unsafe_allow_html=True)
    st.markdown('<div style="height:12px;"></div><div class="kpi-label">CSV DE CAMPAÑAS (GOOGLE/META/LINKEDIN)</div>', unsafe_allow_html=True)
    csv_file = st.file_uploader("CSV", label_visibility="collapsed", type=["csv"])
    if csv_file:
        try:
            df_prev = pd.read_csv(csv_file)
            plat_detectada = autodetect_platform(df_prev)
            st.markdown(f'<div style="background:#0A1C0A; border:1px solid #262626; border-left:4px solid #CCFF00; border-radius:8px; padding:8px; font-size:10px; margin-top:8px; color:#CCFF00;">✅ CSV detectado como {plat_detectada} — {len(df_prev)} campañas</div>', unsafe_allow_html=True)
            st.session_state["plat_autodetect"] = plat_detectada
            csv_file.seek(0)
        except: pass
    btn_auditar = st.button("🔒 AUDITAR CON IA.MRKT", use_container_width=True)
    if btn_auditar and email_valido:
        st.session_state["run_audit"] = True
        st.session_state["email_validado"] = email.strip()
    st.markdown(f'<div style="margin-top:12px; font-size:11px; color:#666; text-align:center;">Plan actual: {LIMITE_CAMPANAS} campaña(s) • ${PRECIO_BASE:,.0f} c/u • PDF v2 tabla completa</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

email_final = st.session_state.get("email_validado", email if 'email' in locals() else None)
if email_final and csv_file and st.session_state.get("run_audit", False):
    ok, msg = validar_email(email_final)
    if not ok:
        st.error(f"Email inválido: {msg}"); st.session_state["run_audit"] = False
    elif st.session_state["auditorias_hechas"] >= LIMITE_CAMPANAS:
        st.error(f"Límite alcanzado: {LIMITE_CAMPANAS} campaña(s).")
    else:
        try:
            df = pd.read_csv(csv_file)
            plat_detectada = autodetect_platform(df)
            plat_selector = st.session_state.get("plat","GOOGLE")
            plat_usar = st.session_state.get("plat_autodetect", plat_detectada)
            num_camp_csv = len(df)
            df_limite = df.head(LIMITE_CAMPANAS) if num_camp_csv > LIMITE_CAMPANAS else df
            res, err = detectar(df_limite, plataforma=plat_usar)
            if err: st.error(err); st.session_state["run_audit"] = False
            else:
                st.session_state["auditorias_hechas"] += 1
                guardar_lead(email_final, plat_usar, res["total_fuga"], LIMITE_CAMPANAS, PRECIO_PLAN, num_camp_csv, len(res["verdes"]), len(res["rojos"]), getattr(csv_file,'name',''))
                st.markdown(f'<div style="display:flex; gap:16px; margin:20px 0;"><div class="card" style="flex:1;"><div class="kpi-label">FUGA ESTIMADA / MES</div><div class="kpi-big mono" style="color:#FF3B30;">${res["total_fuga"]:,.0f}</div></div><div class="card" style="flex:1;"><div class="kpi-label">CAMPAÑAS EN VERDE</div><div class="kpi-big mono">{len(res["verdes"])}</div></div><div class="card" style="flex:1;"><div class="kpi-label">ALERTAS CRÍTICAS</div><div class="kpi-big mono">{len(res["rojos"])}</div></div></div>', unsafe_allow_html=True)
                c1,c2 = st.columns([2,1])
                with c1:
                    for a in res["rojos"]:
                        css = "alert-rojo" if a["color"]=="rojo" else "alert-amarillo"
                        st.markdown(f'<div class="{css}"><span class="mono" style="font-weight:700; font-size:12px; color:{"#FF3B30" if a["color"]=="rojo" else "#FFAA00"};">{a["color"].upper()}</span> <span style="margin-left:8px; font-size:13px;">{a["camp"]} | {a["tipo"]} | Fuga: ${a["fuga"]:,.0f}</span></div>', unsafe_allow_html=True)
                    for a in res["verdes"]:
                        st.markdown(f'<div class="alert-verde"><span class="mono" style="color:#CCFF00; font-weight:700;">VERDE</span> <span style="margin-left:8px;">{a["camp"]} | {a["tipo"]}</span></div>', unsafe_allow_html=True)
                with c2:
                    def gen_pdf():
                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                        c = canvas.Canvas(tmp.name, pagesize=A4); W,H = A4
                        styles = getSampleStyleSheet()
                        style_small = ParagraphStyle('small', parent=styles['Normal'], fontSize=8, leading=10, textColor=HexColor("#CCCCCC"))
                        style_small_w = ParagraphStyle('smallw', parent=styles['Normal'], fontSize=8, leading=10, textColor=HexColor("#FFFFFF"))
                        def fondo(): c.setFillColor(HexColor("#0A0A0A")); c.rect(0,0,W,H, fill=1, stroke=0)
                        def footer(n): c.setFillColor(HexColor("#444444")); c.setFont("Helvetica",7); c.drawString(40,20,f"IA.MRKT • {plat_usar} • {email_final} • Pag {n}"); c.drawRightString(W-40,20,"Confidencial")
                        fondo(); c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica-Bold",32); c.drawString(40,H-70,"IA.MRKT")
                        c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica",11); c.drawString(40,H-90,f"Auditoría {plat_usar} • Plan {LIMITE_CAMPANAS} camp")
                        c.setFont("Helvetica",9); c.setFillColor(HexColor("#888888")); c.drawString(40,H-105,f"Cliente: {email_final} | {datetime.now().strftime('%d/%m/%Y')}")
                        total_fuga=res['total_fuga']; num_rojos=len(res['rojos']); num_verdes=len(res['verdes']); total_camp=len(df_limite)
                        c.setFillColor(HexColor("#1A1A1A")); c.roundRect(40,H-200,W-80,80,12,fill=1,stroke=0)
                        c.setFillColor(HexColor("#FF3B30") if total_fuga>0 else HexColor("#CCFF00")); c.setFont("Helvetica-Bold",28); c.drawString(55,H-165,f"${total_fuga:,.0f} CLP/mes")
                        c.setFont("Helvetica",10); c.setFillColor(HexColor("#FFFFFF")); c.drawString(55,H-185,"Fuga estimada")
                        c.setFont("Helvetica-Bold",16); c.setFillColor(HexColor("#FFFFFF")); c.drawString(300,H-165,f"{total_camp} campañas")
                        c.setFont("Helvetica",9); c.setFillColor(HexColor("#AAAAAA")); c.drawString(300,H-180,f"{num_rojos} críticas • {num_verdes} verde • {plat_usar}")
                        y=H-230; c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold",12); c.drawString(40,y,"Resumen Ejecutivo"); y-=16
                        texto=f"Se analizaron {total_camp} campañas de {plat_usar}. " + (f"Fuga ${total_fuga:,.0f}/mes en {num_rojos} campañas. Recuperable 35-80%." if total_fuga>0 else f"{num_verdes} campañas optimizadas en verde.")
                        p=Paragraph(texto, style_small_w); p.wrap(W-80,100); p.drawOn(c,40,y-40); y-=60
                        c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica-Bold",10); c.drawString(40,y,"Qué incluye este PDF (aunque no llegue por email):"); y-=14
                        c.setFont("Helvetica",8.5); c.setFillColor(HexColor("#AAAAAA"))
                        for b in ["1. Tabla completa campañas + métricas reales", "2. Detalle alertas ROJA/AMARILLA con acción", "3. Verdes para escalar", "4. Metodología + próximos pasos"]:
                            c.drawString(45,y,f"• {b}"); y-=12
                        footer(1); c.showPage()
                        fondo(); c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica-Bold",14); c.drawString(40,H-50,f"Detalle Completo — {total_camp} campañas [{plat_usar}]")
                        data=[["Campaña","Costo","Conv","ROAS","CTR","CPC/Freq","Estado","Fuga"]]
                        for a in res['alertas']:
                            cs=(a['camp'][:32]+'..') if len(a['camp'])>32 else a['camp']
                            data.append([cs, f"${a['costo']:,.0f}", f"{a['conv']:.0f}", f"{a['roas']:.2f}" if a['roas'] else "-", f"{a['ctr']:.2f}%" if a['ctr'] else "-", f"${a['cpc']:.0f}" if a['cpc'] else (f"{a['freq']:.1f}" if a['freq'] else "-"), a['tipo'][:40], f"${a['fuga']:,.0f}" if a['fuga']>0 else "$0"])
                        table=Table(data, colWidths=[135,55,30,30,40,50,110,50], repeatRows=1)
                        style=TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor("#CCFF00")),('TEXTCOLOR',(0,0),(-1,0),HexColor("#000000")),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,0),7),('BACKGROUND',(0,1),(-1,-1),HexColor("#141414")),('TEXTCOLOR',(0,1),(-1,-1),HexColor("#E5E5E5")),('FONTSIZE',(0,1),(-1,-1),7),('GRID',(0,0),(-1,-1),0.5,HexColor("#262626")),('ALIGN',(1,1),(-1,-1),'CENTER')])
                        for i,a in enumerate(res['alertas'], start=1):
                            if i>=len(data): break
                            if a['color']=='rojo': style.add('BACKGROUND',(0,i),(-1,i),HexColor("#2A1212"))
                            elif a['color']=='amarillo': style.add('BACKGROUND',(0,i),(-1,i),HexColor("#2A2512"))
                            elif a['color']=='verde': style.add('BACKGROUND',(0,i),(-1,i),HexColor("#122A12"))
                        table.setStyle(style); tw,th=table.wrap(W-80,H-100); table.drawOn(c,40,H-90-th); footer(2); c.showPage()
                        fondo(); c.setFillColor(HexColor("#FF3B30")); c.setFont("Helvetica-Bold",14); c.drawString(40,H-50,f"Alertas Críticas — {len(res['rojos'])}"); y=H-80
                        if len(res['rojos'])==0:
                            c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica-Bold",12); c.drawString(40,y,"✓ No hay rojas")
                        else:
                            for a in res['rojos'][:8]:
                                if y<100: footer(3); c.showPage(); fondo(); y=H-50
                                c.setFillColor(HexColor("#1C0A0A")); c.roundRect(40,y-50,W-80,50,8,fill=1,stroke=1)
                                c.setFillColor(HexColor("#FF3B30")); c.setFont("Helvetica-Bold",9); c.drawString(50,y-12,f"[{a['color'].upper()}] {a['camp'][:55]}")
                                c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica",8); c.drawString(50,y-26,f"{a['tipo']} | ${a['costo']:,.0f} | Fuga ${a['fuga']:,.0f}")
                                c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica-Bold",7.5)
                                rec="ACCIÓN: Pausar 48h, revisar segmentación" if "0" in a['tipo'] else "ACCIÓN: Cambiar creatividad, bajar freq <2.0"
                                c.drawString(50,y-38,rec); y-=62
                        footer(3); c.showPage()
                        fondo(); c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica-Bold",14); c.drawString(40,H-50,f"Verdes — Escalar ({len(res['verdes'])})"); y=H-80
                        for a in res['verdes'][:6]:
                            if y<150: break
                            c.setFillColor(HexColor("#0A1C0A")); c.roundRect(40,y-28,W-80,28,8,fill=1,stroke=0)
                            c.setFillColor(HexColor("#CCFF00")); c.setFont("Helvetica",8); c.drawString(50,y-16,f"VERDE: {a['camp'][:60]} | {a['tipo']}"); y-=36
                        footer(4); c.showPage(); c.save(); return tmp.name
                    pdf_path = gen_pdf()
                    try:
                        enviado, detalle = enviar_pdf_por_email(email_final, pdf_path, plat_usar, res["total_fuga"])
                        if enviado: st.markdown(f'<div style="padding:10px; background:#0A1C0A; border:1px solid #CCFF00; border-radius:10px; color:#CCFF00;">✅ PDF enviado a {email_final}</div>', unsafe_allow_html=True)
                    except: pass
                    with open(pdf_path,"rb") as f:
                        st.download_button("⬇ Descargar PDF IA.MRKT", f, file_name=f"IA_MRKT_{plat_usar}_{email_final.split('@')[0]}.pdf", mime="application/pdf", use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")
            import traceback; st.code(traceback.format_exc()[:2000])
            st.session_state["run_audit"] = False
