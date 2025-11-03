[README.md](https://github.com/user-attachments/files/23295084/README.md)
# X Liked Tweets → Discord Bot (Beginner Friendly)

This bot sends a message to a Discord channel when a target X (Twitter) account likes new posts.

## Files
- `bot_likes.py` — the bot
- `requirements.txt` — dependencies
- `.env.example` — copy to `.env` and fill in tokens

## Setup
1) Install Python 3.10+
2) In a terminal:
   ```bash
   pip install -r requirements.txt
   ```
3) Create `.env` by copying `.env.example` and fill:
   - `DISCORD_TOKEN` (from Discord Dev Portal)
   - `X_BEARER_TOKEN` (from X/Twitter Dev Portal)
   - optional `POLL_INTERVAL_SECONDS`
4) Run:
   ```bash
   python bot_likes.py
   ```
5) In your Discord server channel:
   ```
   /like_add elonmusk
   ```

## Notes
- If `get_liked_tweets` returns 403, your tier may require user-context auth (OAuth1/2 user tokens) or a higher tier.
- Increase `POLL_INTERVAL_SECONDS` if you hit rate limits.
