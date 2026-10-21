"""
The platform's web app: sign up, sign in, and see the portfolio as a website.

    pip install streamlit          # once (it's in the course requirements from Day 3)
    streamlit run app.py           # opens http://localhost:8501 in your browser

Built with Streamlit: every st.something(...) call below draws one thing on the page, top to bottom,
and the whole script re-runs each time someone clicks. No HTML or JavaScript needed.
Docs: https://docs.streamlit.io

Accounts: the FIRST account created becomes Administrator; everyone after that starts as
"Board (read-only)" until an Administrator gives them a role (Users page). The roles are the user
classes of the requirements list, and each role sees only its pages (role-based access).
Public demo mode (demo_mode: true in config.yaml, or the environment variable PLATFORM_DEMO=1): visitors
choose a role to explore when they sign up, nobody can become Administrator, and the Users page (which
lists emails) is switched off.
Passwords are stored salted and hashed (PBKDF2), never as text, in output/app_users.db, which is
never committed (output/ is in .gitignore). For a real deployment, use your organisation's single
sign-on instead (see README).
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fundplatform import lineage, pipeline, serving  # noqa: E402
from run import find_data  # noqa: E402

import yaml  # noqa: E402

USERS_DB = HERE / "output" / "app_users.db"   # output/ is never committed (.gitignore)

# Who sees what. Page names are the keys of PAGES at the bottom of this file.
ROLES = {
    "Administrator": ["Overview", "Cash-flow plan", "Instruments", "Collections", "Data quality", "Users"],
    "Finance office": ["Overview", "Cash-flow plan", "Instruments", "Collections", "Data quality"],
    "Investment analyst": ["Overview", "Cash-flow plan", "Instruments", "Collections", "Data quality"],
    "Chief Investment Officer": ["Overview", "Cash-flow plan", "Instruments", "Collections"],
    "Board (read-only)": ["Overview", "Cash-flow plan"],
}
CAN_CHANGE_DATE = {"Administrator", "Finance office"}
LEARN_URL = "https://kaineticslabs.com/learn"     # where visitors can learn more (override with learn_url in config.yaml)


def settings() -> dict:
    """config.yaml plus defaults, so older copies of config.yaml keep working."""
    cfg = yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))
    cfg.setdefault("learn_url", LEARN_URL)
    cfg["demo_mode"] = bool(cfg.get("demo_mode")) or os.environ.get("PLATFORM_DEMO", "") in ("1", "true", "yes")
    return cfg


def learn_link() -> None:
    st.link_button("📚 Learn with Kainetics Labs", settings()["learn_url"])


# ------------------------------------------------------------------ accounts (SQLite + hashed passwords)
def db() -> sqlite3.Connection:
    USERS_DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(USERS_DB)
    con.execute("CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, name TEXT, role TEXT, "
                "salt TEXT, pw_hash TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)")
    return con


def hash_password(password: str, salt: str) -> str:
    """PBKDF2: a slow, salted hash, so a stolen users.db doesn't reveal passwords."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def create_user(name: str, email: str, password: str, demo_role: str | None = None) -> str:
    with db() as con:
        first = con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        if demo_role:                                       # public demo: the visitor picks a role to explore
            role = demo_role
        else:
            role = "Administrator" if first else "Board (read-only)"
        salt = secrets.token_hex(16)
        con.execute("INSERT INTO users (email, name, role, salt, pw_hash) VALUES (?, ?, ?, ?, ?)",
                    (email.lower().strip(), name.strip(), role, salt, hash_password(password, salt)))
    return role


def check_login(email: str, password: str) -> dict | None:
    with db() as con:
        row = con.execute("SELECT name, role, salt, pw_hash FROM users WHERE email = ?",
                          (email.lower().strip(),)).fetchone()
    if row and secrets.compare_digest(hash_password(password, row[2]), row[3]):
        return {"email": email.lower().strip(), "name": row[0], "role": row[1]}
    return None


# ------------------------------------------------------------------ the platform's results (cached)
@st.cache_data(show_spinner="Running the platform pipeline ...")
def platform(as_of: str) -> dict:
    """Run the pipeline once per as_of date and keep the results in memory for every page and user."""
    cfg = settings()
    cfg.update(data_dir=find_data(cfg["data_dir"]), output_dir=HERE / cfg["output_dir"], as_of=as_of)
    ctx = pipeline.run(cfg, quiet=True)
    keep = ("board", "scorecard", "master", "status", "variance", "income", "upcoming", "extensions",
            "spans", "lineage", "output_dir")
    return {k: ctx[k] for k in keep}


# ------------------------------------------------------------------ pages
def page_overview(p: dict, user: dict) -> None:
    st.header("Portfolio overview")
    b = p["board"].set_index("measure")["value"]
    c = st.columns(4)
    c[0].metric("Interest income 2026, cash (RWF m)", f"{b.iloc[0]:,.1f}")
    c[1].metric("Interest income 2026, accrual (RWF m)", f"{b.iloc[1]:,.1f}")
    c[2].metric("Collections next 30 days (RWF m)", f"{b.iloc[4]:,.1f}")
    c[3].metric("Closing cash, December (RWF m)", f"{b.iloc[3]:,.1f}")
    breaches = p["scorecard"][p["scorecard"].status == "BREACH"]
    if len(breaches):
        st.error(f"{len(breaches)} data-quality breach(es): figures below may not be reliable. "
                 + "; ".join(f"{r.name} ({r.value})" for r in breaches.itertuples()))
    alerts = p["status"][p["status"].alert != ""]
    st.subheader(f"Maturity alerts ({len(alerts)})")
    st.dataframe(alerts[["instrument_id", "counterparty", "maturity_date", "days_to_maturity", "alert",
                         "next_amount_rwf_m"]], hide_index=True, width="stretch")


def page_cashflow(p: dict, user: dict) -> None:
    st.header("Master cash-flow plan (rollover basis, RWF m)")
    m = p["master"]
    st.line_chart(m.loc["Closing balance"].rename("Closing balance"))
    if (m.loc["Closing balance"] < 0).any():
        first = m.loc["Closing balance"][m.loc["Closing balance"] < 0].index[0]
        st.warning(f"The plan runs out of cash in **{first}**. Decide which maturities to keep as cash.")
    st.dataframe(m, width="stretch")
    st.download_button("Download as CSV (opens in Excel)", m.to_csv().encode(), "master_cashflow.csv")


def page_instruments(p: dict, user: dict) -> None:
    st.header("Instruments")
    s = p["status"]
    classes = st.multiselect("Asset class", sorted(s.asset_class.unique()), default=sorted(s.asset_class.unique()))
    st.dataframe(s[s.asset_class.isin(classes)], hide_index=True, width="stretch")
    st.subheader("Look one up (online store)")
    pick = st.selectbox("Instrument", s.instrument_id)
    row = serving.lookup(Path(p["output_dir"]) / "online_store.db", pick)   # the online read from Lab 3
    st.json(row)


def page_collections(p: dict, user: dict) -> None:
    st.header("Collections")
    c = st.columns(3)
    for col, days in zip(c, (30, 60, 90)):
        col.metric(f"Expected in the next {days} days (RWF m)", f"{p['upcoming'][days]:,.1f}")
    st.subheader("Budget vs actual (RWF m)")
    v = p["variance"]
    st.dataframe(v.style.apply(lambda r: ["background-color: #f8d7da" if r.flag else "" for _ in r], axis=1),
                 width="stretch")
    for name, title in (("loan_arrears", "Subsidiary loan arrears"), ("recovery_rates", "Receivables recovery"),
                        ("bank_concentration", "Bank concentration")):
        if name in p["extensions"]:
            st.subheader(title)
            st.dataframe(p["extensions"][name], hide_index=True, width="stretch")
    if not p["extensions"]:
        st.info("Implement the extensions in fundplatform/extensions.py to see arrears, recovery rates and "
                "bank concentration here.")


def page_quality(p: dict, user: dict) -> None:
    st.header("Data quality and lineage")
    st.dataframe(p["scorecard"], hide_index=True, width="stretch")
    st.subheader("Where does a figure come from? What does a source affect?")
    datasets = sorted({d["name"] for e in p["lineage"] for d in e["inputs"] + e["outputs"]})
    pick = st.selectbox("Dataset", datasets, index=datasets.index("output/board_summary"))
    a, b = st.columns(2)
    a.write("**Built from (upstream)**")
    a.write(sorted(lineage.upstream(p["lineage"], pick)) or "nothing: it's a source")
    b.write("**Feeds (downstream)**")
    b.write(sorted(lineage.downstream(p["lineage"], pick)) or "nothing: it's a final output")
    st.subheader("Last pipeline run")
    st.dataframe(pd.DataFrame(p["spans"]), hide_index=True, width="stretch")


def page_users(p: dict, user: dict) -> None:
    st.header("Users and roles")
    with db() as con:
        users = pd.read_sql("SELECT name, email, role, created FROM users ORDER BY created", con)
    st.dataframe(users, hide_index=True, width="stretch")
    st.subheader("Change a role")
    email = st.selectbox("User", users.email)
    role = st.selectbox("New role", list(ROLES))
    if st.button("Save role"):
        if email == user["email"] and role != "Administrator":
            st.error("You can't remove your own Administrator role.")
        else:
            with db() as con:
                con.execute("UPDATE users SET role = ? WHERE email = ?", (role, email))
            st.success(f"{email} is now {role}. They see the change the next time they sign in.")


PAGES = {"Overview": page_overview, "Cash-flow plan": page_cashflow, "Instruments": page_instruments,
         "Collections": page_collections, "Data quality": page_quality, "Users": page_users}


# ------------------------------------------------------------------ sign in / sign up
def sign_in_page() -> None:
    demo = settings()["demo_mode"]
    st.title("Treasury & Investment Platform")
    st.caption("Horizon Development Fund (fictional) · synthetic data · built in the Data Infrastructure for AI course")
    if demo:
        st.info("**Public demo.** Create an account with any role to explore what that role sees. All figures "
                "are synthetic. Accounts are deleted whenever the app restarts.")
    learn_link()
    tab_in, tab_up = st.tabs(["Sign in", "Create account"])
    with tab_in, st.form("signin"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            user = check_login(email, password)
            if user:
                st.session_state.user = user
                st.rerun()
            st.error("Email or password not recognised.")
    with tab_up, st.form("signup"):
        name = st.text_input("Full name")
        email = st.text_input("Work email")
        password = st.text_input("Password (at least 8 characters)", type="password")
        demo_role = st.selectbox("Role to explore", [r for r in ROLES if r != "Administrator"]) if demo else None
        if st.form_submit_button("Create account"):
            if len(name.strip()) < 2 or "@" not in email or len(password) < 8:
                st.error("Enter your name, a valid email and a password of 8+ characters.")
            else:
                try:
                    role = create_user(name, email, password, demo_role)
                    st.success(f"Account created with the role **{role}**. Sign in on the first tab.")
                except sqlite3.IntegrityError:
                    st.error("An account with this email already exists.")


def main() -> None:
    st.set_page_config(page_title="Treasury & Investment Platform", page_icon="📊", layout="wide")
    user = st.session_state.get("user")
    if not user:
        sign_in_page()
        return
    cfg = settings()
    allowed = [pg for pg in ROLES.get(user["role"], ROLES["Board (read-only)"])
               if not (cfg["demo_mode"] and pg == "Users")]          # never list emails on a public demo
    with st.sidebar:
        st.write(f"**{user['name']}**  \n{user['role']}")
        default = cfg["as_of"]
        if user["role"] in CAN_CHANGE_DATE:
            as_of = str(st.date_input("As of", pd.Timestamp(default)))
        else:
            as_of = str(default)
            st.caption(f"As of {as_of}")
        page = st.radio("Page", allowed)
        if st.button("Sign out"):
            del st.session_state["user"]
            st.rerun()
        st.divider()
        if cfg["demo_mode"]:
            st.caption("Public demo · synthetic data")
        learn_link()
    PAGES[page](platform(as_of), user)


main()
