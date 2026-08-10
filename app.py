import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timedelta
from scipy.stats import norm

st.set_page_config(page_title="Pronostic NBA", page_icon="🏀", layout="centered")

API_KEY = st.secrets["BALLDONTLIE_API_KEY"]
BASE_URL = "https://api.balldontlie.io/v1"
HEADERS = {"Authorization": API_KEY}

K_MARGIN = 0.05
K_TOTAL = 0.04
B2B_PENALTY = -1.0

# ============================================================
# 1. Chargement de l'historique (fichier local, pas d'appel API)
# ============================================================
@st.cache_data
def load_history():
    df = pd.read_csv("games_history.csv")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


@st.cache_data
def compute_rest_days(df):
    team_last_game = {}
    rest_home, rest_away = [], []
    for _, row in df.iterrows():
        date = row["date"]
        for side, col in [("home", "home_team"), ("away", "away_team")]:
            team = row[col]
            last = team_last_game.get(team)
            rest = (date - last).days if last is not None else 5
            (rest_home if side == "home" else rest_away).append(rest)
            team_last_game[team] = date
    df = df.copy()
    df["home_rest"] = rest_home
    df["away_rest"] = rest_away
    df["home_b2b"] = (df["home_rest"] <= 1).astype(int)
    df["away_b2b"] = (df["away_rest"] <= 1).astype(int)
    return df


# ============================================================
# 2. Calcul des ratings dynamiques (walk-forward sur tout l'historique)
# ============================================================
@st.cache_data
def compute_ratings(df):
    teams = pd.unique(df[["home_team", "away_team"]].values.ravel())
    league_avg_total = (df["home_score"] + df["away_score"]).mean()
    home_adv = (df["home_score"] - df["away_score"]).mean()

    power = {t: 0.0 for t in teams}
    total_power = {t: 0.0 for t in teams}
    errors_margin, errors_total = [], []

    for _, row in df.iterrows():
        h, a = row["home_team"], row["away_team"]
        hs, as_ = row["home_score"], row["away_score"]
        h_b2b, a_b2b = row["home_b2b"], row["away_b2b"]

        pred_margin = power[h] - power[a] + home_adv + B2B_PENALTY * (h_b2b - a_b2b)
        pred_total = league_avg_total + total_power[h] + total_power[a]
        actual_margin = hs - as_
        actual_total = hs + as_

        errors_margin.append(actual_margin - pred_margin)
        errors_total.append(actual_total - pred_total)

        err_margin = actual_margin - pred_margin
        power[h] += K_MARGIN * err_margin / 2
        power[a] -= K_MARGIN * err_margin / 2
        err_total = actual_total - pred_total
        total_power[h] += K_TOTAL * err_total / 2
        total_power[a] += K_TOTAL * err_total / 2

    margin_std = np.std(errors_margin)
    total_std = np.std(errors_total)

    return {
        "power": power, "total_power": total_power,
        "league_avg_total": league_avg_total, "home_adv": home_adv,
        "margin_std": margin_std, "total_std": total_std,
        "last_update": df["date"].max(),
    }


def predict_matchup(model, home, away, home_b2b=0, away_b2b=0):
    power, total_power = model["power"], model["total_power"]
    if home not in power or away not in power:
        return None

    pred_margin = (power[home] - power[away] + model["home_adv"]
                   + B2B_PENALTY * (home_b2b - away_b2b))
    pred_total = model["league_avg_total"] + total_power[home] + total_power[away]

    pred_home_score = (pred_total + pred_margin) / 2
    pred_away_score = (pred_total - pred_margin) / 2
    home_win_prob = 1 - norm.cdf(0, loc=pred_margin, scale=model["margin_std"])

    return {
        "pred_home_score": pred_home_score, "pred_away_score": pred_away_score,
        "pred_margin": pred_margin, "pred_total": pred_total,
        "home_win_prob": home_win_prob,
    }


def prob_over(pred_total, line, total_std):
    return 1 - norm.cdf(line, loc=pred_total, scale=total_std)


# ============================================================
# 3. Récupération des matchs à venir (appel API léger, mis en cache court)
# ============================================================
@st.cache_data(ttl=3600)
def fetch_upcoming_games(days_ahead=3):
    today = datetime.now().date()
    end = today + timedelta(days=days_ahead)
    r = requests.get(
        f"{BASE_URL}/games",
        headers=HEADERS,
        params={"start_date": str(today), "end_date": str(end), "per_page": 100},
    )
    if r.status_code != 200:
        return []
    return r.json()["data"]


# ============================================================
# 4. Interface
# ============================================================
st.title("🏀 Pronostic NBA")

history = load_history()
history = compute_rest_days(history)
model = compute_ratings(history)
all_teams = sorted(model["power"].keys())

st.caption(f"Modèle calibré sur l'historique jusqu'au {model['last_update'].strftime('%d/%m/%Y')}")

tab1, tab2 = st.tabs(["📅 Prochains matchs", "🔍 Matchup manuel"])

# --- Onglet 1 : matchs à venir ---
with tab1:
    games = fetch_upcoming_games()
    if not games:
        st.info("Aucun match trouvé dans les prochains jours (intersaison ou erreur API).")
    for g in games:
        home, away = g["home_team"]["full_name"], g["visitor_team"]["full_name"]
        pred = predict_matchup(model, home, away)
        if pred is None:
            continue

        with st.container(border=True):
            st.subheader(f"{home} vs {away}")
            st.caption(g["date"])

            col1, col2 = st.columns(2)
            col1.metric(home, f"{pred['pred_home_score']:.0f} pts", f"{pred['home_win_prob']:.0%} de victoire")
            col2.metric(away, f"{pred['pred_away_score']:.0f} pts", f"{1 - pred['home_win_prob']:.0%} de victoire")

            st.write(f"**Total prédit :** {pred['pred_total']:.1f} pts | **Écart :** {pred['pred_margin']:+.1f} pts ({home})")

            line = st.number_input(
                "Ligne over/under à tester", value=round(pred["pred_total"]),
                key=f"line_{g['id']}", step=1
            )
            p_over = prob_over(pred["pred_total"], line, model["total_std"])
            st.write(f"Probabilité **over {line}** : {p_over:.0%} | **under {line}** : {1 - p_over:.0%}")

# --- Onglet 2 : matchup manuel ---
with tab2:
    col1, col2 = st.columns(2)
    home = col1.selectbox("Équipe à domicile", all_teams, index=0)
    away = col2.selectbox("Équipe à l'extérieur", all_teams, index=1)

    home_b2b = col1.checkbox("Domicile en back-to-back")
    away_b2b = col2.checkbox("Extérieur en back-to-back")

    if home == away:
        st.warning("Choisis deux équipes différentes.")
    else:
        pred = predict_matchup(model, home, away, home_b2b, away_b2b)
        st.subheader(f"{home} {pred['pred_home_score']:.0f} - {pred['pred_away_score']:.0f} {away}")
        st.write(f"**{home}** : {pred['home_win_prob']:.0%} de victoire")
        st.write(f"**{away}** : {1 - pred['home_win_prob']:.0%} de victoire")
        st.write(f"**Total prédit :** {pred['pred_total']:.1f} pts | **Spread :** {pred['pred_margin']:+.1f} ({home})")

        line = st.number_input("Ligne over/under à tester", value=round(pred["pred_total"]), step=1)
        p_over = prob_over(pred["pred_total"], line, model["total_std"])
        st.write(f"Probabilité **over {line}** : {p_over:.0%} | **under {line}** : {1 - p_over:.0%}")
