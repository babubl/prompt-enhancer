# ✦ Prompt Enhancer

A free, open-source web tool that transforms rough prompts into structured, production-ready prompts using Claude AI.

![License](https://img.shields.io/badge/license-MIT-green)

## 🚀 Live Demo

👉 **[https://yourusername.github.io/prompt-enhancer](https://babubl.github.io/prompt-enhancer)**

*(Replace `yourusername` with your GitHub username after deploying)*

## ✨ Features

- 🧠 AI-powered prompt engineering using Claude Sonnet
- 📋 One-click copy of the enhanced prompt or full output
- 🔒 API key stored locally in your browser (never sent to any server except Anthropic)
- ⌨️ Keyboard shortcut: `Ctrl/⌘ + Enter` to enhance
- 📱 Fully responsive — works on desktop and mobile
- ⚡ Zero build step — single HTML file, no frameworks

## 🛠️ Setup & Deployment (GitHub Pages)

### Step 1: Get an Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com/settings/keys)
2. Create a new API key
3. You'll paste this into the app when you first use it

### Step 2: Create a GitHub Repository

1. Go to [github.com/new](https://github.com/new)
2. Name it `prompt-enhancer` (or anything you like)
3. Set it to **Public**
4. Click **Create repository**

### Step 3: Upload the Files

**Option A — Via GitHub Web UI (easiest):**

1. In your new repo, click **"Add file" → "Upload files"**
2. Drag and drop `index.html` and this `README.md`
3. Click **"Commit changes"**

**Option B — Via Git CLI:**

```bash
git clone https://github.com/yourusername/prompt-enhancer.git
cd prompt-enhancer
# Copy index.html and README.md into this folder
git add .
git commit -m "Initial commit"
git push origin main
```

### Step 4: Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**
2. Under "Source", select **Deploy from a branch**
3. Branch: `main`, Folder: `/ (root)`
4. Click **Save**
5. Wait ~1 minute, then visit `https://yourusername.github.io/prompt-enhancer`

🎉 **That's it!** Share the link with anyone.

## 🔐 Security Note

- Your API key is stored **only** in your browser's `localStorage`
- It is sent **only** to `api.anthropic.com` when you click "Enhance"
- No backend, no analytics, no tracking — just a static HTML page
- Anyone using the tool needs their own API key

## 📁 Project Structure

```
prompt-enhancer/
├── index.html    ← The entire app (single file, no build step)
└── README.md     ← This file
```

## 🤝 Contributing

1. Fork the repo
2. Make your changes to `index.html`
3. Open a Pull Request

## 📄 License

MIT — use it however you like.
