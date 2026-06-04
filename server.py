"""
Arc Testnet MCP Server

Exposes Circle's Arc testnet as MCP tools so a Claude Code agent (or any MCP client)
can operate on Arc without hand-rolling JSON-RPC. Arc is an EVM-compatible Layer-1
where USDC is the native gas token.

Network (Arc Testnet):
  RPC:      https://rpc.testnet.arc.network
  Chain ID: 5042002
  Explorer: https://testnet.arcscan.app  (Blockscout)
  Gas:      USDC (native, no ETH). Faucet: https://faucet.circle.com

Tools:
  arc_network_info         network config and token addresses
  arc_block_number         latest block height
  arc_gas_price            current gas price (in USDC terms)
  arc_get_balance          native USDC gas balance of an address
  arc_get_token_balance    ERC-20 balance (USDC, EURC, or any token) of an address
  arc_get_transaction      transaction details and receipt by hash
  arc_recent_transactions  recent transactions for an address (via explorer)
  arc_send_usdc            send native USDC on testnet (needs ARC_PRIVATE_KEY)
  arc_faucet_info          where to get testnet USDC
"""
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

RPC_URL = os.getenv("ARC_TESTNET_RPC_URL", "https://rpc.testnet.arc.network")
CHAIN_ID = 5042002
EXPLORER = "https://testnet.arcscan.app"
EXPLORER_API = os.getenv("ARC_EXPLORER_API", "https://testnet.arcscan.app/api")
FAUCET = "https://faucet.circle.com"

# Native gas token is USDC. ERC-20 USDC uses 6 decimals, the native unit uses 18.
USDC_ADDRESS = "0x3600000000000000000000000000000000000000"
EURC_ADDRESS = "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a"
NATIVE_DECIMALS = 18

KNOWN_TOKENS = {
    "USDC": (USDC_ADDRESS, 6),
    "EURC": (EURC_ADDRESS, 6),
}

mcp = FastMCP("arc-testnet")


def _rpc(method: str, params: list) -> object:
    """Single Ethereum JSON-RPC call against the Arc testnet."""
    with httpx.Client(timeout=20.0) as client:
        r = client.post(RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"RPC error on {method}: {data['error']}")
        return data["result"]


def _hex_to_int(h: str) -> int:
    return int(h, 16) if isinstance(h, str) else int(h)


# ============================================================
# NETWORK
# ============================================================

@mcp.tool()
def arc_network_info() -> dict:
    """Return Arc testnet configuration: RPC, chain id, explorer, gas token, and the
    USDC / EURC token addresses. Use this first to confirm you are on the right network."""
    return {
        "network": "Arc Testnet",
        "rpc_url": RPC_URL,
        "chain_id": CHAIN_ID,
        "explorer": EXPLORER,
        "native_gas_token": "USDC",
        "faucet": FAUCET,
        "tokens": {
            "USDC": {"address": USDC_ADDRESS, "erc20_decimals": 6, "native_decimals": NATIVE_DECIMALS},
            "EURC": {"address": EURC_ADDRESS, "erc20_decimals": 6},
        },
        "evm_compatible": True,
    }


@mcp.tool()
def arc_block_number() -> dict:
    """Latest block height on Arc testnet."""
    bn = _hex_to_int(_rpc("eth_blockNumber", []))
    return {"block_number": bn}


@mcp.tool()
def arc_gas_price() -> dict:
    """Current gas price on Arc testnet. Gas is paid in USDC, so the value is returned
    both in raw wei (18 decimals) and in USDC."""
    wei = _hex_to_int(_rpc("eth_gasPrice", []))
    return {"gas_price_wei": wei, "gas_price_usdc": wei / 10**NATIVE_DECIMALS}


# ============================================================
# BALANCES
# ============================================================

@mcp.tool()
def arc_get_balance(address: str) -> dict:
    """Native USDC gas balance of an address (USDC is the native coin on Arc).

    Args:
        address: 0x-prefixed account address
    """
    wei = _hex_to_int(_rpc("eth_getBalance", [address, "latest"]))
    return {"address": address, "usdc": wei / 10**NATIVE_DECIMALS, "wei": wei}


@mcp.tool()
def arc_get_token_balance(address: str, token: str = "USDC") -> dict:
    """ERC-20 token balance of an address. Pass a known symbol (USDC, EURC) or a raw
    0x token contract address.

    Args:
        address: 0x-prefixed account address to check
        token: "USDC", "EURC", or a 0x token contract address (default USDC)
    """
    if token.upper() in KNOWN_TOKENS:
        token_addr, decimals = KNOWN_TOKENS[token.upper()]
    else:
        token_addr, decimals = token, None
    # balanceOf(address) selector 0x70a08231 + 32-byte padded address
    data = "0x70a08231" + address.lower().replace("0x", "").rjust(64, "0")
    raw = _rpc("eth_call", [{"to": token_addr, "data": data}, "latest"])
    bal = _hex_to_int(raw)
    if decimals is None:
        # try to read token decimals() (selector 0x313ce567)
        try:
            decimals = _hex_to_int(_rpc("eth_call", [{"to": token_addr, "data": "0x313ce567"}, "latest"]))
        except Exception:
            decimals = 18
    return {"address": address, "token": token, "balance": bal / 10**decimals, "raw": bal, "decimals": decimals}


# ============================================================
# TRANSACTIONS
# ============================================================

@mcp.tool()
def arc_get_transaction(tx_hash: str) -> dict:
    """Transaction details and receipt (status, gas used, logs) for a tx hash."""
    tx = _rpc("eth_getTransactionByHash", [tx_hash])
    receipt = _rpc("eth_getTransactionReceipt", [tx_hash])
    out = {"hash": tx_hash, "explorer": f"{EXPLORER}/tx/{tx_hash}", "transaction": tx, "receipt": receipt}
    if receipt:
        out["status"] = "success" if _hex_to_int(receipt.get("status", "0x0")) == 1 else "failed"
    else:
        out["status"] = "pending_or_unknown"
    return out


@mcp.tool()
def arc_recent_transactions(address: str, limit: int = 10) -> dict:
    """Recent transactions for an address, fetched from the Arc testnet explorer.

    Args:
        address: 0x-prefixed account address
        limit: max transactions to return (default 10)
    """
    with httpx.Client(timeout=20.0) as client:
        r = client.get(EXPLORER_API, params={
            "module": "account", "action": "txlist", "address": address,
            "sort": "desc", "page": 1, "offset": limit,
        })
        r.raise_for_status()
        data = r.json()
    txs = data.get("result", []) if isinstance(data.get("result"), list) else []
    slim = [{
        "hash": t.get("hash"),
        "from": t.get("from"),
        "to": t.get("to"),
        "value_usdc": int(t.get("value", "0")) / 10**NATIVE_DECIMALS if str(t.get("value", "0")).isdigit() else t.get("value"),
        "block": t.get("blockNumber"),
        "timestamp": t.get("timeStamp"),
        "ok": t.get("isError") == "0",
    } for t in txs[:limit]]
    return {"address": address, "count": len(slim), "transactions": slim}


# ============================================================
# SENDING (write, needs a key)
# ============================================================

@mcp.tool()
def arc_send_usdc(to: str, amount: float, gas_limit: int = 21000) -> dict:
    """Send native USDC on Arc testnet. Requires ARC_PRIVATE_KEY in the environment.

    This is a TESTNET helper. The key is read from the environment, never passed as an
    argument. Fund the sender first via the faucet.

    Args:
        to: 0x-prefixed recipient address
        amount: amount of USDC to send (e.g. 1.5)
        gas_limit: gas units (default 21000 for a plain transfer)
    """
    key = os.getenv("ARC_PRIVATE_KEY")
    if not key:
        return {"ok": False, "error": "ARC_PRIVATE_KEY not set. Set it in the environment to enable sending."}
    try:
        from eth_account import Account
    except ImportError:
        return {"ok": False, "error": "eth-account not installed. Run: pip install eth-account"}

    from eth_utils import to_checksum_address

    acct = Account.from_key(key)
    nonce = _hex_to_int(_rpc("eth_getTransactionCount", [acct.address, "pending"]))
    value = int(amount * 10**NATIVE_DECIMALS)
    # Arc uses EIP-1559 (type 2) with a 20 Gwei minimum base fee.
    try:
        base = _hex_to_int(_rpc("eth_getBlockByNumber", ["latest", False]).get("baseFeePerGas", "0x0"))
    except Exception:
        base = 0
    base = max(base, 20 * 10**9)
    try:
        priority = _hex_to_int(_rpc("eth_maxPriorityFeePerGas", [])) or 10**9
    except Exception:
        priority = 10**9
    tx = {
        "to": to_checksum_address(to),
        "value": value,
        "gas": gas_limit,
        "maxFeePerGas": base * 2 + priority,
        "maxPriorityFeePerGas": priority,
        "nonce": nonce,
        "chainId": CHAIN_ID,
        "type": 2,
    }
    signed = Account.sign_transaction(tx, key)
    raw = signed.raw_transaction.hex()
    if not raw.startswith("0x"):
        raw = "0x" + raw
    tx_hash = _rpc("eth_sendRawTransaction", [raw])
    return {
        "ok": True,
        "tx_hash": tx_hash,
        "from": acct.address,
        "to": to,
        "amount_usdc": amount,
        "explorer": f"{EXPLORER}/tx/{tx_hash}",
    }


@mcp.tool()
def arc_faucet_info() -> dict:
    """Where to get testnet USDC to fund an Arc testnet address."""
    return {"faucet": FAUCET, "note": "Request testnet USDC before sending transactions. USDC is the gas token on Arc."}


if __name__ == "__main__":
    mcp.run()
