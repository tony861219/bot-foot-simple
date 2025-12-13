import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import pandas as pd
import numpy as np
from scipy.stats import poisson

BOT_TOKEN = os.getenv("BOT_TOKEN", "8440039057:AAHFVl3-axIAcO4wvs_lEgAk81iQQ7_Urjw")

PAST_MATCHES = [
    ("TeamA","TeamB",2,1),
    ("TeamC","TeamA",0,3),
    ("TeamB","TeamC",1,1),
    ("TeamA","TeamC",1,1),
]

df = pd.DataFrame(PAST_MATCHES, columns=["home","away","hg","ag"])

def stats(df):
    teams = set(df["home"]).union(df["away"])
    s = {}
    for t in teams:
        m = df[(df.home==t)|(df.away==t)]
        gf = m.apply(lambda r: r.hg if r.home==t else r.ag, axis=1).sum()
        ga = m.apply(lambda r: r.ag if r.home==t else r.hg, axis=1).sum()
        s[t] = {"gf": gf/len(m), "ga": ga/len(m)}
    return s

STATS = stats(df)

def predict(home, away):
    if home not in STATS or away not in STATS:
        return None
    lh = max(0.2, STATS[home]["gf"] * (1/STATS[away]["ga"]))
    la = max(0.2, STATS[away]["gf"] * (1/STATS[home]["ga"]))
    probs = {(i,j): poisson.pmf(i,lh)*poisson.pmf(j,la) for i in range(6) for j in range(6)}
    p1 = sum(p for (i,j),p in probs.items() if i>j)
    px = sum(p for (i,j),p in probs.items() if i==j)
    p2 = sum(p for (i,j),p in probs.items() if i<j)
    over = sum(p for (i,j),p in probs.items() if i+j>2)
    btts = sum(p for (i,j),p in probs.items() if i>0 and j>0)
    score = max(probs, key=probs.get)
    conf = round(max(p1,px,p2)*10,1)
    return p1,px,p2,over,btts,score,conf

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot pronostics foot 📊\n"
        "Commande : /match EquipeA-EquipeB\n"
        "Exemple : /match TeamA-TeamB"
    )

async def match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        home, away = update.message.text.split()[1].split("-")
        r = predict(home, away)
        if not r:
            await update.message.reply_text("Équipe inconnue.")
            return
        p1,px,p2,over,btts,score,conf = r
        msg = (
            f"{home} vs {away}\n\n"
            f"1 : {p1*100:.1f}%\n"
            f"N : {px*100:.1f}%\n"
            f"2 : {p2*100:.1f}%\n\n"
            f"Over 2.5 : {over*100:.1f}%\n"
            f"BTTS : {btts*100:.1f}%\n\n"
            f"Score probable : {score[0]}-{score[1]}\n"
            f"Confiance : {conf}/10"
        )
        await update.message.reply_text(msg)
    except:
        await update.message.reply_text("Format : /match EquipeA-EquipeB")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("match", match))
    app.run_polling()

if __name__ == "__main__":
    main()
