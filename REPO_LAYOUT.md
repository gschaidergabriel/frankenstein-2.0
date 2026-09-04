# Repo Layout — canonical clones

Stand: 2026-09-04, F2-WP-1207 P8 de-dup pass.

## Die drei kanonischen Klone

| Pfad | GitHub-Remote | Zweck |
|---|---|---|
| `~/frankenstein-2.0` | `gschaidergabriel/frankenstein-2.0` | Hauptcode: runtime, tools, tests, research/ — der aktive Frankenstein-2.0-Stack |
| `~/frankenstein-repo` | `gschaidergabriel/frankenstein.git` (Verzeichnisname weicht bewusst vom Repo-Namen ab, nicht "reparieren") | F2-WP-1207-Kernarbeit: RuntimeEpoch, GRID10-Persistenzschema, Gold-Tests |
| `~/self-integration` | `gschaidergabriel/self-integration` | Blog/Doku-Ablage: Entity-Identity-Design, INTEGRATION_HYPOTHESES.md, Paket-Nachvollzug |

Nur diese drei werden direkt bearbeitet. Alles andere ist Wegwerf-Arbeitskopie.

## De-Dup-Pass 2026-09-04 — was verifiziert und entfernt wurde

Vorheriges Inventar (nicht vollständig geprüft) nannte 5 mutmaßliche Dubletten.
Jede wurde einzeln neu verifiziert (`git remote -v`, vollständiger `git status`,
`git log`, echte Ancestry-Prüfung via `git merge-base --is-ancestor` gegen
`origin/main` bzw. die passende gepushte Branch, plus `git ls-remote origin`
für die LIVE-Wahrheit statt gecachter `git branch -r`-Listen).

**Wichtiger Befund beim Verifizieren:** `~/frankenstein-2.0`s lokaler
Fetch-Refspec holt nur `main` (`+refs/heads/main:refs/remotes/origin/main`),
kein `refs/heads/*`. Deshalb zeigte `git branch -r` in diesem Klon fälschlich
nur 3 Remote-Branches, obwohl auf GitHub tatsächlich Dutzende existieren
(u.a. die hier relevante `self-integration/wp1207-persistence-rebind-reentry-20260903`).
`git ls-remote origin <refname>` liefert die Live-Wahrheit unabhängig vom
lokalen Refspec — das wurde für jede Ancestry-Frage benutzt, nicht der
gecachte `branch -r`.

Alle 5 als DELETE eingestuft und entfernt (`rm -rf`), weil jede Bedingung
erfüllt war: `git status` sauber (bis auf `__pycache__`-Rauschen, inhaltlich
geprüft — reine `.pyc`-Bytecode-Dateien, keine echten Inhalte) UND HEAD
nachweisbar erreichbar von einer bereits gepushten origin-Branch.

- **`~/wp1207-work`** (Klon von frankenstein-2.0, Branch
  `self-integration/wp1207-persistence-rebind-reentry-20260903`, HEAD
  `9afdd8f6`). Vorheriger Fund "merge-base --is-ancestor gegen main
  SCHEITERT, echte unrelated history" war **technisch korrekt aber
  irreführend interpretiert**: der Branch ist 10 Commits *vor* main
  abgezweigt und läuft seither eigenständig weiter — nicht "unrelated",
  sondern ein normaler Feature-Branch, der (noch) nicht in main gemerged
  ist. `merge-base(9afdd8f6, main)` == main-Tip `425d69d` selbst, d.h. main
  IST Vorfahre von `9afdd8f6`, nicht umgekehrt getrennt. Per `git ls-remote
  origin` bestätigt: dieser exakte Branchname liegt bereits live auf GitHub
  (Tip dort ist sogar 1 Commit weiter, `ac57ba43`, s.u.). Nichts zu retten,
  alles bereits gesichert. Gelöscht.
- **`~/wp1207-blog`** (Klon von self-integration, HEAD `de32e63`,
  Branch main). Status war wirklich sauber (keine Dateien, nicht mal
  Rauschen). `de32e63` als Ancestor von `origin/main` (self-integration)
  bestätigt — vollständig bereits gepusht. Gelöscht.
- **`~/arbeit-wp1207-fortsetzung/frankenstein-2.0`** (verschachtelter Klon,
  HEAD `ac57ba43`, gleicher Branch wie wp1207-work, 1 Commit weiter). Die
  "11 uncommitted files" aus dem vorherigen Fund wurden einzeln geprüft:
  alle 11 sind `__pycache__`-Verzeichnisse mit `.cpython-312.pyc`-Dateien,
  keine echten Quelldateien. `git ls-remote origin
  refs/heads/self-integration/wp1207-persistence-rebind-reentry-20260903`
  bestätigt exakt `ac57ba43` live auf GitHub — Klon-HEAD und Remote-Tip sind
  identisch. Nichts Einzigartiges, nichts zu retten. Gelöscht.
- **`~/arbeit-wp1207-fortsetzung/frankenstein`** (verschachtelter Klon von
  frankenstein-repo, HEAD `a92a2f0`, Branch main, sauber). Als Ancestor von
  `origin/main` (frankenstein.git) bestätigt. Gelöscht.
- **`~/arbeit-wp1207-fortsetzung/self-integration`** (verschachtelter Klon,
  HEAD `86677af`, Branch main, sauber). Als Ancestor von `origin/main`
  (self-integration) bestätigt. Gelöscht.

Der leere Elternordner `~/arbeit-wp1207-fortsetzung/` (enthielt nur die drei
genannten Klone) wurde mitentfernt.

## Ergebnis

Kein Branch musste gerettet/gepusht werden — alle geprüften Commits waren
bereits auf GitHub vorhanden (teils unter anderem lokalem Tracking-Namen,
z.B. cachte `arbeit-wp1207-fortsetzung/frankenstein-2.0` lokal
`origin/wp1207-rebind` als Tracking-Branch, während der volle Name auf
GitHub `self-integration/wp1207-persistence-rebind-reentry-20260903` ist —
selbe Commit-SHA, nur unterschiedlicher lokaler Kurzname).

Nichts wurde archiviert — jede der 5 Kopien erfüllte die Lösch-Bedingung
zweifelsfrei nach eigener Prüfung (nicht nach den ungeprüften Labels des
vorherigen Inventars). Falls doch mal ein Klon gebraucht wird: alle Commits
liegen unter ihrem jeweiligen Branch-Namen auf GitHub, einfach neu clonen +
den Branch auschecken.

Von 8 lokalen Arbeitskopien auf 3 kanonische reduziert.
