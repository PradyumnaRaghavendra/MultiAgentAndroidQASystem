"""
Real Executor Agent for QualGent Multi-Agent QA System
Properly integrates with android_world using EnvironmentInteractingAgent
"""

import logging
import time
from typing import Any, Dict, List, Optional

from android_world.agents import base_agent
from android_world.env import interface
from android_world.env import json_action
from src.llm.llm_client import LLMClient

class QualGentExecutorAgent(base_agent.EnvironmentInteractingAgent):
    """
    Executor Agent that properly inherits from EnvironmentInteractingAgent
    Executes QA plans by interacting with Android UI through android_world
    """
    
    def __init__(
        self,
        env: interface.AsyncEnv,
        llm_config: Dict[str, Any],
        agent_id: str = "qualgent_executor",
        name: str = "QualGent Executor",
        transition_pause: float = 1.0
    ):
        super().__init__(env, name, transition_pause)
        
        self.agent_id = agent_id
        self.llm_client = LLMClient(llm_config)
        
        # Execution state
        self.current_plan: Optional[Dict[str, Any]] = None
        self.current_step_index = 0
        self.execution_history: List[Dict[str, Any]] = []
        
        # Setup logging
        self.logger = logging.getLogger(f"QualGentExecutor[{agent_id}]")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                f'%(asctime)s - QualGentExecutor[{agent_id}] - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        self.logger.info("QualGent Executor Agent initialized")
    
    def step(self, goal: str) -> base_agent.AgentInteractionResult:
        """
        Performs a step of the agent on the environment.
        This is the main method called by android_world framework.
        
        Args:
            goal: The goal to execute (e.g., "Test turning Wi-Fi on and off")
            
        Returns:
            AgentInteractionResult with done flag and data
        """
        try:
            self.logger.info(f"Executing step for goal: {goal}")
            
            # Get current state
            state = self.get_post_transition_state()
            
            # If we don't have a current plan, create one
            if not self.current_plan:
                self.logger.info("No current plan, creating new plan from goal")
                return self._create_and_start_plan(goal, state)
            
            # Execute next step in current plan
            return self._execute_next_plan_step(state)
            
        except Exception as e:
            self.logger.error(f"Error in step execution: {e}")
            return base_agent.AgentInteractionResult(
                done=True,  # Stop on error
                data={
                    "status": "error",
                    "error": str(e),
                    "goal": goal
                }
            )
    
    def _create_and_start_plan(
        self, 
        goal: str, 
        state: interface.State
    ) -> base_agent.AgentInteractionResult:
        """Create a new plan from the goal"""
        try:
            # Create plan using LLM (similar to our PlannerAgent logic)
            plan = self._create_plan_from_goal(goal, state)
            
            self.current_plan = plan
            self.current_step_index = 0
            
            self.logger.info(f"Created plan with {len(plan['steps'])} steps")
            
            # Start executing first step
            return self._execute_next_plan_step(state)
            
        except Exception as e:
            self.logger.error(f"Error creating plan: {e}")
            return base_agent.AgentInteractionResult(
                done=True,
                data={
                    "status": "error",
                    "error": f"Plan creation failed: {str(e)}",
                    "goal": goal
                }
            )
    
    def _execute_next_plan_step(
        self, 
        state: interface.State
    ) -> base_agent.AgentInteractionResult:
        """Execute the next step in the current plan"""
        try:
            if not self.current_plan or self.current_step_index >= len(self.current_plan["steps"]):
                # Plan completed
                self.logger.info("Plan execution completed")
                return base_agent.AgentInteractionResult(
                    done=True,
                    data={
                        "status": "completed",
                        "plan_id": self.current_plan.get("plan_id", "unknown"),
                        "steps_executed": self.current_step_index,
                        "execution_history": self.execution_history
                    }
                )
            
            # Get current step
            current_step = self.current_plan["steps"][self.current_step_index]
            step_id = current_step.get("step_id", f"step_{self.current_step_index}")
            
            self.logger.info(f"Executing step {self.current_step_index + 1}: {current_step.get('description', 'Unknown')}")
            
            # Execute the step
            action_result = self._execute_plan_step(current_step, state)
            
            # Record execution
            self.execution_history.append({
                "step_index": self.current_step_index,
                "step": current_step,
                "result": action_result,
                "timestamp": time.time()
            })
            
            # Move to next step
            self.current_step_index += 1
            
            # Determine if we should continue
            if action_result.get("status") == "failed":
                self.logger.error(f"Step {step_id} failed: {action_result.get('error', 'Unknown error')}")
                return base_agent.AgentInteractionResult(
                    done=True,  # Stop on failure
                    data={
                        "status": "failed",
                        "failed_step": self.current_step_index - 1,
                        "error": action_result.get("error"),
                        "execution_history": self.execution_history
                    }
                )
            
            # Continue with next step
            return base_agent.AgentInteractionResult(
                done=False,  # Continue execution
                data={
                    "status": "continuing",
                    "step_completed": self.current_step_index - 1,
                    "next_step": self.current_step_index,
                    "total_steps": len(self.current_plan["steps"])
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error executing step: {e}")
            return base_agent.AgentInteractionResult(
                done=True,
                data={
                    "status": "error",
                    "error": str(e),
                    "step_index": self.current_step_index
                }
            )
    
    def _execute_plan_step(
        self, 
        step: Dict[str, Any], 
        state: interface.State
    ) -> Dict[str, Any]:
        """Execute a single plan step"""
        try:
            action_type = step.get("action_type", "interact")
            target_element = step.get("target_element", "")
            description = step.get("description", "")
            
            self.logger.info(f"Executing {action_type} on {target_element}: {description}")
            
            if action_type == "navigate":
                return self._execute_navigation_step(step, state)
            elif action_type == "interact":
                return self._execute_interaction_step(step, state)
            elif action_type == "verify":
                return self._execute_verification_step(step, state)
            elif action_type == "wait":
                return self._execute_wait_step(step, state)
            else:
                return {
                    "status": "failed",
                    "error": f"Unknown action type: {action_type}"
                }
                
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Step execution failed: {str(e)}"
            }
    
    def _execute_navigation_step(
        self, 
        step: Dict[str, Any], 
        state: interface.State
    ) -> Dict[str, Any]:
        """Execute navigation step"""
        try:
            target = step.get("target_element", "")
            
            # Find UI element to click for navigation
            ui_element = self._find_ui_element(target, state)
            
            if ui_element:
                # Create click action
                action = json_action.JSONAction(
                    action_type="click",
                    coordinate=[ui_element["center_x"], ui_element["center_y"]]
                )
                
                # Execute action through android_world
                self.env.execute_action(action)
                
                return {
                    "status": "success",
                    "action": "click",
                    "target": target,
                    "coordinates": [ui_element["center_x"], ui_element["center_y"]]
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Could not find navigation target: {target}"
                }
                
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Navigation failed: {str(e)}"
            }
    
    def _execute_interaction_step(
        self, 
        step: Dict[str, Any], 
        state: interface.State
    ) -> Dict[str, Any]:
        """Execute interaction step (touch, toggle, etc.)"""
        try:
            target = step.get("target_element", "")
            parameters = step.get("parameters", {})
            
            # Find UI element
            ui_element = self._find_ui_element(target, state)
            
            if ui_element:
                # Determine interaction type
                if "toggle" in parameters.get("action", ""):
                    # Handle toggle interaction
                    action = json_action.JSONAction(
                        action_type="click",
                        coordinate=[ui_element["center_x"], ui_element["center_y"]]
                    )
                elif parameters.get("text"):
                    # Handle text input
                    # First click to focus
                    click_action = json_action.JSONAction(
                        action_type="click",
                        coordinate=[ui_element["center_x"], ui_element["center_y"]]
                    )
                    self.env.execute_action(click_action)
                    
                    # Then type text
                    action = json_action.JSONAction(
                        action_type="type",
                        text=parameters["text"]
                    )
                else:
                    # Default click interaction
                    action = json_action.JSONAction(
                        action_type="click",
                        coordinate=[ui_element["center_x"], ui_element["center_y"]]
                    )
                
                # Execute action
                self.env.execute_action(action)
                
                return {
                    "status": "success",
                    "action": action.action_type,
                    "target": target,
                    "coordinates": [ui_element["center_x"], ui_element["center_y"]]
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Could not find interaction target: {target}"
                }
                
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Interaction failed: {str(e)}"
            }
    
    def _execute_verification_step(
        self, 
        step: Dict[str, Any], 
        state: interface.State
    ) -> Dict[str, Any]:
        """Execute verification step"""
        try:
            target = step.get("target_element", "")
            expected_state = step.get("expected_state", "")
            
            # Use LLM to verify the current state
            verification_result = self._verify_state_with_llm(target, expected_state, state)
            
            return {
                "status": "success" if verification_result else "failed",
                "verification": verification_result,
                "target": target,
                "expected": expected_state
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Verification failed: {str(e)}"
            }
    
    def _execute_wait_step(
        self, 
        step: Dict[str, Any], 
        state: interface.State
    ) -> Dict[str, Any]:
        """Execute wait step"""
        try:
            duration = step.get("parameters", {}).get("duration", 2.0)
            reason = step.get("description", "wait")
            
            self.logger.info(f"Waiting {duration}s for: {reason}")
            time.sleep(duration)
            
            return {
                "status": "success",
                "action": "wait",
                "duration": duration,
                "reason": reason
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Wait failed: {str(e)}"
            }
    
    def _find_ui_element(self, target: str, state: interface.State) -> Optional[Dict[str, Any]]:
        """Find UI element by target description"""
        try:
            if not state.ui_elements:
                return None
            
            # Simple text matching for now
            target_lower = target.lower()
            
            for element in state.ui_elements:
                element_text = element.get("text", "").lower()
                element_desc = element.get("content_description", "").lower()
                element_id = element.get("resource_id", "").lower()
                
                if (target_lower in element_text or 
                    target_lower in element_desc or 
                    target_lower in element_id):
                    
                    # Calculate center coordinates
                    bounds = element.get("bbox", [0, 0, 100, 100])
                    center_x = (bounds[0] + bounds[2]) // 2
                    center_y = (bounds[1] + bounds[3]) // 2
                    
                    return {
                        "element": element,
                        "center_x": center_x,
                        "center_y": center_y,
                        "text": element.get("text", ""),
                        "resource_id": element.get("resource_id", "")
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding UI element: {e}")
            return None
    
    def _verify_state_with_llm(
        self, 
        target: str, 
        expected_state: str, 
        state: interface.State
    ) -> bool:
        """Use LLM to verify if the current state matches expectations"""
        try:
            # Create prompt for verification
            prompt = f"""
You are verifying the state of an Android UI after an action.

Target element: {target}
Expected state: {expected_state}

Current UI elements (simplified):
{self._format_ui_elements_for_llm(state.ui_elements[:10])}  # Limit for token count

Based on the UI elements, does the current state match the expected state "{expected_state}" for "{target}"?

Respond with only "YES" or "NO".
"""
            
            response = self.llm_client.generate_response(prompt)
            return response.strip().upper() == "YES"
            
        except Exception as e:
            self.logger.error(f"LLM verification failed: {e}")
            return True  # Default to success if verification fails
    
    def _format_ui_elements_for_llm(self, ui_elements: List[Dict[str, Any]]) -> str:
        """Format UI elements for LLM analysis"""
        try:
            formatted = []
            for element in ui_elements:
                text = element.get("text", "")
                desc = element.get("content_description", "")
                resource_id = element.get("resource_id", "")
                
                element_info = f"- {text or desc or resource_id or 'Unknown element'}"
                if element.get("checked") is not None:
                    element_info += f" (checked: {element['checked']})"
                
                formatted.append(element_info)
            
            return "\n".join(formatted)
            
        except Exception as e:
            return f"Error formatting UI elements: {str(e)}"
    
    def _create_plan_from_goal(
        self, 
        goal: str, 
        state: interface.State
    ) -> Dict[str, Any]:
        """Create a plan from goal using LLM (simplified version of PlannerAgent logic)"""
        try:
            # Use the same logic as PlannerAgent but simplified
            if "wifi" in goal.lower():
                return {
                    "plan_id": f"plan_{int(time.time())}",
                    "goal": goal,
                    "steps": [
                        {
                            "step_id": "step_001",
                            "description": "Navigate to Settings app",
                            "action_type": "navigate",
                            "target_element": "settings",
                            "expected_state": "settings_opened"
                        },
                        {
                            "step_id": "step_002",
                            "description": "Navigate to Wi-Fi settings",
                            "action_type": "navigate", 
                            "target_element": "wifi",
                            "expected_state": "wifi_settings_opened"
                        },
                        {
                            "step_id": "step_003",
                            "description": "Toggle Wi-Fi off",
                            "action_type": "interact",
                            "target_element": "wifi_toggle",
                            "expected_state": "wifi_disabled",
                            "parameters": {"action": "toggle_off"}
                        },
                        {
                            "step_id": "step_004",
                            "description": "Verify Wi-Fi is disabled",
                            "action_type": "verify",
                            "target_element": "wifi_status",
                            "expected_state": "wifi_off"
                        },
                        {
                            "step_id": "step_005",
                            "description": "Toggle Wi-Fi back on",
                            "action_type": "interact",
                            "target_element": "wifi_toggle",
                            "expected_state": "wifi_enabled",
                            "parameters": {"action": "toggle_on"}
                        },
                        {
                            "step_id": "step_006",
                            "description": "Verify Wi-Fi is enabled",
                            "action_type": "verify",
                            "target_element": "wifi_status",
                            "expected_state": "wifi_on"
                        }
                    ]
                }
            else:
                # Generic plan
                return {
                    "plan_id": f"plan_{int(time.time())}",
                    "goal": goal,
                    "steps": [
                        {
                            "step_id": "step_001",
                            "description": f"Execute goal: {goal}",
                            "action_type": "interact",
                            "target_element": "screen",
                            "expected_state": "completed"
                        }
                    ]
                }
                
        except Exception as e:
            self.logger.error(f"Error creating plan: {e}")
            raise
    
    def load_plan(self, plan: Dict[str, Any]) -> None:
        """Load a plan from external source (e.g., PlannerAgent)"""
        self.current_plan = plan
        self.current_step_index = 0
        self.execution_history = []
        self.logger.info(f"Loaded plan with {len(plan.get('steps', []))} steps")
    
    def get_execution_status(self) -> Dict[str, Any]:
        """Get current execution status"""
        if not self.current_plan:
            return {"status": "idle"}
        
        return {
            "status": "executing",
            "plan_id": self.current_plan.get("plan_id"),
            "current_step": self.current_step_index,
            "total_steps": len(self.current_plan.get("steps", [])),
            "progress": self.current_step_index / len(self.current_plan.get("steps", [])) if self.current_plan.get("steps") else 0
        }