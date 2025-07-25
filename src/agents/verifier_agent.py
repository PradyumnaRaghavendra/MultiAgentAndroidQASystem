"""
Verifier Agent for QualGent Multi-Agent QA System
Determines whether the app behaves as expected after each step
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from src.agents.base_agent import BaseAgent, AgentType, MessageType, AgentMessage
from src.llm.llm_client import LLMClient

class VerificationResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    BUG_DETECTED = "bug_detected"
    INCONCLUSIVE = "inconclusive"

@dataclass
class VerificationReport:
    """Detailed verification result"""
    result: VerificationResult
    step_id: str
    target_element: str
    expected_state: str
    actual_state: str
    confidence: float
    issues_found: List[str]
    bug_type: Optional[str] = None
    recovery_suggestion: Optional[str] = None
    ui_analysis: Dict[str, Any] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.ui_analysis is None:
            self.ui_analysis = {}

class VerifierAgent(BaseAgent):
    """
    Verifier Agent - Determines whether the app behaves as expected after each step
    """
    
    def __init__(self, agent_id: str, llm_config: Dict[str, Any], message_bus=None):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.VERIFIER,
            llm_config=llm_config,
            message_bus=message_bus
        )
        
        # Initialize LLM client
        self.llm_client = LLMClient(llm_config)
        
        # Verification state
        self.verification_history: List[VerificationReport] = []
        self.current_verification: Optional[VerificationReport] = None
        
        # Bug detection patterns
        self.bug_patterns = self._load_bug_patterns()
        
        # Heuristics for common UI states
        self.ui_heuristics = self._load_ui_heuristics()
        
        # Add message handlers specific to verifier
        self.message_handlers.update({
            MessageType.VERIFICATION_REQUEST: self._handle_verification_request,
            MessageType.EXECUTION_RESPONSE: self._handle_execution_response,
        })
        
        self.logger.info("Verifier Agent initialized")
    
    def _load_bug_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Load common bug detection patterns"""
        return {
            "missing_screen": {
                "indicators": ["error", "not found", "unavailable", "crashed"],
                "description": "Expected screen or element is missing",
                "severity": "high"
            },
            "wrong_toggle_state": {
                "indicators": ["enabled", "disabled", "on", "off", "checked", "unchecked"],
                "description": "Toggle state doesn't match expectation",
                "severity": "medium"
            },
            "permission_dialog": {
                "indicators": ["allow", "deny", "permission", "access"],
                "description": "Unexpected permission dialog appeared",
                "severity": "low"
            },
            "network_error": {
                "indicators": ["no connection", "network error", "timeout", "offline"],  
                "description": "Network connectivity issue",
                "severity": "high"
            },
            "app_crash": {
                "indicators": ["has stopped", "isn't responding", "force close", "crash"],
                "description": "Application crashed or stopped responding",
                "severity": "critical"
            },
            "loading_timeout": {
                "indicators": ["loading", "please wait", "processing"],
                "description": "UI stuck in loading state",
                "severity": "medium"
            }
        }
    
    def _load_ui_heuristics(self) -> Dict[str, Dict[str, Any]]:
        """Load heuristics for common UI state verification"""
        return {
            "wifi_enabled": {
                "positive_indicators": ["connected", "wifi on", "enabled", "active"],
                "negative_indicators": ["disconnected", "wifi off", "disabled", "inactive"],
                "ui_elements": ["wifi_toggle", "wifi_switch", "wireless"]
            },
            "wifi_disabled": {
                "positive_indicators": ["disconnected", "wifi off", "disabled", "inactive"],
                "negative_indicators": ["connected", "wifi on", "enabled", "active"],
                "ui_elements": ["wifi_toggle", "wifi_switch", "wireless"]
            },
            "settings_opened": {
                "positive_indicators": ["settings", "preferences", "configuration"],
                "negative_indicators": ["home", "launcher", "desktop"],
                "ui_elements": ["settings_list", "preference_screen"]
            },
            "alarm_created": {
                "positive_indicators": ["alarm set", "scheduled", "active alarm"],
                "negative_indicators": ["no alarms", "inactive", "disabled"],
                "ui_elements": ["alarm_list", "alarm_item", "time_display"]
            }
        }
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute verification task"""
        try:
            action = task.get("action", "verify")
            
            if action == "verify_step":
                return await self._verify_step(task)
            elif action == "detect_bugs":
                return await self._detect_bugs(task)
            elif action == "analyze_ui_state":
                return await self._analyze_ui_state(task)
            else:
                return {
                    "status": "error",
                    "error": f"Unknown verification action: {action}"
                }
                
        except Exception as e:
            self.logger.error(f"Error executing verification task: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _verify_step(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Verify a single step execution"""
        try:
            # Extract verification parameters
            planner_goal = task.get("planner_goal", "")
            executor_result = task.get("executor_result", {})
            ui_state = task.get("ui_state", {})
            step_info = task.get("step_info", {})
            
            target_element = step_info.get("target_element", "")
            expected_state = step_info.get("expected_state", "")
            step_id = step_info.get("step_id", "unknown")
            
            self.logger.info(f"Verifying step {step_id}: {target_element} should be {expected_state}")
            
            # Perform verification using multiple approaches
            heuristic_result = await self._verify_with_heuristics(
                target_element, expected_state, ui_state
            )
            
            llm_result = await self._verify_with_llm(
                target_element, expected_state, ui_state, planner_goal
            )
            
            bug_detection = await self._detect_bugs_in_state(ui_state, step_info)
            
            # Combine results
            verification_report = self._combine_verification_results(
                step_id, target_element, expected_state,
                heuristic_result, llm_result, bug_detection, ui_state
            )
            
            # Store verification
            self.current_verification = verification_report
            self.verification_history.append(verification_report)
            
            # Trigger replanning if needed
            if verification_report.result in [VerificationResult.FAIL, VerificationResult.BUG_DETECTED]:
                await self._trigger_replanning(verification_report, planner_goal)
            
            return {
                "status": "success",
                "verification_result": verification_report.result.value,
                "confidence": verification_report.confidence,
                "issues_found": verification_report.issues_found,
                "bug_type": verification_report.bug_type,
                "recovery_suggestion": verification_report.recovery_suggestion,
                "report": verification_report.__dict__
            }
            
        except Exception as e:
            self.logger.error(f"Error verifying step: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _verify_with_heuristics(
        self, 
        target_element: str, 
        expected_state: str, 
        ui_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verify using predefined heuristics"""
        try:
            expected_lower = expected_state.lower()
            
            # Check if we have heuristics for this expected state
            if expected_lower in self.ui_heuristics:
                heuristics = self.ui_heuristics[expected_lower]
                return await self._apply_heuristics(heuristics, ui_state, target_element)
            
            # Generic heuristic verification
            return await self._generic_heuristic_verification(
                target_element, expected_state, ui_state
            )
            
        except Exception as e:
            self.logger.error(f"Heuristic verification failed: {e}")
            return {
                "result": "inconclusive",
                "confidence": 0.0,
                "reason": f"Heuristic error: {str(e)}"
            }
    
    async def _apply_heuristics(
        self, 
        heuristics: Dict[str, Any], 
        ui_state: Dict[str, Any], 
        target_element: str
    ) -> Dict[str, Any]:
        """Apply specific heuristics to UI state"""
        try:
            ui_elements = ui_state.get("ui_hierarchy", {}).get("nodes", [])
            if not ui_elements:
                return {
                    "result": "inconclusive",
                    "confidence": 0.0,
                    "reason": "No UI elements found"
                }
            
            positive_indicators = heuristics.get("positive_indicators", [])
            negative_indicators = heuristics.get("negative_indicators", [])
            relevant_elements = heuristics.get("ui_elements", [])
            
            # Extract text from UI elements
            ui_text = []
            for element in ui_elements:
                text = element.get("text", "").lower()
                desc = element.get("content_description", "").lower()
                resource_id = element.get("resource_id", "").lower()
                ui_text.extend([text, desc, resource_id])
            
            all_ui_text = " ".join(ui_text)
            
            # Check positive indicators
            positive_matches = sum(1 for indicator in positive_indicators 
                                 if indicator in all_ui_text)
            
            # Check negative indicators  
            negative_matches = sum(1 for indicator in negative_indicators
                                 if indicator in all_ui_text)
            
            # Calculate confidence
            total_indicators = len(positive_indicators) + len(negative_indicators)
            if total_indicators == 0:
                confidence = 0.5
            else:
                confidence = (positive_matches * 2 - negative_matches) / (total_indicators * 2)
                confidence = max(0.0, min(1.0, confidence))
            
            # Determine result
            if positive_matches > 0 and negative_matches == 0:
                result = "pass"
            elif negative_matches > 0 and positive_matches == 0:
                result = "fail"
            elif positive_matches > negative_matches:
                result = "pass"
            elif negative_matches > positive_matches:
                result = "fail"
            else:
                result = "inconclusive"
            
            return {
                "result": result,
                "confidence": confidence,
                "positive_matches": positive_matches,
                "negative_matches": negative_matches,
                "analysis": f"Found {positive_matches} positive and {negative_matches} negative indicators"
            }
            
        except Exception as e:
            return {
                "result": "inconclusive",
                "confidence": 0.0,
                "reason": f"Heuristic application error: {str(e)}"
            }
    
    async def _generic_heuristic_verification(
        self, 
        target_element: str, 
        expected_state: str, 
        ui_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generic heuristic verification for unknown states"""
        try:
            ui_elements = ui_state.get("ui_hierarchy", {}).get("nodes", [])
            
            target_lower = target_element.lower()
            expected_lower = expected_state.lower()
            
            # Find target element in UI
            target_found = False
            target_properties = {}
            
            for element in ui_elements:
                text = element.get("text", "").lower()
                desc = element.get("content_description", "").lower()
                resource_id = element.get("resource_id", "").lower()
                
                if (target_lower in text or target_lower in desc or target_lower in resource_id):
                    target_found = True
                    target_properties = element
                    break
            
            if not target_found:
                return {
                    "result": "fail",
                    "confidence": 0.8,
                    "reason": f"Target element '{target_element}' not found in UI"
                }
            
            # Check if expected state matches element properties
            state_match = self._check_element_state_match(target_properties, expected_state)
            
            return {
                "result": "pass" if state_match else "fail",
                "confidence": 0.7,
                "element_found": target_found,
                "element_properties": target_properties,
                "state_analysis": state_match
            }
            
        except Exception as e:
            return {
                "result": "inconclusive",
                "confidence": 0.0,
                "reason": f"Generic verification error: {str(e)}"
            }
    
    def _check_element_state_match(
        self, 
        element: Dict[str, Any], 
        expected_state: str
    ) -> bool:
        """Check if element state matches expectation"""
        try:
            expected_lower = expected_state.lower()
            
            # Check common state properties
            if "enabled" in expected_lower:
                return element.get("enabled", True)
            elif "disabled" in expected_lower:
                return not element.get("enabled", True)
            elif "checked" in expected_lower or "on" in expected_lower:
                return element.get("checked", False)
            elif "unchecked" in expected_lower or "off" in expected_lower:
                return not element.get("checked", False)
            elif "visible" in expected_lower:
                return element.get("visible", True)
            elif "hidden" in expected_lower:
                return not element.get("visible", True)
            else:
                # Generic text matching
                text = element.get("text", "").lower()
                desc = element.get("content_description", "").lower()
                return expected_lower in text or expected_lower in desc
                
        except Exception as e:
            self.logger.error(f"Error checking element state: {e}")
            return False
    
    async def _verify_with_llm(
        self, 
        target_element: str, 
        expected_state: str, 
        ui_state: Dict[str, Any],
        planner_goal: str
    ) -> Dict[str, Any]:
        """Verify using LLM reasoning"""
        try:
            # Create verification prompt
            prompt = self._build_verification_prompt(
                target_element, expected_state, ui_state, planner_goal
            )
            
            response = await self.llm_client.generate_response(prompt)
            
            # Parse LLM response
            return self._parse_llm_verification_response(response)
            
        except Exception as e:
            self.logger.error(f"LLM verification failed: {e}")
            return {
                "result": "inconclusive",
                "confidence": 0.0,
                "reason": f"LLM verification error: {str(e)}"
            }
    
    def _build_verification_prompt(
        self, 
        target_element: str, 
        expected_state: str, 
        ui_state: Dict[str, Any],
        planner_goal: str
    ) -> str:
        """Build prompt for LLM verification"""
        
        ui_elements = ui_state.get("ui_hierarchy", {}).get("nodes", [])[:15]  # Limit for tokens
        ui_summary = self._format_ui_elements_for_prompt(ui_elements)
        
        return f"""
You are a QA verification expert analyzing an Android UI state after an action.

CONTEXT:
- Overall Goal: {planner_goal}
- Target Element: {target_element}
- Expected State: {expected_state}

CURRENT UI STATE:
{ui_summary}

TASK:
Determine if the current UI state matches the expected state for the target element.

Consider:
1. Is the target element present and in the expected state?
2. Are there any UI indicators that contradict the expected state?
3. Are there any error messages, dialogs, or unexpected screens?
4. Does the overall UI context make sense for the expected state?

Respond in JSON format:
{{
    "result": "pass" | "fail" | "inconclusive",
    "confidence": 0.0-1.0,
    "reasoning": "Detailed explanation",
    "issues_found": ["list", "of", "any", "issues"],
    "suggestions": "What should be done if verification failed"
}}

Respond only with the JSON, no additional text.
"""
    
    def _format_ui_elements_for_prompt(self, ui_elements: List[Dict[str, Any]]) -> str:
        """Format UI elements for LLM prompt"""
        try:
            formatted = []
            for i, element in enumerate(ui_elements):
                text = element.get("text", "")
                desc = element.get("content_description", "")
                resource_id = element.get("resource_id", "")
                checked = element.get("checked")
                enabled = element.get("enabled", True)
                
                element_info = f"{i+1}. "
                if text:
                    element_info += f'Text: "{text}"'
                elif desc:
                    element_info += f'Description: "{desc}"'
                elif resource_id:
                    element_info += f'ID: "{resource_id}"'
                else:
                    element_info += f'Element: {element.get("class", "Unknown")}'
                
                if checked is not None:
                    element_info += f" (checked: {checked})"
                if not enabled:
                    element_info += " (disabled)"
                
                formatted.append(element_info)
            
            return "\n".join(formatted)
            
        except Exception as e:
            return f"Error formatting UI elements: {str(e)}"
    
    def _parse_llm_verification_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM verification response"""
        try:
            # Clean response
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            
            parsed = json.loads(clean_response)
            
            return {
                "result": parsed.get("result", "inconclusive"),
                "confidence": float(parsed.get("confidence", 0.0)),
                "reasoning": parsed.get("reasoning", ""),
                "issues_found": parsed.get("issues_found", []),
                "suggestions": parsed.get("suggestions", "")
            }
            
        except Exception as e:
            self.logger.error(f"Error parsing LLM response: {e}")
            return {
                "result": "inconclusive",
                "confidence": 0.0,
                "reason": f"LLM response parsing error: {str(e)}"
            }
    
    async def _detect_bugs_in_state(
        self, 
        ui_state: Dict[str, Any], 
        step_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Detect bugs in current UI state"""
        try:
            ui_elements = ui_state.get("ui_hierarchy", {}).get("nodes", [])
            
            # Extract all text for pattern matching
            all_text = []
            for element in ui_elements:
                text = element.get("text", "").lower()
                desc = element.get("content_description", "").lower()
                if text:
                    all_text.append(text)
                if desc:
                    all_text.append(desc)
            
            combined_text = " ".join(all_text)
            
            # Check against bug patterns
            bugs_detected = []
            for bug_type, pattern in self.bug_patterns.items():
                indicators = pattern["indicators"]
                
                for indicator in indicators:
                    if indicator in combined_text:
                        bugs_detected.append({
                            "type": bug_type,
                            "indicator": indicator,
                            "severity": pattern["severity"],
                            "description": pattern["description"]
                        })
                        break
            
            return {
                "bugs_found": len(bugs_detected) > 0,
                "bug_count": len(bugs_detected),
                "bugs": bugs_detected,
                "analysis": f"Detected {len(bugs_detected)} potential issues"
            }
            
        except Exception as e:
            self.logger.error(f"Bug detection failed: {e}")
            return {
                "bugs_found": False,
                "bug_count": 0,
                "bugs": [],
                "error": str(e)
            }
    
    def _combine_verification_results(
        self,
        step_id: str,
        target_element: str, 
        expected_state: str,
        heuristic_result: Dict[str, Any],
        llm_result: Dict[str, Any],
        bug_detection: Dict[str, Any],
        ui_state: Dict[str, Any]
    ) -> VerificationReport:
        """Combine multiple verification results into final report"""
        try:
            # Determine overall result
            heuristic_pass = heuristic_result.get("result") == "pass"
            llm_pass = llm_result.get("result") == "pass"
            bugs_found = bug_detection.get("bugs_found", False)
            
            if bugs_found:
                final_result = VerificationResult.BUG_DETECTED
            elif heuristic_pass and llm_pass:
                final_result = VerificationResult.PASS
            elif not heuristic_pass and not llm_pass:
                final_result = VerificationResult.FAIL
            else:
                # Mixed results - use confidence to decide
                heuristic_conf = heuristic_result.get("confidence", 0.0)
                llm_conf = llm_result.get("confidence", 0.0)
                
                if heuristic_conf > llm_conf:
                    final_result = VerificationResult.PASS if heuristic_pass else VerificationResult.FAIL
                else:
                    final_result = VerificationResult.PASS if llm_pass else VerificationResult.FAIL
            
            # Calculate combined confidence
            heuristic_conf = heuristic_result.get("confidence", 0.0)
            llm_conf = llm_result.get("confidence", 0.0)
            combined_confidence = (heuristic_conf + llm_conf) / 2
            
            # Collect issues
            issues_found = []
            issues_found.extend(heuristic_result.get("issues_found", []))
            issues_found.extend(llm_result.get("issues_found", []))
            
            if bugs_found:
                for bug in bug_detection.get("bugs", []):
                    issues_found.append(f"{bug['type']}: {bug['description']}")
            
            # Determine bug type and recovery suggestion
            bug_type = None
            recovery_suggestion = None
            
            if bugs_found:
                primary_bug = bug_detection["bugs"][0]
                bug_type = primary_bug["type"]
                recovery_suggestion = self._get_recovery_suggestion(bug_type, step_id)
            elif final_result == VerificationResult.FAIL:
                recovery_suggestion = llm_result.get("suggestions", "Retry the step or adjust the approach")
            
            # Get actual state description
            actual_state = self._describe_actual_state(ui_state, target_element)
            
            return VerificationReport(
                result=final_result,
                step_id=step_id,
                target_element=target_element,
                expected_state=expected_state,
                actual_state=actual_state,
                confidence=combined_confidence,
                issues_found=issues_found,
                bug_type=bug_type,
                recovery_suggestion=recovery_suggestion,
                ui_analysis={
                    "heuristic_result": heuristic_result,
                    "llm_result": llm_result,
                    "bug_detection": bug_detection
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error combining verification results: {e}")
            return VerificationReport(
                result=VerificationResult.INCONCLUSIVE,
                step_id=step_id,
                target_element=target_element,
                expected_state=expected_state,
                actual_state="Error analyzing state",
                confidence=0.0,
                issues_found=[f"Verification error: {str(e)}"],
                recovery_suggestion="Manual intervention required"
            )
    
    def _describe_actual_state(self, ui_state: Dict[str, Any], target_element: str) -> str:
        """Describe the actual state found in UI"""
        try:
            ui_elements = ui_state.get("ui_hierarchy", {}).get("nodes", [])
            target_lower = target_element.lower()
            
            # Find target element
            for element in ui_elements:
                text = element.get("text", "").lower()
                desc = element.get("content_description", "").lower()
                resource_id = element.get("resource_id", "").lower()
                
                if (target_lower in text or target_lower in desc or target_lower in resource_id):
                    # Describe element state
                    state_parts = []
                    
                    if element.get("text"):
                        state_parts.append(f"text: '{element['text']}'")
                    if element.get("checked") is not None:
                        state_parts.append(f"checked: {element['checked']}")
                    if not element.get("enabled", True):
                        state_parts.append("disabled")
                    if not element.get("visible", True):
                        state_parts.append("hidden")
                    
                    if state_parts:
                        return f"Element found with {', '.join(state_parts)}"
                    else:
                        return "Element found but state unclear"
            
            return f"Target element '{target_element}' not found in current UI"
            
        except Exception as e:
            return f"Error describing actual state: {str(e)}"
    
    def _get_recovery_suggestion(self, bug_type: str, step_id: str) -> str:
        """Get recovery suggestion for detected bug"""
        suggestions = {
            "missing_screen": "Navigate back and retry, or check if prerequisite steps were completed",
            "wrong_toggle_state": "Tap the toggle again to change state, or verify the correct element was targeted",
            "permission_dialog": "Handle the permission dialog (allow/deny) and retry the step",
            "network_error": "Check network connectivity and retry the step",
            "app_crash": "Restart the application and retry from beginning",
            "loading_timeout": "Wait longer for loading to complete, or restart the step"
        }
        
        return suggestions.get(bug_type, "Manual intervention required to resolve the issue")
    
    async def _trigger_replanning(
        self, 
        verification_report: VerificationReport, 
        planner_goal: str
    ) -> None:
        """Trigger replanning when verification fails"""
        try:
            self.logger.info(f"Triggering replanning due to verification {verification_report.result.value}")
            
            # Send replanning request to planner
            await self.send_message(
                receiver="planner_agent",
                message_type=MessageType.PLANNING_REQUEST,
                content={
                    "action": "replan",
                    "plan_id": "current_plan",  # This should be tracked better
                    "feedback": {
                        "type": "verification_failure",
                        "step_id": verification_report.step_id,
                        "issue": verification_report.issues_found,
                        "bug_type": verification_report.bug_type,
                        "recovery_suggestion": verification_report.recovery_suggestion,
                        "verification_report": verification_report.__dict__
                    }
                }
            )
            
            self.logger.info("Replanning request sent to planner")
            
        except Exception as e:
            self.logger.error(f"Error triggering replanning: {e}")
    
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
    
    async def _handle_verification_request(self, message: AgentMessage):
        """Handle verification request from executor"""
        try:
            content = message.content
            
            # Extract verification parameters
            verification_task = {
                "action": "verify_step",
                "planner_goal": content.get("planner_goal", ""),
                "executor_result": content.get("executor_result", {}),
                "ui_state": content.get("ui_state", {}),
                "step_info": {
                    "target_element": content.get("target_element", ""),
                    "expected_state": content.get("expected_state", ""),
                    "step_id": content.get("step_id", "unknown"),
                    "parameters": content.get("parameters", {})
                }
            }
            
            result = await self._verify_step(verification_task)
            
            # Send response back to executor
            await self.send_message(
                receiver=message.sender,
                message_type=MessageType.VERIFICATION_RESPONSE,
                content=result,
                correlation_id=message.correlation_id
            )
            
        except Exception as e:
            self.logger.error(f"Error handling verification request: {e}")
            await self._send_error_response(message, str(e))
    
    async def _handle_execution_response(self, message: AgentMessage):
        """Handle execution response from executor for logging"""
        try:
            content = message.content
            self.logger.info(f"Received execution response: {content.get('status', 'unknown')}")
            
            # Log execution result for QA reporting
            # This could be expanded to trigger automatic verification
            
        except Exception as e:
            self.logger.error(f"Error handling execution response: {e}")
    
    def get_verification_history(self) -> List[Dict[str, Any]]:
        """Get verification history"""
        return [report.__dict__ for report in self.verification_history]
    
    def get_verification_summary(self) -> Dict[str, Any]:
        """Get summary of verification results"""
        if not self.verification_history:
            return {
                "total_verifications": 0,
                "pass_rate": 0.0,
                "bug_detection_rate": 0.0,
                "issues": []
            }
        
        total = len(self.verification_history)
        passed = sum(1 for report in self.verification_history 
                    if report.result == VerificationResult.PASS)
        bugs_detected = sum(1 for report in self.verification_history 
                           if report.result == VerificationResult.BUG_DETECTED)
        
        all_issues = []
        for report in self.verification_history:
            all_issues.extend(report.issues_found)
        
        return {
            "total_verifications": total,
            "pass_rate": passed / total,
            "bug_detection_rate": bugs_detected / total,
            "average_confidence": sum(report.confidence for report in self.verification_history) / total,
            "unique_issues": list(set(all_issues)),
            "latest_verification": self.current_verification.__dict__ if self.current_verification else None
        }