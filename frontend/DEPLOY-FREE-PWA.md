# Deploy as app for free (PWA – no App Store)

You can get the app onto friends’ iPhones **at no cost** by using it as a **Progressive Web App (PWA)**. They don’t need the App Store or an Apple Developer account.

## How it works

1. You host the **web app** (this frontend) on HTTPS (e.g. your EC2 server or any static host).
2. Friends open the site in **Safari** on their iPhone.
3. They tap **Share** → **Add to Home Screen**.
4. An icon appears on their home screen; opening it runs the app in full-screen (no Safari UI). Same backend and data as the website.

**Cost:** $0. No Apple Developer Program, no store fees.

## What was added

- **`public/manifest.webmanifest`** – PWA manifest (name, icons, standalone display).
- **`public/icons/`** – App icons (192px, 512px) for home screen.
- **`index.html`** – Manifest link, theme color, and iOS “Add to Home Screen” meta tags and `apple-touch-icon`.

## Deploy steps

1. **Build the frontend**
   ```bash
   cd frontend && npm run build
   ```
2. **Serve `dist/` over HTTPS**  
   Use your existing setup (e.g. Nginx on EC2 serving the `dist` folder). PWA requires HTTPS (and a real hostname for best results).
3. **Share the URL**  
   Send friends the URL (e.g. `https://your-domain.com`).
4. **They install on iPhone**
   - Open the URL in **Safari** (Chrome on iOS uses Safari under the hood; “Add to Home Screen” still works from Safari).
   - Tap the **Share** button (square with arrow).
   - Tap **Add to Home Screen** → name it (e.g. “AI Market”) → **Add**.

After that, they open “AI Market” from the home screen like any app; it runs in standalone mode and uses your same API.

## Limitations vs native App Store app

- No listing in the App Store (discovery is by link only).
- Some iOS limits: no push notifications in the same way as native, possible minor Safari engine quirks.
- For most use cases (dashboard, scan, trackers, research), the PWA is enough and **free**.

## Optional: custom domain

Using a domain (e.g. `https://aimarket.yourdomain.com`) instead of a raw IP makes the install experience and branding clearer. Point the domain to the same server that serves the built frontend over HTTPS.
