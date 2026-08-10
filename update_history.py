"""
Script de mise à jour incrémentale de l'historique NBA (games_history.csv).
Ne récupère que les matchs depuis la dernière mise à jour (rapide),
sauf si le fichier n'existe pas encore (dans ce cas, fetch complet).

Utilisable en local OU via GitHub Actions (lit la clé API depuis
la variable d'environnement BALLDONTLIE_API_KEY).
"""

import requests
import pandas as pd
import time
import os
from datetime import datetime, timedelta

API_KEY = os.environ.get("BALLDONTLIE_API_KEY", "COLLE_TA_CLE_ICI")
BASE_URL = "https://api.balldontlie.io/v1"
HEADERS = {"Authorization": API_KEY}
CSV_PATH = "games_history.csv"

SEASONS_FULL = [2023, 2024, 2025]
DELAY = 13


def game_to_row(g):
    return {
        "date": g["date"],
        "season": g["season"],
        "postseason": g["postseason"],
        "home_team": g["home_team"]["full_name"],
        "home_team_abbr": g["home_team"]["abbreviation"],
        "away_team": g["visitor_team"]["full_name"],
        "away_team_abbr": g["visitor_team"]["abbreviation"],
        "home_score": g["home_team_score"],
        "away_score": g["visitor_team_score"],
    }


def fetch_games(params_base):
    games = []
    cursor = None
    while True:
        params = dict(params_base)
        params["per_page"] = 100
        if cursor is not None:
            params["cursor"] = cursor

        r = requests.get(f"{BASE_URL}/games", headers=HEADERS, params=params)

        if r.status_code == 429:
            print("  Rate limit atteint, pause de 20s...")
            time.sleep(20)
            continue
        if r.status_code != 200:
            print(f"Erreur: {r.status_code} - {r.text}")
            break

        data = r.json()
        batch = data["data"]
        if not batch:
            break

        for g in batch:
            if g["status"] == "Final":
                games.append(game_to_row(g))

        cursor = data.get("meta", {}).get("next_cursor")
        print(f"  {len(games)} matchs cumulés dans cette passe")
        if not cursor:
            break
        time.sleep(DELAY)

    return games


def full_fetch():
    print("Aucun historique existant : fetch complet (plusieurs minutes)...")
    all_games = []
    for season in SEASONS_FULL:
        print(f"Saison {season}...")
        all_games.extend(fetch_games({"seasons[]": season}))
    return pd.DataFrame(all_games)


def incremental_fetch(existing_df):
    last_date = pd.to_datetime(existing_df["date"]).max().date()
    start_date = last_date + timedelta(days=1)
    today = datetime.now().date()

    if start_date > today:
        print("Historique déjà à jour, rien à faire.")
        return existing_df

    print(f"Récupération des matchs du {start_date} au {today}...")
    new_games = fetch_games({"start_date": str(start_date), "end_date": str(today)})

    if not new_games:
        print("Aucun nouveau match terminé trouvé.")
        return existing_df

    new_df = pd.DataFrame(new_games)
    combined = pd.concat([existing_df, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["date", "home_team", "away_team"])
    print(f"{len(new_df)} nouveaux matchs ajoutés.")
    return combined


if __name__ == "__main__":
    if os.path.exists(CSV_PATH):
        existing = pd.read_csv(CSV_PATH)
        updated = incremental_fetch(existing)
    else:
        updated = full_fetch()

    updated = updated.sort_values("date").reset_index(drop=True)
    updated.to_csv(CSV_PATH, index=False)
    print(f"\nTotal matchs dans l'historique : {len(updated)}")
    print(f"Fichier {CSV_PATH} sauvegardé.")
