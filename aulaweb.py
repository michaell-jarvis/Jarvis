# =====================================================================
#  AULAWEB - collegamento di Jarvis al Moodle dell'Università di Genova
#  Usa lo stesso accesso dell'app ufficiale di Moodle (un token personale).
#  Jarvis legge soltanto: non pubblica, non consegna, non scrive nulla.
# =====================================================================

import base64
import datetime
import difflib
import io
import time

from zoneinfo import ZoneInfo

import requests

FUSO = ZoneInfo("Europe/Rome")
TIMEOUT = 25
MAX_FILE_MB = 40
PEZZO = 5000  # caratteri letti per volta da un file


class ErroreAulaweb(Exception):
    pass


def token_da_link(testo):
    """Estrae il token dal link 'moodlemobile://token=...' (metodo B della guida)."""
    testo = (testo or "").strip()
    if "token=" in testo:
        testo = testo.split("token=", 1)[1]
    testo = testo.strip().strip("'\"").split("&")[0].split("#")[0]
    testo += "=" * (-len(testo) % 4)
    try:
        decodificato = base64.b64decode(testo).decode("utf-8", errors="ignore")
    except Exception:
        return None
    parti = decodificato.split(":::")
    if len(parti) >= 2 and len(parti[1]) >= 20:
        return parti[1].strip()
    return None


class Aulaweb:
    def __init__(self, indirizzo, token):
        self.indirizzo = indirizzo.rstrip("/")
        self.token = token
        self._utente = None
        self._corsi = None
        self._contenuti = {}  # cache: id corso -> (istante, contenuti)
        self._testi = {}      # cache: url file -> testo estratto

    # ------------------------------------------------------------ base
    def chiama(self, funzione, **parametri):
        dati = {"wstoken": self.token, "wsfunction": funzione, "moodlewsrestformat": "json"}
        dati.update(parametri)
        try:
            r = requests.post(f"{self.indirizzo}/webservice/rest/server.php", data=dati, timeout=TIMEOUT)
            r.raise_for_status()
            risposta = r.json()
        except Exception as errore:
            raise ErroreAulaweb(f"Aulaweb non risponde: {errore}")
        if isinstance(risposta, dict) and risposta.get("exception"):
            codice = risposta.get("errorcode", "")
            if codice in ("invalidtoken", "accessexception"):
                raise ErroreAulaweb("Il token di Aulaweb non è valido o è scaduto (vedi Passo 9 della guida).")
            raise ErroreAulaweb(f"Aulaweb ha risposto con un errore: {risposta.get('message', codice)}")
        return risposta

    def utente(self):
        if self._utente is None:
            self._utente = self.chiama("core_webservice_get_site_info")
        return self._utente

    def corsi(self):
        if self._corsi is None:
            uid = self.utente()["userid"]
            elenco = self.chiama("core_enrol_get_users_courses", userid=uid)
            self._corsi = [
                {"id": c["id"], "nome": c.get("fullname", ""), "breve": c.get("shortname", ""),
                 "ultimo_accesso": c.get("lastaccess") or 0}
                for c in elenco
                if not c.get("hidden")
            ]
            self._corsi.sort(key=lambda c: -(c["ultimo_accesso"] or 0))
        return self._corsi

    def trova_corso(self, nome):
        corsi = self.corsi()
        if not corsi:
            raise ErroreAulaweb("Non risulti iscritto a nessun corso su questo sito Aulaweb.")
        nome = str(nome or "").strip().lower()
        if nome.isdigit():
            for c in corsi:
                if c["id"] == int(nome):
                    return c
        for c in corsi:
            if nome and (nome in c["nome"].lower() or nome == c["breve"].lower()):
                return c
        parole = [p for p in nome.replace("'", " ").split() if len(p) >= 4]
        for c in corsi:
            parole_corso = c["nome"].lower().replace("'", " ").split()
            if parole and all(any(pc.startswith(p[:5]) for pc in parole_corso) for p in parole):
                return c
        nomi = [c["nome"].lower() for c in corsi]
        simili = difflib.get_close_matches(nome, nomi, n=1, cutoff=0.6)
        if simili:
            return corsi[nomi.index(simili[0])]
        elenco = "; ".join(c["nome"] for c in corsi)
        raise ErroreAulaweb(f"Corso '{nome}' non trovato. I tuoi corsi sono: {elenco}")

    def contenuti(self, corso_id, max_eta=600):
        salvato = self._contenuti.get(corso_id)
        if salvato and time.time() - salvato[0] < max_eta:
            return salvato[1]
        dati = self.chiama("core_course_get_contents", courseid=corso_id)
        self._contenuti[corso_id] = (time.time(), dati)
        return dati

    # ------------------------------------------------------------ elenchi
    def elenco_corsi(self):
        righe = [f"- {c['nome']} (id {c['id']})" for c in self.corsi()]
        return "Corsi a cui sei iscritto su Aulaweb:\n" + "\n".join(righe)

    def file_del_corso(self, corso):
        """Tutti i file e link del corso, con sezione e data."""
        elementi = []
        for sezione in self.contenuti(corso["id"]):
            for modulo in sezione.get("modules", []):
                if not modulo.get("uservisible", True):
                    continue
                for contenuto in modulo.get("contents", []) or []:
                    if contenuto.get("type") not in ("file", "url"):
                        continue
                    elementi.append({
                        "sezione": sezione.get("name", ""),
                        "attivita": modulo.get("name", ""),
                        "tipo": modulo.get("modname", ""),
                        "nome_file": contenuto.get("filename", ""),
                        "url": contenuto.get("fileurl", ""),
                        "modificato": contenuto.get("timemodified") or 0,
                        "dimensione": contenuto.get("filesize") or 0,
                        "chiave": f"{corso['id']}|{modulo.get('id')}|{contenuto.get('filename', '')}",
                    })
        return elementi

    def materiale(self, nome_corso):
        corso = self.trova_corso(nome_corso)
        righe = [f"Materiale del corso: {corso['nome']}"]
        for sezione in self.contenuti(corso["id"]):
            moduli = [m for m in sezione.get("modules", []) if m.get("uservisible", True)]
            if not moduli:
                continue
            righe.append(f"\n## {sezione.get('name') or 'Sezione'}")
            for modulo in moduli:
                file = [c for c in (modulo.get("contents") or []) if c.get("type") == "file"]
                if file:
                    for c in file[:15]:
                        righe.append(f"- {modulo.get('name')}: {c.get('filename')} ({data(c.get('timemodified'))})")
                else:
                    righe.append(f"- [{modulo.get('modname')}] {modulo.get('name')}")
        testo = "\n".join(righe)
        return testo[:7000] + ("\n…(elenco troncato)" if len(testo) > 7000 else "")

    # ------------------------------------------------------------ lettura file
    def leggi_file(self, nome_corso, nome_file, parte=1):
        corso = self.trova_corso(nome_corso)
        elementi = [e for e in self.file_del_corso(corso) if e["tipo"] != "url" and e["url"]]
        if not elementi:
            return "Questo corso non ha file scaricabili."
        cerca = str(nome_file or "").lower().strip()
        scelto = None
        for e in elementi:
            if cerca and (cerca in e["nome_file"].lower() or cerca in e["attivita"].lower()):
                scelto = e
                break
        if not scelto:
            nomi = [f"{e['attivita']} {e['nome_file']}".lower() for e in elementi]
            simili = difflib.get_close_matches(cerca, nomi, n=1, cutoff=0.2)
            if not simili:
                elenco = "; ".join(e["nome_file"] for e in elementi[:40])
                return f"File '{nome_file}' non trovato. File disponibili: {elenco}"
            scelto = elementi[nomi.index(simili[0])]

        if scelto["url"] not in self._testi:
            if scelto["dimensione"] > MAX_FILE_MB * 1024 * 1024:
                return f"Il file {scelto['nome_file']} è troppo grande da leggere ({scelto['dimensione'] // 1048576} MB)."
            separatore = "&" if "?" in scelto["url"] else "?"
            try:
                r = requests.get(f"{scelto['url']}{separatore}token={self.token}", timeout=60)
                r.raise_for_status()
            except Exception as errore:
                return f"Download non riuscito: {errore}"
            self._testi[scelto["url"]] = estrai_testo(scelto["nome_file"], r.content)

        testo = self._testi[scelto["url"]]
        if not testo.strip():
            return f"Ho scaricato {scelto['nome_file']} ma non contiene testo leggibile (forse è una scansione o solo immagini)."
        totale = max(1, -(-len(testo) // PEZZO))
        parte = min(max(1, int(parte or 1)), totale)
        pezzo = testo[(parte - 1) * PEZZO: parte * PEZZO]
        intestazione = f"File: {scelto['nome_file']} (corso {corso['nome']}) — parte {parte} di {totale}."
        if parte < totale:
            intestazione += f" Per continuare chiedi la parte {parte + 1}."
        return intestazione + "\n\n" + pezzo

    # ------------------------------------------------------------ scadenze e annunci
    def scadenze(self, giorni=60):
        adesso = int(time.time())
        dati = self.chiama(
            "core_calendar_get_action_events_by_timesort",
            timesortfrom=adesso,
            timesortto=adesso + giorni * 86400,
            limitnum=30,
        )
        eventi = dati.get("events", []) if isinstance(dati, dict) else []
        if not eventi:
            return f"Nessuna scadenza su Aulaweb nei prossimi {giorni} giorni."
        righe = [f"Scadenze su Aulaweb nei prossimi {giorni} giorni:"]
        for e in eventi:
            corso = (e.get("course") or {}).get("fullname", "")
            righe.append(f"- {data(e.get('timesort'), ora=True)}: {e.get('name')} ({corso})")
        return "\n".join(righe)

    def annunci(self, nome_corso, quanti=5):
        corso = self.trova_corso(nome_corso)
        forum = self.chiama("mod_forum_get_forums_by_courses", **{"courseids[0]": corso["id"]})
        notizie = [f for f in forum if f.get("type") == "news"] or forum[:1]
        if not notizie:
            return f"Il corso {corso['nome']} non ha un forum annunci."
        discussioni = self.chiama(
            "mod_forum_get_forum_discussions", forumid=notizie[0]["id"], page=0, perpage=quanti
        ).get("discussions", [])
        if not discussioni:
            return f"Nessun annuncio nel corso {corso['nome']}."
        righe = [f"Ultimi annunci del corso {corso['nome']}:"]
        for d in discussioni[:quanti]:
            messaggio = pulisci_html(d.get("message", ""))[:600]
            righe.append(f"\n### {d.get('name')} — {data(d.get('created') or d.get('timemodified'))}, {d.get('userfullname', '')}\n{messaggio}")
        return "\n".join(righe)

    # ------------------------------------------------------------ novità
    def novita(self, visti):
        """Confronta i file attuali con quelli già visti. Restituisce (testo, nuovi_visti)."""
        prima_volta = not visti
        nuovi_visti = dict(visti)
        nuovi = []
        for corso in self.corsi():
            try:
                elementi = self.file_del_corso(corso)
            except ErroreAulaweb:
                continue
            for e in elementi:
                vecchio = visti.get(e["chiave"])
                if vecchio is None or e["modificato"] > vecchio:
                    nuovi.append((corso["nome"], e, vecchio is not None))
                nuovi_visti[e["chiave"]] = e["modificato"]
        if prima_volta:
            ultimi = sorted(nuovi, key=lambda x: -x[1]["modificato"])[:10]
            righe = [f"Prima scansione completata: registrati {len(nuovi)} file. Ecco i 10 più recenti:"]
            righe += [f"- {data(e['modificato'])} · {corso}: {e['nome_file']}" for corso, e, _ in ultimi]
            return "\n".join(righe), nuovi_visti
        if not nuovi:
            return "Nessuna novità su Aulaweb dall'ultimo controllo.", nuovi_visti
        nuovi.sort(key=lambda x: -x[1]["modificato"])
        righe = [f"Novità su Aulaweb ({len(nuovi)}):"]
        for corso, e, aggiornato in nuovi[:30]:
            stato = "aggiornato" if aggiornato else "nuovo"
            righe.append(f"- [{stato}] {corso}: {e['nome_file']} (sezione '{e['sezione']}', {data(e['modificato'])})")
        return "\n".join(righe), nuovi_visti


# ---------------------------------------------------------------- utilità
def data(istante, ora=False):
    if not istante:
        return "data sconosciuta"
    momento = datetime.datetime.fromtimestamp(int(istante), FUSO)
    return momento.strftime("%d/%m/%Y %H:%M" if ora else "%d/%m/%Y")


def pulisci_html(html):
    try:
        from bs4 import BeautifulSoup
        return " ".join(BeautifulSoup(html or "", "html.parser").get_text(" ").split())
    except Exception:
        return html or ""


def estrai_testo(nome_file, contenuto):
    nome = (nome_file or "").lower()
    try:
        if nome.endswith(".pdf") or contenuto[:4] == b"%PDF":
            from pypdf import PdfReader
            lettore = PdfReader(io.BytesIO(contenuto))
            pagine = []
            for numero, pagina in enumerate(lettore.pages, start=1):
                testo = (pagina.extract_text() or "").strip()
                if testo:
                    pagine.append(f"[pagina {numero}]\n{testo}")
            return "\n\n".join(pagine)
        if nome.endswith(".pptx"):
            from pptx import Presentation
            presentazione = Presentation(io.BytesIO(contenuto))
            slide = []
            for numero, s in enumerate(presentazione.slides, start=1):
                testi = [f.text_frame.text for f in s.shapes if getattr(f, "has_text_frame", False) and f.text_frame.text.strip()]
                if testi:
                    slide.append(f"[slide {numero}]\n" + "\n".join(testi))
            return "\n\n".join(slide)
        if nome.endswith(".docx"):
            from docx import Document
            documento = Document(io.BytesIO(contenuto))
            return "\n".join(p.text for p in documento.paragraphs if p.text.strip())
        if nome.endswith((".txt", ".md", ".csv")):
            return contenuto.decode("utf-8", errors="ignore")
        if nome.endswith((".html", ".htm")):
            return pulisci_html(contenuto.decode("utf-8", errors="ignore"))
    except Exception as errore:
        return f"(Non sono riuscito a leggere il file: {errore})"
    return f"(Il formato del file {nome_file} non è leggibile da Jarvis: posso leggere PDF, PowerPoint .pptx, Word .docx e testo.)"
