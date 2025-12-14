# bot_predictor.py
import requests
import os
import logging
from telegram import Update, ForceReply
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

import pandas as pd
import numpy as np
from scipy.stats import poisson
API_KEY = os.getenv("FOOTBALL_API_KEY")

HEADERS = {
    "x-apisports-key": API_KEY
}

LEAGUES = [61, 39, 140, 135, 78]  # Ligue 1, PL, Liga, Serie A, Bundesliga
def search_team(team_name):
    url = "https://v3.football.api-sports.io/teams"
    params = {"search": team_name}
    r = requests.get(url, headers=HEADERS, params=params)
    data = r.json().get("response", [])
    if not data:
        return None
    return data[0]["team"]["id"]


def get_last_matches(team_id, season=2024):
    url = "https://v3.football.api-sports.io/fixtures"
    params = {
        "team": team_id,
        "season": season,
        "last": 5
    }
    r = requests.get(url, headers=HEADERS, params=params)
    matches = []
    for f in r.json().get("response", []):
        goals = f["goals"]
        matches.append((goals["home"], goals["away"]))
    return matches
    
# --------- CONFIG ----------
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
# Exemple de dataset synthétique pour démo; remplace par ta vraie base ou appel API
home_id = search_team(home)
away_id = search_team(away)

if not home_id or not away_id:
    await update.message.reply_text("❌ Équipe non trouvée")
    return

home_matches = get_last_matches(home_id)
away_matches = get_last_matches(away_id)

if not home_matches or not away_matches:
    await update.message.reply_text("❌ Pas assez de données")
    return
]
# ---------------------------

# Build a DataFrame from PAST_MATCHES
df = pd.DataFrame(PAST_MATCHES, columns=["home_team","away_team","home_goals","away_goals"])

def compute_team_stats(df):
    overall_home_goals = df['home_goals'].mean()
    overall_away_goals = df['away_goals'].mean()
    home_advantage = overall_home_goals / overall_away_goals if overall_away_goals>0 else 1.1
    teams = sorted(set(df['home_team']).union(df['away_team']))
    team_stats = {}
    for t in teams:
        home_matches = df[df['home_team']==t]
        away_matches = df[df['away_team']==t]
        goals_scored = home_matches['home_goals'].sum() + away_matches['away_goals'].sum()
        goals_conceded = home_matches['away_goals'].sum() + away_matches['home_goals'].sum()
        matches_played = len(home_matches) + len(away_matches)
        team_stats[t] = {
            'avg_scored_per_match': goals_scored / matches_played if matches_played>0 else 0.0,
            'avg_conceded_per_match': goals_conceded / matches_played if matches_played>0 else 0.0,
            'matches': matches_played
        }
    meta = {
        'overall_home_goals': overall_home_goals,
        'overall_away_goals': overall_away_goals,
        'home_advantage': home_advantage
    }
    return team_stats, meta

team_stats, meta = compute_team_stats(df)

def predict_poisson(home_team, away_team, max_goals=6):
    # handle unknown teams
    if home_team not in team_stats or away_team not in team_stats:
        return None, f"Erreur: une des équipes ({home_team} ou {away_team}) n'est pas dans la base."

    # strengths relative to league average
    league_avg = (meta['overall_home_goals'] + meta['overall_away_goals'])/2
    home_attack = team_stats[home_team]['avg_scored_per_match'] / (league_avg if league_avg>0 else 1)
    away_attack = team_stats[away_team]['avg_scored_per_match'] / (league_avg if league_avg>0 else 1)
    home_defense = team_stats[home_team]['avg_conceded_per_match'] / (league_avg if league_avg>0 else 1)
    away_defense = team_stats[away_team]['avg_conceded_per_match'] / (league_avg if league_avg>0 else 1)

    lambda_home = meta['overall_home_goals'] * home_attack * (1/(away_defense if away_defense>0 else 1)) * meta['home_advantage']
    lambda_away = meta['overall_away_goals'] * away_attack * (1/(home_defense if home_defense>0 else 1))

    probs = {}
    for i in range(max_goals+1):
        for j in range(max_goals+1):
            prob = poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
            probs[(i,j)] = prob

    prob_home_win = sum(p for (i,j),p in probs.items() if i>j)
    prob_draw = sum(p for (i,j),p in probs.items() if i==j)
    prob_away_win = sum(p for (i,j),p in probs.items() if i<j)
    sorted_scores = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:6]
    top_scores = [{"score": f"{i}-{j}", "prob": p} for (i,j),p in sorted_scores]

    return {
        'lambda_home': lambda_home,
        'lambda_away': lambda_away,
        'prob_home_win': prob_home_win,
        'prob_draw': prob_draw,
        'prob_away_win': prob_away_win,
        'top_scores': top_scores
    }, None

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = ("Salut ! Je suis ton bot de prédictions.\n\n"
           "Utilise /predict TeamA-TeamB [odds_home odds_draw odds_away]\n"
           "Ex: /predict TeamA-TeamB 2.10 3.20 3.60\n\n"
           "Je renverrai probas, scores probables et value bets.")
    await update.message.reply_text(txt)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Commandes:\n/predict TeamA-TeamB [odds_home od_draw od_away]\n/start")

async def predict_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.split()
    if len(msg) < 2:
        await update.message.reply_text("Usage: /predict TeamA-TeamB [odds_home odds_draw odds_away]")
        return
    match = msg[1]
    if "-" not in match:
        await update.message.reply_text("Format: TeamA-TeamB (avec un tiret)")
        return
    home, away = match.split("-", 1)
    odds = None
    if len(msg) >= 5:
        try:
            odds = {'home': float(msg[2]), 'draw': float(msg[3]), 'away': float(msg[4])}
        except:
            odds = None

    result, err = predict_poisson(home, away)
    if err:
        await update.message.reply_text(err)
        return

    # Build response
    lines = []
    lines.append(f"Prédiction: {home} vs {away}")
    lines.append(f"Lambda (buts attendus): {result['lambda_home']:.2f} (home) — {result['lambda_away']:.2f} (away)")
    lines.append(f"Probabilités: {home} win {result['prob_home_win']:.3f}, draw {result['prob_draw']:.3f}, {away} win {result['prob_away_win']:.3f}")
    lines.append("Top scores probables:")
    for s in result['top_scores']:
        lines.append(f" • {s['score']} → {s['prob']:.3f}")

    if odds:
        ev_home = result['prob_home_win'] - 1/odds['home']
        ev_draw = result['prob_draw'] - 1/odds['draw']
        ev_away = result['prob_away_win'] - 1/odds['away']
        lines.append("\nComparaison cotes (EV = prob - 1/odds):")
        lines.append(f" EV home: {ev_home:.3f}, EV draw: {ev_draw:.3f}, EV away: {ev_away:.3f}")
        positives = []
        if ev_home>0: positives.append(f"home (EV {ev_home:.3f})")
        if ev_draw>0: positives.append(f"draw (EV {ev_draw:.3f})")
        if ev_away>0: positives.append(f"away (EV {ev_away:.3f})")
        if positives:
            lines.append("Value bets détectés: " + ", ".join(positives))
        else:
            lines.append("Aucun value bet détecté vs ces cotes.")
    else:
        lines.append("\nPour comparer avec des cotes, envoie 3 cotes après la commande.")
    await update.message.reply_text("\n".join(lines))

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("predict", predict_cmd))
    print("Bot démarré...")
    app.run_polling()

if __name__ == "__main__":
    main()
