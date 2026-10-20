"""Opt-in Base Sepolia x402 MCP server for bounded payment-flow testing.

This server is deliberately separate from the free prototype endpoint. It has
no mainnet configuration path and its fixed price cannot exceed $0.01 USDC.
"""
import asyncio
import json
import os

from mcp.server.fastmcp import FastMCP
from x402 import x402ResourceServer
from x402.http import FacilitatorConfig, HTTPFacilitatorClient
from x402.mcp import create_payment_wrapper
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.schemas import ResourceConfig, ResourceInfo

from app import diagnose

NETWORK = "eip155:84532"  # Base Sepolia only
PRICE = "$0.01"  # Fixed ceiling for this integration test
PORT = 8001


async def build_server(pay_to: str) -> FastMCP:
    if os.getenv("AGENTRESCUE_X402_TEST_MODE") != "1":
        raise RuntimeError("Set AGENTRESCUE_X402_TEST_MODE=1 to enable testnet payments")
    if not pay_to.startswith("0x") or len(pay_to) != 42:
        raise ValueError("AGENTRESCUE_X402_PAY_TO must be an EVM address")

    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url="https://x402.org/facilitator"))
    resource_server = x402ResourceServer(facilitator)
    resource_server.register(NETWORK, ExactEvmServerScheme())
    resource_server.initialize()
    accepts = resource_server.build_payment_requirements(
        ResourceConfig(
            scheme="exact",
            network=NETWORK,
            payTo=pay_to,
            price=PRICE,
            extra={"name": "USDC", "version": "2"},
        )
    )
    paid = create_payment_wrapper(
        resource_server,
        accepts=accepts,
        resource=ResourceInfo(
            url="mcp://tool/diagnose_failure",
            description="Structured HTTP, API, and MCP failure diagnosis",
            mime_type="application/json",
        ),
    )

    server = FastMCP("AgentRescue x402 test", host="127.0.0.1", port=PORT)

    @server.tool(name="diagnose_failure", description="Diagnose an HTTP/API/MCP failure ($0.01 test USDC on Base Sepolia)")
    @paid
    async def diagnose_failure(error: str, system: str = "mcp") -> str:
        result = diagnose(error, system)
        result["payment"] = {"mode": "base-sepolia-testnet", "charged": True}
        return json.dumps(result, separators=(",", ":"))

    return server


async def main() -> None:
    pay_to = os.getenv("AGENTRESCUE_X402_PAY_TO", "")
    server = await build_server(pay_to)
    await server.run_streamable_http_async()


if __name__ == "__main__":
    asyncio.run(main())
