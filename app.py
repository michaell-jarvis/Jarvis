# =====================================================================
#  JARVIS - Assistente personale (gratuito)
#  Cervello: Groq (modelli open source, gratis)
#  Ricerche: DuckDuckGo (gratis, senza chiave)
#  Memoria, abitudini e piano di studio: un Gist privato su GitHub (gratis)
#  Università: Aulaweb (Moodle UniGe), in sola lettura
#  Interfaccia: Streamlit (pubblicata gratis su Streamlit Community Cloud)
#
#  NON serve modificare questo file: tutte le impostazioni personali
#  (chiavi, password, nome) vanno nei "Secrets" di Streamlit.
# =====================================================================

import datetime
import hashlib
import hmac
import json
import re
import time
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)

import abitudini as ab
from aulaweb import Aulaweb, ErroreAulaweb, token_da_link


# ---------------------------------------------------------------------
#  Impostazioni (lette dai Secrets di Streamlit)
# ---------------------------------------------------------------------
def segreto(nome, predefinito=""):
    try:
        valore = st.secrets.get(nome, predefinito)
    except Exception:
        valore = predefinito
    return str(valore).strip() if valore is not None else predefinito


GROQ_API_KEY = segreto("GROQ_API_KEY")
PASSWORD = segreto("PASSWORD")
GITHUB_TOKEN = segreto("GITHUB_TOKEN")
GIST_ID = segreto("GIST_ID")
NOME_UTENTE = segreto("NOME_UTENTE", "signore")
NOME_ASSISTENTE = segreto("NOME_ASSISTENTE", "J.A.R.V.I.S.")
BASE_URL = segreto("BASE_URL", "https://api.groq.com/openai/v1")
MODELLO_PREFERITO = segreto("MODELLO", "openai/gpt-oss-120b")
AULAWEB_URL = segreto("AULAWEB_URL", "https://2026.aulaweb.unige.it")
AULAWEB_TOKEN = segreto("AULAWEB_TOKEN")

# Ogni modello gratuito di Groq ha i suoi limiti: quando uno è al limite, Jarvis passa al successivo.
MODELLI = [MODELLO_PREFERITO] + [
    m for m in ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
    if m != MODELLO_PREFERITO
]
MODELLI_VOCE = ["whisper-large-v3-turbo", "whisper-large-v3"]

FUSO = ZoneInfo("Europe/Rome")
FILE_MEMORIA = "memoria.json"
FILE_CRONOLOGIA = "cronologia.json"
FILE_ABITUDINI = "abitudini.json"
FILE_STUDIO = "studio.json"
MAX_CRONOLOGIA = 40       # messaggi salvati tra un dispositivo e l'altro
MAX_CONTESTO = 12         # messaggi recenti che il cervello rilegge ogni volta
MAX_GIRI_STRUMENTI = 6    # quante azioni (ricerche ecc.) può fare per risposta

SEZIONI = ["💬 Jarvis", "📅 Abitudini", "📚 Studio"]
GIORNI_SETTIMANA = {1: "lun", 2: "mar", 3: "mer", 4: "gio", 5: "ven", 6: "sab", 0: "dom"}


st.set_page_config(
    page_title="JARVIS",
    page_icon="🔷",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def oggi():
    return datetime.datetime.now(FUSO).date()


# ---------------------------------------------------------------------
#  Grafica stile HUD futuristico
# ---------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&display=swap');

:root {
  --blu: #2563eb; --blu-scuro: #1e3a8a; --blu-chiaro: #dbeafe;
  --testo: #0f172a; --testo-tenue: #475569; --bordo: #e2e8f0; --carta: #ffffff;
}

.stApp {
  background:
    radial-gradient(1200px 500px at 50% -120px, #dbeafe 0%, rgba(219,234,254,0) 70%),
    #f5f8fc;
  color: var(--testo);
}
.stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input, .stApp textarea {
  font-family: 'Figtree', system-ui, sans-serif;
}
/* le icone di Streamlit (frecce del menu e dei riquadri) devono tenere il loro carattere speciale */
.stApp [data-testid="stIconMaterial"], [data-testid="stIconMaterial"] {
  font-family: 'Material Symbols Rounded' !important;
}
.stApp p, .stApp li, .stApp label { color: var(--testo); font-size: 1.02rem; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { font-family: 'Figtree', sans-serif; color: var(--blu-scuro); font-weight: 700; }
.stApp a { color: var(--blu); }
header[data-testid="stHeader"] { background: transparent; }
footer { visibility: hidden; }

/* --- Intestazione con il nucleo luminoso --- */
.hud { text-align: center; margin: -1.6rem 0 0.9rem 0; }
.nucleo-box { position: relative; width: 96px; height: 96px; margin: 0 auto 0.55rem auto; }
.anello { position: absolute; border-radius: 50%; border: 2px solid var(--blu); }
.a1 { inset: 0; border-color: var(--blu) transparent #60a5fa transparent; animation: gira 7s linear infinite;
      box-shadow: 0 6px 24px rgba(37,99,235,.18); }
.a2 { inset: 12px; border-style: dashed; border-color: #93c5fd; animation: gira 12s linear infinite reverse; }
.a3 { inset: 24px; border-color: transparent var(--blu) transparent #60a5fa; animation: gira 4s linear infinite; }
.cuore { position: absolute; inset: 35px; border-radius: 50%;
         background: radial-gradient(circle, #ffffff 0%, #bfdbfe 40%, var(--blu) 100%);
         box-shadow: 0 0 18px rgba(37,99,235,.35); animation: pulsa 2.6s ease-in-out infinite; }
@keyframes gira { to { transform: rotate(360deg); } }
@keyframes pulsa { 0%,100% { transform: scale(.9); } 50% { transform: scale(1.05); } }
.titolo { font-family: 'Figtree', sans-serif; font-weight: 800; font-size: 1.9rem; letter-spacing: .32rem;
          color: var(--blu-scuro); }
.sottotitolo { font-size: .78rem; letter-spacing: .14rem; color: var(--testo-tenue); text-transform: uppercase; font-weight: 600; }
.punto { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #22c55e;
         margin-right: 6px; vertical-align: 1px; box-shadow: 0 0 0 3px rgba(34,197,94,.18); }

/* --- Messaggi --- */
[data-testid="stChatMessage"] {
  background: var(--carta);
  border: 1px solid var(--bordo);
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(15,23,42,.06);
}
[data-testid="stChatInput"] textarea { color: var(--testo); font-size: 1.02rem; }
[data-testid="stChatInput"] > div { border: 1px solid #cbd5e1; background: var(--carta); border-radius: 14px; }

/* --- Barra laterale --- */
[data-testid="stSidebar"] { background: var(--carta); border-right: 1px solid var(--bordo); }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: var(--blu-scuro); font-size: 1.05rem; }

/* --- Pulsanti, riquadri, scelta della sezione --- */
.stButton button, .stFormSubmitButton button {
  border: 1px solid #cbd5e1; color: var(--testo); background: var(--carta); border-radius: 12px; font-weight: 600;
}
.stButton button:hover, .stFormSubmitButton button:hover { border-color: var(--blu); color: var(--blu); background: #f8fbff; }
[data-testid="stExpander"] { border: 1px solid var(--bordo); border-radius: 14px; background: var(--carta); }
div[role="radiogroup"] { background: var(--carta); border: 1px solid var(--bordo); border-radius: 14px;
                         padding: 6px 10px; box-shadow: 0 1px 3px rgba(15,23,42,.05); justify-content: center; }
</style>
"""


def mostra_hud(stato="sistemi online"):
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
<div class="hud">
  <div class="nucleo-box">
    <div class="anello a1"></div><div class="anello a2"></div>
    <div class="anello a3"></div><div class="cuore"></div>
  </div>
  <div class="titolo">{NOME_ASSISTENTE}</div>
  <div class="sottotitolo"><span class="punto"></span>{stato}</div>
</div>
""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------
#  Accesso con password (così nessun altro usa il tuo Jarvis)
# ---------------------------------------------------------------------
def controllo_accesso():
    if not PASSWORD or st.session_state.get("autorizzato"):
        return
    mostra_hud("identificazione richiesta")
    with st.form("accesso"):
        tentativo = st.text_input("Password", type="password")
        entra = st.form_submit_button("Accedi")
    if entra:
        if hmac.compare_digest(tentativo.strip(), PASSWORD):
            st.session_state.autorizzato = True
            st.rerun()
        else:
            st.error("Accesso negato.")
    st.stop()


# ---------------------------------------------------------------------
#  Memoria permanente (Gist privato di GitHub)
# ---------------------------------------------------------------------
def memoria_configurata():
    return bool(GITHUB_TOKEN and GIST_ID)


def _intestazioni_github():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def carica_dal_gist():
    """Legge tutti i file del Gist. Restituisce (dati, collegata)."""
    predefiniti = {
        FILE_MEMORIA: [],
        FILE_CRONOLOGIA: [],
        FILE_ABITUDINI: ab.vuoto(),
        FILE_STUDIO: {"piano": [], "visti": {}},
    }
    if not memoria_configurata():
        return predefiniti, False
    try:
        r = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=_intestazioni_github(), timeout=15)
        r.raise_for_status()
        files = r.json().get("files", {})
    except Exception as errore:
        st.session_state.errore_memoria = str(errore)
        return predefiniti, False
    dati = {}
    for nome, predefinito in predefiniti.items():
        info = files.get(nome) or {}
        contenuto = info.get("content")
        if info.get("truncated") and info.get("raw_url"):
            try:
                contenuto = requests.get(info["raw_url"], headers=_intestazioni_github(), timeout=15).text
            except Exception:
                pass
        try:
            valore = json.loads(contenuto) if contenuto else predefinito
        except json.JSONDecodeError:
            valore = predefinito
        dati[nome] = valore if isinstance(valore, type(predefinito)) else predefinito
    if not ab.valido(dati[FILE_ABITUDINI]):
        dati[FILE_ABITUDINI] = ab.vuoto()
    dati[FILE_STUDIO].setdefault("piano", [])
    dati[FILE_STUDIO].setdefault("visti", {})
    return dati, True


def leggi_dal_gist(nome_file):
    """Rilegge un solo file dal Gist (serve per vedere le X messe dal habit tracker)."""
    try:
        r = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=_intestazioni_github(), timeout=15)
        r.raise_for_status()
        info = r.json().get("files", {}).get(nome_file) or {}
        contenuto = info.get("content")
        if info.get("truncated") and info.get("raw_url"):
            contenuto = requests.get(info["raw_url"], headers=_intestazioni_github(), timeout=15).text
        return json.loads(contenuto) if contenuto else None
    except Exception:
        return None


def salva_nel_gist(nome_file, dati):
    if not st.session_state.get("memoria_ok"):
        return
    try:
        r = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers=_intestazioni_github(),
            json={"files": {nome_file: {"content": json.dumps(dati, ensure_ascii=False, indent=1)}}},
            timeout=15,
        )
        r.raise_for_status()
    except Exception:
        st.toast("⚠️ Non sono riuscito a salvare sulla memoria permanente.")


def salva_ricordi():
    salva_nel_gist(FILE_MEMORIA, st.session_state.memoria)


def salva_cronologia():
    st.session_state.cronologia = st.session_state.cronologia[-MAX_CRONOLOGIA:]
    salva_nel_gist(FILE_CRONOLOGIA, st.session_state.cronologia)


def salva_abitudini():
    st.session_state.abitudini["jarvis"] = True
    salva_nel_gist(FILE_ABITUDINI, st.session_state.abitudini)


# ---------------------------------------------------------------------
#  Il tuo habit tracker "Le mie abitudini" (file habit_tracker.html)
#  Il file è quello dell'artefatto, senza modifiche: Jarvis gli dà i dati
#  dal Gist e gli fa salvare lì invece che su Claude.
# ---------------------------------------------------------------------
FILE_TRACKER = Path(__file__).parent / "habit_tracker.html"
STATO_TRACKER = re.compile(r'(<script type="application/json" id="state">)(.*?)(</script>)', re.S)

COLLEGAMENTO_TRACKER = r"""<script>
(function () {
  var GIST = __GIST__, TOKEN = __TOKEN__;
  function salva(documento) {
    var m = documento.match(/<script type="application\/json" id="state">([\s\S]*?)<\/script>/);
    if (!m) return Promise.reject(new Error('stato non trovato'));
    var stato = JSON.parse(m[1]);
    stato.jarvis = true;
    return fetch('https://api.github.com/gists/' + GIST, {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer ' + TOKEN, 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ files: { 'abitudini.json': { content: JSON.stringify(stato) } } })
    }).then(function (r) { if (!r.ok) throw new Error('salvataggio non riuscito: ' + r.status); });
  }
  window.claude = { use: function (nome) {
    if (nome !== 'artifact' || !GIST || !TOKEN) return Promise.reject(new Error('non disponibile'));
    return Promise.resolve({ publish: salva });
  } };
})();
</script>
<style>[data-act="exp-open"]{display:none!important}</style>
"""


def html_tracker():
    try:
        return FILE_TRACKER.read_text(encoding="utf-8")
    except Exception:
        return None


def stato_dal_tracker():
    """I dati scritti dentro habit_tracker.html (quelli dell'artefatto al momento della copia)."""
    html = html_tracker()
    m = STATO_TRACKER.search(html or "")
    if not m:
        return None
    try:
        dati = json.loads(m.group(2))
    except json.JSONDecodeError:
        return None
    return dati if ab.valido(dati) else None


def scegli_abitudini(dal_gist):
    """La prima volta usa i dati dell'artefatto; poi sempre quelli salvati da Jarvis. Restituisce (dati, da_salvare)."""
    if isinstance(dal_gist, dict) and dal_gist.get("jarvis") and ab.valido(dal_gist):
        return dal_gist, False
    iniziali = stato_dal_tracker()
    if iniziali:
        iniziali["jarvis"] = True
        return iniziali, True
    return (dal_gist if ab.valido(dal_gist) else ab.vuoto()), False


def ricarica_abitudini():
    if not st.session_state.get("memoria_ok"):
        return
    dati = leggi_dal_gist(FILE_ABITUDINI)
    if isinstance(dati, dict) and dati.get("jarvis") and ab.valido(dati):
        st.session_state.abitudini = dati


def prepara_tracker(html):
    stato = json.dumps(st.session_state.abitudini, ensure_ascii=False).replace("<", "\\u003c")
    html = STATO_TRACKER.sub(lambda m: m.group(1) + stato + m.group(3), html, count=1)
    # salva dopo mezzo secondo invece di 1,6 secondi, così non si perde nulla cambiando sezione
    html = html.replace("timer=setTimeout(flush,1600)}", "timer=setTimeout(flush,400)}", 1)
    collegamento = (COLLEGAMENTO_TRACKER
                    .replace("__GIST__", json.dumps(GIST_ID if st.session_state.get("memoria_ok") else ""))
                    .replace("__TOKEN__", json.dumps(GITHUB_TOKEN if st.session_state.get("memoria_ok") else "")))
    return html.replace('<script id="app">', collegamento + '<script id="app">', 1)


def salva_studio():
    salva_nel_gist(FILE_STUDIO, st.session_state.studio)


# ---------------------------------------------------------------------
#  Aulaweb
# ---------------------------------------------------------------------
def aulaweb():
    if not AULAWEB_TOKEN:
        return None
    client = st.session_state.get("aulaweb")
    if client is None or client.token != AULAWEB_TOKEN or client.indirizzo != AULAWEB_URL.rstrip("/"):
        client = Aulaweb(AULAWEB_URL, AULAWEB_TOKEN)
        st.session_state.aulaweb = client
    return client


def controlla_novita():
    client = aulaweb()
    if not client:
        return "Aulaweb non è collegato: segui il Passo 9 della guida."
    testo, visti = client.novita(st.session_state.studio.get("visti", {}))
    st.session_state.studio["visti"] = visti
    st.session_state.studio["ultimo_controllo"] = int(time.time())
    salva_studio()
    return testo


# ---------------------------------------------------------------------
#  Utilità per le date dette a parole
# ---------------------------------------------------------------------
def leggi_data(testo, predefinita=None):
    testo = str(testo or "").strip().lower()
    base = oggi()
    if not testo or testo == "oggi":
        return predefinita or base
    if testo == "ieri":
        return base - datetime.timedelta(days=1)
    if testo == "domani":
        return base + datetime.timedelta(days=1)
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(testo, formato).date()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})", testo)
    if m:
        return datetime.date(base.year, int(m.group(2)), int(m.group(1)))
    raise ValueError(f"Data non capita: '{testo}'. Usa il formato AAAA-MM-GG.")


# ---------------------------------------------------------------------
#  Strumenti che il cervello può usare
# ---------------------------------------------------------------------
def cerca_sul_web(query, tipo="web"):
    try:
        from ddgs import DDGS

        motore = DDGS()
        if tipo == "notizie":
            risultati = motore.news(query, region="it-it", max_results=6)
        else:
            risultati = motore.text(query, region="it-it", max_results=6)
        if not risultati:
            return "Nessun risultato trovato."
        righe = []
        for r in risultati:
            link = r.get("href") or r.get("url", "")
            righe.append(f"- {r.get('title', '')} ({link}) {r.get('date', '')}\n  {r.get('body', '')[:300]}")
        return "\n".join(righe)
    except Exception as errore:
        return f"Ricerca non riuscita: {errore}"


def leggi_pagina(url):
    if not str(url).startswith(("http://", "https://")):
        return "Indirizzo non valido."
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Jarvis personal assistant)"}, timeout=12)
        r.raise_for_status()
        if "html" not in r.headers.get("Content-Type", "html"):
            return "La pagina non è una pagina web di testo."
        zuppa = BeautifulSoup(r.text, "html.parser")
        for tag in zuppa(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        testo = " ".join(zuppa.get_text(" ").split())
        return testo[:5000] or "Pagina vuota."
    except Exception as errore:
        return f"Impossibile leggere la pagina: {errore}"


def salva_ricordo(testo):
    testo = str(testo).strip()
    if not testo:
        return "Niente da salvare."
    if any(r["testo"].lower() == testo.lower() for r in st.session_state.memoria):
        return "Lo sapevo già."
    st.session_state.memoria.append({"id": uuid.uuid4().hex[:8], "testo": testo, "data": oggi().isoformat()})
    salva_ricordi()
    return "Ricordo salvato."


def dimentica_ricordo(parole):
    parole = str(parole).lower().strip()
    if not parole:
        return "Specifica cosa dimenticare."
    prima = len(st.session_state.memoria)
    st.session_state.memoria = [r for r in st.session_state.memoria if parole not in r["testo"].lower()]
    tolti = prima - len(st.session_state.memoria)
    if tolti:
        salva_ricordi()
    return f"Ricordi cancellati: {tolti}."


def strumento_memoria(azione, testo=""):
    return dimentica_ricordo(testo) if azione == "dimentica" else salva_ricordo(testo)


def strumento_aulaweb(azione, corso="", file="", parte=1):
    client = aulaweb()
    if not client:
        return "Aulaweb non è collegato. L'utente deve seguire il Passo 9 della guida per inserire AULAWEB_TOKEN."
    try:
        if azione == "corsi":
            return client.elenco_corsi()
        if azione == "materiale":
            return client.materiale(corso)
        if azione == "leggi_file":
            return client.leggi_file(corso, file, parte)
        if azione == "scadenze":
            return client.scadenze()
        if azione == "annunci":
            return client.annunci(corso)
        if azione == "novita":
            return controlla_novita()
        return f"Azione sconosciuta: {azione}"
    except ErroreAulaweb as errore:
        return str(errore)


def strumento_abitudini(azione, abitudine="", data="", voto=None, testo="", mese=""):
    ricarica_abitudini()  # prende anche le X messe nel habit tracker
    stato = st.session_state.abitudini
    try:
        giorno = leggi_data(data)
    except ValueError as errore:
        return str(errore)
    if giorno > oggi():
        return "Non posso segnare giorni futuri."
    if azione == "riepilogo":
        chiave = mese if re.fullmatch(r"\d{4}-\d{2}", str(mese or "")) else ab.chiave_mese(oggi())
        return ab.riepilogo_testo(stato, oggi(), chiave)
    M = ab.mese(stato, ab.chiave_mese(giorno))
    if azione in ("segna", "togli"):
        nomi = [n.strip() for n in re.split(r",| e ", str(abitudine)) if n.strip()]
        fatte, sconosciute = [], []
        for nome in nomi:
            h = ab.trova_abitudine(M, nome)
            if h:
                ab.imposta_segno(stato, giorno, h["id"], fatto=(azione == "segna"))
                fatte.append(h["name"])
            else:
                sconosciute.append(nome)
        if fatte:
            salva_abitudini()
        risposta = f"{'Segnate' if azione == 'segna' else 'Tolte'} il {giorno.strftime('%d/%m')}: {', '.join(fatte) or 'nessuna'}."
        if sconosciute:
            risposta += f" Non trovate: {', '.join(sconosciute)}. Abitudini esistenti: {', '.join(h['name'] for h in M['habits'])}."
        return risposta
    if azione == "voto":
        ab.imposta_voto(stato, giorno, voto)
        salva_abitudini()
        return f"Voto del {giorno.strftime('%d/%m')} impostato a {voto}."
    if azione == "buona_azione":
        ab.imposta_buona_azione(stato, giorno, testo)
        salva_abitudini()
        return f"Buona azione del {giorno.strftime('%d/%m')} salvata."
    return f"Azione sconosciuta: {azione}"


def _descrivi_sessione(s):
    stato = "✅" if s.get("fatto") else "⬜"
    return f"{stato} [{s['id']}] {s['data']} · {s.get('materia', '')}: {s.get('attivita', '')} ({s.get('durata_min', '?')} min)"


def strumento_piano(azione, dal="", giorni=14, sessioni=None, id=""):
    piano = st.session_state.studio.setdefault("piano", [])
    try:
        inizio = leggi_data(dal)
    except ValueError as errore:
        return str(errore)
    if azione == "leggi":
        fine = inizio + datetime.timedelta(days=int(giorni or 14))
        in_ritardo = [s for s in piano if s["data"] < oggi().isoformat() and not s.get("fatto")]
        periodo = [s for s in piano if inizio.isoformat() <= s["data"] <= fine.isoformat()]
        righe = []
        if in_ritardo:
            righe.append("In ritardo (non fatte):")
            righe += [_descrivi_sessione(s) for s in sorted(in_ritardo, key=lambda x: x["data"])]
        righe.append(f"Piano dal {inizio.strftime('%d/%m')} al {fine.strftime('%d/%m')}:")
        righe += [_descrivi_sessione(s) for s in sorted(periodo, key=lambda x: x["data"])] or ["(vuoto)"]
        return "\n".join(righe)
    if azione in ("sostituisci", "aggiungi"):
        nuove = []
        for s in sessioni or []:
            try:
                giorno = leggi_data(s.get("data"))
            except ValueError:
                continue
            nuove.append({
                "id": uuid.uuid4().hex[:6], "data": giorno.isoformat(),
                "materia": str(s.get("materia", ""))[:60], "attivita": str(s.get("attivita", ""))[:160],
                "durata_min": int(s.get("durata_min") or 60), "fatto": False,
            })
        if azione == "sostituisci":
            piano[:] = [s for s in piano if s.get("fatto") or s["data"] < inizio.isoformat()]
        piano.extend(nuove)
        piano.sort(key=lambda x: x["data"])
        salva_studio()
        st.session_state.piano_ver = st.session_state.get("piano_ver", 0) + 1
        return f"Piano aggiornato: {len(nuove)} sessioni {'inserite' if azione == 'aggiungi' else 'pianificate dal ' + inizio.strftime('%d/%m')}."
    if azione == "segna_fatto":
        for s in piano:
            if s["id"] == str(id):
                s["fatto"] = True
                salva_studio()
                st.session_state.piano_ver = st.session_state.get("piano_ver", 0) + 1
                return f"Sessione segnata come fatta: {s['materia']} – {s['attivita']}."
        return "Sessione non trovata: leggi prima il piano per vedere gli id."
    return f"Azione sconosciuta: {azione}"


def definizione_strumenti():
    strumenti = [
        {"type": "function", "function": {
            "name": "cerca_sul_web",
            "description": "Cerca informazioni aggiornate su internet.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
                "tipo": {"type": "string", "enum": ["web", "notizie"]},
            }, "required": ["query"]}}},
        {"type": "function", "function": {
            "name": "leggi_pagina",
            "description": "Legge il testo di una pagina web.",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
        {"type": "function", "function": {
            "name": "memoria",
            "description": "Memoria permanente: 'salva' un fatto duraturo sull'utente, 'dimentica' i ricordi che contengono il testo.",
            "parameters": {"type": "object", "properties": {
                "azione": {"type": "string", "enum": ["salva", "dimentica"]},
                "testo": {"type": "string"},
            }, "required": ["azione", "testo"]}}},
        {"type": "function", "function": {
            "name": "abitudini",
            "description": "Habit tracker dell'utente. 'riepilogo' (mese AAAA-MM opzionale); 'segna'/'togli' una o più abitudini (separate da virgola) in una data; 'voto' 0-5 della giornata; 'buona_azione' con testo. data: AAAA-MM-GG, 'oggi' o 'ieri'.",
            "parameters": {"type": "object", "properties": {
                "azione": {"type": "string", "enum": ["riepilogo", "segna", "togli", "voto", "buona_azione"]},
                "abitudine": {"type": "string"},
                "data": {"type": "string"},
                "voto": {"type": "integer"},
                "testo": {"type": "string"},
                "mese": {"type": "string"},
            }, "required": ["azione"]}}},
        {"type": "function", "function": {
            "name": "piano_studio",
            "description": "Calendario di studio. 'leggi' (dal, giorni); 'sostituisci' cancella le sessioni non fatte dalla data 'dal' in poi e inserisce 'sessioni'; 'aggiungi' inserisce 'sessioni'; 'segna_fatto' con id.",
            "parameters": {"type": "object", "properties": {
                "azione": {"type": "string", "enum": ["leggi", "sostituisci", "aggiungi", "segna_fatto"]},
                "dal": {"type": "string"},
                "giorni": {"type": "integer"},
                "id": {"type": "string"},
                "sessioni": {"type": "array", "items": {"type": "object", "properties": {
                    "data": {"type": "string"}, "materia": {"type": "string"},
                    "attivita": {"type": "string"}, "durata_min": {"type": "integer"},
                }, "required": ["data", "materia", "attivita"]}},
            }, "required": ["azione"]}}},
    ]
    if AULAWEB_TOKEN:
        strumenti.append({"type": "function", "function": {
            "name": "aulaweb",
            "description": "Aulaweb (Moodle dell'Università di Genova) in sola lettura: 'corsi', 'materiale' di un corso, 'leggi_file' (corso, file, parte 1,2,...), 'scadenze', 'annunci' di un corso, 'novita' dall'ultimo controllo.",
            "parameters": {"type": "object", "properties": {
                "azione": {"type": "string", "enum": ["corsi", "materiale", "leggi_file", "scadenze", "annunci", "novita"]},
                "corso": {"type": "string"},
                "file": {"type": "string"},
                "parte": {"type": "integer"},
            }, "required": ["azione"]}}})
    return strumenti


FUNZIONI = {
    "cerca_sul_web": cerca_sul_web,
    "leggi_pagina": leggi_pagina,
    "memoria": strumento_memoria,
    "aulaweb": strumento_aulaweb,
    "abitudini": strumento_abitudini,
    "piano_studio": strumento_piano,
}

ETICHETTE = {
    "cerca_sul_web": "🔎 Ricerca",
    "leggi_pagina": "📄 Lettura pagina",
    "memoria": "💾 Memoria",
    "aulaweb": "🎓 Aulaweb",
    "abitudini": "📅 Abitudini",
    "piano_studio": "🗓️ Piano di studio",
}


def esegui_strumento(nome, argomenti):
    funzione = FUNZIONI.get(nome)
    if not funzione:
        return f"Strumento sconosciuto: {nome}"
    try:
        return str(funzione(**argomenti))
    except TypeError as errore:
        return f"Argomenti non validi per {nome}: {errore}"
    except Exception as errore:
        return f"Errore durante {nome}: {errore}"


# ---------------------------------------------------------------------
#  Il cervello
# ---------------------------------------------------------------------
@st.cache_resource
def _crea_cliente(chiave, indirizzo):
    return OpenAI(api_key=chiave, base_url=indirizzo, max_retries=0, timeout=60)


def cliente():
    # la chiave fa parte della "cache": se la cambi nei Secrets, viene usata subito quella nuova
    return _crea_cliente(GROQ_API_KEY, BASE_URL)


def istruzioni_di_sistema():
    adesso = datetime.datetime.now(FUSO)
    giorni = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
    if st.session_state.memoria:
        ricordi = "\n".join(f"- {r['testo']}" for r in st.session_state.memoria[-150:])
    else:
        ricordi = "(ancora nessun ricordo)"
    aulaweb_stato = "collegato" if AULAWEB_TOKEN else "NON collegato (se serve, di' all'utente di seguire il Passo 9 della guida)"
    return f"""Sei {NOME_ASSISTENTE}, assistente personale ispirato al maggiordomo digitale dei film: elegante, calmo, efficiente, ironia garbata.
Chiami l'utente "{NOME_UTENTE}". Rispondi in italiano, conciso (spesso legge dal telefono). Non inventare fatti.
Adesso: {giorni[adesso.weekday()]} {adesso.strftime('%d/%m/%Y %H:%M')}. L'utente è uno studente universitario a Genova.

STRUMENTI
- cerca_sul_web/leggi_pagina: per tutto ciò che cambia nel tempo; cita i link delle fonti.
- memoria: salva fatti duraturi (date di esami e parziali, corsi, preferenze, persone, impegni fissi) o ciò che chiede di ricordare.
- aulaweb ({aulaweb_stato}): materiale dei corsi, file da leggere a parti, scadenze, annunci, novità.
- abitudini: quando dice di aver fatto un'abitudine, segnala; per sapere come va usa riepilogo.
- piano_studio: il suo calendario di studio.

ORGANIZZARE LO STUDIO
1. Prendi le date di esami/parziali dalla memoria; se mancano, chiedile e salvale.
2. Guarda materiale, scadenze e annunci su Aulaweb per sapere cosa c'è da studiare.
3. Leggi il piano esistente e il riepilogo abitudini (es. giorni di allenamento); se non sai quante ore al giorno ha, chiedilo.
4. Crea sessioni concrete (materia, cosa fare: es. "slide lezione 4 + autotest", durata), con ripassi distanziati
   e una simulazione d'esame prima di ogni prova; non sovraccaricare un giorno.
5. Salva con piano_studio 'sostituisci' e riassumi in poche righe.

COSA RICORDI DELL'UTENTE:
{ricordi}
"""


class TuttiOccupati(Exception):
    pass


def _in_pausa(modello):
    return st.session_state.setdefault("modelli_pausa", {}).get(modello, 0) > time.time()


def _metti_in_pausa(modello, secondi):
    st.session_state.setdefault("modelli_pausa", {})[modello] = time.time() + secondi


def completa(messaggi, strumenti, scelta, indice):
    """Una chiamata al cervello; se un modello è al limite passa al successivo. Restituisce (risposta, indice)."""
    ultimo_errore = None
    while indice < len(MODELLI):
        modello = MODELLI[indice]
        if _in_pausa(modello):
            indice += 1
            continue
        extra = {"reasoning_effort": "low"} if "gpt-oss" in modello else {}
        for tentativo in range(2):
            try:
                risposta = cliente().chat.completions.create(
                    model=modello, messages=messaggi, tools=strumenti, tool_choice=scelta,
                    temperature=0.5, extra_body=extra or None,
                )
                st.session_state.modello_in_uso = modello
                return risposta, indice
            except AuthenticationError:
                raise
            except RateLimitError as errore:
                ultimo_errore = errore
                giornaliero = "per day" in str(errore).lower() or "tpd" in str(errore).lower() or "rpd" in str(errore).lower()
                _metti_in_pausa(modello, 3600 if giornaliero else 60)
                break
            except BadRequestError as errore:
                ultimo_errore = errore
                testo = str(errore).lower()
                if "tool" in testo and tentativo == 0:
                    continue  # chiamata a strumento mal formata: riprova una volta
                break
            except (NotFoundError, APIStatusError, APIConnectionError) as errore:
                ultimo_errore = errore
                if isinstance(errore, APIConnectionError) and tentativo == 0:
                    continue
                break
        indice += 1
    raise TuttiOccupati(str(ultimo_errore))


def ragiona(aggiorna_stato):
    storia = []
    for m in st.session_state.cronologia[-MAX_CONTESTO:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content"):
            testo = m["content"] if m["role"] == "user" else m["content"][:1500]
            storia.append({"role": m["role"], "content": testo})
    messaggi = [{"role": "system", "content": istruzioni_di_sistema()}] + storia
    strumenti = definizione_strumenti()
    indice = 0
    try:
        for giro in range(MAX_GIRI_STRUMENTI + 1):
            scelta = "none" if giro == MAX_GIRI_STRUMENTI else "auto"
            risposta, indice = completa(messaggi, strumenti, scelta, indice)
            messaggio = risposta.choices[0].message
            if not messaggio.tool_calls:
                return (messaggio.content or "").strip() or "Mi scusi, non ho una risposta: può riformulare?"
            messaggi.append({
                "role": "assistant",
                "content": messaggio.content,
                "tool_calls": [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                    for c in messaggio.tool_calls
                ],
            })
            for chiamata in messaggio.tool_calls:
                nome = chiamata.function.name
                try:
                    argomenti = json.loads(chiamata.function.arguments or "{}")
                    if not isinstance(argomenti, dict):
                        argomenti = {}
                except json.JSONDecodeError:
                    argomenti = {}
                dettaglio = " ".join(str(v) for v in argomenti.values() if isinstance(v, (str, int)))[:80]
                aggiorna_stato(f"{ETICHETTE.get(nome, nome)}: {dettaglio}")
                risultato = esegui_strumento(nome, argomenti)
                messaggi.append({"role": "tool", "tool_call_id": chiamata.id, "content": risultato[:6000]})
        return "Mi scusi, mi sono perso nei miei stessi calcoli. Può ripetere la domanda?"
    except AuthenticationError:
        return "⚠️ La chiave GROQ_API_KEY non è valida. Controlla i Secrets dell'app (Passo 6 della guida)."
    except TuttiOccupati as errore:
        return ("⏳ Tutti i miei cervelli gratuiti hanno raggiunto il limite per ora. Riprovi tra un minuto "
                f"(se succede spesso, i limiti giornalieri di Groq si azzerano entro 24 ore).\n\nDettaglio: {errore}")


def trascrivi(audio_bytes):
    for modello in MODELLI_VOCE:
        try:
            risultato = cliente().audio.transcriptions.create(model=modello, file=("voce.wav", audio_bytes), language="it")
            return (risultato.text or "").strip()
        except Exception:
            continue
    st.toast("⚠️ Non sono riuscito a capire l'audio.")
    return ""


# ---------------------------------------------------------------------
#  Voce di Jarvis (sintesi vocale del browser, gratuita)
# ---------------------------------------------------------------------
MODELLO_VOCE_HTML = """
<style>
  body { margin: 0; }
  button { background: #ffffff; color: #1e3a8a; border: 1px solid #cbd5e1; border-radius: 10px;
           padding: 4px 12px; font-size: 14px; cursor: pointer; font-family: system-ui, sans-serif; }
  button:hover { border-color: #2563eb; color: #2563eb; }
</style>
<button id="parla">🔊 Ascolta</button>
<button id="zitto">⏹</button>
<script>
  const testo = __TESTO__;
  function parla() {
    try {
      const s = window.speechSynthesis;
      if (!s) return;
      s.cancel();
      const u = new SpeechSynthesisUtterance(testo);
      u.lang = 'it-IT';
      const voce = s.getVoices().find(v => v.lang && v.lang.toLowerCase().startsWith('it'));
      if (voce) u.voice = voce;
      u.rate = 1.03;
      s.speak(u);
    } catch (e) {}
  }
  document.getElementById('parla').onclick = parla;
  document.getElementById('zitto').onclick = () => { try { window.speechSynthesis.cancel(); } catch (e) {} };
  if (__AUTO__) { setTimeout(parla, 400); }
</script>
"""


def pulsante_voce(testo, automatico=False):
    pulito = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", testo)
    pulito = re.sub(r"https?://\S+", "", pulito)
    pulito = re.sub(r"[*#_`>|]", "", pulito)
    html = (MODELLO_VOCE_HTML
            .replace("__TESTO__", json.dumps(pulito[:3500]))
            .replace("__AUTO__", "true" if automatico else "false"))
    components.html(html, height=42)


# ---------------------------------------------------------------------
#  Barra laterale: memoria e impostazioni
# ---------------------------------------------------------------------
def barra_laterale():
    with st.sidebar:
        st.header("⚙️ Pannello")
        st.session_state.voce_auto = st.toggle(
            "🔊 Leggi le risposte ad alta voce", value=st.session_state.get("voce_auto", False))
        if st.button("🧹 Nuova conversazione"):
            st.session_state.cronologia = []
            salva_cronologia()
            st.rerun()

        st.subheader("🧠 Memoria")
        if st.session_state.memoria_ok:
            st.caption("Memoria permanente collegata ✅")
        elif memoria_configurata():
            st.caption("⚠️ Memoria permanente non raggiungibile: controlla GITHUB_TOKEN e GIST_ID.")
        else:
            st.caption("Memoria solo temporanea (si azzera chiudendo l'app). Vedi il Passo 7 della guida.")

        with st.form("nuovo_ricordo", clear_on_submit=True):
            nuovo = st.text_input("Aggiungi un ricordo a mano")
            if st.form_submit_button("Salva") and nuovo.strip():
                salva_ricordo(nuovo)
                st.rerun()

        if not st.session_state.memoria:
            st.caption("Nessun ricordo, per ora.")
        for ricordo in reversed(st.session_state.memoria):
            colonna_testo, colonna_tasto = st.columns([5, 1])
            colonna_testo.markdown(f"• {ricordo['testo']}")
            if colonna_tasto.button("🗑️", key=f"canc_{ricordo['id']}"):
                st.session_state.memoria = [r for r in st.session_state.memoria if r["id"] != ricordo["id"]]
                salva_ricordi()
                st.rerun()

        st.divider()
        st.caption(f"Cervello: {st.session_state.get('modello_in_uso', MODELLI[0])}")
        st.caption(f"Aulaweb: {'collegato' if AULAWEB_TOKEN else 'non collegato'}")


# ---------------------------------------------------------------------
#  Sezione 1: chat con Jarvis
# ---------------------------------------------------------------------
def saluto():
    ora = datetime.datetime.now(FUSO).hour
    parte = "Buongiorno" if 5 <= ora < 13 else ("Buon pomeriggio" if ora < 18 else "Buonasera")
    return f"{parte}, {NOME_UTENTE}. Tutti i sistemi sono operativi. Come posso esserle utile?"


COMANDI_RAPIDI = [
    "Cosa devo fare oggi?",
    "Ci sono novità su Aulaweb?",
    "Come vanno le mie abitudini questo mese?",
]


def imposta_domanda(testo):
    st.session_state.domanda_auto = testo


def sezione_jarvis():
    area_chat = st.container()
    if not st.session_state.cronologia:
        colonne = st.columns(len(COMANDI_RAPIDI))
        for colonna, comando in zip(colonne, COMANDI_RAPIDI):
            colonna.button(comando, on_click=imposta_domanda, args=(comando,), key=f"rapido_{comando}")
    audio = st.audio_input("🎙️ Premi il microfono, parla, poi premilo di nuovo")
    scritto = st.chat_input(f"Scrivi a {NOME_ASSISTENTE}…")

    domanda = scritto or st.session_state.pop("domanda_auto", None)
    if audio is not None and not domanda:
        dati_audio = audio.getvalue()
        impronta = hashlib.md5(dati_audio).hexdigest()
        if impronta != st.session_state.ultimo_audio:
            st.session_state.ultimo_audio = impronta
            with st.spinner("Ascolto…"):
                domanda = trascrivi(dati_audio)

    with area_chat:
        if not st.session_state.cronologia and not domanda:
            with st.chat_message("assistant", avatar="🔷"):
                st.markdown(saluto())

        totale = len(st.session_state.cronologia)
        for indice, messaggio in enumerate(st.session_state.cronologia):
            avatar = "🔷" if messaggio["role"] == "assistant" else "🧑"
            with st.chat_message(messaggio["role"], avatar=avatar):
                st.markdown(messaggio["content"])
                if indice == totale - 1 and messaggio["role"] == "assistant" and not domanda:
                    pulsante_voce(messaggio["content"])

        if domanda:
            st.session_state.cronologia.append({"role": "user", "content": domanda})
            with st.chat_message("user", avatar="🧑"):
                st.markdown(domanda)
            with st.chat_message("assistant", avatar="🔷"):
                with st.status("Elaborazione in corso…", expanded=False) as stato:
                    def aggiorna_stato(testo):
                        stato.update(label=testo)
                        stato.write(testo)

                    risposta = ragiona(aggiorna_stato)
                    stato.update(label="Completato", state="complete")
                st.markdown(risposta)
                pulsante_voce(risposta, automatico=st.session_state.voce_auto)
            st.session_state.cronologia.append({"role": "assistant", "content": risposta})
            salva_cronologia()


# ---------------------------------------------------------------------
#  Sezione 2: abitudini (il tuo habit tracker)
# ---------------------------------------------------------------------
def sezione_abitudini():
    html = html_tracker()
    if not html:
        st.error("Manca il file **habit_tracker.html** nel repository GitHub: caricalo come gli altri file.")
        return
    if not st.session_state.memoria_ok:
        st.warning("La memoria permanente non è collegata (Passo 7): le modifiche al habit tracker non verranno salvate.")
    ricarica_abitudini()
    components.html(prepara_tracker(html), height=1250, scrolling=True)
    st.caption("Quello che segni qui lo vede anche Jarvis, e puoi segnarlo anche a voce: «ho fatto allenamento».")


# ---------------------------------------------------------------------
#  Sezione 3: studio
# ---------------------------------------------------------------------
def cb_sessione(id_sessione, chiave):
    for s in st.session_state.studio["piano"]:
        if s["id"] == id_sessione:
            s["fatto"] = bool(st.session_state[chiave])
    salva_studio()


def vai_a_jarvis(domanda):
    st.session_state.sezione = SEZIONI[0]
    st.session_state.domanda_auto = domanda


def sezione_studio():
    client = aulaweb()
    if client:
        c1, c2, c3 = st.columns(3)
        if c1.button("🔄 Novità"):
            with st.spinner("Controllo i corsi su Aulaweb…"):
                try:
                    st.session_state.risultato_studio = controlla_novita()
                except ErroreAulaweb as errore:
                    st.session_state.risultato_studio = f"⚠️ {errore}"
        if c2.button("⏰ Scadenze"):
            with st.spinner("Leggo il calendario…"):
                try:
                    st.session_state.risultato_studio = client.scadenze()
                except ErroreAulaweb as errore:
                    st.session_state.risultato_studio = f"⚠️ {errore}"
        if c3.button("📂 I miei corsi"):
            with st.spinner("Leggo i corsi…"):
                try:
                    st.session_state.risultato_studio = client.elenco_corsi()
                except ErroreAulaweb as errore:
                    st.session_state.risultato_studio = f"⚠️ {errore}"
        if st.session_state.get("risultato_studio"):
            st.info(st.session_state.risultato_studio)
        ultimo = st.session_state.studio.get("ultimo_controllo")
        if ultimo:
            st.caption("Ultimo controllo novità: " + datetime.datetime.fromtimestamp(ultimo, FUSO).strftime("%d/%m/%Y %H:%M"))
    else:
        st.info("Aulaweb non è ancora collegato. Segui il Passo 9 della guida (e usa il riquadro «Collega Aulaweb» qui sotto).")

    st.button("✨ Chiedi a Jarvis di organizzarmi lo studio", on_click=vai_a_jarvis,
              args=("Organizzami lo studio delle prossime due settimane: controlla Aulaweb, le mie scadenze, "
                    "il piano attuale e le mie abitudini, poi crea il piano.",))

    st.markdown("### Piano di studio")
    piano = st.session_state.studio.get("piano", [])
    pv = st.session_state.get("piano_ver", 0)
    oggi_iso = oggi().isoformat()
    in_ritardo = [s for s in piano if s["data"] < oggi_iso and not s.get("fatto")]
    prossime = [s for s in piano if oggi_iso <= s["data"] <= (oggi() + datetime.timedelta(days=14)).isoformat()]
    if not piano:
        st.caption("Il piano è vuoto: chiedi a Jarvis di organizzarti lo studio.")
    if in_ritardo:
        st.markdown("**⚠️ In ritardo**")
        for s in sorted(in_ritardo, key=lambda x: x["data"]):
            k = f"sess_{pv}_{s['id']}"
            st.checkbox(f"{datetime.date.fromisoformat(s['data']).strftime('%d/%m')} · **{s['materia']}** – {s['attivita']} ({s['durata_min']} min)",
                        value=False, key=k, on_change=cb_sessione, args=(s["id"], k))
    giorno_corrente = None
    nomi = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
    for s in sorted(prossime, key=lambda x: x["data"]):
        if s["data"] != giorno_corrente:
            giorno_corrente = s["data"]
            d = datetime.date.fromisoformat(giorno_corrente)
            etichetta = "Oggi" if d == oggi() else ("Domani" if d == oggi() + datetime.timedelta(days=1) else nomi[d.weekday()].capitalize())
            st.markdown(f"**{etichetta} {d.strftime('%d/%m')}**")
        k = f"sess_{pv}_{s['id']}"
        st.checkbox(f"**{s['materia']}** – {s['attivita']} ({s['durata_min']} min)", value=bool(s.get("fatto")),
                    key=k, on_change=cb_sessione, args=(s["id"], k))

    with st.expander("🔑 Collega Aulaweb (converti il link in token)"):
        st.caption("Metodo B della guida: incolla qui il link che inizia con moodlemobile://token= e copia il token che appare.")
        link = st.text_input("Link moodlemobile://", key="link_token")
        if link:
            token = token_da_link(link)
            if token:
                st.success("Ecco il tuo token: copialo nei Secrets come AULAWEB_TOKEN.")
                st.code(token, language=None)
            else:
                st.error("Non riesco a leggere questo link: copialo per intero.")


# ---------------------------------------------------------------------
#  Programma principale
# ---------------------------------------------------------------------
def main():
    controllo_accesso()

    if not GROQ_API_KEY:
        mostra_hud("cervello non collegato")
        st.error("Manca la chiave **GROQ_API_KEY** nei Secrets dell'app. Segui il Passo 6 della guida.")
        st.stop()

    if "pronto" not in st.session_state:
        dati, collegata = carica_dal_gist()
        st.session_state.memoria = dati[FILE_MEMORIA]
        st.session_state.cronologia = dati[FILE_CRONOLOGIA]
        abitudini, da_salvare = scegli_abitudini(dati[FILE_ABITUDINI])
        st.session_state.abitudini = abitudini
        st.session_state.studio = dati[FILE_STUDIO]
        st.session_state.memoria_ok = collegata
        if da_salvare and collegata:
            salva_abitudini()
        st.session_state.ultimo_audio = None
        st.session_state.pronto = True

    mostra_hud()
    barra_laterale()
    sezione = st.radio("Sezione", SEZIONI, horizontal=True, key="sezione", label_visibility="collapsed")
    if sezione == SEZIONI[1]:
        sezione_abitudini()
    elif sezione == SEZIONI[2]:
        sezione_studio()
    else:
        sezione_jarvis()


main()
