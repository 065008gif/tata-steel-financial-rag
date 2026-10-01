# Restoring financial-rag on a personal laptop

The backup is `financial-rag-backup-20261001.tar.gz`, stored in Google Drive under `financial-rag-backup/`
together with `financial-rag-backup-20261001.tar.gz.sha256`, `MANIFEST.txt` and this file.
The source code is also on GitHub: https://github.com/065008gif/tata-steel-financial-rag

**What the archive contains:** the whole project folder (`financial-rag/`), including `.git` (full history,
`origin` remote), `data/` (raw PDFs, interim and processed data), `qdrant_storage/` (the built vector index),
`.cache/` (fastembed models, including the empty `tamil.txt` / `mock.file` offline fix) and `eval/results/`.

**What it does NOT contain (recreate these):** `.env` (your API key), `.venv/` (Python env), `frontend/node_modules/`,
`frontend/dist/`, `__pycache__/`, `.pytest_cache/`.

You do **not** need to re-run the ingestion pipeline or rebuild the index: `data/`, `qdrant_storage/` and `.cache/`
are restored as they were.

---

## 1. Install the prerequisites

### Windows (recommended: WSL2 Ubuntu + Docker Desktop)
1. Open PowerShell **as Administrator** and run `wsl --install -d Ubuntu`, then reboot and create your Ubuntu user.
2. Install **Docker Desktop** (https://www.docker.com/products/docker-desktop/). In *Settings → General*, enable
   "Use the WSL 2 based engine"; in *Settings → Resources → WSL integration*, enable **Ubuntu**.
3. Do everything below **inside the Ubuntu terminal**, and keep the project in the Linux home folder (`~/`),
   **not** under `/mnt/c/...` (much slower, and file permissions break).
4. Then follow the **Linux** steps below (Git, Miniforge, Node 22) inside Ubuntu. Docker is provided by Docker Desktop:
   check with `docker version` and `docker compose version` in Ubuntu.

### macOS
1. Git: `xcode-select --install` (or `brew install git`).
2. Docker Desktop for Mac (Apple Silicon or Intel build): https://www.docker.com/products/docker-desktop/
3. Miniforge:
   ```bash
   curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
   bash Miniforge3-$(uname)-$(uname -m).sh -b && ~/miniforge3/bin/conda init "$(basename $SHELL)"
   ```
   Close and reopen the terminal.
4. Node 22: `brew install node@22` (then follow brew's PATH hint), or nvm: `nvm install 22`.

### Linux (Ubuntu/Debian; also inside WSL2)
```bash
sudo apt update && sudo apt install -y git curl
# Miniforge
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash Miniforge3-$(uname)-$(uname -m).sh -b && ~/miniforge3/bin/conda init bash && exec bash
# Node 22 via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash && exec bash
nvm install 22
```
Docker on native Linux (skip in WSL2, Docker Desktop provides it):
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # then log out and back in
```
Check everything: `git --version; conda --version; node -v (v22.x); docker compose version`.

---

## 2. Download, verify and extract the archive

1. In Google Drive open the `financial-rag-backup` folder. Download `financial-rag-backup-20261001.tar.gz` and
   `financial-rag-backup-20261001.tar.gz.sha256`. If Drive asks, choose "Download anyway" (it can't virus-scan large files).
2. Move both files to your home folder. In WSL the Windows Downloads folder is `/mnt/c/Users/<you>/Downloads`:
   ```bash
   mv /mnt/c/Users/<you>/Downloads/financial-rag-backup-20261001.tar.gz* ~/
   ```
3. Verify the checksum (it must print `OK`):
   ```bash
   cd ~
   sha256sum -c financial-rag-backup-20261001.tar.gz.sha256            # Linux / WSL
   shasum -a 256 -c financial-rag-backup-20261001.tar.gz.sha256        # macOS
   ```
4. Extract the archive. This creates `~/financial-rag`:
   ```bash
   tar -xzf financial-rag-backup-20261001.tar.gz
   cd ~/financial-rag
   ```
   On Linux/WSL, extract as your normal user (not with sudo), so that you own all the files.

---

## 3. Python environment (Python 3.11, Conda)

```bash
cd ~/financial-rag
conda create -p ./.venv python=3.11 -y
conda activate ./.venv
```

**Linux / WSL** (the CPU-only torch wheels pinned with `+cpu`):
```bash
pip install -r requirements-full.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

**macOS and native Windows** (`+cpu` wheels don't exist there, so install torch without the suffix):
```bash
grep -v -E '^torch(vision)?==' requirements-full.txt > /tmp/req-nocpu.txt
pip install torch==2.14.0 torchvision==0.29.0
pip install -r /tmp/req-nocpu.txt
```
If a pinned version isn't available for your platform/architecture, relax that one pin (e.g. `pip install torch torchvision`).
The Docker backend doesn't use this env; you only need it for the host scripts (evaluation, ingestion, tests).

---

## 4. Frontend dependencies

```bash
cd ~/financial-rag/frontend
npm ci
cd ..
```

---

## 5. Create `.env` (the archive doesn't include it)

```bash
cd ~/financial-rag
printf 'OLLAMA_API_KEY=%s\n' 'PASTE_YOUR_OLLAMA_CLOUD_KEY_HERE' > .env
chmod 600 .env
```
Never commit `.env` (it's already in `.gitignore`).

---

## 6. Run the full stack (Qdrant + backend + frontend + Cloudflare tunnel)

```bash
cd ~/financial-rag
docker compose --profile full up -d --build
docker compose ps                                     # all four services "running"
curl -s http://127.0.0.1:8000/api/reports | head -c 300; echo   # backend answers
```
- Local app: http://localhost:8080
- Public tunnel link (changes on every restart):
  ```bash
  docker compose logs tunnel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
  ```
- Stop everything (the tunnel is public while it's running): `docker compose --profile full down`

---

## 7. Dev mode (Vite hot reload)

```bash
cd ~/financial-rag
docker compose up -d qdrant backend          # backend on 127.0.0.1:8000
cd frontend
npm run dev                                  # http://localhost:5173; /api is proxied to 127.0.0.1:8000
```
To point the dev frontend at another backend (e.g. a teammate's tunnel), set `VITE_API_TARGET`:
```bash
VITE_API_TARGET=https://xxxx.trycloudflare.com npm run dev
```

---

## 8. Pushing further changes to GitHub (065008gif/tata-steel-financial-rag)

The archive includes `.git` with `origin` set to `https://github.com/065008gif/tata-steel-financial-rag.git`.
```bash
cd ~/financial-rag
git config --global user.name  "Akshit Kansal"
git config --global user.email "<your email>"
git pull --rebase origin main                # pick up anything pushed after this backup
git add <files> && git commit -m "message"
git push origin main
```
GitHub doesn't accept passwords for HTTPS pushes. Either install the GitHub CLI and run `gh auth login` (easiest),
or use a Personal Access Token (Settings → Developer settings → Tokens) as the password, or switch to SSH:
`git remote set-url origin git@github.com:065008gif/tata-steel-financial-rag.git` after adding an SSH key to GitHub.
`data/`, `qdrant_storage/`, `.cache/` and `.env` are gitignored on purpose; back them up with a new archive instead.

---

## 9. Troubleshooting

**Backend crashes at start-up with a Hugging Face / fastembed "offline" or "file not found" error.**
The backend runs with `HF_HUB_OFFLINE=1` and only uses the models in `./.cache/fastembed`. Check that the cache was restored:
```bash
ls .cache/fastembed/
ls .cache/fastembed/models--Qdrant--bm25/snapshots/*/      # must include tamil.txt and mock.file (empty files)
```
If `tamil.txt` / `mock.file` are missing, recreate them as empty files: fastembed 0.8.1 requires them, but they're
missing upstream, and English-only BM25 never reads them:
```bash
for d in .cache/fastembed/models--Qdrant--bm25/snapshots/*/; do touch "$d/tamil.txt" "$d/mock.file"; done
```
If `.cache` is missing completely, start the backend once with network access to download the models (temporarily
set `HF_HUB_OFFLINE: "0"` in `docker-compose.yml`), then recreate the two files and switch back to `"1"`.

**Port already in use** (`bind: address already in use` for 6333, 8000, 8080 or 5173).
Find the process: `sudo lsof -i :8000` (Linux/macOS) or `netstat -ano | findstr :8000` (Windows PowerShell).
Stop it, or change the left-hand host port in `docker-compose.yml` (e.g. `"127.0.0.1:8001:8000"`). If you change the
backend port, start dev mode with `VITE_API_TARGET=http://127.0.0.1:8001 npm run dev`.

**Docker memory / containers killed (exit code 137) / very slow.**
Give Docker at least 4 GB of RAM (6–8 GB recommended). Docker Desktop: *Settings → Resources → Memory*. With WSL2,
the memory limit comes from `C:\Users\<you>\.wslconfig`:
```
[wsl2]
memory=8GB
```
then run `wsl --shutdown` in PowerShell and restart Docker Desktop.

**Qdrant starts but the collection is empty / missing.**
Make sure you started compose from `~/financial-rag`, so that `./qdrant_storage` is mounted, and that the folder was
extracted (`ls qdrant_storage/collections` should show `tata_steel`). On Linux, if Qdrant can't write to it:
`sudo chown -R $USER: qdrant_storage`.

**`env file .env not found`.** Do step 5.

**Apple Silicon:** all images used (qdrant, python:3.11-slim, node/nginx, cloudflared) are multi-arch; no extra flags needed.
