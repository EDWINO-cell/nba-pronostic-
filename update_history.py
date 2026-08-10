"""
Script de mise à jour de l'historique NBA (games_history.csv).
À lancer manuellement de temps en temps (ex: une fois par semaine) sur Colab,
PAS dans l'app Streamlit — le rate limit gratuit (5 req/min) est trop lent
pour un usage en direct.

Après exécution, remplace le fichier games_history.csv dans le repo GitHub
de l'app avec le nouveau fichier généré ici.
"""

import requests
import pandas as pd
import time

API_KEY = "COLLE_TA_CLE_ICI"
BASE_URL = "https://api.balldontlie.io/v1"
HEADERS = {"Authorization": API_KEY}

SEASONS = [2023, 2024, 2025]
DELAY = 13  # secondes entre requêtes (limite = 5 req/min sur le plan gratuit)


def fetch_all_games(seasons):
    all_games = []
    for season in seasons:
        print(f"Récupération saison {season}...")
        cursor = None
        while True:
            params = {"seasons[]": season, "per_page": 100}
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
            games = data["data"]
            if not games:
                break

            for g in games:
                if g["status"] != "Final":
                    continue
                all_games.append({
                    "date": g["date"],
                    "season": g["season"],
                    "postseason": g["postseason"],
                    "home_team": g["home_team"]["full_name"],
                    "home_team_abbr": g["home_team"]["abbreviation"],
                    "away_team": g["visitor_team"]["full_name"],
                    "away_team_abbr": g["visitor_team"]["abbreviation"],
                    "home_score": g["home_team_score"],
                    "away_score": g["visitor_team_score"],
                })

            meta = data.get("meta", {})
            cursor = meta.get("next_cursor")
            print(f"  {len(all_games)} matchs cumulés")
            if not cursor:
                break
            time.sleep(DELAY)

    return pd.DataFrame(all_games)


if __name__ == "__main__":
    df = fetch_all_games(SEASONS)
    print(f"\nTotal matchs récupérés : {len(df)}")
    df.to_csv("games_history.csv", index=False)
    print("Fichier games_history.csv sauvegardé.")
