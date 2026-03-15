# Deploy AI Market on EC2 — step-by-step (after SSH)

You're already SSH'd in. Follow these in order.

---

## 1. Install Docker and Docker Compose (if not already)

```bash
sudo dnf update -y -q
sudo dnf install -y docker git
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

Install Docker Compose plugin:

```bash
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
```

**Log out and back in** (or run `newgrp docker`) so your user is in the `docker` group. Then you can use `docker` without `sudo` if you want.

---

## 2. Get the app code on the server

**Option A — Clone from GitHub (if your code is in that repo):**

```bash
cd ~
git clone https://github.com/pmarrupe/AI-market.git
cd AI-market
```

**Option B — You have a different repo or branch:**  
Use your repo URL and branch, e.g.:

```bash
git clone -b main https://github.com/YOUR_USER/AI-market.git
cd AI-market
```

**Option C — Copy from your Mac with SCP (no git on server):**  
From your Mac (in a new terminal, not on EC2):

```bash
cd /Users/prashanth_1/Downloads/code/AI-market
scp -i /Users/prashanth_1/Downloads/ai-market-key.pem -r . ec2-user@98.84.157.50:~/AI-market
```

Then on EC2: `cd ~/AI-market`.

---

## 3. Create and edit `.env`

```bash
cd ~/AI-market
cp .env.example .env
nano .env
```

**Set at least these:**

- `LLM_ENABLED=true`  
- `LLM_API_KEY=sk-your-actual-openai-key`  
- `CORS_ORIGINS=*`  

So the app can use the LLM and accept requests from any origin (your browser at `http://<EC2-IP>:8000`).

Save and exit: **Ctrl+O**, Enter, then **Ctrl+X**.

---

## 4. Build and start the app

```bash
cd ~/AI-market
sudo docker compose up -d --build
```

First run will build the image (including the React frontend and PWA) and start the container. Wait until it finishes.

---

## 5. Check it’s running

```bash
sudo docker compose ps
```

You should see the `app` service **Up**. Then:

```bash
sudo docker compose logs -f
```

Press **Ctrl+C** to stop following logs. You should see the app listening on port 8000.

---

## 6. Open port 8000 on EC2 (AWS Security Group)

Otherwise your browser can’t reach the app.

1. In **AWS Console** → **EC2** → **Security Groups**.
2. Select the security group attached to your instance.
3. **Edit inbound rules** → **Add rule**:
   - Type: **Custom TCP**
   - Port: **8000**
   - Source: **0.0.0.0/0** (anywhere) or **My IP** (only your IP)
4. Save.

---

## 7. Open the app in your browser

Use your EC2 **public IP** (e.g. `98.84.157.50`):

```
http://98.84.157.50:8000
```

You should see the AI Market app (React frontend with dashboard, scanner, etc.).

---

## 8. (Optional) Run the full setup script next time

If you prefer a single script on a **new** EC2 (or after a clean OS):

```bash
curl -sSL https://raw.githubusercontent.com/pmarrupe/AI-market/main/deploy/setup-ec2.sh -o setup-ec2.sh
chmod +x setup-ec2.sh
./setup-ec2.sh
```

(Or clone the repo first and run `bash deploy/setup-ec2.sh` from inside it.) The script does steps 1–2 and then either creates `.env` and tells you to edit it and run `docker compose up`, or runs `docker compose up` if `.env` already exists.

---

## Useful commands (after deploy)

| Task | Command |
|------|--------|
| View logs | `sudo docker compose logs -f` |
| Stop app | `sudo docker compose down` |
| Start again | `sudo docker compose up -d` |
| Rebuild after code change | `cd ~/AI-market && git pull && sudo docker compose up -d --build` |

---

## PWA / “Add to Home Screen” (free app on iPhone)

- The app is already set up as a PWA (manifest + icons).
- For **Add to Home Screen** to work, the site must be served over **HTTPS**.
- Right now you’re using **HTTP** on port 8000, so:
  - You can use the app in the browser at `http://<EC2-IP>:8000`.
  - To get “Add to Home Screen” on iPhone, later add a domain and HTTPS (e.g. Nginx + Certbot). See **frontend/DEPLOY-FREE-PWA.md** and **NEXT-STEPS.md**.
