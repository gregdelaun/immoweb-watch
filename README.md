# immoweb-watch

Surveille une recherche Immoweb et envoie un mail (Zoho, hello@aurelienowe.com) à chaque nouveau bien.

- `search.json` : l'URL de la recherche (page « recherche » Immoweb, convertie en endpoint JSON `search-results`) + réglages SMTP.
- `watch.py` : récupère les annonces, compare à `seen.json`, mail HTML avec photo/prix/commune/lien.
- `seen.json` : état, commité par le workflow à chaque passage.
- GitHub Actions toutes les 10 min (`.github/workflows/watch.yml`). Secrets : `SMTP_PASSWORD`, `ALERT_TO` (adresses séparées par des virgules).
- 3 échecs consécutifs (blocage Immoweb, panne) → mail d'alerte ; rétablissement → mail OK.

Changer la recherche : coller une nouvelle URL Immoweb dans `search.json`, vider `seen.json`, pousser. Le premier passage ré-amorce sans renvoyer les biens déjà en ligne.

Local : `echo "a@b.com,c@d.com" > recipients.local` puis `python3 watch.py --dry-run`.
