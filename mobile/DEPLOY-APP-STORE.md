# Deploy AI Market to the App Store

Follow these steps so friends can download the app on their iPhones.

---

## 1. Apple Developer Account ($99/year)

- Go to [developer.apple.com](https://developer.apple.com) and sign in with your Apple ID.
- Enroll in the **Apple Developer Program** ($99/year). Approval can take 24–48 hours.
- After approval, note your **Team ID** (Apple Developer → Membership → Team ID).

---

## 2. Install EAS CLI

EAS (Expo Application Services) builds and submits your app.

```bash
npm install -g eas-cli
eas login
```

Log in with your **Expo account** (create one at [expo.dev](https://expo.dev) if needed).

---

## 3. Configure the project for EAS

In the `mobile` folder:

```bash
cd /Users/prashanth_1/Downloads/code/AI-market/mobile
eas build:configure
```

Choose **All** when asked which platforms. This will confirm or create `eas.json`.

---

## 4. Create the app in App Store Connect

- Go to [appstoreconnect.apple.com](https://appstoreconnect.apple.com) → **My Apps** → **+** → **New App**.
- **Platform:** iOS  
- **Name:** AI Market  
- **Primary Language:** English  
- **Bundle ID:** pick the one you use in the app (e.g. `com.aimarket.app`). It must match `app.json` → `expo.ios.bundleIdentifier`.
- **SKU:** e.g. `ai-market-1`.  
- Leave **User Access** as full access unless you need otherwise.

After creation, open the app and copy the **App ID** (numeric, e.g. `1234567890`) from the **App Information** section. You’ll use it for `ascAppId` in EAS submit.

---

## 5. Set the production API URL

Your production backend URL (e.g. your EC2 or domain) must be set for the **production** build.

**Option A – in `eas.json` (recommended)**  
In `eas.json`, under `build.production.env`, set:

```json
"EXPO_PUBLIC_API_URL": "https://your-actual-domain.com:8000"
```

(or `http://...` if you’re not using HTTPS). Use the same URL your web app uses.

**Option B – `.env` during build**  
You can also use a `.env` that sets `EXPO_PUBLIC_API_URL` and run the build from the same machine (EAS will pick it up if configured). For a single source of truth, Option A is simpler.

---

## 6. Build for iOS (production)

```bash
cd /Users/prashanth_1/Downloads/code/AI-market/mobile
eas build --platform ios --profile production
```

- First time: EAS will ask for your **Apple ID** and **Team ID** (and optionally create/distribute certificates).
- Build runs in the cloud (about 10–20 minutes). You’ll get a link to the build page.
- When the build succeeds, you’ll see a build ID and a link to the `.ipa`.

---

## 7. Submit to App Store Connect

**Option A – EAS Submit (easiest)**

Update `eas.json` → `submit.production.ios` with your real values:

```json
"appleId": "your-apple-id@email.com",
"ascAppId": "1234567890",
"appleTeamId": "XXXXXXXXXX"
```

Then run:

```bash
eas submit --platform ios --profile production
```

When prompted, select the **latest production build**. EAS uploads the build to App Store Connect.

**Option B – Manual upload**

- Download the `.ipa` from the EAS build page.
- Use **Transporter** (Mac App Store) or **Xcode → Window → Organizer** to upload the build to App Store Connect, selecting the correct app and version.

---

## 8. Complete the listing in App Store Connect

In App Store Connect, open your app:

1. **Version information**
   - Version number (e.g. 1.0.0) and “What’s New”.
2. **Screenshots**
   - Required for 6.7", 6.5", 5.5" (or use one size and let Apple scale). Run the app in the simulator, take screenshots (Cmd+S), and upload.
3. **Description, keywords, category**
   - Short description, full description, keywords, category (e.g. Finance or News).
4. **Support URL**
   - A URL you own (e.g. your repo or a simple landing page).
5. **Privacy**
   - Add a **Privacy Policy URL** (required). You can host a simple page (e.g. GitHub Pages or your backend) that explains what data the app uses (e.g. “Connects to our API to show market data; we do not collect personal data”).
6. **Pricing**
   - Choose **Free** (or paid if you prefer).

---

## 9. Submit for review

- In App Store Connect, select the build you uploaded and **Add for Review** (or **Submit for Review**).
- Answer the export compliance and other questions (for this app they’re usually “No” or “N/A”).
- Submit. Review usually takes 24–48 hours.

Once approved, the app goes **Live** and anyone can search “AI Market” on the App Store and download it (or you share the link from App Store Connect).

---

## Quick checklist

| Step | Done |
|------|------|
| Apple Developer Program ($99) | ☐ |
| Expo account + `eas login` | ☐ |
| `eas build:configure` | ☐ |
| App created in App Store Connect (Bundle ID matches) | ☐ |
| `EXPO_PUBLIC_API_URL` set for production in `eas.json` | ☐ |
| `eas build --platform ios --profile production` | ☐ |
| `eas submit` or manual upload | ☐ |
| Screenshots, description, privacy URL, support URL | ☐ |
| Submit for review | ☐ |

---

## Optional: TestFlight (before public release)

- After uploading a build, it appears in **TestFlight** in App Store Connect.
- Add testers by email (up to 10,000 external testers). They get an invite and install via the TestFlight app.
- No App Store review needed for TestFlight; use it to let friends try the app before you submit for public release.
