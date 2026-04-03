# Aktien-update

Tägliches automatisches Short-Squeeze-Reporting für internationale Märkte.  
Jeden Werktag um ~09:00 Uhr (Berlin) werden die 10 vielversprechendsten Squeeze-Kandidaten ermittelt und als GitHub Pages Website veröffentlicht.

---

## Einmalige Einrichtung

### 1. GitHub Pages aktivieren

1. Diesen Branch in `main` mergen.
2. Im Repository: **Settings → Pages → Source → Deploy from branch**
3. Branch: `gh-pages`, Ordner: `/ (root)` → **Save**

Der Report ist danach unter folgender URL erreichbar:  
`https://easywebb911.github.io/Aktien-Update/`

---

### 2. GitHub Personal Access Token erstellen (für den „Jetzt neu berechnen"-Button)

Der blaue Button auf der Report-Seite ruft die GitHub Actions API auf und startet das Python-Skript sofort – dafür benötigst du ein persönliches Zugriffstoken.

**Schritt-für-Schritt:**

1. Auf GitHub einloggen → oben rechts auf dein Profilbild klicken → **Settings**
2. Links unten: **Developer settings → Personal access tokens → Fine-grained tokens**
3. Klick auf **Generate new token**
4. Felder ausfüllen:
   - **Token name:** z. B. `squeeze-report-dispatch`
   - **Expiration:** nach Belieben (z. B. 1 Jahr)
   - **Repository access:** *Only select repositories* → `Aktien-update` auswählen
5. Unter **Permissions → Repository permissions:**
   - **Actions** → `Read and write` setzen
6. Klick auf **Generate token** → Token **sofort kopieren** (wird nur einmal angezeigt!)

**Token im Browser hinterlegen:**

1. Die Report-Seite im Browser öffnen
2. Auf **„Jetzt neu berechnen"** tippen
3. Das Token einfügen und auf **„Speichern & starten"** tippen
4. Das Token wird im `localStorage` deines Browsers gespeichert – kein erneutes Eingeben nötig

> Das Token verlässt deinen Browser **ausschließlich** in Richtung der offiziellen GitHub API (`api.github.com`). Es wird nirgendwo sonst übertragen oder gespeichert.

---

### 3. Repository-/Benutzernamen anpassen (nur bei Fork)

Falls du dieses Repository geforkt oder umbenannt hast, musst du in `generate_report.py` die folgenden Konstanten am Ende der Datei im `<script>`-Block der HTML-Vorlage anpassen:

```javascript
const GH_OWNER    = 'DEIN-BENUTZERNAME';   // ← hier ändern
const GH_REPO     = 'DEIN-REPO-NAME';      // ← hier ändern
const GH_WORKFLOW = 'daily-squeeze-report.yml';
const GH_BRANCH   = 'main';
```

Diese Zeilen befinden sich in der Funktion `generate_html()` in `generate_report.py`, im `<script>`-Block am Ende des HTML-Templates.

---

## Technischer Überblick

| Datei | Zweck |
|---|---|
| `generate_report.py` | Hauptskript: Finviz-Scraping, yfinance-Anreicherung, HTML-Generierung |
| `requirements.txt` | Python-Abhängigkeiten |
| `.github/workflows/daily-squeeze-report.yml` | GitHub Actions: täglich Mo–Fr ~09:00 Uhr Berlin |
| `docs/index.html` | Generierter Report (wird automatisch erstellt) |

**Datenquellen:** Finviz (Screener) · Yahoo Finance via yfinance (Kurse, Nachrichten)  
**Filterkriterien:** Short Float >15 % · Rel. Volumen ≥1,5× · Marktkapitalisierung <$10 Mrd. · Kurs >$1 USD
# Aktien-Update
Tägliche Meldungen zu Squeeze Kandidaten
