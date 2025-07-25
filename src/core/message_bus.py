"""
Message Bus for Inter-Agent Communication
Handles message routing, queuing, and delivery between agents
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set
from dataclasses import asdict

from src.agents.base_agent import AgentMessage, MessageType

class MessageBus:
    """
    Central message bus for agent communication
    Handles routing, queuing, and delivery of messages between agents
    """
    
    def __init__(self, max_queue_size: int = 1000, message_retention_hours: int = 24):
        self.max_queue_size = max_queue_size
        self.message_retention_seconds = message_retention_hours * 3600
        
        # Agent registry
        self.registered_agents: Dict[str, object] = {}
        
        # Message queues for each agent
        self.message_queues: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_queue_size))
        
        # Message history for debugging and monitoring
        self.message_history: deque = deque(maxlen=10000)
        
        # Subscriptions for broadcast messages
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)
        
        # Statistics
        self.stats = {
            "messages_sent": 0,
            "messages_delivered": 0,
            "messages_failed": 0,
            "broadcast_messages": 0
        }
        
        # Setup logging
        self.logger = logging.getLogger("MessageBus")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - MessageBus - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_old_messages())
    
    async def register_agent(self, agent) -> bool:
        """Register an agent with the message bus"""
        try:
            agent_id = agent.agent_id
            self.registered_agents[agent_id] = agent
            
            # Initialize message queue if not exists
            if agent_id not in self.message_queues:
                self.message_queues[agent_id] = deque(maxlen=self.max_queue_size)
            
            self.logger.info(f"Registered agent: {agent_id} ({agent.agent_type.value})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to register agent: {e}")
            return False
    
    async def unregister_agent(self, agent) -> bool:
        """Unregister an agent from the message bus"""
        try:
            agent_id = agent.agent_id
            
            if agent_id in self.registered_agents:
                del self.registered_agents[agent_id]
                
                # Clear message queue
                if agent_id in self.message_queues:
                    self.message_queues[agent_id].clear()
                
                # Remove from all subscriptions
                for topic in self.subscriptions:
                    self.subscriptions[topic].discard(agent_id)
                
                self.logger.info(f"Unregistered agent: {agent_id}")
                return True
            else:
                self.logger.warning(f"Agent not found for unregistration: {agent_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to unregister agent: {e}")
            return False
    
    async def send_message(self, message: AgentMessage) -> bool:
        """Send a message to a specific agent"""
        try:
            receiver_id = message.receiver
            
            # Check if receiver is registered
            if receiver_id not in self.registered_agents:
                self.logger.error(f"Receiver not found: {receiver_id}")
                self.stats["messages_failed"] += 1
                return False
            
            # Add to receiver's queue
            self.message_queues[receiver_id].append(message)
            
            # Add to history
            self.message_history.append({
                "message": asdict(message),
                "delivered": True,
                "timestamp": time.time()
            })
            
            self.stats["messages_sent"] += 1
            self.stats["messages_delivered"] += 1
            
            self.logger.debug(f"Message sent: {message.id} from {message.sender} to {message.receiver}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            self.stats["messages_failed"] += 1
            return False
    
    async def get_messages(self, agent_id: str) -> List[AgentMessage]:
        """Get pending messages for an agent"""
        try:
            if agent_id not in self.message_queues:
                return []
            
            messages = []
            queue = self.message_queues[agent_id]
            
            # Get all pending messages
            while queue:
                messages.append(queue.popleft())
            
            if messages:
                self.logger.debug(f"Retrieved {len(messages)} messages for {agent_id}")
            
            return messages
            
        except Exception as e:
            self.logger.error(f"Failed to get messages for {agent_id}: {e}")
            return []
    
    async def broadcast_message(
        self,
        sender_id: str,
        message_type: MessageType,
        content: Dict,
        topic: Optional[str] = None
    ) -> int:
        """Broadcast a message to multiple agents"""
        try:
            recipients = set()
            
            if topic and topic in self.subscriptions:
                recipients = self.subscriptions[topic].copy()
            else:
                # Broadcast to all registered agents except sender
                recipients = set(self.registered_agents.keys()) - {sender_id}
            
            sent_count = 0
            for recipient_id in recipients:
                message = AgentMessage(
                    id=f"broadcast_{int(time.time() * 1000)}_{recipient_id}",
                    sender=sender_id,
                    receiver=recipient_id,
                    message_type=message_type,
                    content=content,
                    timestamp=time.time()
                )
                
                if await self.send_message(message):
                    sent_count += 1
            
            self.stats["broadcast_messages"] += 1
            self.logger.info(f"Broadcast message sent to {sent_count} agents")
            return sent_count
            
        except Exception as e:
            self.logger.error(f"Failed to broadcast message: {e}")
            return 0
    
    async def broadcast_state_update(self, agent_id: str, state: Dict) -> int:
        """Broadcast agent state update"""
        return await self.broadcast_message(
            sender_id=agent_id,
            message_type=MessageType.STATE_UPDATE,
            content={"agent_state": state},
            topic="state_updates"
        )
    
    async def subscribe(self, agent_id: str, topic: str) -> bool:
        """Subscribe an agent to a topic for broadcast messages"""
        try:
            if agent_id not in self.registered_agents:
                self.logger.error(f"Agent not registered: {agent_id}")
                return False
            
            self.subscriptions[topic].add(agent_id)
            self.logger.info(f"Agent {agent_id} subscribed to topic: {topic}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to subscribe agent {agent_id} to topic {topic}: {e}")
            return False
    
    async def unsubscribe(self, agent_id: str, topic: str) -> bool:
        """Unsubscribe an agent from a topic"""
        try:
            if topic in self.subscriptions:
                self.subscriptions[topic].discard(agent_id)
                self.logger.info(f"Agent {agent_id} unsubscribed from topic: {topic}")
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to unsubscribe agent {agent_id} from topic {topic}: {e}")
            return False
    
    async def get_registered_agents(self) -> List[Dict]:
        """Get list of registered agents"""
        agents = []
        for agent_id, agent in self.registered_agents.items():
            agents.append({
                "agent_id": agent_id,
                "agent_type": agent.agent_type.value,
                "status": agent.state.status,
                "queue_size": len(self.message_queues[agent_id])
            })
        return agents
    
    async def get_statistics(self) -> Dict:
        """Get message bus statistics"""
        return {
            **self.stats,
            "registered_agents": len(self.registered_agents),
            "total_queued_messages": sum(len(queue) for queue in self.message_queues.values()),
            "subscriptions": {topic: len(agents) for topic, agents in self.subscriptions.items()},
            "message_history_size": len(self.message_history)
        }
    
    async def clear_agent_queue(self, agent_id: str) -> bool:
        """Clear message queue for a specific agent"""
        try:
            if agent_id in self.message_queues:
                self.message_queues[agent_id].clear()
                self.logger.info(f"Cleared message queue for agent: {agent_id}")
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to clear queue for agent {agent_id}: {e}")
            return False
    
    async def _cleanup_old_messages(self):
        """Periodic cleanup of old messages from history"""
        while True:
            try:
                current_time = time.time()
                cutoff_time = current_time - self.message_retention_seconds
                
                # Clean up message history
                while (self.message_history and 
                       self.message_history[0]["timestamp"] < cutoff_time):
                    self.message_history.popleft()
                
                await asyncio.sleep(3600)  # Run cleanup every hour
                
            except Exception as e:
                self.logger.error(f"Error in message cleanup: {e}")
                await asyncio.sleep(3600)
    
    async def health_check(self) -> Dict:
        """Perform health check on message bus"""
        stats = await self.get_statistics()
        
        # Check for potential issues
        issues = []
        if stats["messages_failed"] > stats["messages_sent"] * 0.1:
            issues.append("High message failure rate")
        
        if stats["total_queued_messages"] > self.max_queue_size * 0.8:
            issues.append("High queue utilization")
        
        return {
            "status": "healthy" if not issues else "warning",
            "issues": issues,
            "statistics": stats
        }

# Global message bus instance
_message_bus_instance = None

def get_message_bus() -> MessageBus:
    """Get global message bus instance"""
    global _message_bus_instance
    if _message_bus_instance is None:
        _message_bus_instance = MessageBus()
    return _message_bus_instance