# core/message.py
from __future__ import annotations
import time, uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class MessageType(str, Enum):
    ALERT        = "ALERT"
    COMMAND      = "COMMAND"
    STATUS       = "STATUS"
    FORECAST     = "FORECAST"
    COORDINATION = "COORDINATION"
    RESTORATION  = "RESTORATION"
    EXPLANATION  = "EXPLANATION"   # LLM-generated human-readable explanation


class Priority(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Message:
    sender:       str
    receiver:     str
    msg_type:     MessageType
    substation:   str
    payload:      Dict[str, Any]
    priority:     Priority          = Priority.MEDIUM
    timestamp:    float             = field(default_factory=time.time)
    msg_id:       str               = field(default_factory=lambda: str(uuid.uuid4())[:8])
    vector_clock: Dict[str, int]    = field(default_factory=dict)
    llm_reason:   str               = ""   # Groq-generated explanation

    def to_dict(self) -> dict:
        return {
            "msg_id":       self.msg_id,
            "sender":       self.sender,
            "receiver":     self.receiver,
            "msg_type":     self.msg_type.value,
            "substation":   self.substation,
            "payload":      self.payload,
            "priority":     self.priority.value,
            "timestamp":    self.timestamp,
            "vector_clock": self.vector_clock,
            "llm_reason":   self.llm_reason,
        }
