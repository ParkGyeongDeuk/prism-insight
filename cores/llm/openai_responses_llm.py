"""
OpenAI Responses API LLM for mcp-agent trading agents.

Replaces Chat Completions (client.chat.completions.create) with the Responses API
(client.responses.create). It uses previous_response_id when supported and falls
back to locally accumulated history for stateless OAuth proxy endpoints.

Drop-in replacement: swap attach_llm(OpenAIAugmentedLLM) →
                               attach_llm(OpenAIResponsesLLM)
"""
import json
from typing import List, Optional

from openai import AsyncOpenAI, BadRequestError
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    EmbeddedResource,
    TextContent,
    TextResourceContents,
)

from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


class OpenAIResponsesLLM(OpenAIAugmentedLLM):
    """
    OpenAIAugmentedLLM variant that drives the agentic tool-call loop via the
    Responses API instead of Chat Completions.

    Token efficiency improvement: stateful providers receive only new tool results
    after the first turn. Stateless providers receive locally accumulated history
    so tool-call context remains intact.
    """

    async def generate_str(
        self,
        message,
        request_params: Optional[RequestParams] = None,
    ) -> str:
        params = self.get_request_params(request_params)
        model = await self.select_model(params)

        # Collect MCP tools in Responses API format (flat, no "function" wrapper)
        tools_result = await self.agent.list_tools(tool_filter=params.tool_filter)
        tools: Optional[List] = (
            [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                }
                for tool in tools_result.tools
            ]
            or None
        )

        # Build initial input (developer system prompt + user message)
        input_items: List = []
        system_prompt = self.instruction or params.systemPrompt
        if system_prompt:
            input_items.append({"role": "developer", "content": system_prompt})

        if isinstance(message, str):
            input_items.append({"role": "user", "content": message})
        elif isinstance(message, list):
            for m in message:
                if isinstance(m, str):
                    input_items.append({"role": "user", "content": m})
                elif isinstance(m, dict):
                    input_items.append(m)
        else:
            input_items.append({"role": "user", "content": str(message)})

        # Build kwargs shared across all iterations
        base_kwargs: dict = {"model": model, "tools": tools}

        if self._reasoning(model):
            effort = params.reasoning_effort or self._reasoning_effort
            if effort and effort != "none":
                # Responses API uses reasoning={"effort": ...} instead of reasoning_effort=
                base_kwargs["reasoning"] = {"effort": effort}
            base_kwargs["max_output_tokens"] = params.maxTokens
        else:
            base_kwargs["max_output_tokens"] = params.maxTokens

        if params.stopSequences:
            base_kwargs["stop"] = params.stopSequences

        provider_config = self.get_provider_config(self.context)
        if provider_config is None:
            raise RuntimeError("OpenAI provider config is missing from mcp_agent.config.yaml")

        previous_response_id: Optional[str] = None
        use_previous_response_id = True
        conversation_items = list(input_items)
        final_text = ""

        async with AsyncOpenAI(
            api_key=provider_config.api_key,
            base_url=provider_config.base_url,
        ) as client:
            for i in range(params.max_iterations):
                self._log_chat_progress(chat_turn=i, model=model)

                call_kwargs = {
                    **base_kwargs,
                    "input": (
                        input_items
                        if use_previous_response_id
                        else conversation_items
                    ),
                }
                if previous_response_id and use_previous_response_id:
                    call_kwargs["previous_response_id"] = previous_response_id

                try:
                    response = await client.responses.create(**call_kwargs)  # type: ignore[attr-defined]
                except BadRequestError:
                    if not previous_response_id or not use_previous_response_id:
                        raise

                    # The ChatGPT OAuth Codex endpoint uses store=False and does
                    # not support previous_response_id. Retry with the complete
                    # local conversation while preserving the efficient stateful
                    # path for providers that support it.
                    use_previous_response_id = False
                    call_kwargs.pop("previous_response_id", None)
                    call_kwargs["input"] = conversation_items
                    response = await client.responses.create(**call_kwargs)  # type: ignore[attr-defined]
                previous_response_id = response.id

                # Separate text content and function calls from output items
                text_parts: List[str] = []
                function_calls = []
                for item in response.output:
                    if item.type == "message":
                        for part in item.content:
                            if hasattr(part, "text"):
                                text_parts.append(part.text)
                    elif item.type == "function_call":
                        function_calls.append(item)

                if not function_calls:
                    final_text = "\n".join(text_parts)
                    break

                # Execute all tool calls via MCP and collect results
                tool_result_items = []
                assistant_items = []
                if text_parts:
                    assistant_items.append(
                        {"role": "assistant", "content": "\n".join(text_parts)}
                    )
                for fc in function_calls:
                    assistant_items.append(
                        {
                            "type": "function_call",
                            "name": fc.name,
                            "arguments": fc.arguments,
                            "call_id": fc.call_id,
                        }
                    )
                    result_str = await self._call_mcp_tool(
                        name=fc.name,
                        arguments=fc.arguments,
                        call_id=fc.call_id,
                    )
                    tool_result_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": fc.call_id,
                            "output": result_str,
                        }
                    )

                conversation_items.extend(assistant_items)
                conversation_items.extend(tool_result_items)

                # Stateful providers need only tool results. The fallback uses
                # conversation_items assembled above.
                input_items = tool_result_items

        self._log_chat_finished(model=model)
        return final_text

    async def _call_mcp_tool(self, name: str, arguments: str, call_id: str) -> str:
        """Execute one MCP tool call and return the result as a plain string."""
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}

        request = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name=name, arguments=args),
        )
        result = await self.call_tool(request=request, tool_call_id=call_id)

        parts = []
        for content in result.content:
            if isinstance(content, TextContent):
                parts.append(content.text)
            elif isinstance(content, EmbeddedResource) and isinstance(
                content.resource, TextResourceContents
            ):
                parts.append(content.resource.text)
        return "\n".join(parts) if parts else ""
