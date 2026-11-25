# CLAUDE.md — NOFX Fork (Hyperliquid AI Trading)

Инструкция для coding-агентов (Claude Code / Codex / Antigravity) по работе с нашим форком NOFX для агентной торговли на Hyperliquid.

> **Важно про `AGENTS.md` на macOS:** в корне репозитория есть upstream-файл `agents.md` (спецификация встроенного NOFXi-ассистента на китайском). На macOS (case-insensitive APFS) `AGENTS.md` и `agents.md` — один и тот же файл. **Не перезаписывай `agents.md`**, вся локальная документация форка хранится в этом `CLAUDE.md`.

---

## 1. Где находится проект и инфраструктура

| Компонент | Расположение |
|---|---|
| Локальная папка (Mac) | `/Users/nickeo23/code_projects/trading/nofx` |
| Папка на VPS | `vps-apds:/home/administrator/nofx` (`ssh vps-apds`) |
| GitHub-форк (`origin`) | `https://github.com/n23eos/nofx.git` (рабочая ветка `dev`) |
| Upstream (`upstream`) | `https://github.com/NoFxAiOS/nofx.git` |
| Контейнер бэкенда | `nofx-trading` (собирается из исходников `./docker/Dockerfile.backend`), `127.0.0.1:8090 -> 8080` |
| Контейнер фронта | `nofx-frontend` (`ghcr.io/nofxaios/nofx/nofx-frontend:stable`), `127.0.0.1:3090 -> 80` |
| Веб-интерфейс с Mac | SSH-туннель `ssh -N -L 3090:127.0.0.1:3090 vps-apds` → `http://127.0.0.1:3090` |
| База данных | SQLite в `/home/administrator/nofx/data/data.db` на VPS |

Почему выбраны порты `3090` / `8090`: на `vps-apds` порты `3000` и `8080` заняты другими сервисами; на Mac порт `8080` занят `llama-server`.

---

## 2. Что уже сделано в форке

Базовый коммит форка: `0dd85ea4` (поверх `NoFxAiOS/nofx@65e9037b`, 2026-11-25):

1. **Отключён Hyperliquid builder fee (+0.05% / 5 bps на сторону):**
   - `trader/hyperliquid/trader.go`: `defaultBuilder = nil` (ордера на native perps и `xyz` DEX уходят напрямую в Hyperliquid без комиссии билдера).
   - `api/handler_hyperliquid_wallet.go`, `api/handler_exchange.go`, `api/launch_preflight.go`, `api/handler_trader.go`, `api/handler_planning.go`, `manager/trader_manager.go`: сняты проверки `HyperliquidBuilderApproved`, API возвращает `builderApproved: true`.
   - Обновлены и пройдены Go-тесты: `nofx/trader/hyperliquid`, `nofx/api`, `nofx/manager`.
2. **Фронт в `docker-compose.yml`:**
   - Переведён на опубликованный образ `ghcr.io/nofxaios/nofx/nofx-frontend:stable`, потому что сабмодуль TradingView `web/vendor/charting` (`tinkle-community/charting_library`) приватный и недоступен внешним форкам.
3. **Деплой на `vps-apds`:**
   - Сгенерирован `.env` (права `600`, ключи `JWT_SECRET`, `DATA_ENCRYPTION_KEY`, `RSA_PRIVATE_KEY`, `NOFX_BIND_ADDRESS=127.0.0.1`, `NOFX_BACKEND_PORT=8090`, `NOFX_FRONTEND_PORT=3090`, `NOFX_TIMEZONE=Asia/Tbilisi`, `DB_TYPE=sqlite`).
   - Оба контейнера подняты и `healthy`, `GET /api/health` через `:8090` и `:3090` возвращает `{"status":"ok"}`.

---

## 3. Инварианты безопасности (не нарушать)

1. **Сначала только Hyperliquid Testnet.** Никаких реальных денег и mainnet-ордеров до завершения testnet-периода и явного согласия владельца.
2. **Только Hyperliquid API/Agent Wallet** (`app.hyperliquid-testnet.xyz/API`, позже `app.hyperliquid.xyz/agents`). Основной приватный ключ кошелька в NOFX не передавать и не хранить.
3. **Loopback-only binding:** на VPS `NOFX_BIND_ADDRESS=127.0.0.1` обязателен. Не открывать `:3090` и `:8090` на `0.0.0.0` без TLS и аутентификации.
4. **Секреты:** `.env` и `data/` никогда не коммитить; приватные ключи и API-ключи не выводить в логи, терминал и чат.
5. **Не ломать чужие сервисы на VPS:** на `vps-apds` работают другие контейнеры и сервисы на `:3000`/`:8080`. Работать только в `/home/administrator/nofx` и только с контейнерами `nofx-trading` / `nofx-frontend`.

---

## 4. Что нужно сделать дальше (пошаговый план для агента)

### Этап A — Первичная настройка (делает владелец, агент помогает)
- [ ] Открыть NOFX через SSH-туннель (`ssh -N -L 3090:127.0.0.1:3090 vps-apds` → `http://127.0.0.1:3090`) и создать локальный аккаунт NOFX.
- [ ] В **Settings → AI Models** подключить AI-провайдера (OpenRouter / OpenAI / DeepSeek / Qwen / custom OpenAI-compatible API или Claw402).
- [ ] На **Hyperliquid Testnet** (`https://app.hyperliquid-testnet.xyz`):
  - получить тестовые USDC через `/drip`;
  - создать API/Agent Wallet в `/API` и сохранить адрес основного кошелька (`0x...`) и приватник агента (без префикса `0x`).

### Этап B — Подключение Hyperliquid Testnet (задача агента №1)
**Контекст проблемы:** в свежем UI (`web/src/components/trader/ExchangeConfigModal.tsx`, ~строки 1092–1104) авторы убрали ручную форму ввода Hyperliquid и оставили только `HyperliquidWalletConnect` (MetaMask/Rabby), который жёстко привязан к `testnet: false` (Mainnet). При этом бэкенд API `POST /api/exchanges` и движок `trader/hyperliquid` полностью поддерживают `testnet: true` (`https://api.hyperliquid-testnet.xyz`).

Что сделать агенту:
- [x] Разблокированы прямые провайдеры AI API-ключей (`openai`, `deepseek`, `claude`, `gemini`, `qwen`, `custom`/OpenRouter) в `api/handler_ai_model.go`.
- [x] Создана консервативная стратегия `Hyperliquid Testnet Conservative (BTC/ETH/SOL)` в SQLite на `vps-apds` (бесплатные рыночные данные, плечо до 3x/2x, max 2 позиции, max 30% маржи).
- [x] Написан единый CLI-мастер `scripts/setup_testnet_bot.py` (подключает AI API-ключ + Hyperliquid Testnet Agent Wallet + создаёт и запускает Autopilot-трейдера в обход залоченного UI).
- [ ] Владелец запускает `python3 scripts/setup_testnet_bot.py`, после чего агент проверяет первый цикл, логи и исполнение ордеров на `vps-apds`.

> Примечание: **Frontier** (`api/handler_planning.go:163`) ограничивает живое исполнение только Mainnet (`if ex.Testnet`), хотя строить планы/аналитику в Frontier можно без биржи. Для тестовых сделок использовать **Autopilot**. Если позже понадобится Testnet и в Frontier — это отдельная небольшая правка `api/handler_planning.go`.

### Этап C — Сбор данных, стратегия и жёсткие риск-гарды (задача агента №2)
- [ ] Провести аудит того, какую информацию сейчас собирает и передаёт в LLM движок Autopilot (`market/`, `decision/`, `provider/hyperliquid/`, `store/`):
  - какие таймфреймы свечей, индикаторы, funding rate, open interest, стакан и внешние новости/фиды реально попадают в промпт;
  - какие источники требуют платного Claw402, а какие работают бесплатно напрямую с Hyperliquid/Binance/RSS.
- [ ] Настроить первую консервативную тестовую стратегию для Hyperliquid Testnet (малое плечо 1x–3x, ограничение размера позиции, обязательный stop-loss, интервал цикла 5–15 мин, лимит одновременных позиций).
- [ ] Проверить кодовые риск-ограничения в `trader/auto_trader_risk.go` и `manager/trader_manager.go`. При необходимости усилить детерминированные лимиты в Go-коде (hard cap на плечо, дневной лимит просадки с latching kill switch, запрет ордера без stop-loss — по принципам из `~/Documents/hyperliquid-trade/hltrade/risk/engine.py`), чтобы LLM не могла обойти риск-менеджмент через промпт.
- [ ] Если нужны дополнительные источники информации для агента (новости крипто/макро, RSS, ончейн/киты, ликвидации, X/Telegram-алерты) — спроектировать и встроить их в `market/` или как внешний data-provider до передачи контекста в LLM.

### Этап D — Testnet-прогон и проверка исполнения (задача агента №3)
- [ ] Проверить первый реальный тестовый цикл на Hyperliquid Testnet:
  - подтвердить, что `CheckTradingAuthorization()` проходит на `api.hyperliquid-testnet.xyz`;
  - подтвердить, что ордера (entry + SL/TP + close) исполняются без ошибок с `defaultBuilder = nil`;
  - сверить отображение позиций, баланса, PnL и decision logs в UI и SQLite.
- [ ] Запустить тестовый прогон Autopilot на Testnet на 7–14 дней и по итогам собрать отчёт: количество сделок, net PnL после комиссий/funding, max drawdown, ошибки исполнения, качество решений LLM.
- [ ] Решение о переходе на Mainnet принимать только после положительного и стабильного Testnet-отчёта и явного одобрения владельца.

---

## 5. Как собирать, тестировать и деплоить

На Mac локально стоит Go 1.20 (проекту нужен Go 1.26.10), а локальный Colima VM на 2026-11-25 имел переполненный 20 GB диск. Поэтому **сборку и Go-тесты удобно выполнять в Docker на `vps-apds`** (там Go 1.26 в Dockerfile и >40 GB свободно).

### Проверка Go-тестов на VPS
```bash
ssh vps-apds 'cd /home/administrator/nofx && \
  docker build --target backend-builder -f docker/Dockerfile.backend -t nofx-backend-builder . && \
  docker run --rm nofx-backend-builder sh -c "CGO_ENABLED=1 CGO_CFLAGS=\"-D_LARGEFILE64_SOURCE\" go test -count=1 ./trader/hyperliquid/... ./api/... ./manager/..." && \
  docker rmi nofx-backend-builder'
```

### Деплой изменений на VPS (после `git push origin dev`)
```bash
ssh vps-apds 'cd /home/administrator/nofx && \
  git pull --ff-only origin dev && \
  docker compose up -d --build && \
  docker compose ps'
```

### Проверка статуса и логов на VPS
```bash
ssh vps-apds 'cd /home/administrator/nofx && docker compose ps && docker compose logs --tail=50 nofx'
```

### Обновление из upstream (осторожно, сохраняя наш форк-патч)
```bash
git fetch upstream
git rebase upstream/dev   # проверить, что defaultBuilder = nil и docker-compose.yml сохранились
```
