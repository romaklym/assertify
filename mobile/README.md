# Assertify mobile

The phone app for Assertify. Log in to any website in the app's browser once; AI agents (Claude mobile, ChatGPT/Codex, or anything that speaks MCP) then work in that site inside a hidden browser on the phone, using your login. Your password never leaves the phone.

```
Claude / Codex  --MCP over HTTPS-->  assertify relay  --WebSocket-->  Assertify app (hidden WebView)
```

## Use it

1. On a computer or server, run the relay:

   ```bash
   assertify relay --public-url https://relay.example.com
   ```

   It prints an **MCP URL** and a **pairing link**. Phone and relay on the same Wi-Fi? Leave out `--public-url`; the relay then listens on port 8765 and you use `ws://<computer's LAN IP>:8765/phone`.
2. In the app, tap **Pair** and paste the pairing link (or open it on the phone).
3. Tap **Log in to a site**, pick or type a site (linkedin.com, x.com…), and log in by hand. Tap **Done**.
4. Add the MCP URL to your agent as a custom connector, then ask it: "check my LinkedIn messages".

Keep the app open while the agent works. iOS pauses apps in the background; the app reconnects as soon as you open it again.

## What the agent can and can't do

- It only reaches sites you logged in to here, and only their own domains.
- Send, post, buy, delete, connect and block buttons are paused until the agent asks again with your approval.
- Password fields are never filled by the agent. Pages' `alert`/`confirm` boxes are cancelled and reported.
- To remove a site, tap the bin icon. To sign out completely, also sign out in the site itself.

## Build

Flutter 3.38 or newer.

```bash
flutter pub get
flutter run                     # simulator / emulator / connected phone
flutter build apk --release     # Android
flutter build ipa               # iOS (set your signing team in Xcode first)
```

For quick testing you can bake a pairing link into a debug build: `--dart-define=PAIR='assertify://pair?relay=ws://10.0.2.2:8765/phone&token=…'` (10.0.2.2 is the host computer from the Android emulator; use 127.0.0.1 in the iOS simulator). Never ship a build with a token in it.

On a physical iPhone, run a release or profile build (`flutter run --release`): Flutter debug builds only start while a debugger is attached.
