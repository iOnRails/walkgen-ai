# WalkGen AI - Setup Guide (Complete Beginner Edition)

You need 4 free accounts. Budget about 20 minutes total. Follow each step in order.

---

## Step 1: GitHub Account (2 minutes)

GitHub stores your code online so Railway and Vercel can deploy it.

1. Go to **github.com**
2. Click **Sign Up**
3. Create your account (email + password)
4. Verify your email

---

## Step 2: Anthropic API Key (3 minutes)

This is what powers the AI analysis. You get $5 free credit to start.

1. Go to **console.anthropic.com**
2. Click **Sign Up** and create an account
3. Once logged in, click **API Keys** in the left sidebar
4. Click **Create Key**
5. Name it "WalkGen" and click Create
6. **COPY THE KEY** immediately (starts with `sk-ant-...`) — you won't see it again
7. Save it somewhere safe (a text file, password manager, etc.)

Cost: Each video analysis costs about $0.02-0.05. The $5 free credit gives you ~100-250 videos.

---

## Step 3: YouTube Data API Key (5 minutes)

This lets the app fetch video titles, durations, and thumbnails from YouTube.

1. Go to **console.cloud.google.com**
2. Sign in with your Google account
3. Click **Select a Project** at the top, then **New Project**
4. Name it "WalkGen" and click Create
5. Wait for it to create, then make sure it's selected
6. In the search bar at the top, type **YouTube Data API v3**
7. Click the result, then click **Enable**
8. After enabling, click **Create Credentials** (or go to APIs & Services > Credentials)
9. Click **Create Credentials** > **API Key**
10. **COPY THE KEY** (starts with `AIza...`)
11. Save it with your Anthropic key

Cost: Free. YouTube gives you 10,000 requests/day which is plenty.

---

## Step 4: Push Code to GitHub (3 minutes)

1. Go to **github.com** and log in
2. Click the **+** in the top right > **New Repository**
3. Name it `walkgen-ai`
4. Keep it **Public** (required for free Vercel/Railway)
5. Click **Create Repository**
6. You'll see instructions — you need to upload the walkgen folder contents

**If you've never used git before**, the easiest way:
- On the repo page, click **uploading an existing file**
- Drag and drop ALL files from the `walkgen/` folder
- Click **Commit changes**

You may need to do this in two rounds — one for `backend/` files and one for `frontend/` files.

---

## Step 5: Deploy Backend on Railway (5 minutes)

Railway runs your Python server.

1. Go to **railway.app**
2. Click **Login** > **Login with GitHub**
3. Authorize Railway to access your GitHub
4. Click **New Project** > **Deploy from GitHub Repo**
5. Select your `walkgen-ai` repository
6. Railway will detect the code — click on the service
7. Go to **Settings** tab:
   - Set **Root Directory** to `backend`
   - Set **Start Command** to: `uvicorn main:app --host 0.0.0.0 --port $PORT`
8. Go to **Variables** tab and add:
   - `ANTHROPIC_API_KEY` = (paste your key from Step 2)
   - `YOUTUBE_API_KEY` = (paste your key from Step 3)
   - `CORS_ORIGINS` = (leave blank for now, you'll update after Step 6)
9. Go to **Settings** > **Networking** > click **Generate Domain**
10. **COPY YOUR RAILWAY URL** (looks like `walkgen-ai-production.up.railway.app`)

Test it: visit `https://YOUR-RAILWAY-URL/api/health` — you should see a JSON response.

Cost: Railway gives a free trial. After that, ~$5/month for this app.

---

## Step 6: Deploy Frontend on Vercel (3 minutes)

Vercel hosts your React website.

1. Go to **vercel.com**
2. Click **Sign Up** > **Continue with GitHub**
3. Click **Add New Project** > **Import** your `walkgen-ai` repo
4. In the configuration:
   - Set **Root Directory** to `frontend`
   - Set **Framework Preset** to `Create React App`
   - Under **Environment Variables**, add:
     - `REACT_APP_API_URL` = `https://YOUR-RAILWAY-URL` (from Step 5)
5. Click **Deploy**
6. Wait 1-2 minutes — Vercel will give you a URL like `walkgen-ai.vercel.app`

**IMPORTANT — Final step:** Go back to Railway, update the `CORS_ORIGINS` variable:
- Set it to your Vercel URL: `https://walkgen-ai.vercel.app`

---

## You're Live!

Visit your Vercel URL. Paste any YouTube gameplay walkthrough link. Watch the AI work.

**Test with this video:**
`https://www.youtube.com/watch?v=NLdZ8Zex1cw` (any Elden Ring walkthrough with captions)

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Analysis failed" | Video might not have captions. Try a different video |
| CORS error in browser | Make sure CORS_ORIGINS in Railway matches your Vercel URL exactly |
| Railway won't deploy | Check that Root Directory is set to `backend` |
| Vercel won't deploy | Check that Root Directory is set to `frontend` |
| API key error | Double-check keys in Railway Variables — no extra spaces |

---

## Monthly Costs

| Service | Cost |
|---------|------|
| Vercel (frontend) | Free |
| Railway (backend) | ~$5/month |
| Anthropic API | ~$0.03 per video (pay as you go) |
| YouTube API | Free |
| **Total for ~100 videos/month** | **~$8/month** |
