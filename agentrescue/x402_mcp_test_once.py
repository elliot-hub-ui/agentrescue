"""Perform exactly one capped Base Sepolia payment via the official x402 MCP client.

The test wallet is stored outside the project. A durable sentinel is written
before the payment attempt; rerunning after an uncertain outcome is refused.
"""
import asyncio
from datetime import timedelta
import json
import os
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

from eth_account import Account
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from x402.mcp import create_x402_mcp_client_from_config
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact import ExactEvmClientScheme

NETWORK = "eip155:84532"
USDC_TEST = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
AMOUNT = "10000"  # $0.01 USDC (6 decimals)
WALLET_FILE = Path(os.environ.get("AGENTRESCUE_TEST_WALLET_FILE", "/private/tmp/agentrescue-test-wallet.json"))
SENTINEL = Path("/private/tmp/agentrescue-x402-payment-attempted")
URL = "http://127.0.0.1:8001/mcp"


class X402McpSdkAdapter:
    """Adapt the official Python MCP session signature to x402's SDK contract."""

    def __init__(self, session):
        self.session = session

    async def call_tool(self, params, **kwargs):
        timeout = kwargs.get("read_timeout_seconds")
        if isinstance(timeout, (int, float)):
            timeout = timedelta(seconds=timeout)
        result = await self.session.call_tool(
            params["name"],
            params.get("arguments"),
            read_timeout_seconds=timeout,
            meta=params.get("_meta"),
        )
        # MCP Python exposes `meta`; x402 2.25.0 reads `_meta` from the object.
        # Normalize the SDK response shape so its settlement extractor sees it.
        return SimpleNamespace(
            content=result.content,
            isError=result.isError,
            _meta=result.meta,
            structuredContent=result.structuredContent,
        )

    async def list_tools(self):
        return await self.session.list_tools()


async def main() -> None:
    if os.getenv("AGENTRESCUE_X402_TEST_MODE") != "1":
        raise RuntimeError("Refusing to run unless AGENTRESCUE_X402_TEST_MODE=1")
    if SENTINEL.exists():
        raise RuntimeError("A payment was already attempted; inspect Base Sepolia before any further test")
    wallet = json.loads(WALLET_FILE.read_text())
    buyer = Account.from_key(wallet["buyer_private_key"])
    seller = wallet["seller_address"]
    os.environ["AGENTRESCUE_X402_PAY_TO"] = seller

    server_env = os.environ.copy()
    server_env["AGENTRESCUE_X402_PAY_TO"] = seller
    server_log = Path("/private/tmp/agentrescue-x402-server.log")
    log_file = server_log.open("w")
    server = subprocess.Popen(
        [str(Path(__file__).with_name(".venv") / "bin" / "python"), "x402_mcp_server.py"],
        cwd=Path(__file__).parent,
        env=server_env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    try:
        ready = False
        for _ in range(40):
            if server.poll() is not None:
                raise RuntimeError("The local Base Sepolia-only MCP test server exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", 8001), timeout=0.25):
                    ready = True
                    break
            except OSError:
                await asyncio.sleep(0.25)
        if not ready:
            raise RuntimeError("The local Base Sepolia-only MCP test server did not start")
        async with streamablehttp_client(URL, timeout=30, sse_read_timeout=150) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                approval_calls = 0

                def approve_exactly_one(ctx) -> bool:
                    nonlocal approval_calls
                    approval_calls += 1
                    if approval_calls != 1 or ctx.tool_name != "diagnose_failure":
                        return False
                    accepts = ctx.payment_required.accepts
                    return len(accepts) == 1 and all(
                        req.scheme == "exact"
                        and str(req.network) == NETWORK
                        and req.asset.lower() == USDC_TEST.lower()
                        and req.amount == AMOUNT
                        and req.pay_to.lower() == seller.lower()
                        for req in accepts
                    )

                paid = create_x402_mcp_client_from_config(
                    X402McpSdkAdapter(client),
                    {
                        "schemes": [{"network": NETWORK, "client": ExactEvmClientScheme(EthAccountSigner(buyer))}],
                        "auto_payment": True,
                        "on_payment_requested": approve_exactly_one,
                        "max_request_timeout_seconds": 120,
                    },
                )
                # Spend-once guard is durable and written immediately before signing.
                SENTINEL.write_text("one Base Sepolia payment attempt; inspect before retry\n")
                os.chmod(SENTINEL, 0o600)
                result = await paid.call_tool(
                    "diagnose_failure",
                    {"error": "HTTP 429 synthetic recovery test", "system": "http"},
                    read_timeout_seconds=150,
                )
                if not result.payment_made or result.is_error or not result.payment_response:
                    details = {
                        "payment_made": result.payment_made,
                        "is_error": result.is_error,
                        "content": [getattr(item, "text", str(item)) for item in result.content],
                    }
                    raise RuntimeError("x402 call did not return settlement metadata: " + json.dumps(details))
                response = result.payment_response
                transaction = getattr(response, "transaction", None)
                if not transaction and hasattr(response, "model_dump"):
                    transaction = response.model_dump().get("transaction")
                print(json.dumps({"payment_made": True, "network": NETWORK, "amount": AMOUNT, "transaction": transaction}))
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        log_file.close()
        if server.returncode and server_log.exists():
            print("test server log:", server_log.read_text()[-3000:])
        if SENTINEL.exists():
            # Keep the sentinel; it prevents a second payment attempt.
            pass


if __name__ == "__main__":
    asyncio.run(main())
