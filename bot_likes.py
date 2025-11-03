import os
import json
import asyncio
from typing import Dict, Any, Set, Optional

import tweepy
from discord import Intents, Interaction
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

# =========================
# Load ENV
# =========================
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "120"))

CONSUMER_KEY = os.getenv("X_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("X_CONSUMER_SECRET")
ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

if not all([DISCORD_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_SECRET]):
    raise RuntimeError("Set DISCORD_TOKEN, X_CONSUMER_KEY, X_CONSUMER_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET in .env")

# =========================
# X (Twitter) Clients
# =========================
client = tweepy.Client(
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_SECRET,
    wait_on_rate_limit=True,
)

auth = tweepy.OAuth1UserHandler(
    CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_SECRET
)
api_v1 = tweepy.API(auth, wait_on_rate_limit=True)

try:
    me = api_v1.verify_credentials()
    if me:
        print("OAuth1 OK as:", getattr(me, "screen_name", "unknown"))
except Exception as e:
    print("verify_credentials error:", e)

# =========================
# Discord Bot
# =========================
intents = Intents.none()  # cuma pakai slash commands
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "likes_tracked.json"
state: Dict[str, Any] = {"users": {}}

def load_state():
    global state
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {"users": {}}
    else:
        state = {"users": {}}

def save_state():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# =========================
# Helpers
# =========================
async def resolve_user_id(username: str) -> Optional[str]:
    uname = username.strip().lstrip("@")
    try:
        resp = client.get_user(username=uname)
        if resp and resp.data:
            return str(resp.data.id)
    except tweepy.TweepyException as e:
        print("get_user (v2) error:", e)
    try:
        u = api_v1.get_user(screen_name=uname)
        if u and getattr(u, "id_str", None):
            return str(u.id_str)
        if u and getattr(u, "id", None):
            return str(u.id)
    except Exception as e:
        print("get_user (v1.1) error:", e)
    return None

async def fetch_recent_liked_ids(user_id: str, max_pages: int = 3) -> Set[str]:
    ids: Set[str] = set()
    try:
        paginator = tweepy.Paginator(
            client.get_liked_tweets,
            id=user_id,
            max_results=100,
            tweet_fields=["author_id","created_at"],
            expansions=["author_id"],
        )
        pages = 0
        for page in paginator:
            if page.data:
                for t in page.data:
                    ids.add(str(t.id))
            pages += 1
            if pages >= max_pages:
                break
            await asyncio.sleep(0.2)
    except tweepy.TweepyException as e:
        print("get_liked_tweets error:", e)
    return ids

async def get_tweet_brief(tweet_id: str) -> str:
    try:
        r = client.get_tweet(
            id=tweet_id,
            expansions=["author_id"],
            tweet_fields=["text"],
            user_fields=["username"]
        )
        if not r or not r.data:
            return f"https://x.com/i/web/status/{tweet_id}"
        text = (r.data.text or "").replace("\n"," ")
        author = None
        if r.includes and r.includes.get("users"):
            author = r.includes["users"][0].username
        if author:
            url = f"https://x.com/{author}/status/{tweet_id}"
            if len(text) > 200:
                text = text[:200] + "…"
            return f"@{author}: {text} {url}"
        else:
            url = f"https://x.com/i/web/status/{tweet_id}"
            if len(text) > 200:
                text = text[:200] + "…"
            return f"{text} {url}"
    except tweepy.TweepyException:
        return f"https://x.com/i/web/status/{tweet_id}"

async def announce_new_likes(user_id: str):
    info = state["users"].get(user_id)
    if not info:
        return
    uname = info["username"]
    guild_id = info["guild_id"]
    channel_id = info["channel_id"]

    current = await fetch_recent_liked_ids(user_id)
    if not current:
        return

    old = set(info.get("liked_ids", []))
    new_ids = list(current - old)
    if not new_ids:
        return

    state["users"][user_id]["liked_ids"] = list(current)
    save_state()

    new_ids = new_ids[:10]
    try:
        guild = bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        if not channel:
            return
        lines = []
        for tid in new_ids:
            brief = await get_tweet_brief(tid)
            lines.append(f"**{uname}** liked: {brief}")
            await asyncio.sleep(0.2)
        await channel.send("\n".join(lines))
    except Exception as e:
        print("send error:", e)

@tasks.loop(seconds=5)
async def background_loop():
    await asyncio.sleep(POLL_INTERVAL_SECONDS)
    for uid in list(state["users"].keys()):
        try:
            await announce_new_likes(uid)
        except Exception as e:
            print("loop error:", e)
            await asyncio.sleep(1)

@bot.event
async def on_ready():
    load_state()
    try:
        await bot.tree.sync()
    except Exception as e:
        print("sync error:", e)
    if not background_loop.is_running():
        background_loop.start()
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="like_add", description="Pantau likes akun X (username tanpa @)")
@app_commands.describe(username="Contoh: elonmusk")
async def like_add(interaction: Interaction, username: str):
    await interaction.response.defer(ephemeral=True)
    uname = username.strip().lstrip("@")
    uid = await resolve_user_id(uname)
    if not uid:
        await interaction.followup.send(f"User not found or unauthorized: {uname}")
        return
    ids = await fetch_recent_liked_ids(uid)
    if not ids:
        await interaction.followup.send("Tidak bisa ambil liked tweets (rate limit, akun private, atau akses API).")
        return
    state["users"][uid] = {
        "username": f"@{uname}",
        "liked_ids": list(ids),
        "guild_id": interaction.guild_id,
        "channel_id": interaction.channel_id,
    }
    save_state()
    await interaction.followup.send(f"Tracking **@{uname}** likes di channel ini.")

@bot.tree.command(name="like_remove", description="Berhenti pantau likes akun X")
@app_commands.describe(username="Username tanpa @")
async def like_remove(interaction: Interaction, username: str):
    await interaction.response.defer(ephemeral=True)
    uname = username.strip().lstrip("@").lower()
    target_id = None
    for uid, info in state["users"].items():
        if info.get("username","").lower() == f"@{uname}":
            target_id = uid
            break
    if not target_id:
        await interaction.followup.send(f"@{uname} tidak sedang dipantau.")
        return
    del state["users"][target_id]
    save_state()
    await interaction.followup.send(f"Berhenti memantau **@{uname}**.")

@bot.tree.command(name="like_list", description="Daftar akun yang dipantau")
async def like_list(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    if not state["users"]:
        await interaction.followup.send("Belum ada pantauan. Pakai `/like_add <username>` dulu.")
        return
    lines = ["Akun yang dipantau:"]
    for _, info in state["users"].items():
        lines.append(f"- {info.get('username')}")
    await interaction.followup.send("\n".join(lines))

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
