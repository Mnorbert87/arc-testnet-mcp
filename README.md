# arc-testnet-mcp

An [MCP](https://modelcontextprotocol.io) server for Circle's **Arc** testnet. It lets a
Claude Code agent (or any MCP client) operate on Arc without hand-rolling JSON-RPC:
check balances, read transactions, watch an address, and send testnet USDC.

Arc is an EVM-compatible Layer-1 where **USDC is the native gas token**, built for
stablecoin payments, FX, and capital markets. This server wraps the Arc testnet RPC and
explorer as typed tools, so an agent calls `arc_get_balance` instead of constructing an `eth_getBalance` request by hand.

## Why

Circle ships Arc with first-class Claude Code support. This server pushes that further:
it gives an agent a clean, typed surface to read and write Arc state, so you can build
agent-driven onchain automation (payments, monitoring, balance sweeps) on USDC rails.

## Network (Arc Testnet)

| | |
|---|---|
| RPC | `https://rpc.testnet.arc.network` |
| Chain ID | `5042002` |
| Explorer | https://testnet.arcscan.app |
| Gas token | USDC (native, no ETH) |
| Faucet | https://faucet.circle.com |
| USDC | `0x3600000000000000000000000000000000000000` |
| EURC | `0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a` |

## Tools

| Tool | What it does |
|------|--------------|
| `arc_network_info` | Network config and token addresses (call first) |
| `arc_block_number` | Latest block height |
| `arc_gas_price` | Current gas price, in USDC terms |
| `arc_get_balance` | Native USDC gas balance of an address |
| `arc_get_token_balance` | ERC-20 balance (USDC, EURC, or any token) |
| `arc_get_transaction` | Transaction details and receipt by hash |
| `arc_recent_transactions` | Recent transactions for an address (via explorer) |
| `arc_send_usdc` | Send native USDC on testnet (needs a key) |
| `arc_faucet_info` | Where to get testnet USDC |

Read-only tools need no key. Only `arc_send_usdc` needs `ARC_PRIVATE_KEY`.

## Configure

```bash
cp .env.example .env
# ARC_TESTNET_RPC_URL is preset to the public endpoint.
# Set ARC_PRIVATE_KEY only if you want the agent to SEND. Use a throwaway testnet key.
```

Fund the sender first at https://faucet.circle.com (USDC is the gas token).

## Run

With [uv](https://docs.astral.sh/uv/):

```bash
uv run server.py
```

Register it with an MCP client (Claude Code / Claude Desktop):

```json
{
  "mcpServers": {
    "arc-testnet": {
      "command": "uv",
      "args": ["--directory", "/path/to/arc-testnet-mcp", "run", "server.py"],
      "env": {
        "ARC_TESTNET_RPC_URL": "https://rpc.testnet.arc.network"
      }
    }
  }
}
```

Then ask your agent things like "what is my USDC balance on Arc", "show the last 5
transactions for 0x...", or "send 1 testnet USDC to 0x...".

## Safety

- The private key is read from the environment, never passed as a tool argument and
  never logged.
- This targets **testnet**. Use a throwaway key. Do not point it at mainnet keys.
- Verify `chain_id` is `5042002` (via `arc_network_info`) before sending.

## License

MIT, see [LICENSE](LICENSE).
