"""
Base Agent Class for QualGent Multi-Agent QA System
Integrates with Agent-S framework and provides foundation for all agents
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from uuid import uuid4

# Agent-S imports
try:
    from gui_agents.s2 import Agent as AgentSBase
except ImportError:
    # Fallback if gui_agents import fails
    AgentSBase = object

class AgentType(Enum):
    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    SUPERVISOR = "supervisor"

class MessageType(Enum):
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    STATE_UPDATE = "state_update"
    ERROR = "error"
    VERIFICATION_REQUEST = "verification_request"
    VERIFICATION_RESPONSE = "verification_response"
    EXECUTION_REQUEST = "execution_request"
    EXECUTION_RESPONSE = "execution_response"
    PLANNING_REQUEST = "planning_request"
    PLANNING_RESPONSE = "planning_response"
    SUPERVISION_REQUEST = "supervision_request"
    SUPERVISION_RESPONSE = "supervision_response"

@dataclass
class AgentMessage:
    """Standard message format for inter-agent communication"""
    id: str
    sender: str
    receiver: str
    message_type: MessageType
    content: Dict[str, Any]
    timestamp: float
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        data['message_type'] = MessageType(data['message_type'])
        return cls(**data)

@dataclass
class AgentState:
    """Agent state tracking"""
    agent_id: str
    agent_type: AgentType
    status: str  # "idle", "processing", "error", "busy"
    current_task: Optional[str] = None
    last_activity: Optional[float] = None
    error_count: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.last_activity is None:
            self.last_activity = time.time()

class BaseAgent(ABC):
    """
    Base class for all agents in the QualGent Multi-Agent QA System
    Integrates with Agent-S framework and provides core functionality
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_type: AgentType,
        llm_config: Dict[str, Any],
        message_bus=None,
        logger: Optional[logging.Logger] = None
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.llm_config = llm_config
        self.message_bus = message_bus
        
        # Set up logging
        self.logger = logger or self._setup_logger()
        
        # Initialize state
        self.state = AgentState(
            agent_id=agent_id,
            agent_type=agent_type,
            status="idle"
        )
        
        # Message handling
        self.message_handlers = {
            MessageType.TASK_REQUEST: self._handle_task_request,
            MessageType.STATE_UPDATE: self._handle_state_update,
            MessageType.ERROR: self._handle_error_message,
        }
        
        # Task tracking
        self.active_tasks = {}
        self.task_history = []
        
        self.logger.info(f"Initialized {agent_type.value} agent: {agent_id}")
    
    def _setup_logger(self) -> logging.Logger:
        """Set up agent-specific logger"""
        logger = logging.getLogger(f"{self.agent_type.value}_{self.agent_id}")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                f'%(asctime)s - {self.agent_type.value}[{self.agent_id}] - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    async def start(self):
        """Start the agent and begin message processing"""
        self.logger.info("Starting agent...")
        self.state.status = "idle"
        self.state.last_activity = time.time()
        
        if self.message_bus:
            await self.message_bus.register_agent(self)
        
        # Start message processing loop
        asyncio.create_task(self._message_processing_loop())
    
    async def stop(self):
        """Stop the agent gracefully"""
        self.logger.info("Stopping agent...")
        self.state.status = "stopped"
        
        if self.message_bus:
            await self.message_bus.unregister_agent(self)
    
    async def _message_processing_loop(self):
        """Main message processing loop"""
        while self.state.status != "stopped":
            try:
                if self.message_bus:
                    messages = await self.message_bus.get_messages(self.agent_id)
                    for message in messages:
                        await self.process_message(message)
                
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                
            except Exception as e:
                self.logger.error(f"Error in message processing loop: {e}")
                self.state.error_count += 1
                await asyncio.sleep(1)  # Longer delay on error
    
    async def process_message(self, message: AgentMessage):
        """Process incoming message"""
        try:
            self.logger.debug(f"Processing message: {message.message_type.value} from {message.sender}")
            
            handler = self.message_handlers.get(message.message_type)
            if handler:
                await handler(message)
            else:
                self.logger.warning(f"No handler for message type: {message.message_type.value}")
                
            self.state.last_activity = time.time()
            
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            await self._send_error_response(message, str(e))
    
    async def send_message(
        self,
        receiver: str,
        message_type: MessageType,
        content: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> str:
        """Send message to another agent"""
        message = AgentMessage(
            id=str(uuid4()),
            sender=self.agent_id,
            receiver=receiver,
            message_type=message_type,
            content=content,
            timestamp=time.time(),
            correlation_id=correlation_id
        )
        
        if self.message_bus:
            await self.message_bus.send_message(message)
        else:
            self.logger.warning("No message bus available - message not sent")
        
        return message.id
    
    async def _send_error_response(self, original_message: AgentMessage, error: str):
        """Send error response"""
        await self.send_message(
            receiver=original_message.sender,
            message_type=MessageType.ERROR,
            content={
                "error": error,
                "original_message_id": original_message.id
            },
            correlation_id=original_message.correlation_id
        )
    
    # Abstract methods to be implemented by specific agents
    @abstractmethod
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute agent-specific task"""
        pass
    
    @abstractmethod
    async def _handle_task_request(self, message: AgentMessage):
        """Handle task request message"""
        pass
    
    # Default message handlers
    async def _handle_state_update(self, message: AgentMessage):
        """Handle state update message"""
        self.logger.info(f"Received state update: {message.content}")
    
    async def _handle_error_message(self, message: AgentMessage):
        """Handle error message"""
        self.logger.error(f"Received error from {message.sender}: {message.content.get('error')}")
    
    # Utility methods
    def get_state(self) -> Dict[str, Any]:
        """Get current agent state"""
        return asdict(self.state)
    
    async def update_status(self, status: str, current_task: Optional[str] = None):
        """Update agent status"""
        self.state.status = status
        self.state.current_task = current_task
        self.state.last_activity = time.time()
        
        # Broadcast status update if message bus is available
        if self.message_bus:
            await self.message_bus.broadcast_state_update(self.agent_id, self.get_state())
    
    def is_busy(self) -> bool:
        """Check if agent is currently busy"""
        return self.state.status in ["processing", "busy"]
    
    def get_task_history(self) -> List[Dict[str, Any]]:
        """Get task execution history"""
        return self.task_history.copy()
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "status": self.state.status,
            "last_activity": self.state.last_activity,
            "error_count": self.state.error_count,
            "active_tasks": len(self.active_tasks),
            "healthy": self.state.error_count < 5 and self.state.status != "error"
        }