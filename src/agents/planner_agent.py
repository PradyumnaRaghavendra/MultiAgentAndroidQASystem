"""
Planner Agent for QualGent Multi-Agent QA System
Parses high-level QA goals and decomposes them into actionable subgoals
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .base_agent import BaseAgent, AgentType, MessageType, AgentMessage
from src.llm.llm_client import LLMClient

@dataclass
class PlanStep:
    """Individual step in a QA plan"""
    step_id: str
    description: str
    action_type: str  # "navigate", "interact", "verify", "wait"
    target_element: Optional[str] = None
    expected_state: Optional[str] = None
    parameters: Dict[str, Any] = None
    dependencies: List[str] = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.dependencies is None:
            self.dependencies = []

@dataclass
class QAPlan:
    """Complete QA test plan"""
    plan_id: str
    goal: str
    steps: List[PlanStep]
    estimated_duration: float
    created_at: float
    updated_at: float
    status: str = "pending"  # "pending", "executing", "completed", "failed", "replanning"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [step.__dict__ for step in self.steps],
            "estimated_duration": self.estimated_duration,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status
        }

class PlannerAgent(BaseAgent):
    """
    Planner Agent - Parses high-level QA goals and decomposes them into subgoals
    """
    
    def __init__(self, agent_id: str, llm_config: Dict[str, Any], message_bus=None):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.PLANNER,
            llm_config=llm_config,
            message_bus=message_bus
        )
        
        # Initialize LLM client
        self.llm_client = LLMClient(llm_config)
        
        # Planning state
        self.current_plans: Dict[str, QAPlan] = {}
        self.plan_templates = self._load_plan_templates()
        
        # Add message handlers specific to planner
        self.message_handlers.update({
            MessageType.PLANNING_REQUEST: self._handle_planning_request,
            MessageType.EXECUTION_RESPONSE: self._handle_execution_response,
            MessageType.VERIFICATION_RESPONSE: self._handle_verification_response,
        })
        
        self.logger.info("Planner Agent initialized")
    
    def _load_plan_templates(self) -> Dict[str, Any]:
        """Load plan templates for common QA scenarios"""
        return {
            "wifi_toggle": {
                "pattern": "wifi|wi-fi|wireless",
                "template": [
                    {"action": "navigate", "target": "settings"},
                    {"action": "navigate", "target": "wifi_settings"},
                    {"action": "interact", "target": "wifi_toggle"},
                    {"action": "verify", "expected": "wifi_state_changed"},
                    {"action": "interact", "target": "wifi_toggle"},
                    {"action": "verify", "expected": "wifi_state_restored"}
                ]
            },
            "alarm_management": {
                "pattern": "alarm|clock|timer",
                "template": [
                    {"action": "navigate", "target": "clock_app"},
                    {"action": "interact", "target": "add_alarm"},
                    {"action": "interact", "target": "set_time"},
                    {"action": "interact", "target": "save_alarm"},
                    {"action": "verify", "expected": "alarm_created"}
                ]
            },
            "email_search": {
                "pattern": "email|mail|message",
                "template": [
                    {"action": "navigate", "target": "email_app"},
                    {"action": "interact", "target": "search_box"},
                    {"action": "interact", "target": "enter_search_term"},
                    {"action": "verify", "expected": "search_results_displayed"}
                ]
            }
        }
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute planning task"""
        try:
            goal = task.get("goal", "")
            context = task.get("context", {})
            
            self.logger.info(f"Creating plan for goal: {goal}")
            
            # Create plan
            plan = await self._create_plan(goal, context)
            
            # Store plan
            self.current_plans[plan.plan_id] = plan
            
            # Send plan to executor
            await self._send_plan_to_executor(plan)
            
            return {
                "status": "success",
                "plan_id": plan.plan_id,
                "plan": plan.to_dict()
            }
            
        except Exception as e:
            self.logger.error(f"Error executing planning task: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _create_plan(self, goal: str, context: Dict[str, Any]) -> QAPlan:
        """Create a detailed QA plan from high-level goal"""
        plan_id = f"plan_{int(time.time() * 1000)}"
        
        # Check if we have a template for this goal
        template_steps = self._match_template(goal)
        
        if template_steps:
            self.logger.info(f"Using template for goal: {goal}")
            steps = await self._refine_template_steps(template_steps, goal, context)
        else:
            self.logger.info(f"Generating custom plan for goal: {goal}")
            steps = await self._generate_custom_plan(goal, context)
        
        plan = QAPlan(
            plan_id=plan_id,
            goal=goal,
            steps=steps,
            estimated_duration=len(steps) * 5.0,  # Rough estimate: 5 seconds per step
            created_at=time.time(),
            updated_at=time.time()
        )
        
        return plan
    
    def _match_template(self, goal: str) -> Optional[List[Dict[str, Any]]]:
        """Match goal against predefined templates"""
        goal_lower = goal.lower()
        
        for template_name, template_data in self.plan_templates.items():
            if any(pattern in goal_lower for pattern in template_data["pattern"].split("|")):
                self.logger.info(f"Matched template: {template_name}")
                return template_data["template"]
        
        return None
    
    async def _refine_template_steps(
        self, 
        template_steps: List[Dict[str, Any]], 
        goal: str, 
        context: Dict[str, Any]
    ) -> List[PlanStep]:
        """Refine template steps using LLM"""
        
        prompt = self._build_refinement_prompt(template_steps, goal, context)
        
        try:
            response = await self.llm_client.generate_response(prompt)
            refined_steps = self._parse_llm_steps(response)
            return refined_steps
            
        except Exception as e:
            self.logger.warning(f"LLM refinement failed, using template: {e}")
            # Fallback to template
            return self._convert_template_to_steps(template_steps)
    
    async def _generate_custom_plan(self, goal: str, context: Dict[str, Any]) -> List[PlanStep]:
        """Generate custom plan using LLM"""
        
        prompt = self._build_custom_plan_prompt(goal, context)
        
        try:
            response = await self.llm_client.generate_response(prompt)
            steps = self._parse_llm_steps(response)
            return steps
            
        except Exception as e:
            self.logger.error(f"Custom plan generation failed: {e}")
            # Fallback to basic steps
            return self._create_fallback_plan(goal)
    
    def _build_refinement_prompt(
        self, 
        template_steps: List[Dict[str, Any]], 
        goal: str, 
        context: Dict[str, Any]
    ) -> str:
        """Build prompt for refining template steps"""
        
        template_str = json.dumps(template_steps, indent=2)
        context_str = json.dumps(context, indent=2)
        
        return f"""
You are a QA test planner for Android applications. Refine the following template steps for the specific goal.

Goal: {goal}
Context: {context_str}

Template Steps:
{template_str}

Please refine these steps to be more specific and actionable. Return a JSON array of steps with this format:
[
  {{
    "step_id": "step_001",
    "description": "Detailed description",
    "action_type": "navigate|interact|verify|wait",
    "target_element": "specific UI element",
    "expected_state": "expected outcome",
    "parameters": {{"key": "value"}}
  }}
]

Focus on:
1. Specific UI elements and their expected locations
2. Clear verification criteria
3. Handling of potential modal states or interruptions
4. Recovery actions if steps fail

Return only the JSON array, no additional text.
"""
    
    def _build_custom_plan_prompt(self, goal: str, context: Dict[str, Any]) -> str:
        """Build prompt for custom plan generation"""
        
        context_str = json.dumps(context, indent=2)
        
        return f"""
You are a QA test planner for Android applications. Create a detailed test plan for the following goal.

Goal: {goal}
Context: {context_str}

Create a step-by-step plan that thoroughly tests this functionality. Return a JSON array of steps with this format:
[
  {{
    "step_id": "step_001",
    "description": "Detailed description",
    "action_type": "navigate|interact|verify|wait",
    "target_element": "specific UI element",
    "expected_state": "expected outcome",
    "parameters": {{"key": "value"}}
  }}
]

Guidelines:
1. Start with navigation to the relevant app/screen
2. Include verification steps after each major action
3. Test both positive and negative scenarios where applicable
4. Consider edge cases (popups, permissions, network issues)
5. End with verification that the goal was achieved

Return only the JSON array, no additional text.
"""
    
    def _parse_llm_steps(self, response: str) -> List[PlanStep]:
        """Parse LLM response into PlanStep objects"""
        try:
            # Clean up response (remove markdown formatting if present)
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            
            steps_data = json.loads(clean_response)
            
            steps = []
            for i, step_data in enumerate(steps_data):
                step = PlanStep(
                    step_id=step_data.get("step_id", f"step_{i+1:03d}"),
                    description=step_data.get("description", ""),
                    action_type=step_data.get("action_type", "interact"),
                    target_element=step_data.get("target_element"),
                    expected_state=step_data.get("expected_state"),
                    parameters=step_data.get("parameters", {}),
                    dependencies=step_data.get("dependencies", [])
                )
                steps.append(step)
            
            return steps
            
        except Exception as e:
            self.logger.error(f"Failed to parse LLM steps: {e}")
            return self._create_fallback_plan("unknown goal")
    
    def _convert_template_to_steps(self, template_steps: List[Dict[str, Any]]) -> List[PlanStep]:
        """Convert template format to PlanStep objects"""
        steps = []
        for i, template_step in enumerate(template_steps):
            step = PlanStep(
                step_id=f"step_{i+1:03d}",
                description=f"{template_step['action']} {template_step.get('target', '')}",
                action_type=template_step["action"],
                target_element=template_step.get("target"),
                expected_state=template_step.get("expected"),
                parameters=template_step.get("parameters", {})
            )
            steps.append(step)
        return steps
    
    def _create_fallback_plan(self, goal: str) -> List[PlanStep]:
        """Create a basic fallback plan"""
        return [
            PlanStep(
                step_id="step_001",
                description=f"Navigate to app for goal: {goal}",
                action_type="navigate",
                target_element="home_screen"
            ),
            PlanStep(
                step_id="step_002", 
                description="Perform main action",
                action_type="interact",
                target_element="primary_button"
            ),
            PlanStep(
                step_id="step_003",
                description="Verify result",
                action_type="verify",
                expected_state="action_completed"
            )
        ]
    
    async def _send_plan_to_executor(self, plan: QAPlan):
        """Send plan to executor agent"""
        try:
            await self.send_message(
                receiver="executor_agent",
                message_type=MessageType.EXECUTION_REQUEST,
                content={
                    "plan_id": plan.plan_id,
                    "plan": plan.to_dict(),
                    "action": "execute_plan"
                }
            )
            
            plan.status = "executing"
            plan.updated_at = time.time()
            
            self.logger.info(f"Sent plan {plan.plan_id} to executor")
            
        except Exception as e:
            self.logger.error(f"Failed to send plan to executor: {e}")
    
    async def replan(self, plan_id: str, feedback: Dict[str, Any]) -> QAPlan:
        """Replan based on feedback from verifier or executor"""
        try:
            original_plan = self.current_plans.get(plan_id)
            if not original_plan:
                raise ValueError(f"Plan {plan_id} not found")
            
            self.logger.info(f"Replanning for plan {plan_id} based on feedback")
            
            # Update plan based on feedback
            updated_plan = await self._update_plan_with_feedback(original_plan, feedback)
            
            # Store updated plan
            self.current_plans[plan_id] = updated_plan
            
            # Send updated plan to executor
            await self._send_plan_to_executor(updated_plan)
            
            return updated_plan
            
        except Exception as e:
            self.logger.error(f"Replanning failed: {e}")
            raise
    
    async def _update_plan_with_feedback(self, plan: QAPlan, feedback: Dict[str, Any]) -> QAPlan:
        """Update plan based on feedback"""
        
        feedback_type = feedback.get("type", "error")
        current_step = feedback.get("current_step", 0)
        issue = feedback.get("issue", "")
        
        # Create prompt for replanning
        prompt = f"""
You are a QA test planner. The following plan encountered an issue and needs to be updated:

Original Goal: {plan.goal}
Current Step Index: {current_step}
Issue Encountered: {issue}
Feedback Type: {feedback_type}

Original Plan Steps:
{json.dumps([step.__dict__ for step in plan.steps], indent=2)}

Please provide an updated plan that addresses this issue. You can:
1. Modify existing steps
2. Add new steps to handle the issue
3. Remove problematic steps
4. Add recovery actions

Return a JSON array of updated steps with the same format as the original.
"""
        
        try:
            response = await self.llm_client.generate_response(prompt)
            updated_steps = self._parse_llm_steps(response)
            
            # Create updated plan
            updated_plan = QAPlan(
                plan_id=plan.plan_id,
                goal=plan.goal,
                steps=updated_steps,
                estimated_duration=len(updated_steps) * 5.0,
                created_at=plan.created_at,
                updated_at=time.time(),
                status="replanning"
            )
            
            return updated_plan
            
        except Exception as e:
            self.logger.error(f"Failed to update plan with feedback: {e}")
            # Return original plan with status update
            plan.status = "failed"
            plan.updated_at = time.time()
            return plan
    
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
    
    async def _handle_planning_request(self, message: AgentMessage):
        """Handle planning request message"""
        try:
            content = message.content
            action = content.get("action")
            
            if action == "create_plan":
                goal = content.get("goal", "")
                context = content.get("context", {})
                result = await self.execute_task({"goal": goal, "context": context})
                
            elif action == "replan":
                plan_id = content.get("plan_id")
                feedback = content.get("feedback", {})
                updated_plan = await self.replan(plan_id, feedback)
                result = {
                    "status": "success",
                    "plan_id": plan_id,
                    "plan": updated_plan.to_dict()
                }
                
            else:
                result = {"status": "error", "error": f"Unknown action: {action}"}
            
            # Send response
            await self.send_message(
                receiver=message.sender,
                message_type=MessageType.PLANNING_RESPONSE,
                content=result,
                correlation_id=message.correlation_id
            )
            
        except Exception as e:
            self.logger.error(f"Error handling planning request: {e}")
            await self._send_error_response(message, str(e))
    
    async def _handle_execution_response(self, message: AgentMessage):
        """Handle execution response from executor"""
        try:
            content = message.content
            plan_id = content.get("plan_id")
            status = content.get("status")
            
            if plan_id in self.current_plans:
                plan = self.current_plans[plan_id]
                
                if status == "step_failed":
                    # Trigger replanning
                    feedback = content.get("feedback", {})
                    await self.replan(plan_id, feedback)
                    
                elif status == "completed":
                    plan.status = "completed"
                    plan.updated_at = time.time()
                    self.logger.info(f"Plan {plan_id} completed successfully")
                    
        except Exception as e:
            self.logger.error(f"Error handling execution response: {e}")
    
    async def _handle_verification_response(self, message: AgentMessage):
        """Handle verification response from verifier"""
        try:
            content = message.content
            plan_id = content.get("plan_id")
            verification_result = content.get("result")
            
            if plan_id in self.current_plans and verification_result == "failed":
                # Trigger replanning based on verification failure
                feedback = content.get("feedback", {})
                await self.replan(plan_id, feedback)
                
        except Exception as e:
            self.logger.error(f"Error handling verification response: {e}")
    
    def get_current_plans(self) -> Dict[str, Dict[str, Any]]:
        """Get all current plans"""
        return {
            plan_id: plan.to_dict() 
            for plan_id, plan in self.current_plans.items()
        }