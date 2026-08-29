"""
Model Armor — Inline Guardrails for Security & Governance.
Addresses the Hackathon rubric for blocking prompt injection,
tool poisoning, and PII leaks.
"""
import re
import logging

class ModelArmor:
    @staticmethod
    def scan_for_pii(text: str) -> str:
        """Redacts basic PII (Email, Phone) before it hits the LLM."""
        if not text:
            return text
        
        # Redact emails (except local mocked ones)
        text = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '[REDACTED_EMAIL]', text)
        
        # Redact phone numbers (simple pattern for demo)
        text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED_PHONE]', text)
        
        return text

    @staticmethod
    def detect_prompt_injection(text: str) -> bool:
        """Heuristic check for common prompt injection patterns."""
        if not text:
            return False
            
        text_lower = text.lower()
        injection_patterns = [
            "ignore previous instructions",
            "forget your instructions",
            "system prompt",
            "you are now",
            "output the above",
            "bypass",
        ]
        
        for pattern in injection_patterns:
            if pattern in text_lower:
                logging.warning(f"[ModelArmor] Prompt Injection detected: '{pattern}'")
                return True
        return False
        
    @staticmethod
    def sanitize_tool_args(args: dict) -> dict:
        """Prevents Tool Poisoning by enforcing arg length and type limits."""
        sanitized = {}
        for k, v in args.items():
            if isinstance(v, str):
                # Hard truncate strings to prevent buffer/context attacks
                sanitized[k] = v[:2000]
            else:
                sanitized[k] = v
        return sanitized
