# Cloud Deployment Guide: Render & Railway

This application can be deployed as a containerized web service to cloud platforms such as **Render** or **Railway**.

---

## Deploying to Render (render.com)

### 1. Push code to GitHub
Ensure all your latest changes are pushed to your GitHub repository:
```bash
git add .
git commit -m "Add manual job evaluator and cloud deployment configs"
git push origin main
```

### 2. Create Web Service on Render
1. Go to [dashboard.render.com](https://dashboard.render.com) and sign in.
2. Click **New +** → **Web Service**.
3. Connect your GitHub repository (`Indeed-Scraper`).
4. Select **Docker** as the runtime (it detects your `Dockerfile` automatically).
5. Choose your plan (**Free** or **Starter**).

### 3. Configure Environment Variables
In the **Environment** tab of your Render service, add the following variables from your `.env`:

| Key | Description | Example / Default |
| :--- | :--- | :--- |
| `DASHBOARD_HOST` | Host binding | `0.0.0.0` |
| `SCRAPER_HEADLESS` | Run headless | `true` |
| `ENABLE_KB_MATCHING` | Enable AI Match | `true` |
| `LLM_PROVIDER` | LLM service provider | `openrouter` or `azure` |
| `OPENROUTER_API_KEY` | OpenRouter API Key | `sk-or-v1-...` |
| `OPENROUTER_MODEL` | Target OpenRouter model | `google/gemma-4-31b-it` |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI Key (if using Azure) | `...` |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI Endpoint | `https://<name>.openai.azure.com/` |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search Endpoint | `https://<name>.search.windows.net` |
| `AZURE_SEARCH_API_KEY` | Azure AI Search Key | `...` |
| `AZURE_SEARCH_INDEX_NAME` | Search Index Name | `...` |

*(Note: Render automatically injects `PORT`, and your Dockerfile binds dynamically to `${PORT:-8000}`)*.

### 4. Deploy
Click **Create Web Service**. Render will build your Docker image and provide a live URL (e.g. `https://indeed-scraper-xyz.onrender.com`).

---

## Deploying to Railway (railway.app)

### 1. Create Project on Railway
1. Go to [railway.app](https://railway.app) and sign in with GitHub.
2. Click **New Project** → **Deploy from GitHub repo**.
3. Select your repository.

### 2. Add Environment Variables
1. In the service settings, go to the **Variables** tab.
2. Click **Raw Editor** and paste the relevant lines from your `.env` (excluding local file paths).
3. Ensure `DASHBOARD_HOST=0.0.0.0` is present.

### 3. Generate Domain
1. In the **Settings** tab, under **Networking**, click **Generate Domain**.
2. Railway will give you a public URL (e.g. `https://indeed-scraper-production.up.railway.app`).

---

## Using Manual Job Description Evaluation

Once deployed:
1. Open the public URL in any browser.
2. Select the **"Manual Job Evaluator (Paste Description)"** tab.
3. Paste any job posting from LinkedIn, Upwork, Indeed, etc.
4. Click **"Evaluate Fit with AI"**.
5. The lead will be scored against your company capabilities and displayed in the table.
6. Click **"Download Excel"** to save the formatted `.xlsx` workbook anytime.
