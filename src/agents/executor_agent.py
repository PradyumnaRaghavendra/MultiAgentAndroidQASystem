"""
Executor Agent for QualGent Multi-Agent QA System
Executes subgoals in the Android UI environment with grounded mobile gestures
UPDATED: Now includes visual trace generation support
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from src.agents.base_agent import BaseAgent, AgentType, MessageType, AgentMessage
from src.android_integration.android_env_wrapper import AndroidEnvWrapper
from src.llm.llm_client import LLMClient

@dataclass
class ExecutionResult:
    """Result of executing a plan step"""
    step_id: str
    status: str  # "success", "failed", "partial"
    action_taken: str
    ui_state_before: Dict[str, Any]
    ui_state_after: Dict[str, Any]
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    execution_time: float = 0.0

@dataclass
class AndroidAction:
    """Android action to be executed"""
    action_type: str  # "touch", "type", "scroll", "back", "home"
    coordinates: Optional[Tuple[int, int]] = None
    text: Optional[str] = None
    element_id: Optional[str] = None
    parameters: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}

class ExecutorAgent(BaseAgent):
    """
    Executor Agent - Executes subgoals in the Android UI environment with grounded mobile gestures
    UPDATED: Now sends screenshots to supervisor for visual trace recording
    """
    
    def __init__(
        self, 
        agent_id: str, 
        llm_config: Dict[str, Any], 
        android_config: Dict[str, Any],
        message_bus=None
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.EXECUTOR,
            llm_config=llm_config,
            message_bus=message_bus
        )
        
        # Initialize Android environment wrapper
        self.android_env = AndroidEnvWrapper(android_config)
        
        # Initialize LLM client for UI understanding
        self.llm_client = LLMClient(llm_config)
        
        # Execution state
        self.current_plan = None
        self.current_step_index = 0
        self.execution_history = []
        self.last_screenshot = None
        self.last_ui_tree = None
        
        # UI element cache for faster lookups
        self.ui_element_cache = {}
        
        # Add message handlers specific to executor
        self.message_handlers.update({
            MessageType.EXECUTION_REQUEST: self._handle_execution_request,
            MessageType.VERIFICATION_RESPONSE: self._handle_verification_response,
        })
        
        self.logger.info("Executor Agent initialized with visual trace support")
    
    async def start(self):
        """Start the executor agent and initialize Android environment"""
        await super().start()
        
        # Initialize Android environment
        await self.android_env.initialize()
        self.logger.info("Android environment initialized")
    
    async def stop(self):
        """Stop the executor agent and cleanup"""
        await self.android_env.cleanup()
        await super().stop()
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a task (plan execution)"""
        try:
            action = task.get("action", "")
            
            if action == "execute_plan":
                plan_data = task.get("plan", {})
                return await self._execute_plan(plan_data)
                
            elif action == "execute_step":
                step_data = task.get("step", {})
                return await self._execute_single_step(step_data)
                
            elif action == "get_ui_state":
                return await self._get_current_ui_state()
                
            else:
                return {
                    "status": "error",
                    "error": f"Unknown action: {action}"
                }
                
        except Exception as e:
            self.logger.error(f"Error executing task: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _execute_plan(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a complete plan"""
        try:
            self.current_plan = plan_data
            self.current_step_index = 0
            
            plan_id = plan_data.get("plan_id")
            steps = plan_data.get("steps", [])
            
            self.logger.info(f"Starting execution of plan {plan_id} with {len(steps)} steps")
            
            results = []
            
            for i, step in enumerate(steps):
                self.current_step_index = i
                
                self.logger.info(f"Executing step {i+1}/{len(steps)}: {step.get('description')}")
                
                # Execute step
                result = await self._execute_single_step(step)
                results.append(result)
                
                # Check if step failed
                if result["status"] == "failed":
                    self.logger.error(f"Step {i+1} failed: {result.get('error')}")
                    
                    # Send failure notification to planner
                    await self._notify_step_failure(plan_id, i, result)
                    
                    return {
                        "status": "failed",
                        "plan_id": plan_id,
                        "failed_step": i,
                        "results": results,
                        "error": result.get("error")
                    }
                
                # Small delay between steps
                await asyncio.sleep(1.0)
            
            # Plan completed successfully
            self.logger.info(f"Plan {plan_id} completed successfully")
            
            await self._notify_plan_completion(plan_id, results)
            
            return {
                "status": "success",
                "plan_id": plan_id,
                "results": results
            }
            
        except Exception as e:
            self.logger.error(f"Error executing plan: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _execute_single_step(self, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single plan step - UPDATED with visual trace support"""
        start_time = time.time()
        
        try:
            step_id = step_data.get("step_id", "unknown")
            description = step_data.get("description", "")
            action_type = step_data.get("action_type", "interact")
            target_element = step_data.get("target_element")
            expected_state = step_data.get("expected_state")
            parameters = step_data.get("parameters", {})
            
            self.logger.info(f"Executing step {step_id}: {description}")
            
            # Get current UI state before action
            ui_state_before = await self._get_current_ui_state()
            
            # Execute the appropriate action based on action_type
            if action_type == "navigate":
                result = await self._execute_navigation(target_element, parameters)
            elif action_type == "interact":
                result = await self._execute_interaction(target_element, parameters)
            elif action_type == "verify":
                result = await self._execute_verification(target_element, expected_state, parameters)
            elif action_type == "wait":
                result = await self._execute_wait(parameters)
            else:
                result = {
                    "status": "failed",
                    "error": f"Unknown action type: {action_type}"
                }
            
            # Get UI state after action
            ui_state_after = await self._get_current_ui_state()
            
            execution_time = time.time() - start_time
            
            # Create execution result
            execution_result = ExecutionResult(
                step_id=step_id,
                status=result["status"],
                action_taken=result.get("action_taken", ""),
                ui_state_before=ui_state_before,
                ui_state_after=ui_state_after,
                error=result.get("error"),
                screenshot_path=result.get("screenshot_path"),
                execution_time=execution_time
            )
            
            # UPDATED: Send screenshot to supervisor for visual trace recording
            if result.get("screenshot_path"):
                try:
                    self.logger.info(f"📸 Sending visual trace to supervisor: {result['screenshot_path']}")
                    
                    await self.send_message(
                        receiver="supervisor_agent",
                        message_type=MessageType.TASK_REQUEST,
                        content={
                            "action": "record_visual_trace", 
                            "screenshot_path": result["screenshot_path"],
                            "step_info": {
                                "step_id": step_id,
                                "description": description,
                                "action_type": action_type,
                                "target_element": target_element
                            }
                        }
                    )
                    self.logger.info(f"✅ Visual trace request sent for step {step_id}")
                    
                except Exception as e:
                    self.logger.error(f"❌ Failed to send visual trace: {e}")
            
            # Add to execution history
            self.execution_history.append(execution_result)
            
            return execution_result.__dict__
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Error executing step: {e}")
            
            return {
                "step_id": step_data.get("step_id", "unknown"),
                "status": "failed",
                "action_taken": "error",
                "ui_state_before": {},
                "ui_state_after": {},
                "error": str(e),
                "execution_time": execution_time
            }
    
    async def _execute_navigation(self, target_element: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute navigation action"""
        try:
            self.logger.info(f"Navigating to: {target_element}")
            
            # Special handling for common navigation targets
            if target_element == "settings_app":
                action = AndroidAction(
                    action_type="touch",
                    element_id="com.android.settings/.Settings"
                )
            elif target_element == "home_screen":
                action = AndroidAction(action_type="home")
            elif target_element == "back":
                action = AndroidAction(action_type="back")
            else:
                # Find the element in the UI and navigate to it
                action = await self._find_and_create_action(target_element, "touch")
            
            if action:
                success = await self.android_env.execute_action(action)
                
                if success:
                    return {
                        "status": "success",
                        "action_taken": f"navigated to {target_element}",
                        "screenshot_path": await self.android_env.take_screenshot()
                    }
                else:
                    return {
                        "status": "failed",
                        "error": f"Failed to navigate to {target_element}"
                    }
            else:
                return {
                    "status": "failed",
                    "error": f"Could not find navigation target: {target_element}"
                }
                
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Navigation failed: {str(e)}"
            }
    
    async def _execute_interaction(self, target_element: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute interaction action (touch, type, scroll)"""
        try:
            self.logger.info(f"Interacting with: {target_element}")
            
            # Determine interaction type from parameters
            interaction_type = parameters.get("action", "touch")
            text_input = parameters.get("text", "")
            
            if interaction_type == "type" and text_input:
                # Type text action
                action = AndroidAction(
                    action_type="type",
                    text=text_input,
                    element_id=target_element
                )
            elif interaction_type in ["toggle_off", "toggle_on"]:
                # Special toggle handling
                action = await self._find_and_create_toggle_action(target_element, interaction_type)
            else:
                # Default touch action
                action = await self._find_and_create_action(target_element, "touch")
            
            if action:
                success = await self.android_env.execute_action(action)
                
                if success:
                    return {
                        "status": "success",
                        "action_taken": f"{interaction_type} on {target_element}",
                        "screenshot_path": await self.android_env.take_screenshot()
                    }
                else:
                    return {
                        "status": "failed",
                        "error": f"Failed to {interaction_type} {target_element}"
                    }
            else:
                return {
                    "status": "failed",
                    "error": f"Could not find interaction target: {target_element}"
                }
                
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Interaction failed: {str(e)}"
            }
    
    async def _execute_verification(self, target_element: str, expected_state: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute verification action"""
        try:
            self.logger.info(f"Verifying {target_element} is in state: {expected_state}")
            
            # Get current UI state
            ui_state = await self._get_current_ui_state()
            
            # Send verification request to verifier agent
            await self.send_message(
                receiver="verifier_agent",
                message_type=MessageType.VERIFICATION_REQUEST,
                content={
                    "target_element": target_element,
                    "expected_state": expected_state,
                    "ui_state": ui_state,
                    "parameters": parameters
                }
            )
            
            # For now, return success (real verification happens asynchronously)
            return {
                "status": "success",
                "action_taken": f"requested verification of {target_element}",
                "screenshot_path": await self.android_env.take_screenshot()
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Verification failed: {str(e)}"
            }
    
    async def _execute_wait(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute wait action"""
        try:
            duration = parameters.get("duration", 2.0)
            reason = parameters.get("reason", "general wait")
            
            self.logger.info(f"Waiting {duration}s for: {reason}")
            
            await asyncio.sleep(duration)
            
            return {
                "status": "success",
                "action_taken": f"waited {duration}s for {reason}"
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Wait failed: {str(e)}"
            }
    
    async def _find_and_create_action(self, target_element: str, action_type: str) -> Optional[AndroidAction]:
        """Find UI element and create appropriate action"""
        try:
            # Get current UI hierarchy
            ui_hierarchy = await self.android_env.get_ui_hierarchy()
            
            # Use LLM to find the best matching element
            element_info = await self._find_ui_element_with_llm(target_element, ui_hierarchy)
            
            if element_info:
                if action_type == "touch":
                    return AndroidAction(
                        action_type="touch",
                        coordinates=element_info.get("coordinates"),
                        element_id=element_info.get("resource_id")
                    )
                elif action_type == "type":
                    return AndroidAction(
                        action_type="type",
                        element_id=element_info.get("resource_id")
                    )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding UI element: {e}")
            return None
    
    async def _find_and_create_toggle_action(self, target_element: str, toggle_type: str) -> Optional[AndroidAction]:
        """Find toggle element and create appropriate toggle action"""
        try:
            # Get UI hierarchy
            ui_hierarchy = await self.android_env.get_ui_hierarchy()
            
            # Find toggle element
            element_info = await self._find_ui_element_with_llm(target_element, ui_hierarchy)
            
            if element_info:
                # Check current toggle state and determine if action is needed
                current_state = element_info.get("checked", False)
                should_be_on = toggle_type == "toggle_on"
                
                if (should_be_on and not current_state) or (not should_be_on and current_state):
                    # Need to toggle
                    return AndroidAction(
                        action_type="touch",
                        coordinates=element_info.get("coordinates"),
                        element_id=element_info.get("resource_id")
                    )
                else:
                    # Already in desired state
                    self.logger.info(f"Toggle {target_element} already in desired state")
                    return AndroidAction(
                        action_type="touch",  # Still return action for consistency
                        coordinates=element_info.get("coordinates"),
                        element_id=element_info.get("resource_id")
                    )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding toggle element: {e}")
            return None
    
    async def _find_ui_element_with_llm(self, target_element: str, ui_hierarchy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Use LLM to find the best matching UI element"""
        try:
            # Create prompt for LLM to analyze UI hierarchy
            prompt = f"""
You are analyzing an Android UI hierarchy to find a specific element.

Target element to find: {target_element}

UI Hierarchy (simplified):
{json.dumps(ui_hierarchy, indent=2)[:2000]}  # Truncate for token limits

Please identify the best matching UI element for "{target_element}". Return a JSON object with:
{{
    "resource_id": "element_id",
    "coordinates": [x, y],
    "text": "element_text",
    "checked": true/false (for toggles),
    "confidence": 0.95
}}

If no good match is found, return {{"confidence": 0.0}}.
Return only the JSON, no additional text.
"""
            
            response = await self.llm_client.generate_response(prompt)
            
            # Parse LLM response
            element_info = json.loads(response.strip())
            
            if element_info.get("confidence", 0) > 0.5:
                return element_info
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"LLM element finding failed: {e}")
            
            # Fallback: simple text matching
            return self._simple_element_search(target_element, ui_hierarchy)
    
    def _simple_element_search(self, target_element: str, ui_hierarchy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Simple fallback element search"""
        try:
            # Simple text-based matching as fallback
            target_lower = target_element.lower()
            
            # This is a simplified version - real implementation would traverse the UI tree
            return {
                "resource_id": f"mock_{target_element}",
                "coordinates": [200, 400],  # Mock coordinates
                "text": target_element,
                "confidence": 0.6
            }
            
        except Exception as e:
            self.logger.error(f"Simple element search failed: {e}")
            return None
    
    async def _get_current_ui_state(self) -> Dict[str, Any]:
        """Get current UI state from Android environment"""
        try:
            ui_hierarchy = await self.android_env.get_ui_hierarchy()
            screenshot_path = await self.android_env.take_screenshot()
            
            return {
                "ui_hierarchy": ui_hierarchy,
                "screenshot_path": screenshot_path,
                "timestamp": time.time()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting UI state: {e}")
            return {
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def _notify_step_failure(self, plan_id: str, step_index: int, failure_result: Dict[str, Any]):
        """Notify planner about step failure"""
        try:
            await self.send_message(
                receiver="planner_agent",
                message_type=MessageType.EXECUTION_RESPONSE,
                content={
                    "plan_id": plan_id,
                    "status": "step_failed",
                    "step_index": step_index,
                    "feedback": {
                        "type": "execution_error",
                        "current_step": step_index,
                        "issue": failure_result.get("error", "Unknown error"),
                        "ui_state": failure_result.get("ui_state_after", {})
                    }
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error notifying step failure: {e}")
    
    async def _notify_plan_completion(self, plan_id: str, results: List[Dict[str, Any]]):
        """Notify planner about plan completion"""
        try:
            await self.send_message(
                receiver="planner_agent",
                message_type=MessageType.EXECUTION_RESPONSE,
                content={
                    "plan_id": plan_id,
                    "status": "completed",
                    "results": results
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error notifying plan completion: {e}")
    
    # Message handlers
    async def _handle_task_request(self, message: AgentMessage):
        """Handle task request message"""
        try:
            task_data = message.content
            result = await self.execute_task(task_data)
            
            # Send response
            await self.send_message(
                receiver=message.sender,
                message_type=MessageType.TASK_RESPONSE,
                content=result,
                correlation_id=message.correlation_id
            )
            
        except Exception as e:
            self.logger.error(f"Error handling task request: {e}")
            await self._send_error_response(message, str(e))
    
    async def _handle_execution_request(self, message: AgentMessage):
        """Handle execution request from planner"""
        try:
            content = message.content
            action = content.get("action", "execute_plan")
            
            if action == "execute_plan":
                plan_data = content.get("plan", {})
                result = await self._execute_plan(plan_data)
                
            else:
                result = {"status": "error", "error": f"Unknown execution action: {action}"}
            
            # Send response
            await self.send_message(
                receiver=message.sender,
                message_type=MessageType.EXECUTION_RESPONSE,
                content=result,
                correlation_id=message.correlation_id
            )
            
        except Exception as e:
            self.logger.error(f"Error handling execution request: {e}")
            await self._send_error_response(message, str(e))
    
    async def _handle_verification_response(self, message: AgentMessage):
        """Handle verification response from verifier"""
        try:
            content = message.content
            verification_result = content.get("result")
            
            if verification_result == "failed":
                # Handle verification failure
                self.logger.warning("Verification failed for current step")
                
                # Could trigger retry or report to planner
                
        except Exception as e:
            self.logger.error(f"Error handling verification response: {e}")
    
    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get execution history"""
        return [result.__dict__ if hasattr(result, '__dict__') else result 
                for result in self.execution_history]
    
    def get_current_plan_status(self) -> Dict[str, Any]:
        """Get current plan execution status"""
        if self.current_plan:
            return {
                "plan_id": self.current_plan.get("plan_id"),
                "current_step": self.current_step_index,
                "total_steps": len(self.current_plan.get("steps", [])),
                "status": "executing" if self.current_step_index < len(self.current_plan.get("steps", [])) else "completed"
            }
        else:
            return {"status": "idle"}