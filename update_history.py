name: Mise à jour hebdomadaire de l'historique NBA

on:
  schedule:
    # Tous les lundis à 6h00 UTC
    - cron: "0 6 * * 1"
  workflow_dispatch: {}  # permet aussi de le lancer manuellement depuis GitHub

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout du repo
        uses: actions/checkout@v4

      - name: Installer Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Installer les dépendances
        run: pip install requests pandas

      - name: Lancer la mise à jour
        env:
          BALLDONTLIE_API_KEY: ${{ secrets.BALLDONTLIE_API_KEY }}
        run: python update_history.py

      - name: Commit et push si changement
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add games_history.csv
          git diff --staged --quiet || git commit -m "Mise à jour automatique de l'historique NBA"
          git push
