#!/usr/bin/env python3
"""Safely register a Hyperliquid Testnet Agent Wallet account in NOFX.

Uses only Python stdlib. Reads credentials interactively (hidden via getpass),
verifies the wallet on Hyperliquid Testnet public /info endpoint, and calls
POST /api/exchanges with testnet=true so Autopilot can run on Testnet.
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
EVM_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
HEX_KEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")


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
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc


def check_testnet_wallet(wallet_addr: str) -> None:
    try:
        state = http_json(
            TESTNET_INFO_URL,
            {"type": "clearinghouseState", "user": wallet_addr},
        )
        margin = state.get("marginSummary") or state.get("crossMarginSummary") or {}
        equity = margin.get("accountValue", "0")
        agents = http_json(
            TESTNET_INFO_URL,
            {"type": "extraAgents", "user": wallet_addr},
        )
        agent_count = len(agents) if isinstance(agents, list) else 0
        print(
            f"[OK] Hyperliquid Testnet wallet found: equity=${equity}, "
            f"approved API agents={agent_count}"
        )
        if float(equity or 0) <= 0:
            print(
                "[WARN] Testnet equity is $0. Claim free testnet USDC at "
                "https://app.hyperliquid-testnet.xyz/drip"
            )
        if agent_count == 0:
            print(
                "[WARN] No approved API agents found on-chain for this wallet yet. "
                "Make sure you created & authorized the agent at "
                "https://app.hyperliquid-testnet.xyz/API"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Could not pre-check Hyperliquid Testnet API: {exc}")


def main() -> int:
    print("=== Add Hyperliquid Testnet account to NOFX ===\n")

    base_url = (
        input(f"NOFX URL [{DEFAULT_NOFX_URL}]: ").strip() or DEFAULT_NOFX_URL
    ).rstrip("/")

    # Quick health check
    try:
        health = http_json(f"{base_url}/api/health")
        if health.get("status") != "ok":
            print(f"[ERROR] Unexpected /api/health response: {health}")
            return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}")
        print(
            "Hint: start the SSH tunnel first:\n"
            "  ssh -N -L 3090:127.0.0.1:3090 vps-apds"
        )
        return 1

    email = input("NOFX account email: ").strip()
    password = getpass.getpass("NOFX account password: ")
    if not email or not password:
        print("[ERROR] Email and password are required.")
        return 1

    try:
        login_resp = http_json(
            f"{base_url}/api/login",
            {"email": email, "password": password},
        )
        token = login_resp.get("token", "")
        if not token:
            print(f"[ERROR] Login did not return a token: {login_resp}")
            return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Login failed: {exc}")
        return 1
    print("[OK] Logged in to NOFX.")

    account_name = (
        input("Account label in NOFX [Hyperliquid Testnet]: ").strip()
        or "Hyperliquid Testnet"
    )
    wallet_addr = input("Main Hyperliquid wallet address (0x...): ").strip()
    if not EVM_ADDR_RE.match(wallet_addr):
        print("[ERROR] Invalid EVM address format (expected 0x + 40 hex chars).")
        return 1

    agent_key_raw = getpass.getpass(
        "Hyperliquid Testnet Agent Wallet private key (input hidden): "
    ).strip()
    agent_key = agent_key_raw[2:] if agent_key_raw.lower().startswith("0x") else agent_key_raw
    if not HEX_KEY_RE.match(agent_key):
        print("[ERROR] Invalid private key format (expected 64 hex chars, with or without 0x).")
        return 1

    check_testnet_wallet(wallet_addr)

    payload = {
        "exchange_type": "hyperliquid",
        "account_name": account_name,
        "enabled": True,
        "api_key": agent_key,
        "hyperliquid_wallet_addr": wallet_addr,
        "hyperliquid_unified_account": True,
        "hyperliquid_builder_approved": True,
        "testnet": True,
    }

    try:
        created = http_json(f"{base_url}/api/exchanges", payload, token=token)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Failed to create Hyperliquid Testnet exchange: {exc}")
        return 1

    print(f"[OK] Saved exchange in NOFX: {json.dumps(created, ensure_ascii=False)}")

    try:
        exchanges = http_json(f"{base_url}/api/exchanges", token=token)
        hl_testnet = [
            e
            for e in exchanges
            if isinstance(e, dict)
            and e.get("exchange_type") == "hyperliquid"
            and e.get("testnet") is True
        ]
        print(f"[OK] Verified Hyperliquid Testnet accounts in NOFX: {len(hl_testnet)}")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Could not verify exchange list: {exc}")

    print("\nDone! Refresh http://127.0.0.1:3090 -> Autopilot and select this Testnet account.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
