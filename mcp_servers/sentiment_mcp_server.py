"""MCP Server for Sentiment Classification.

A custom MCP server that provides sentiment analysis using a simple keyword-based
approach. Can be upgraded to use a small ML model (distilbert, etc.) by installing
transformers.

Usage:
    python sentiment_mcp_server.py

The server communicates via stdio using JSON-RPC 2.0 protocol (MCP standard).
"""

import json
import sys
import logging
from typing import Any

# Configure logging to stderr (stdout is for JSON-RPC)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[sentiment-mcp] %(message)s"
)
logger = logging.getLogger(__name__)

# ===== Sentiment Classifier =====

# Simple keyword-based sentiment analysis
POSITIVE_WORDS = {
    "good", "great", "excellent", "amazing", "wonderful", "fantastic",
    "love", "happy", "joy", "pleased", "satisfied", "delighted",
    "beautiful", "awesome", "perfect", "best", "nice", "cool",
    "thank", "thanks", "appreciate", "grateful", "brilliant",
    "成功", "好", "棒", "优秀", "喜欢", "开心", "满意", "感谢", "棒", "赞"
}

NEGATIVE_WORDS = {
    "bad", "terrible", "awful", "horrible", "poor", "worst",
    "hate", "angry", "sad", "disappointed", "frustrated", "upset",
    "ugly", "fail", "failure", "wrong", "error", "problem", "issue",
    "difficult", "hard", "complicated", "confusing", "boring",
    "失败", "坏", "差", "糟糕", "讨厌", "难过", "失望", "错误", "问题"
}

NEUTRAL_WORDS = {
    "normal", "average", "okay", "ok", "standard", "typical",
    "一般", "普通", "还行", "可以"
}


def classify_sentiment(text: str) -> dict[str, Any]:
    """Classify sentiment of text using keyword matching.

    Args:
        text: Input text to analyze

    Returns:
        Dict with sentiment, score, confidence, and details
    """
    text_lower = text.lower()
    words = set(text_lower.split())

    positive_count = sum(1 for w in POSITIVE_WORDS if w in words or any(w in text_lower for w in [w]))
    negative_count = sum(1 for w in NEGATIVE_WORDS if w in words or any(w in text_lower for w in [w]))
    neutral_count = sum(1 for w in NEUTRAL_WORDS if w in words or any(w in text_lower for w in [w]))

    total = positive_count + negative_count + neutral_count

    if total == 0:
        # No sentiment words found - default to neutral
        sentiment = "neutral"
        score = 0.0
        confidence = 0.3
    elif positive_count > negative_count:
        sentiment = "positive"
        score = (positive_count - negative_count) / (total + 1)
        confidence = min(0.9, 0.5 + score * 0.4)
    elif negative_count > positive_count:
        sentiment = "negative"
        score = -(negative_count - positive_count) / (total + 1)
        confidence = min(0.9, 0.5 + abs(score) * 0.4)
    else:
        sentiment = "neutral"
        score = 0.0
        confidence = 0.5

    return {
        "sentiment": sentiment,
        "score": round(score, 3),
        "confidence": round(confidence, 3),
        "positive_words_found": positive_count,
        "negative_words_found": negative_count,
        "analysis_method": "keyword_matching"
    }


def analyze_batch(texts: list[str]) -> list[dict[str, Any]]:
    """Analyze sentiment for multiple texts.

    Args:
        texts: List of texts to analyze

    Returns:
        List of sentiment results
    """
    return [classify_sentiment(t) for t in texts]


# ===== MCP Protocol Implementation =====

class MCPServer:
    """MCP Server implementation for sentiment analysis."""

    def __init__(self):
        self.tools = [
            {
                "name": "sentiment_classify",
                "description": "Classify the sentiment of a text as positive, negative, or neutral. Returns sentiment label, confidence score, and analysis details.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The text to analyze for sentiment"
                        }
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "sentiment_batch",
                "description": "Analyze sentiment for multiple texts in batch. Returns list of sentiment results with labels and confidence scores.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "texts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of texts to analyze"
                        }
                    },
                    "required": ["texts"]
                }
            },
            {
                "name": "sentiment_keywords",
                "description": "Get the list of positive and negative keywords used for sentiment classification. Useful for understanding how the classifier works.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        ]

    def handle_initialize(self, params: dict) -> dict:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "sentiment-mcp-server",
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": {}
            }
        }

    def handle_tools_list(self, params: dict) -> dict:
        """Handle tools/list request."""
        return {
            "tools": self.tools
        }

    def handle_tools_call(self, params: dict) -> dict:
        """Handle tools/call request."""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            if name == "sentiment_classify":
                text = arguments.get("text", "")
                if not text:
                    return self._error_result("Missing 'text' argument")

                result = classify_sentiment(text)
                return self._success_result(result)

            elif name == "sentiment_batch":
                texts = arguments.get("texts", [])
                if not texts:
                    return self._error_result("Missing 'texts' argument")

                results = analyze_batch(texts)
                return self._success_result(results)

            elif name == "sentiment_keywords":
                return self._success_result({
                    "positive_keywords": list(POSITIVE_WORDS),
                    "negative_keywords": list(NEGATIVE_WORDS),
                    "neutral_keywords": list(NEUTRAL_WORDS),
                    "total_positive": len(POSITIVE_WORDS),
                    "total_negative": len(NEGATIVE_WORDS),
                    "total_neutral": len(NEUTRAL_WORDS)
                })

            else:
                return self._error_result(f"Unknown tool: {name}")

        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return self._error_result(str(e))

    def _success_result(self, data: Any) -> dict:
        """Create a successful tool result."""
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(data, ensure_ascii=False, indent=2)
                }
            ]
        }

    def _error_result(self, message: str) -> dict:
        """Create an error tool result."""
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"error": message}, ensure_ascii=False)
                }
            ],
            "isError": True
        }

    def process_request(self, request: dict) -> dict:
        """Process a JSON-RPC request."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        response = {
            "jsonrpc": "2.0",
            "id": request_id
        }

        try:
            if method == "initialize":
                response["result"] = self.handle_initialize(params)
            elif method == "tools/list":
                response["result"] = self.handle_tools_list(params)
            elif method == "tools/call":
                response["result"] = self.handle_tools_call(params)
            elif method == "notifications/initialized":
                # No response needed for notifications
                return None
            else:
                response["error"] = {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }

        except Exception as e:
            response["error"] = {
                "code": -32603,
                "message": str(e)
            }

        return response

    def run(self):
        """Run the MCP server, reading from stdin and writing to stdout."""
        logger.info("Sentiment MCP Server starting...")

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                logger.info(f"Received request: {request.get('method')}")

                response = self.process_request(request)
                if response:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Parse error"
                    }
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()


# ===== Entry Point =====

if __name__ == "__main__":
    server = MCPServer()
    server.run()