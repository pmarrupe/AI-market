# AI Market — Mobile (Expo)

React Native app that uses the same backend as the web dashboard. Five tabs: **Dashboard** (KPIs, summary bar, disclaimer, top opportunities, sectors), **Scanner** (full opportunity table with filters, sort, expandable rows), **Trackers** (Startup & Funding + Product Launches), **Research** (AI research items), and **Search** (S&P 500 search → AI opinion).

## Prerequisites

- Node.js 18+
- npm or yarn
- [Expo Go](https://expo.dev/go) on your iPhone (for quick testing)
- Xcode (only if you want to run in simulator or build for App Store)

## Setup

1. **Install dependencies**

   ```bash
   cd mobile
   npm install
   ```

2. **Point the app at your backend**

   - Default is `http://98.84.157.50:8000` (set in `config.js`).
   - To override: create a `.env` file with:
     ```bash
     EXPO_PUBLIC_API_URL=https://your-ec2-or-domain.com:8000
     ```
   - For a **physical device**, use your computer’s local IP if the backend runs on your machine, e.g. `http://192.168.1.5:8000`, and ensure the phone and computer are on the same Wi‑Fi.

3. **Ensure backend allows the app**

   - If you use a custom URL, add it to the backend `CORS_ORIGINS` (e.g. your EC2 URL or `*` for testing).

## Run

```bash
npm start
```

- Scan the QR code with the **Expo Go** app (Camera on iOS) to open on your phone.
- Or press `i` for iOS simulator (requires Xcode).

## Build for App Store

1. Install EAS CLI: `npm install -g eas-cli`
2. Log in: `eas login`
3. Configure: `eas build:configure`
4. Build: `eas build --platform ios`
5. Submit from [expo.dev](https://expo.dev) or EAS Submit.

Requires an [Apple Developer](https://developer.apple.com) account ($99/year).

## Project structure

- `app/(tabs)/index.js` — Dashboard (summary bar, disclaimer, KPIs, top opportunities, sectors)
- `app/(tabs)/scanner.js` — Full scanner (filters, sort, expandable rows, link to opinion)
- `app/(tabs)/trackers.js` — Startup & Funding + Product Launches (featured + feed)
- `app/(tabs)/research.js` — Research items list (tap to open URL)
- `app/(tabs)/search.js` — S&P 500 search and navigation to opinion
- `app/opinion/[ticker].js` — Stock opinion (price, thesis, uncertainties, headlines)
- `api.js` — API client (dashboard, search, opinion)
- `config.js` — Backend base URL (from env or default)
