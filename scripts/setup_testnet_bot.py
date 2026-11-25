#!/usr/bin/env python3
"""All-in-one interactive setup for NOFX on Hyperliquid Testnet.

Configures:
  1. Direct AI model API key (OpenAI / DeepSeek / OpenRouter / Gemini / Claude / Custom)
  2. Hyperliquid Testnet Agent Wallet (testnet=true, no builder fee)
  3. Autopilot Trader bound to the conservative BTC/ETH/SOL strategy
  4. Optional immediate Start

Stdlib Python only. Never logs or prints secrets.
"""

from __future__ import annotations

import getpass
import json
import re
import sys
import urllib.error
import urllib.request

TESTNET_INFO_URL = "https://api.hyperliquid-testnet.xyz/info"
DEFAULT_NOFX_URL = "http://127.0.0.1:3090"
DEFAULT_EMAIL = "mns.nicholas@gmail.com"
PREFERRED_STRATEGY = "Hyperliquid Testnet Conservative (BTC/ETH/SOL)"

EVM_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
HEX_KEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")

PROVIDERS = {
    "1": ("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4.1-mini"),
    "2": ("deepseek", "DeepSeek", "https://api.deepseek.com", "deepseek-chat"),
    "3": ("custom", "OpenRouter", "https://openrouter.ai/api/v1", "openai/gpt-4.1-mini"),
    "4": ("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    "5": ("claude", "Anthropic Claude", "", "claude-sonnet-4-5"),
    "6": ("custom", "Custom OpenAI-compatible", "", ""),
}


def http_json(
    url: str,
    payload: dict | None = None,
    token: str | None = None,
    method: str | None = None,
) -> dict | list:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method or ("POST" if payload is not None else "GET"),
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc


def check_testnet_wallet(wallet_addr: str) -> float:
    equity = 1000.0
    try:
        state = http_json(
            TESTNET_INFO_URL,
            {"type": "clearinghouseState", "user": wallet_addr},
        )
        margin = state.get("marginSummary") or state.get("crossMarginSummary") or {}
        equity = float(margin.get("accountValue", "0") or 0)
        agents = http_json(
            TESTNET_INFO_URL,
            {"type": "extraAgents", "user": wallet_addr},
        )
        agent_count = len(agents) if isinstance(agents, list) else 0
        print(
            f"[OK] Hyperliquid Testnet wallet: equity=${equity:.2f}, "
            f"approved API agents={agent_count}"
        )
        if equity <= 0:
            print(
                "[WARN] Equity is $0. Claim free 1000 testnet USDC at:\n"
                "       https://app.hyperliquid-testnet.xyz/drip"
            )
            equity = 1000.0
        if agent_count == 0:
            print(
                "[WARN] No approved API agents found on Hyperliquid Testnet yet.\n"
                "       Create & authorize one at: https://app.hyperliquid-testnet.xyz/API"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Could not query Hyperliquid Testnet public API: {exc}")
    return equity


def main() -> int:
    print("=== NOFX All-in-One Hyperliquid Testnet Setup ===\n")

    base_url = (
        input(f"NOFX URL [{DEFAULT_NOFX_URL}]: ").strip() or DEFAULT_NOFX_URL
    ).rstrip("/")

    try:
        health = http_json(f"{base_url}/api/health")
        if health.get("status") != "ok":
            print(f"[ERROR] Unexpected /api/health: {health}")
            return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}")
        print("Start the SSH tunnel first:\n  ssh -N -L 3090:127.0.0.1:3090 vps-apds")
        return 1

    email = input(f"NOFX email [{DEFAULT_EMAIL}]: ").strip() or DEFAULT_EMAIL
    password = getpass.getpass("NOFX password: ")
    if not password:
        print("[ERROR] Password is required.")
        return 1

    login = http_json(f"{base_url}/api/login", {"email": email, "password": password})
    token = login.get("token", "")
    user_id = login.get("user_id", "")
    if not token:
        print(f"[ERROR] Login failed: {login}")
        return 1
    print("[OK] Logged in to NOFX.\n")

    # 1. AI Model
    print("--- Step 1/3: AI Model (standard API key, no Claw402 needed) ---")
    for k, (_, label, _, default_model) in PROVIDERS.items():
        hint = f" (default: {default_model})" if default_model else ""
        print(f"  {k}) {label}{hint}")
    choice = input("Choose provider [1]: ").strip() or "1"
    if choice not in PROVIDERS:
        print("[ERROR] Invalid choice.")
        return 1
    provider_id, label, default_url, default_model = PROVIDERS[choice]

    custom_url = default_url
    if provider_id == "custom":
        prompt_url = f"API Base URL [{default_url}]: " if default_url else "API Base URL (e.g. https://openrouter.ai/api/v1): "
        custom_url = input(prompt_url).strip() or default_url
        if not custom_url:
            print("[ERROR] API Base URL is required for custom provider.")
            return 1

    model_name = (
        input(f"Model name [{default_model}]: ").strip() or default_model
    )
    api_key = getpass.getpass(f"{label} API key (hidden): ").strip()
    if not api_key:
        print("[ERROR] API key is required.")
        return 1

    http_json(
        f"{base_url}/api/models",
        {
            "models": {
                provider_id: {
                    "enabled": True,
                    "api_key": api_key,
                    "custom_api_url": custom_url,
                    "custom_model_name": model_name,
                }
            }
        },
        token=token,
        method="PUT",
    )

    models = http_json(f"{base_url}/api/models", token=token)
    ai_model_id = ""
    if isinstance(models, list):
        for m in models:
            if m.get("provider") == provider_id and m.get("enabled"):
                ai_model_id = m.get("id", "")
                break
    if not ai_model_id:
        ai_model_id = f"{user_id}_{provider_id}" if user_id else provider_id
    print(f"[OK] AI model saved: id={ai_model_id}, model={model_name}\n")

    # 2. Hyperliquid Testnet Exchange
    print("--- Step 2/3: Hyperliquid Testnet Exchange ---")
    existing_exchanges = http_json(f"{base_url}/api/exchanges", token=token)
    existing_hl = [
        e
        for e in (existing_exchanges if isinstance(existing_exchanges, list) else [])
        if e.get("exchange_type") == "hyperliquid" and e.get("testnet") is True
    ]

    exchange_id = ""
    equity = 1000.0
    if existing_hl:
        first = existing_hl[0]
        reuse = (
            input(
                f"Found existing Hyperliquid Testnet ({first.get('account_name')}, "
                f"{first.get('hyperliquidWalletAddr')}). Reuse it? [Y/n]: "
            )
            .strip()
            .lower()
        )
        if reuse in ("", "y", "yes"):
            exchange_id = first["id"]
            equity = check_testnet_wallet(first.get("hyperliquidWalletAddr", ""))

    if not exchange_id:
        wallet_addr = input("Main Hyperliquid wallet address (0x...): ").strip()
        if not EVM_ADDR_RE.match(wallet_addr):
            print("[ERROR] Invalid EVM address (expected 0x + 40 hex chars).")
            return 1
        agent_key_raw = getpass.getpass(
            "Hyperliquid Testnet Agent Wallet private key (hidden): "
        ).strip()
        agent_key = (
            agent_key_raw[2:]
            if agent_key_raw.lower().startswith("0x")
            else agent_key_raw
        )
        if not HEX_KEY_RE.match(agent_key):
            print("[ERROR] Invalid private key (expected 64 hex chars).")
            return 1

        equity = check_testnet_wallet(wallet_addr)
        created_ex = http_json(
            f"{base_url}/api/exchanges",
            {
                "exchange_type": "hyperliquid",
                "account_name": "Hyperliquid Testnet",
                "enabled": True,
                "api_key": agent_key,
                "hyperliquid_wallet_addr": wallet_addr,
                "hyperliquid_unified_account": True,
                "hyperliquid_builder_approved": True,
                "testnet": True,
            },
            token=token,
        )
        exchange_id = created_ex.get("id", "")
        if not exchange_id:
            # Fallback: fetch list
            refreshed = http_json(f"{base_url}/api/exchanges", token=token)
            for e in refreshed if isinstance(refreshed, list) else []:
                if e.get("exchange_type") == "hyperliquid" and e.get("testnet") is True:
                    exchange_id = e.get("id", "")
                    break
        print(f"[OK] Saved Hyperliquid Testnet exchange: id={exchange_id}\n")

    # 3. Strategy & Autopilot Trader
    print("--- Step 3/3: Create Autopilot Trader ---")
    strategies = http_json(f"{base_url}/api/strategies", token=token)
    strategy_list = (
        strategies.get("strategies", [])
        if isinstance(strategies, dict)
        else (strategies if isinstance(strategies, list) else [])
    )
    strategy_id = ""
    for s in strategy_list:
        if s.get("name") == PREFERRED_STRATEGY:
            strategy_id = s.get("id", "")
            break
    if not strategy_id and strategy_list:
        strategy_id = strategy_list[0].get("id", "")
    print(f"[OK] Selected strategy: {PREFERRED_STRATEGY} ({strategy_id})")

    trader_name = (
        input("Trader name [HL Testnet AI Bot]: ").strip() or "HL Testnet AI Bot"
    )
    created_trader = http_json(
        f"{base_url}/api/traders",
        {
            "name": trader_name,
            "ai_model_id": ai_model_id,
            "exchange_id": exchange_id,
            "strategy_id": strategy_id,
            "initial_balance": round(max(equity, 100.0), 2),
            "scan_interval_minutes": 15,
            "is_cross_margin": True,
            "show_in_competition": False,
            "btc_eth_leverage": 3,
            "altcoin_leverage": 2,
            "trading_symbols": "BTCUSDT,ETHUSDT,SOLUSDT",
        },
        token=token,
    )
    trader_id = (
        created_trader.get("trader_id")
        or created_trader.get("id")
        or (created_trader.get("trader") or {}).get("id", "")
    )
    print(f"[OK] Created trader: id={trader_id}, name={trader_name}")

    start_now = input("\nStart this Testnet bot right now? [Y/n]: ").strip().lower()
    if start_now in ("", "y", "yes") and trader_id:
        res = http_json(
            f"{base_url}/api/traders/{trader_id}/start",
            {},
            token=token,
            method="POST",
        )
        print(f"[OK] Bot started: {json.dumps(res, ensure_ascii=False)}")
    else:
        print("[OK] Bot created (stopped). Start it anytime at http://127.0.0.1:3090/traders")

    print("\nOpen http://127.0.0.1:3090/traders and refresh to watch live decisions!")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
