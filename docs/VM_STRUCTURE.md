# VM Structure (Client VM)

Version: 2025-12-28  
Purpose: Document the VM that hosts the client UI and proxy.
Note: Usernames and home paths are placeholders (for example, `<USER>`).

## Snapshot captured (2025-12-11)

### Host summary

- Hostname: `fuzzybot`
- OS: CentOS Stream 9 (kernel `5.14.0-472.el9.x86_64`)
- Home dir: `/home/<USER>`
- Interfaces:
  - `enp1s0`: `10.134.82.13/24` (default route via `10.134.82.1`)
  - `enp2s0`: `192.168.2.36/24`
- Storage:
  - `/` on `cs-root` (65G, ~10% used)
  - `/home` on `cs-home` (32G, ~2% used)

### Listening ports (from `ss -lntp`)

- `0.0.0.0:22` (sshd)
- `0.0.0.0:80` and `0.0.0.0:443` (httpd)
- `127.0.0.1:8000` (python, likely UI proxy)
- `127.0.0.1:9000` (ssh, likely port-forward to GPU node)
- `127.0.0.1:631` (cups)

### Services and jobs

- Active services include: `httpd`, `sshd`, `firewalld`, `NetworkManager`, `crond`.
- No user crontab for `<USER>`.

### Repo and processes

- Repo path: not present on the VM. Source of truth is GitHub:
  `https://github.com/strangerattractor/FuzzyBot_HSBI`
- UI serving: the VM serves the UI (Apache on ports 80/443).
- UI deployment: `/opt/Fuzzybot_Server` contains `index.html`, `app.js`, `styles.css`,
  plus `proxy.py` (legacy name: `ProxyRequest.py`).
- Local proxy: `python proxy.py` runs from `/opt/Fuzzybot_Server` on `127.0.0.1:8000`
  (snapshot showed `ProxyRequest.py`; rename recommended).
- SSH tunnel: `ssh` listening on `127.0.0.1:9000` (PID 38682 at time of snapshot).

### Apache config snapshot

- ServerRoot: `/etc/httpd`
- Main DocumentRoot: `/var/www/html` (contains a default `index.html`)
- Vhost files:
  - `/etc/httpd/conf.d/vhost_fuzzybot.yai.hsbi.de-80.conf`
  - `/etc/httpd/conf.d/vhost_fuzzybot.yai.hsbi.de-443.conf`
  - `/etc/httpd/conf.d/ssl.conf`
- Vhost bindings:
  - `10.134.82.13:80` -> `fuzzybot.yai.hsbi.de`
  - `10.134.82.13:443` -> `fuzzybot.yai.hsbi.de`
- HTTP behavior: port 80 redirects to HTTPS.
- HTTPS behavior: reverse proxy from `/` to `http://127.0.0.1:8000/`.
- SSL certs:
  - `/etc/ssl/localcerts/fuzzybot-server.crt`
  - `/etc/ssl/localcerts/fuzzybot-server.key`
  - `/etc/ssl/localcerts/fuzzybot-rootCA.crt`

### Network to GPU node

- Active SSH port-forward on `127.0.0.1:9000`.
- The proxy points at `APERTUS_URL=http://127.0.0.1:9000`, which forwards to
  the GPU node at `:9000`.
- Captured tunnel command:
  `ssh -i .ssh/id_fuzzybot_ed25519 -L 9000:cpnXXX:9000 <USER>@usr.yai.hsbi.de`

## Commands to run on the VM

```bash
hostname
uname -a
cat /etc/os-release
pwd
ls -lah
```

```bash
ip addr
ip route
ss -lntp
```

```bash
systemctl --no-pager --type=service --state=running
crontab -l
```

```bash
df -h
mount
```

```bash
ps aux | grep -Ei "proxy|python|uvicorn|nginx|httpd|ssh"
```
