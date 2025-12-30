# Leitfaden: Allgemeine Arbeit mit einem HPC- und KI-Cluster an einer Hochschule

## 1. Ziel dieses Dokuments

Dieser Leitfaden hilft, einen typischen Hochschul-Cluster zu verstehen. Der Text ist bewusst allgemein gehalten und beschreibt keine privaten Installationen oder personenbezogenen Pfade. Er erklaert typische Ablaeufe, Begriffe und Befehle, die an vielen akademischen High-Performance-Computing- und KI-Clustern aehnlich sind. Der Leitfaden ist so formuliert, dass er sich gut fuer Embeddings eignet:

- wichtige Begriffe werden mehrfach und mit unterschiedlichen Formulierungen erwaehnt,
- es gibt viele Beispiel-Fragen in Alltagssprache,
- die Antworten sind moeglichst klar, konkret und technisch korrekt.

## 2. Was ist ein Cluster?

Ein Rechencluster ist eine Gruppe vieler miteinander verbundener Server, die zusammenarbeiten. Jeder Server ist ein Knoten (Node). Alle Knoten sind ueber ein schnelles Netzwerk verbunden und greifen auf gemeinsame Dateisysteme zu. Aus Sicht der Benutzerinnen und Benutzer wirkt ein Cluster wie ein grosser Rechner, auf dem mehrere Rechenjobs parallel laufen koennen.

Typische Ziele eines Hochschul-Clusters:

- Bereitstellung von Rechenleistung fuer Simulationen und numerische Experimente,
- Training und Ausfuehrung von KI- und Machine-Learning-Modellen,
- Verarbeitung grosser Datenmengen, z. B. aus Messreihen, Sensoren oder Log-Dateien,
- Unterstuetzung von Forschungsprojekten und Abschlussarbeiten.

Ein Cluster besteht meist aus:

- Login-Knoten (User-Nodes),
- Compute-Nodes mit vielen CPU-Kernen,
- GPU-Nodes fuer Deep Learning,
- Storage- und Fileservern fuer gemeinsamen Speicher.

## 3. Login-Knoten und Rechenknoten

Der Login-Knoten ist der Einstiegspunkt in den Cluster. Dort erfolgen interaktive Arbeiten, das Bearbeiten von Dateien und das Starten von Jobs.

Wichtige Merkmale des Login-Knotens:

- Er ist fuer interaktive Arbeit gedacht, nicht fuer lange oder rechenintensive Jobs.
- Er hat oft Internetzugang, damit Software installiert oder Repos geklont werden koennen.
- Er stellt die gewohnte Shell-Umgebung bereit.

Compute-Nodes sind die Maschinen, auf denen die eigentlichen Rechenjobs laufen. Es gibt CPU-Nodes ohne GPUs und GPU-Nodes mit einer oder mehreren GPUs. Auf den Compute-Nodes laufen SLURM-Jobs, die der Scheduler plant und startet. Compute-Nodes haben oft keinen direkten Internetzugang.

Eine Grundregel:

- Vorbereitung, Skripte schreiben, Daten kopieren: auf dem Login-Node.
- Lange Simulationen, Trainingslaeufe, umfangreiche Analysen: als SLURM-Job auf einem Compute-Node.

## 4. SSH-Verbindung zum Cluster

Der Zugang erfolgt per SSH (Secure Shell). Ein typischer Login-Befehl sieht so aus:

```bash
ssh benutzername@cluster.hochschule-example.de
```

Dabei ist "benutzername" der Hochschul- oder Cluster-Account und "cluster.hochschule-example.de" der Hostname des Login-Knotens. In vielen Faellen ist zusaetzlich eine VPN-Verbindung noetig, wenn der Zugang von ausserhalb des Hochschulnetzes erfolgt.

Es gibt zwei verbreitete Authentifizierungsverfahren:

- Anmeldung mit Passwort,
- Anmeldung mit SSH-Schluesseln (Public-Key-Authentifizierung).

SSH-Keys sind komfortabel und sicher, wenn sie korrekt eingerichtet sind. Ein Schluesselpaar laesst sich lokal erzeugen, zum Beispiel mit:

```bash
ssh-keygen -t ed25519 -C "cluster-zugang"
```

Der oeffentliche Schluessel (Datei mit Endung .pub) wird in `~/.ssh/authorized_keys` auf dem Cluster hinterlegt. Wichtig sind die Dateirechte: `~/.ssh` sollte 700 haben, `authorized_keys` 600. Bei falschen Rechten ignoriert SSH den Schluessel.

Haeufige Fragen in Alltagssprache:

- "Wie erfolgt der Login auf dem Cluster?"
- "Warum klappt der SSH-Login nicht?"
- "Was bedeutet Permission denied (publickey)?"

## 5. Dateisystem, Home-Verzeichnis und Quotas

Jede Person erhaelt auf dem Cluster ein Home-Verzeichnis, zum Beispiel `/home/benutzername`. Dort liegen persoenliche Dateien, Konfigurationen und kleinere Datenmengen. Zusaetzlich gibt es oft Projektverzeichnisse, etwa `/project/projektname` oder `/data/projektname`. Dort werden groessere Datensaetze und gemeinsam genutzte Dateien abgelegt.

Viele Hochschulcluster verwenden Quotas, also Speicherlimits. Wird das Quota ueberschritten, koennen keine weiteren Daten geschrieben werden.

Typische Fehlermeldungen bei vollem Quota:

- Permission denied beim Schreiben einer Datei,
- No space left on device,
- Input/output error beim Versuch, eine Datei zu erstellen.

Das fuehrt oft zu Verwirrung, weil zunaechst ein Programmfehler vermutet wird. In Wahrheit ist der Speicher voll. Um die Belegung zu pruefen, eignen sich:

```bash
df -h
du -sh ~/*
```

`df -h` zeigt die Belegung der Dateisysteme, `du -sh` listet die Groesse von Unterverzeichnissen im Home-Verzeichnis. Auf dieser Basis laesst sich entscheiden, welche Daten geloescht oder archiviert werden koennen.

## 6. Daten auf den Cluster uebertragen

Fuer den Datentransfer werden haeufig `scp` und `rsync` verwendet. Mit `scp` lassen sich einzelne Dateien oder Ordner kopieren:

```bash
scp datei.txt benutzername@cluster.hochschule-example.de:/home/benutzername/
```

Um eine Datei vom Cluster auf den lokalen Rechner zu holen:

```bash
scp benutzername@cluster.hochschule-example.de:/home/benutzername/ergebnis.csv .
```

Fuer grosse Datenmengen ist `rsync` oft besser geeignet. `rsync` synchronisiert Verzeichnisse und uebertraegt nur Veraenderungen:

```bash
rsync -avh lokaler_ordner/ benutzername@cluster.hochschule-example.de:/home/benutzername/projekt/
```

Die Optionen bedeuten:

- a: Archivmodus (erhaelt Rechte und Zeiten),
- v: verbose, ausfuehrliche Ausgabe,
- h: human readable, leicht lesbare Groessenangaben.

Haeufige Fragen in natuerlicher Sprache:

- "Wie lassen sich Daten auf den Cluster hochladen?"
- "Wie kommen Ergebnisse zurueck auf den lokalen Rechner?"
- "Was ist der Unterschied zwischen scp und rsync?"

## 7. Der Workload-Manager SLURM

SLURM ist ein verbreiteter Workload-Manager fuer Cluster. Er verwaltet Rechenjobs, weist Ressourcen zu und fuehrt Jobs auf passenden Knoten aus. In Dokumentationen tauchen Begriffe wie Job, Partition, QOS und GRES auf.

Wichtige SLURM-Befehle:

- `sinfo`: Informationen ueber Knoten und Partitionen,
- `squeue`: Jobs in der Warteschlange,
- `salloc`: interaktive Ressourcenreservierung,
- `sbatch`: Batch-Job einreichen,
- `scancel`: Job abbrechen.

Ein einfacher Aufruf von `sinfo` zeigt, welche Partitionen existieren und wie ausgelastet sie sind. Mit `squeue` lassen sich laufende oder wartende Jobs pruefen. Wenn nur eigene Jobs angezeigt werden sollen:

```bash
squeue -u $USER
```

Typische Fragen:

- "Was bedeutet ST=PD in der Jobliste?"
- "Wie laesst sich erkennen, ob eine Partition frei ist?"
- "Wie laesst sich ein Job abbrechen?"

## 8. Batch-Jobs: Skripte mit sbatch starten

Batch-Skripte enthalten SLURM-Direktiven (`#SBATCH`) und die Befehle, die ausgefuehrt werden sollen.

Beispiel fuer einen GPU-Job:

```bash
#!/bin/bash
#SBATCH --job-name=beispiel_gpu_job
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=logs/%x-%j.out
module load python/3.11
source ~/venvs/projektenv/bin/activate
python train.py
```

Das Skript wird gespeichert (z. B. `job_gpu.sh`) und mit `sbatch` eingereicht:

```bash
sbatch job_gpu.sh
```

SLURM weist dem Job Ressourcen zu, sobald sie verfuegbar sind. Der Job laeuft unabhaengig von der SSH-Sitzung.

## 9. Interaktive Jobs mit salloc und srun

Interaktives Arbeiten auf einem Compute-Node erfolgt ueber `salloc` und `srun`.

Beispiel:

1. Ressourcen reservieren:

```bash
salloc --partition=gpu --gres=gpu:1 --cpus-per-task=4 --mem=32G --time=02:00:00
```

2. Interaktive Shell starten:

```bash
srun --pty bash -l
```

Wenn Ressourcen frei sind, wird eine Shell auf einem GPU-Knoten bereitgestellt. Dort kann z. B. `nvidia-smi` ausgefuehrt oder eine Python-Umgebung aktiviert werden.

## 10. QOS, Limits und Pending-Jobs

QOS steht fuer Quality of Service. QOS-Regeln legen fest, wie viele Ressourcen genutzt werden duerfen und wie lange Jobs laufen duerfen. Wenn ein Job laenger laufen soll als erlaubt, bleibt er im Pending-Zustand. In `squeue` stehen dann Gruende wie `QOSMaxWallDurationPerJobLimit`.

Weitere typische Gruende:

- Resources: Es sind keine passenden Ressourcen frei.
- Priority: Andere Jobs haben hoehere Prioritaet.
- QOSMaxGRESPerUser: Die maximal erlaubten GPUs sind bereits belegt.

Wenn ein Job lange pending ist, sollte geprueft werden:

- ob zu viele Ressourcen angefordert wurden,
- ob die Laufzeit zu hoch ist,
- ob die Partition stark ausgelastet ist.

Oft hilft es, Ressourcenanforderungen zu reduzieren, die Laufzeit zu kuerzen oder eine andere Partition zu waehlen.

## 11. Software-Umgebungen: Module, venv und Conda

Auf Clustern muessen oft mehrere Softwareversionen parallel genutzt werden. Modulsysteme helfen dabei. Mit `module avail` lassen sich verfuegbare Module anzeigen, mit `module load` eine Version laden:

```bash
module avail
module load python/3.11
```

Eigene Python-Umgebungen lassen sich mit `python -m venv` oder Conda anlegen.

Beispiel mit venv:

```bash
module load python/3.11
python -m venv ~/venvs/projektenv
source ~/venvs/projektenv/bin/activate
pip install numpy pandas torch
```

Diese Umgebung kann im Jobscript aktiviert werden, damit der Job reproduzierbar bleibt.

## 12. Netzwerk und Internetzugang

Aus Sicherheitsgruenden ist Internetzugang oft nur auf dem Login-Knoten erlaubt. Compute-Nodes haben haeufig keinen direkten Internetzugang. Das hat Folgen:

- `pip install` oder `git clone` funktionieren in der Regel nur auf dem Login-Node,
- Skripte, die waehrend der Laufzeit Daten aus dem Internet laden, scheitern auf Compute-Nodes,
- Modelle und Datensaetze sollten vor Jobstart vollstaendig bereitgestellt werden.

Typische Fragen:

- "Warum funktioniert pip install auf dem Rechenknoten nicht?"
- "Wieso kann ein Skript keine Daten aus dem Internet nachladen?"
- "Wie laesst sich die Umgebung fuer den Offline-Betrieb vorbereiten?"

## 13. SSH-Tunnels und Portweiterleitung

Wenn ein Webinterface oder HTTP-Dienst im Cluster aus dem Browser genutzt werden soll, ist ein SSH-Tunnel noetig. Ein allgemeiner Befehl:

```bash
ssh -L lokaler_port:zielknoten:zielport benutzername@cluster.hochschule-example.de
```

Wenn auf einem GPU-Node ein Webserver auf Port 8000 laeuft:

```bash
ssh -L 9000:node-gpu01:8000 benutzername@cluster.hochschule-example.de
```

Danach ist das Interface unter `http://localhost:9000` erreichbar.

Viele Fragen in freier Formulierung:

    - "Wie laesst sich das Webinterface eines Trainings sehen?"
    - "Wie laesst sich der Browser mit einem Dienst auf dem Cluster verbinden?"
    - "Was ist ein SSH-Tunnel und wie wird er eingerichtet?"

Die Antwort: Ein SSH-Tunnel leitet lokalen Netzwerkverkehr ueber eine SSH-Verbindung an einen Zielhost und -port im Cluster weiter.

## 14. Typische Fehlermeldungen und ihre Bedeutung

Im Alltag tauchen bestimmte Fehlermeldungen immer wieder auf. Beispiele:

- Permission denied: Fehlende Rechte oder volles Quota.
- No space left on device: Speicher erschoepft.
- ModuleNotFoundError in Python: Paket fehlt in der aktiven Umgebung.
- Job in Pending mit REASON=Resources: Keine passenden Ressourcen frei.
- Job in Pending mit REASON=QOSMaxGRESPerUser: QOS-Limits erreicht.

Ein Chatbot, der diese Meldungen versteht, kann konkrete Hilfe geben, zum Beispiel: "Pruefe dein Quota und loesche grosse Dateien", "Aktiviere deine Python-Umgebung", "Reduziere die angeforderte Laufzeit" oder "Waehle eine kleinere Anzahl von GPUs".

## 15. Best Practices fuer effizientes Arbeiten

Allgemeine Empfehlungen:

- SLURM konsequent fuer rechenintensive Aufgaben nutzen.
- Ressourcen realistisch planen, um Wartezeiten zu reduzieren.
- Jobskripte dokumentieren, um erfolgreiche Konfigurationen wiederzuverwenden.
- Versionierung (Git) nutzen und Umgebungen nachvollziehbar halten.
- Ordnung im Dateisystem halten, um Quota-Probleme frueh zu erkennen.

Typische Fragen dazu:

- "Welche Tipps gibt es fuer neue Cluster-Nutzer?"
- "Was sind gute HPC-Gewohnheiten?"
    - "Wie laesst sich effektiv mit einem Hochschul-Cluster arbeiten?"

## 16. Zusammenfassung

Dieser Leitfaden beschreibt grundlegende Konzepte und Arbeitsweisen fuer einen typischen HPC- und KI-Cluster an einer Hochschule. Er deckt SSH-Zugriff, Dateisysteme, Quotas, Datenuebertragung, SLURM, Batch- und interaktive Jobs, Software-Umgebungen, Netzwerkbeschraenkungen, SSH-Tunnels, Fehlermeldungen und Best Practices ab. Durch die Vielzahl an Formulierungen und Beispielen ist der Text so gestaltet, dass er von einem Embeddings-basierten Frage-Antwort-System gut durchsucht und genutzt werden kann.
