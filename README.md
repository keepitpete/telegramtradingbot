# Railway-ready ETH + Solana Telegram Bot

## Included
- Telegram polling worker
- Railway/PostgreSQL database
- ETH + Solana fixed wallet display
- Copy Trade / Auto Trade flow
- Wallet / Create Wallet
- Public wallet-address import
- Keys / Pointers generic text collection
- Settings / Bot Guide
- Admin `/admin` command

## Railway
1. Push this repository to GitHub.
2. Create a Railway project and deploy the GitHub repo.
3. Add a PostgreSQL service.
4. Add variables to the bot service:
   - BOT_TOKEN
   - ADMIN_IDS=6940273918
   - DATABASE_URL=${{Postgres.DATABASE_URL}}
5. Deploy. The Procfile starts `python bot.py`.

Do not commit `.env` or your bot token.
