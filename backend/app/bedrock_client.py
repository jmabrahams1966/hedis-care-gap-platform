"""In-VPC Claude access via AWS Bedrock for KaveraChat AI assist (Feature E).

Bedrock is the *only* inference path — no request leaves the AWS VPC, so member
PHI in a draft prompt never reaches an external LLM provider. Every AI surface
is human-gated (drafts only) and audited; this module is just the transport.

The wire format is the Anthropic Messages API wrapped for Bedrock InvokeModel:
the request body carries `anthropic_version: "bedrock-2023-05-31"` instead of an
HTTP header, and the model id is a Bedrock model / inference-profile id rather
than a first-party alias. The IAM grant lives in infra/modules/ecs (task role,
`bedrock:InvokeModel`).
"""

import asyncio
import json
import logging

import boto3

from .config import settings

logger = logging.getLogger("ai.bedrock")

# Bedrock's own version tag for the Anthropic Messages schema — NOT a model id
# and not the first-party `anthropic-version` header. Fixed string per AWS.
_BEDROCK_ANTHROPIC_VERSION = "bedrock-2023-05-31"


class BedrockClaudeClient:
    """Thin wrapper over Bedrock InvokeModel returning a provider-neutral shape.

    `complete()` runs the blocking boto3 call off the event loop via
    asyncio.to_thread — an LLM turn takes seconds, so blocking the loop would
    stall every other request on the worker.
    """

    def __init__(self, client=None, model: str | None = None) -> None:
        self._client = client
        self.model = model or settings.bedrock_model_id

    def _bedrock(self):
        # Lazily built so importing this module never touches AWS (tests inject
        # a fake client via the constructor; dev never constructs a real one).
        if self._client is None:
            self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        return self._client

    def _invoke_sync(self, body: dict, model: str) -> dict:
        response = self._bedrock().invoke_model(modelId=model, body=json.dumps(body))
        return json.loads(response["body"].read())

    async def complete(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """Return {"text": str, "usage": {"input_tokens": int, "output_tokens": int}}.

        `messages` is a list of {"role", "content"} dicts in Anthropic Messages
        shape. Raises on transport/throttle errors — the caller records the
        failed AiInteraction and surfaces a retryable error to the operator.
        """
        chosen = model or self.model
        body = {
            "anthropic_version": _BEDROCK_ANTHROPIC_VERSION,
            "max_tokens": max_tokens or settings.ai_max_tokens,
            "system": system,
            "messages": messages,
        }
        payload = await asyncio.to_thread(self._invoke_sync, body, chosen)

        text = "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        )
        usage = payload.get("usage", {}) or {}
        return {
            "text": text,
            "usage": {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
        }
