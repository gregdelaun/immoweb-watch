#!/usr/bin/env python3
"""Immoweb search watcher: polls a saved search, mails every new listing.

State lives in seen.json (committed back to the repo by the workflow).
Secrets: SMTP_PASSWORD and ALERT_TO (comma-separated recipients) from the
environment, or from ~/creator_pipeline/secrets.json when run locally.
"""
import json, os, sys, ssl, smtplib, html, time, datetime, urllib.request, urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "search.json")))
STATE_PATH = os.path.join(HERE, "seen.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def log(msg):
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def secrets():
    pw, to = os.environ.get("SMTP_PASSWORD"), os.environ.get("ALERT_TO")
    if not pw:
        p = os.path.expanduser("~/creator_pipeline/secrets.json")
        if os.path.exists(p):
            pw = json.load(open(p)).get("smtp_password")
    if not to:
        p = os.path.join(HERE, "recipients.local")  # gitignored
        if os.path.exists(p):
            to = open(p).read().strip()
    if not pw or not to:
        sys.exit("missing SMTP_PASSWORD or ALERT_TO")
    return pw, [a.strip() for a in to.replace(";", ",").split(",") if a.strip()]


def api_url(page):
    u = CFG["search_url"].replace("/fr/recherche/", "/fr/search-results/")
    sep = "&" if "?" in u else "?"
    return f"{u}{sep}page={page}"


def fetch(page):
    req = urllib.request.Request(api_url(page), headers={
        "User-Agent": UA, "Accept": "application/json", "Accept-Language": "fr-BE,fr;q=0.9",
        "Referer": CFG["search_url"]})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def listings():
    out = {}
    for page in range(1, CFG.get("max_pages", 5) + 1):
        d = fetch(page)
        res = d.get("results") or []
        for r in res:
            p = r.get("property") or {}
            loc = p.get("location") or {}
            rent = ((r.get("transaction") or {}).get("rental") or {})
            pic = ((r.get("media") or {}).get("pictures") or [{}])[0]
            out[str(r["id"])] = {
                "id": r["id"],
                "title": p.get("title") or f"{p.get('subtype','').title()} {p.get('bedroomCount','?')} ch",
                "type": p.get("subtype") or p.get("type"),
                "bedrooms": p.get("bedroomCount"),
                "surface": p.get("netHabitableSurface"),
                "rent": rent.get("monthlyRentalPrice"),
                "costs": rent.get("monthlyRentalCosts"),
                "price_label": (r.get("price") or {}).get("mainDisplayPrice"),
                "locality": loc.get("locality"), "postal": loc.get("postalCode"),
                "street": " ".join(x for x in [loc.get("street"), loc.get("number")] if x),
                "agency": r.get("customerName"),
                "epc": (r.get("transaction") or {}).get("certificate"),
                "image": pic.get("largeUrl") or pic.get("mediumUrl"),
                "url": f"https://www.immoweb.be/fr/annonce/{r['id']}",
                "seen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            }
        total = d.get("totalItems")
        if len(res) < 30 or (total and len(out) >= total):
            break
    return out


def load_state():
    if os.path.exists(STATE_PATH):
        return json.load(open(STATE_PATH))
    return {"seen": {}, "failures": 0, "seeded": False}


def save_state(st):
    json.dump(st, open(STATE_PATH, "w"), ensure_ascii=False, indent=1, sort_keys=True)


def send_mail(subject, html_body, text_body):
    pw, to = secrets()
    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((CFG["sender_name"], CFG["smtp_user"]))
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(CFG["smtp_host"], CFG.get("smtp_port", 465), context=ctx, timeout=60) as s:
        s.login(CFG["smtp_user"], pw)
        s.sendmail(CFG["smtp_user"], to, msg.as_string())
    log(f"mail sent to {len(to)} recipient(s): {subject}")


def card(l):
    e = html.escape
    price = l["price_label"] or (f"{l['rent']} €" if l["rent"] else "prix n.c.")
    bits = [f"{l['bedrooms']} ch" if l["bedrooms"] else None,
            f"{l['surface']} m²" if l["surface"] else None,
            f"PEB {l['epc']}" if l["epc"] else None, l["agency"]]
    meta = " · ".join(e(str(b)) for b in bits if b)
    img = f'<img src="{e(l["image"])}" width="220" style="border-radius:8px;display:block">' if l["image"] else ""
    return f"""
<table cellpadding="0" cellspacing="0" style="margin:0 0 20px;border:1px solid #e5e5e5;border-radius:10px;width:100%;max-width:640px">
<tr><td style="padding:12px;vertical-align:top;width:220px"><a href="{e(l['url'])}">{img}</a></td>
<td style="padding:12px;vertical-align:top;font-family:-apple-system,Helvetica,Arial,sans-serif;font-size:14px;color:#222">
<div style="font-size:18px;font-weight:700;margin-bottom:4px">{e(price)}</div>
<div style="font-weight:600">{e(l['postal'] or '')} {e(l['locality'] or '')}{(' · ' + e(l['street'])) if l['street'] else ''}</div>
<div style="color:#555;margin:4px 0">{e(l['title'])}</div>
<div style="color:#777;font-size:12px">{meta}</div>
<div style="margin-top:10px"><a href="{e(l['url'])}" style="background:#111;color:#fff;text-decoration:none;padding:8px 14px;border-radius:6px;display:inline-block">Voir l'annonce</a></div>
</td></tr></table>"""


def notify(new):
    new = sorted(new, key=lambda l: (l["rent"] or 9999))
    head = new[0]
    n = len(new)
    subject = (f"🏠 {n} nouveau{'x' if n > 1 else ''} bien{'s' if n > 1 else ''} Immoweb — "
               f"{head['price_label'] or ''} {head['locality'] or ''} {head['bedrooms'] or '?'} ch".strip())
    body = "".join(card(l) for l in new)
    html_body = f"""<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:640px">
<p style="color:#555">Recherche : <a href="{html.escape(CFG['search_url'])}">{html.escape(CFG['name'])}</a></p>{body}
<p style="color:#999;font-size:11px">Vérification toutes les 10 min · état dans seen.json</p></div>"""
    text = "\n".join(f"{l['price_label']} — {l['postal']} {l['locality']} — {l['title']}\n{l['url']}\n" for l in new)
    send_mail(subject, html_body, text)


def main():
    st = load_state()
    dry = "--dry-run" in sys.argv
    try:
        cur = listings()
    except Exception as ex:  # network / block
        st["failures"] = st.get("failures", 0) + 1
        log(f"fetch failed ({st['failures']}): {ex!r}")
        if st["failures"] == CFG.get("failure_alert_after", 3) and not dry:
            send_mail("⚠️ Alerte Immoweb en panne", f"<p>{html.escape(repr(ex))}</p><p>{st['failures']} échecs consécutifs.</p>", repr(ex))
        save_state(st)
        sys.exit(1)
    if st.get("failures", 0) >= CFG.get("failure_alert_after", 3) and not dry:
        send_mail("✅ Alerte Immoweb rétablie", "<p>La surveillance fonctionne à nouveau.</p>", "OK")
    st["failures"] = 0
    seen = st["seen"]
    new = [l for k, l in cur.items() if k not in seen]
    log(f"{len(cur)} listings online, {len(new)} new, {len(seen)} known")
    if not st.get("seeded"):
        for k, l in cur.items():
            seen[k] = l
        st["seeded"] = True
        if not dry:
            send_mail("✅ Alerte Immoweb activée",
                      f"<p>Surveillance active sur <a href=\"{html.escape(CFG['search_url'])}\">{html.escape(CFG['name'])}</a>.</p>"
                      f"<p>{len(cur)} biens déjà en ligne (non renvoyés). Vous recevrez un mail à chaque nouveau bien, vérification toutes les 10 minutes.</p>",
                      f"Surveillance active, {len(cur)} biens déjà en ligne.")
    elif new:
        if not dry:
            notify(new)
        for l in new:
            seen[str(l["id"])] = l
    # keep state small: forget listings gone for > 60 days
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=60)).isoformat()
    for k in list(seen):
        if k not in cur and seen[k].get("seen_at", "") < cutoff:
            del seen[k]
    st["last_run"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    st["online"] = len(cur)
    save_state(st)


if __name__ == "__main__":
    main()
