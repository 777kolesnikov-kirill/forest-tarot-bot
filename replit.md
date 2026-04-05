# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.
Also contains a Python Telegram bot (Лесной Маг / Forest Mage Tarot bot).

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)
- **Python**: 3.11
- **Telegram bot**: python-telegram-bot 20.8

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally
- `python telegram-bot/bot.py` — run the Telegram bot

## Telegram Bot

Located in `telegram-bot/`.

### Files
- `bot.py` — main bot logic with handlers
- `cards.py` — all 22 Major Arcana tarot cards with Russian names, descriptions, and image paths
- `requirements.txt` — Python dependencies
- `tarot.db` — SQLite database (auto-created on first run), stores user_id + last_date + card_index

### Features
- `/start` — shows Russian welcome message with a draw button
- One free card per user per day (enforced via SQLite)
- If user already drew today, shows a Russian reminder message
- Sends card image if `telegram-bot/images/<filename>` exists; otherwise sends text only

### Secrets
- `TELEGRAM_BOT_TOKEN` — must be set in Replit Secrets

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.
