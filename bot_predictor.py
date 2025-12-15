import os
import requests
import math
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# =========================
# CONFIG
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")

HEADERS = {"x-apisports-key": FOOTBALL_API_KEY}
SEASON = 2024

ALLOWED_LEAGUES = {
    61: "Ligue 1",
    39: "Premier League",
    140: "La Liga",
    135: "Serie A",
    78: "Bundesliga"
}

# =========================
# API FOOTBALL
# =========================

def search_team(team_name):
    url = "https://v3.football.api-sports.io/teams"
    params = {"search": team_name}
    r = requests.get(url, headers=HEADERS, params=params)
    for item in r.json().get("response", []):
        league_id = item.get("league", {}).get("id")
        if league_id in ALLOWED_LEAGUES:
            return item["team"]["id"], ALLOWED_LEAGUES[league_id]
    return None, None


def get_last_matches(team_id, last=5):
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"team": team_id, "season": SEASON, "last": last}
    r = requests.get(url, headers=HEADERS, params=params)
    matches = []
    for f in r.json().get("response", []):
        g = f["goals"]
        matches.append((g["home"], g["away"]))
    return matches

# =========================
# MATHS
# =========================

def avg_goals(matches, home=True):
    if not matches:
        return 1.2
    goals = [h if home else a for h, a in matches]
    return sum(goals) / len(goals)


def poisson(l, k):
    return (l ** k * math.exp(-l)) / math.factorial(k)

# =========================
# TELEGRAM
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot pronostics football\n\n"
        "Championnats supportés :\n"
        "• Ligue 1\n• Premier League\n• La Liga\n• Serie A\n• Bundesliga\n\n"
        "Commande :\n/match PSG vs Marseille"
    )


async def match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.replace("/match", "").strip()
        home, away = text.split("vs")
        home, away = home.strip(), away.strip()
    except:
        await update.message.reply_text("❌ Format incorrect\nEx : /match PSG vs Marseille")
        return

    home_id, home_league = search_team(home)
    away_id, away_league = search_team(away)

    if not home_id or not away_id:
        await update.message.reply_text("❌ Équipe non trouvée ou championnat non supporté")
        return

    if home_league != away_league:
        await update.message.reply_text("❌ Les deux équipes ne sont pas dans le même championnat")
        return

    home_matches = get_last_matches(home_id)
    away_matches = get_last_matches(away_id)

    avg_home = avg_goals(home_matches, True)
    avg_away = avg_goals(away_matches, False)

    probs = {(i, j): poisson(avg_home, i) * poisson(avg_away, j) for i in range(5) for j in range(5)}

    home_win = sum(v for (i, j), v in probs.items() if i > j)
    draw = sum(v for (i, j), v in probs.items() if i == j)
    away_win = sum(v for (i, j), v in probs.items() if i < j)
    over25 = sum(v for (i, j), v in probs.items() if i + j > 2)
    btts = sum(v for (i, j), v in probs.items() if i > 0 and j > 0)

    score = max(probs, key=probs.get)
    confidence = max(home_win, draw, away_win) * 10

    await update.message.reply_text(
        f"⚽ {home} vs {away} ({home_league})\n\n"
        f"1 : {home_win*100:.1f}%\n"
        f"N : {draw*100:.1f}%\n"
        f"2 : {away_win*100:.1f}%\n\n"
        f"Over 2.5 : {over25*100:.1f}%\n"
        f"BTTS : {btts*100:.1f}%\n\n"
        f"Score probable : {score[0]}-{score[1]}\n"
        f"Confiance : {confidence:.1f}/10"
    )

# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("match", match))
    app.run_polling()

if __name__ == "__main__":
    main()
