# =====================================================================
#  ABITUDINI - il tuo habit tracker "Le mie abitudini" dentro Jarvis
#  Stesso formato dati dell'artefatto, così puoi importare tutto.
# =====================================================================

import calendar
import datetime
import difflib
import html
import uuid

MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio",
        "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
GIORNI_BREVI = ["L", "M", "M", "G", "V", "S", "D"]  # lunedì = 0
NOMI_GIORNI_JS = ["dom", "lun", "mar", "mer", "gio", "ven", "sab"]  # come nell'artefatto: domenica = 0
TUTTI = [0, 1, 2, 3, 4, 5, 6]
VOTO_MAX = 5  # dalla versione 5 dell'habit tracker il voto va da 0 a 5


def vuoto():
    return {"version": 5, "scoreLabel": "Voto alla giornata", "mantraList": [], "mantraEvery": "week",
            "mantraPick": {}, "months": {}}


def mantra_attuale(stato, giorno):
    """Stessa regola dell'habit tracker: mantra scelto per la settimana/mese, altrimenti a rotazione dalla lista."""
    lista = stato.get("mantraList") or []
    scelti = stato.get("mantraPick") or {}
    lunedi = giorno - datetime.timedelta(days=giorno.weekday())
    if stato.get("mantraEvery") == "month":
        chiave, indice = "m" + chiave_mese(giorno), giorno.year * 12 + giorno.month - 1
    else:
        chiave, indice = "w" + lunedi.isoformat(), round((lunedi - datetime.date(1970, 1, 1)).days / 7)
    if isinstance(scelti.get(chiave), str):
        return scelti[chiave]
    if lista:
        return lista[indice % len(lista)]
    return mese(stato, chiave_mese(giorno)).get("mantra", "")


def giorno_js(data):
    """Numero del giorno della settimana come nell'artefatto (domenica = 0)."""
    return (data.weekday() + 1) % 7


def previsto(abitudine, data):
    return giorno_js(data) in (abitudine.get("days") or TUTTI)


def testo_giorni(giorni):
    if not giorni or len(giorni) == 7:
        return "ogni giorno"
    ordine = [1, 2, 3, 4, 5, 6, 0]
    return ", ".join(NOMI_GIORNI_JS[g] for g in ordine if g in giorni)


def valido(dati):
    return isinstance(dati, dict) and isinstance(dati.get("months"), dict)


def chiave_mese(giorno):
    return f"{giorno.year}-{giorno.month:02d}"


def giorni_nel_mese(chiave):
    anno, mese = map(int, chiave.split("-"))
    return calendar.monthrange(anno, mese)[1]


def nome_mese(chiave):
    anno, mese = map(int, chiave.split("-"))
    return f"{MESI[mese - 1]} {anno}"


def _normalizza(M):
    M.setdefault("mantra", "")
    M.setdefault("habits", [])
    M.setdefault("marks", {})
    M.setdefault("score", {})
    M.setdefault("good", {})
    M.setdefault("goals", [])
    for h in M["habits"]:
        if not isinstance(h.get("days"), list) or not h["days"]:
            h["days"] = list(TUTTI)
    return M


def mese(stato, chiave):
    """Il mese richiesto; se non esiste lo crea copiando abitudini, mantra e obiettivi aperti dal mese prima."""
    mesi = stato.setdefault("months", {})
    if chiave in mesi:
        return _normalizza(mesi[chiave])
    precedenti = sorted(k for k in mesi if k < chiave)
    fonte = _normalizza(mesi[precedenti[-1]]) if precedenti else (_normalizza(mesi[sorted(mesi)[0]]) if mesi else None)
    nuovo = {
        "mantra": fonte["mantra"] if fonte else "",
        "habits": [{"id": h["id"], "name": h["name"], "days": list(h.get("days") or TUTTI), **({"color": h["color"]} if "color" in h else {})} for h in fonte["habits"]] if fonte else [],
        "marks": {}, "score": {}, "good": {},
        "goals": [{"id": g["id"], "text": g["text"], "done": False} for g in fonte["goals"] if not g.get("done")] if fonte else [],
    }
    mesi[chiave] = nuovo
    return nuovo


def segnato(M, id_abitudine, giorno):
    return giorno in (M["marks"].get(id_abitudine) or [])


def trova_abitudine(M, nome):
    nome = str(nome or "").strip().lower()
    for h in M["habits"]:
        if h["name"].lower() == nome or h["id"].lower() == nome:
            return h
    for h in M["habits"]:
        if nome and (nome in h["name"].lower() or h["name"].lower() in nome):
            return h
    nomi = [h["name"].lower() for h in M["habits"]]
    simili = difflib.get_close_matches(nome, nomi, n=1, cutoff=0.5)
    return M["habits"][nomi.index(simili[0])] if simili else None


def imposta_segno(stato, giorno, id_abitudine, fatto=True):
    M = mese(stato, chiave_mese(giorno))
    lista = M["marks"].setdefault(id_abitudine, [])
    if fatto and giorno.day not in lista:
        lista.append(giorno.day)
        lista.sort()
    elif not fatto and giorno.day in lista:
        lista.remove(giorno.day)


def imposta_voto(stato, giorno, voto):
    M = mese(stato, chiave_mese(giorno))
    if voto is None:
        M["score"].pop(str(giorno.day), None)
    else:
        M["score"][str(giorno.day)] = max(0, min(VOTO_MAX, int(voto)))


def imposta_buona_azione(stato, giorno, testo):
    M = mese(stato, chiave_mese(giorno))
    testo = str(testo or "").strip()[:70]
    if testo:
        M["good"][str(giorno.day)] = testo
    else:
        M["good"].pop(str(giorno.day), None)


def aggiungi_abitudine(stato, chiave, nome):
    M = mese(stato, chiave)
    nome = str(nome).strip()[:24]
    if nome and not trova_abitudine(M, nome):
        M["habits"].append({"id": "x" + uuid.uuid4().hex[:8], "name": nome, "days": list(TUTTI)})


def togli_abitudine(stato, chiave, id_abitudine):
    M = mese(stato, chiave)
    M["habits"] = [h for h in M["habits"] if h["id"] != id_abitudine]
    M["marks"].pop(id_abitudine, None)


def serie_attuale(stato, id_abitudine, oggi):
    """Giorni previsti fatti di fila fino a oggi; i giorni non previsti si saltano, oggi non interrompe la serie."""
    g, n, primo = oggi, 0, True
    for _ in range(900):
        M = stato["months"].get(chiave_mese(g))
        h = next((x for x in (M or {}).get("habits", []) if x["id"] == id_abitudine), None)
        if not h:
            break
        if previsto(h, g):
            if g.day in ((M.get("marks") or {}).get(id_abitudine) or []):
                n += 1
            elif not primo:
                break
        primo = False
        g -= datetime.timedelta(days=1)
    return n


def statistiche(stato, chiave, oggi):
    M = mese(stato, chiave)
    N = giorni_nel_mese(chiave)
    anno, numero_mese = map(int, chiave.split("-"))
    attuale = chiave_mese(oggi)
    fino_a = oggi.day if chiave == attuale else (N if chiave < attuale else 0)
    per = {h["id"]: {"id": h["id"], "nome": h["name"], "giorni": testo_giorni(h["days"]),
                     "previsti": 0, "fatti": 0, "in_piu": 0, "record": 0, "fila": 0} for h in M["habits"]}
    perfetti = previsti_tot = fatti_tot = 0
    for d in range(1, fino_a + 1):
        data = datetime.date(anno, numero_mese, d)
        previsti_giorno = fatti_giorno = 0
        for h in M["habits"]:
            P = per[h["id"]]
            fatto = segnato(M, h["id"], d)
            if previsto(h, data):
                P["previsti"] += 1
                previsti_giorno += 1
                if fatto:
                    P["fatti"] += 1
                    fatti_giorno += 1
                    P["fila"] += 1
                    P["record"] = max(P["record"], P["fila"])
                else:
                    P["fila"] = 0
            elif fatto:
                P["in_piu"] += 1
        previsti_tot += previsti_giorno
        fatti_tot += fatti_giorno
        if previsti_giorno and fatti_giorno == previsti_giorno:
            perfetti += 1
    per_abitudine = []
    for h in M["habits"]:
        P = per[h["id"]]
        P["percentuale"] = round(P["fatti"] / P["previsti"] * 100) if P["previsti"] else None
        P.pop("fila")
        per_abitudine.append(P)
    voti = [v for k, v in M["score"].items() if int(k) <= fino_a and isinstance(v, (int, float))]
    return {
        "giorni_mese": N, "fino_a": fino_a, "per_abitudine": per_abitudine,
        "media_voto": round(sum(voti) / len(voti), 1) if voti else None,
        "giorni_perfetti": perfetti,
        "complessivo": round(fatti_tot / previsti_tot * 100) if previsti_tot else None,
    }


def riepilogo_testo(stato, oggi, chiave=None):
    """Riassunto compatto per il cervello di Jarvis."""
    chiave = chiave or chiave_mese(oggi)
    M = mese(stato, chiave)
    S = statistiche(stato, chiave, oggi)
    righe = [f"Habit tracker – {nome_mese(chiave)} (giorni contati: {S['fino_a']} su {S['giorni_mese']})"]
    mantra = mantra_attuale(stato, oggi)
    if mantra:
        righe.append(f"Mantra attuale: {mantra}")
    if not M["habits"]:
        righe.append("Nessuna abitudine impostata.")
    for p in S["per_abitudine"]:
        serie = serie_attuale(stato, p["id"], oggi) if chiave == chiave_mese(oggi) else None
        giorni = M["marks"].get(p["id"]) or []
        percentuale = "–" if p["percentuale"] is None else f"{p['percentuale']}%"
        righe.append(
            f"- {p['nome']} (prevista: {p['giorni']}): {p['fatti']} su {p['previsti']} giorni previsti ({percentuale}), record {p['record']}"
            + (f", serie attuale {serie}" if serie is not None else "")
            + (f", {p['in_piu']} volte in più" if p["in_piu"] else "")
            + f"; giorni fatti: {giorni}"
        )
    if S["complessivo"] is not None:
        righe.append(f"Completamento complessivo del mese: {S['complessivo']}%")
    if chiave == chiave_mese(oggi):
        oggi_previste = [h for h in M["habits"] if previsto(h, oggi)]
        fatte = [h["name"] for h in oggi_previste if segnato(M, h["id"], oggi.day)]
        mancano = [h["name"] for h in oggi_previste if not segnato(M, h["id"], oggi.day)]
        righe.append(f"Oggi ({oggi.day}): previste e fatte {fatte or 'nessuna'}; previste da fare {mancano or 'nessuna'}.")
        voto = M["score"].get(str(oggi.day))
        if voto is not None:
            righe.append(f"Voto di oggi: {voto}/{VOTO_MAX}")
    if S["media_voto"] is not None:
        righe.append(f"Media '{stato.get('scoreLabel', 'voto')}': {S['media_voto']}/{VOTO_MAX}; giorni perfetti: {S['giorni_perfetti']}")
    if M["goals"]:
        righe.append("Obiettivi: " + "; ".join(f"{g['text']} ({'raggiunto' if g.get('done') else 'aperto'})" for g in M["goals"]))
    return "\n".join(righe)


# ---------------------------------------------------------------- disegno della pagina del mese
CSS_QUADERNO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Patrick+Hand&display=swap');
.stApp .quaderno, .stApp .quaderno * { font-family:'Patrick Hand',cursive !important; color:#25348C; }
.quaderno { background-color:#FDFDFA; color:#25348C; font-family:'Patrick Hand',cursive;
  background-image:linear-gradient(#D9E0E8 1px,transparent 1px),linear-gradient(90deg,#D9E0E8 1px,transparent 1px);
  background-size:14px 14px; border-radius:6px; padding:16px 14px; overflow-x:auto;
  box-shadow:0 0 18px rgba(0,217,255,.18); }
.quaderno h3 { font-family:'Patrick Hand',cursive; color:#25348C; margin:0 0 4px 0; font-size:1.7rem; font-weight:400; }
.stApp .quaderno p.mantra { color:#25348C; }
.quaderno .mantra { text-transform:uppercase; letter-spacing:.03em; margin:0 0 10px 0; color:#25348C; font-size:1rem; }
.quaderno table { border-collapse:collapse; font-size:.95rem; }
.quaderno th { writing-mode:vertical-rl; transform:rotate(180deg); text-transform:uppercase; font-weight:400;
  font-size:.8rem; padding:4px 2px; border-right:1px solid #7C87BE; border-bottom:2px solid #25348C; height:96px;
  white-space:nowrap; color:#25348C; }
.quaderno th.giorno { writing-mode:horizontal-tb; transform:none; border-right:1.5px solid #25348C; }
.quaderno td { width:24px; height:22px; text-align:center; border-right:1px solid #7C87BE; border-bottom:1px solid #7C87BE;
  padding:0; color:#25348C; line-height:22px; }
.quaderno td.g { text-align:right; padding-right:5px; border-right:1.5px solid #25348C; white-space:nowrap; width:44px; }
.quaderno td.g i { font-style:normal; font-size:.7rem; color:#7B808A; margin-left:3px; }
.quaderno tr.oggi td.g b { background:#FFE680; border-radius:3px; padding:0 3px; font-weight:400; }
.quaderno tr.futuro td { opacity:.35; }
.quaderno td.x { font-size:1.15rem; }
.quaderno td.voto { font-size:.85rem; border-left:1.5px solid #25348C; width:30px; }
.quaderno td.azione { text-align:left; padding:0 8px; border-right:none; color:#25348C; font-size:.85rem; width:auto; white-space:nowrap; }
.quaderno tr.tot td { border-top:2px solid #25348C; color:#7C87BE; font-size:.85rem; }
</style>
"""


def griglia_html(stato, chiave, oggi):
    M = mese(stato, chiave)
    N = giorni_nel_mese(chiave)
    anno, numero_mese = map(int, chiave.split("-"))
    attuale = chiave_mese(oggi)
    e = html.escape
    parti = [CSS_QUADERNO, '<div class="quaderno">', f"<h3>{e(nome_mese(chiave))}</h3>"]
    if M["mantra"]:
        parti.append(f'<p class="mantra">Mantra: {e(M["mantra"])}</p>')
    parti.append('<table><tr><th class="giorno"></th>')
    for h in M["habits"]:
        parti.append(f"<th title=\"{e(testo_giorni(h['days']))}\">{e(h['name'])}</th>")
    parti.append('<th class="giorno">0–6</th><th class="giorno" style="text-align:left;padding-left:8px">Buone azioni</th></tr>')
    for d in range(1, N + 1):
        giorno_settimana = GIORNI_BREVI[datetime.date(anno, numero_mese, d).weekday()]
        futuro = chiave > attuale or (chiave == attuale and d > oggi.day)
        classe = "oggi" if (chiave == attuale and d == oggi.day) else ("futuro" if futuro else "")
        parti.append(f'<tr class="{classe}"><td class="g"><b>{d}</b><i>{giorno_settimana}</i></td>')
        data = datetime.date(anno, numero_mese, d)
        for h in M["habits"]:
            if segnato(M, h["id"], d):
                simbolo = "✕"
            else:
                simbolo = "" if previsto(h, data) else '<span style="color:#AAB0C8">–</span>'
            parti.append(f'<td class="x">{simbolo}</td>')
        voto = M["score"].get(str(d))
        parti.append(f'<td class="voto">{"" if voto is None else voto}</td>')
        parti.append(f'<td class="azione">{e(M["good"].get(str(d), ""))}</td></tr>')
    S = statistiche(stato, chiave, oggi)
    parti.append('<tr class="tot"><td class="g">%</td>')
    for p in S["per_abitudine"]:
        parti.append(f"<td>{'–' if p['percentuale'] is None else p['percentuale']}</td>")
    media = "" if S["media_voto"] is None else str(S["media_voto"]).replace(".", ",")
    parti.append(f'<td class="voto">{media}</td><td class="azione"></td></tr></table></div>')
    return "".join(parti)
