# ZubbyEdit Backend API

Pure Python + SQLite backend for the ZubbyEdit content services marketplace.

## Run

```bash
cd zubbyedit-backend
python3 server.py
```

API runs at: **http://localhost:8000**

## Demo accounts

| Email | Password | Role |
|-------|----------|------|
| demo@zubbyedit.com | demo1234 | Buyer |
| tunde@zubbyedit.com | demo1234 | Seller |
| amaka@zubbyedit.com | demo1234 | Seller |

## Endpoints

### Public
- `GET  /api/health` — health check
- `GET  /api/categories` — list categories
- `GET  /api/listings` — list active services
- `GET  /api/listings/:id` — single listing

### Auth
- `POST /api/auth/register` — `{ name, email, phone, password, role }`
- `POST /api/auth/login` — `{ email, password }` → returns `{ token, user }`

### Authenticated (Header: `Authorization: Bearer <token>`)
- `GET  /api/me` — current user
- `GET  /api/orders` — my orders
- `POST /api/orders` — create order
- `GET  /api/orders/:id` — order detail
- `PATCH /api/orders/:id` — update status (`delivered`, `completed`, `revision`)
- `POST /api/listings` — create listing (seller)
- `GET  /api/wallet` — balance + transactions
- `POST /api/wallet/withdraw` — withdraw funds
- `GET  /api/verifications` — verification queue
- `POST /api/verifications` — apply for verification
- `PATCH /api/verifications/:id` — approve/reject
- `GET  /api/chat/:thread_id` — chat messages
- `POST /api/chat` — send message

## Database

SQLite file: `zubbyedit.db` (auto-created on first run)

Tables: users, tokens, categories, listings, verifications, orders, messages, wallets, wallet_transactions
