# Treasury & Investment Platform: live demo

A working investment data platform for a development fund's treasury desk. It turns registers kept in Excel
(government bonds, term deposits, corporate bonds, subsidiary loans, borrowings, FX rates) into payment
schedules, cash vs accrual income, a 12-month master cash-flow plan, maturity alerts, a data-quality
scorecard and a lineage record for every figure, behind accounts with role-based access.

**All data is synthetic** (fictional Horizon Development Fund; counterparties Bank A–I, Subsidiary A–C).

Built in the course *Data Infrastructure for AI: Feature Stores, Real-Time Pipelines and MLOps*.
**Learn more: [kaineticslabs.com/learn](https://kaineticslabs.com/learn)**

## Explore it
Open the app, choose **Create account**, pick a role (Finance office, Investment analyst, Chief Investment
Officer or Board) and sign in. Each role sees different pages. Accounts are deleted whenever the app restarts.

## Run it on your computer
```bash
pip install -r requirements.txt
streamlit run app.py          # http://localhost:8501
python run.py                 # the same pipeline without the website: results in output/
```

## Deploy it for free (Streamlit Community Cloud)
1. Push this folder to a **public** GitHub repository (e.g. `fund-platform-demo`).
2. Go to https://share.streamlit.io, sign in with GitHub, click **Create app** → **Deploy a public app from GitHub**.
3. Repository: this one · Branch: `main` · Main file path: `app.py` · Advanced settings → Python 3.11.
4. Click **Deploy**. After a few minutes you get a public link like `https://<name>.streamlit.app` to share.
Every push to the repository updates the site automatically.

## What's inside
`app.py` (the website) · `run.py` (the pipeline) · `fundplatform/` (registers, schedules, FX, cash-flow,
serving, quality, lineage, pipeline) · `contracts/` (data contracts) · `dags/` (the same pipeline as an
Apache Airflow DAG) · `data/` (synthetic registers) · `config.yaml` (settings; `demo_mode: true`).
