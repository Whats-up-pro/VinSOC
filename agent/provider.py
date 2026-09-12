"""
LLM Provider Adapters

Abstract interface for LLM providers (OpenAI, Gemini, etc.)
so the orchestrator is provider-agnostic.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json


@dataclass
class LLMResponse:
    """Container for LLM response."""
    content: str
    tool_calls: List[Dict[str, Any]]
    raw: Dict[str, Any]


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Implement this interface to add support for different LLM providers.
    """

    @abstractmethod
    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None):
        """Initialize the provider."""
        pass

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            messages: Conversation history
            tools: Optional tool definitions
            system_prompt: Optional system prompt override
            temperature: Sampling temperature

        Returns:
            LLMResponse with content and/or tool calls
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get provider name."""
        pass


class OpenAIProvider(LLMProvider):
    """
    OpenAI GPT provider implementation.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None
    ):
        """
        Initialize OpenAI provider.

        Args:
            model: Model to use (gpt-4o, gpt-4o-mini, gpt-4-turbo)
            api_key: OpenAI API key. Uses env OPENAI_API_KEY if not provided.
        """
        self.model = model
        self.api_key = api_key

        # Import openai here to allow graceful fallback
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)
        except ImportError:
            self.client = None
            print("Warning: OpenAI SDK not installed. Install with: pip install openai")

    def generate(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> LLMResponse:
        """Generate response using OpenAI API."""
        if self.client is None:
            raise RuntimeError("OpenAI client not initialized. Install openai package.")

        # Build messages with system prompt
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        # Call API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=all_messages,
            tools=tools,
            temperature=temperature,
        )

        # Extract content and tool calls
        message = response.choices[0].message
        content = message.content or ""
        tool_calls = []

        if message.tool_calls:
            for call in message.tool_calls:
                tool_calls.append({
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": json.loads(call.function.arguments)
                })

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw=response.model_dump()
        )

    def get_name(self) -> str:
        """Get provider name."""
        return f"OpenAI {self.model}"


class MockProvider(LLMProvider):
    """
    Mock LLM provider for testing.

    Returns predefined responses based on prompts.
    """

    def __init__(
        self,
        model: str = "mock",
        responses: Optional[Dict[str, str]] = None
    ):
        """
        Initialize mock provider.

        Args:
            model: Mock model name
            responses: Dict mapping prompt keywords to responses
        """
        self.model = model
        self.responses = responses or {}
        self.call_history: List[Dict[str, Any]] = []

    def generate(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> LLMResponse:
        """Generate mock response."""
        # Record call
        self.call_history.append({
            "messages": messages,
            "tools": tools,
            "system_prompt": system_prompt,
        })

        # Find matching response
        last_message = messages[-1]["content"] if messages else ""
        response_text = self._match_response(last_message)

        return LLMResponse(
            content=response_text,
            tool_calls=[],  # Mock doesn't generate tool calls by default
            raw={"mock": True}
        )

    def _match_response(self, prompt: str) -> str:
        """Match prompt to predefined response."""
        prompt_lower = prompt.lower()

        for keyword, response in self.responses.items():
            if keyword.lower() in prompt_lower:
                return response

        return "I need to investigate further. Let me call the appropriate tool."

    def get_name(self) -> str:
        """Get provider name."""
        return f"MockProvider ({self.model})"

    def add_response(self, keyword: str, response: str):
        """Add a response mapping."""
        self.responses[keyword] = response


def create_provider(
    provider_type: str = "openai",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    **kwargs
) -> LLMProvider:
    """
    Factory function to create LLM provider.

    Args:
        provider_type: "openai", "gemini", or "mock"
        model: Model name
        api_key: API key
        **kwargs: Additional provider-specific arguments

    Returns:
        LLMProvider instance
    """
    if provider_type.lower() == "openai":
        return OpenAIProvider(model=model, api_key=api_key)
    elif provider_type.lower() == "mock":
        return MockProvider(model=model, **kwargs)
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
