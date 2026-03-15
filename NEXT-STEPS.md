# Next steps (free PWA “app” for friends)

To get the app onto friends’ iPhones **at no cost** (no App Store, no $99/year):

---

## 1. Build the frontend (includes PWA)

From the project root:

```bash
cd frontend && npm run build && cd ..
```

This produces `frontend/dist/` with the app, `manifest.webmanifest`, and icons so “Add to Home Screen” works.

---

## 2. Deploy with Docker (backend + frontend)

Your Dockerfile already builds the frontend and copies `frontend/dist` into the image. So:

- **If you already use EC2** (or any server):
  - Copy the whole project (including the new PWA files and backend changes).
  - Run: `sudo docker compose up -d --build`
  - The app will serve the React build at `/` and PWA manifest/icons at `/manifest.webmanifest` and `/icons/`.

- **If you haven’t set up a server yet:**
  - Launch an EC2 instance (e.g. Amazon Linux 2023).
  - Run the setup script: `bash deploy/setup-ec2.sh` (after cloning the repo and configuring `.env`).
  - The script installs Docker, builds the app, and runs it.

---

## 3. Use HTTPS (required for PWA)

“Add to Home Screen” on iPhone needs **HTTPS**.

- **Option A – EC2 with a domain:**  
  Point a domain (e.g. `aimarket.yourdomain.com`) to your EC2 IP, then use Let’s Encrypt (e.g. Certbot) with Nginx to get HTTPS.

- **Option B – No domain:**  
  You can still use the app in the browser over HTTP, but “Add to Home Screen” will be limited or not offered until the site is served over HTTPS.

---

## 4. Share the URL with friends

Send them your app URL, e.g. `https://your-domain.com` or `https://your-ec2-ip` (if you have HTTPS there).

---

## 5. They “install” the app on iPhone

1. Open the URL in **Safari**.
2. Tap the **Share** button (square with arrow).
3. Tap **Add to Home Screen** → name it (e.g. “AI Market”) → **Add**.

After that, they open “AI Market” from the home screen like an app; it runs full-screen and uses your same backend. No App Store, no cost.

---

## Summary checklist

| Step | Action |
|------|--------|
| 1 | `cd frontend && npm run build` (or rely on Docker build) |
| 2 | Deploy: `docker compose up -d --build` on your server |
| 3 | Put the app behind HTTPS (domain + Certbot, or other) |
| 4 | Share the HTTPS URL with friends |
| 5 | Friends: Safari → Share → Add to Home Screen |

More detail: **frontend/DEPLOY-FREE-PWA.md**.
