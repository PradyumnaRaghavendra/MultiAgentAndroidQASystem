"""
Supervisor Agent for QualGent Multi-Agent QA System
Reviews entire test episodes and proposes improvements
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from src.agents.base_agent import BaseAgent, AgentType, MessageType, AgentMessage
from src.llm.llm_client import LLMClient

@dataclass
class TestEpisode:
    """Complete test episode data"""
    episode_id: str
    goal: str
    plan: Dict[str, Any]
    execution_trace: List[Dict[str, Any]]
    verification_results: List[Dict[str, Any]]
    visual_trace: List[str]  # Paths to screenshots
    start_time: float
    end_time: float
    final_status: str  # "success", "failed", "partial"
    agents_involved: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "goal": self.goal,
            "plan": self.plan,
            "execution_trace": self.execution_trace,
            "verification_results": self.verification_results,
            "visual_trace": self.visual_trace,
            "duration": self.end_time - self.start_time,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "final_status": self.final_status,
            "agents_involved": self.agents_involved
        }

@dataclass
class EvaluationReport:
    """Comprehensive evaluation report"""
    report_id: str
    episodes_analyzed: List[str]
    bug_detection_accuracy: float
    agent_recovery_ability: float
    supervisor_feedback_effectiveness: float
    improvement_suggestions: List[str]
    failure_patterns: List[Dict[str, Any]]
    performance_metrics: Dict[str, Any]
    visual_analysis_results: List[Dict[str, Any]]
    generated_at: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "episodes_analyzed": self.episodes_analyzed,
            "metrics": {
                "bug_detection_accuracy": self.bug_detection_accuracy,
                "agent_recovery_ability": self.agent_recovery_ability,
                "supervisor_feedback_effectiveness": self.supervisor_feedback_effectiveness
            },
            "improvement_suggestions": self.improvement_suggestions,
            "failure_patterns": self.failure_patterns,
            "performance_metrics": self.performance_metrics,
            "visual_analysis_results": self.visual_analysis_results,
            "generated_at": self.generated_at,
            "generated_at_human": datetime.fromtimestamp(self.generated_at).isoformat()
        }

class SupervisorAgent(BaseAgent):
    """
    Supervisor Agent - Reviews entire test episodes and proposes improvements
    """
    
    def __init__(self, agent_id: str, llm_config: Dict[str, Any], message_bus=None):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.SUPERVISOR,
            llm_config=llm_config,
            message_bus=message_bus
        )
        
        # Initialize LLM client (preferably Gemini 2.5)
        self.llm_client = LLMClient(llm_config)
        
        # Episode tracking
        self.test_episodes: Dict[str, TestEpisode] = {}
        self.current_episode: Optional[TestEpisode] = None
        
        # Evaluation state
        self.evaluation_reports: List[EvaluationReport] = []
        self.performance_database: Dict[str, List[float]] = {
            "bug_detection_accuracy": [],
            "agent_recovery_success": [],
            "plan_completion_rate": [],
            "verification_accuracy": []
        }
        
        # Visual trace management
        self.visual_traces_dir = "outputs/visual_traces"
        os.makedirs(self.visual_traces_dir, exist_ok=True)
        
        # Add message handlers specific to supervisor
        self.message_handlers.update({
            MessageType.SUPERVISION_REQUEST: self._handle_supervision_request,
            MessageType.EXECUTION_RESPONSE: self._handle_execution_response,
            MessageType.VERIFICATION_RESPONSE: self._handle_verification_response,
        })
        
        self.logger.info("Supervisor Agent initialized")
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute supervision task"""
        try:
            action = task.get("action", "")
            
            if action == "start_episode":
                return await self._start_episode(task)
            elif action == "end_episode":
                return await self._end_episode(task)
            elif action == "analyze_episode":
                return await self._analyze_episode(task)
            elif action == "generate_report":
                return await self._generate_evaluation_report(task)
            elif action == "record_visual_trace":
                return await self._record_visual_trace(task)
            else:
                return {
                    "status": "error",
                    "error": f"Unknown supervision action: {action}"
                }
                
        except Exception as e:
            self.logger.error(f"Error executing supervision task: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _start_episode(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Start tracking a new test episode"""
        try:
            episode_id = task.get("episode_id", f"episode_{int(time.time())}")
            goal = task.get("goal", "")
            plan = task.get("plan", {})
            
            self.current_episode = TestEpisode(
                episode_id=episode_id,
                goal=goal,
                plan=plan,
                execution_trace=[],
                verification_results=[],
                visual_trace=[],
                start_time=time.time(),
                end_time=0.0,
                final_status="running",
                agents_involved=["planner", "executor", "verifier", "supervisor"]
            )
            
            self.test_episodes[episode_id] = self.current_episode
            
            self.logger.info(f"Started tracking episode {episode_id}: {goal}")
            
            return {
                "status": "success",
                "episode_id": episode_id,
                "message": "Episode tracking started"
            }
            
        except Exception as e:
            self.logger.error(f"Error starting episode: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _end_episode(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """End current episode and perform analysis"""
        try:
            if not self.current_episode:
                return {
                    "status": "error",
                    "error": "No active episode to end"
                }
            
            final_status = task.get("final_status", "completed")
            
            self.current_episode.end_time = time.time()
            self.current_episode.final_status = final_status
            
            episode_id = self.current_episode.episode_id
            
            self.logger.info(f"Ended episode {episode_id} with status: {final_status}")
            
            # Perform immediate analysis
            analysis_result = await self._analyze_current_episode()
            
            # Clear current episode
            self.current_episode = None
            
            return {
                "status": "success",
                "episode_id": episode_id,
                "final_status": final_status,
                "analysis": analysis_result
            }
            
        except Exception as e:
            self.logger.error(f"Error ending episode: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _analyze_episode(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a specific episode or current episode"""
        try:
            episode_id = task.get("episode_id")
            
            if episode_id:
                if episode_id not in self.test_episodes:
                    return {
                        "status": "error",
                        "error": f"Episode {episode_id} not found"
                    }
                episode = self.test_episodes[episode_id]
            else:
                if not self.current_episode:
                    return {
                        "status": "error",
                        "error": "No episode specified and no current episode"
                    }
                episode = self.current_episode
            
            analysis_result = await self._perform_episode_analysis(episode)
            
            return {
                "status": "success",
                "episode_id": episode.episode_id,
                "analysis": analysis_result
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing episode: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _analyze_current_episode(self) -> Dict[str, Any]:
        """Analyze the current episode"""
        if not self.current_episode:
            return {"error": "No current episode"}
        
        return await self._perform_episode_analysis(self.current_episode)
    
    async def _perform_episode_analysis(self, episode: TestEpisode) -> Dict[str, Any]:
        """Perform comprehensive analysis of an episode"""
        try:
            self.logger.info(f"Analyzing episode {episode.episode_id}")
            
            # Analyze execution trace
            execution_analysis = self._analyze_execution_trace(episode.execution_trace)
            
            # Analyze verification results
            verification_analysis = self._analyze_verification_results(episode.verification_results)
            
            # Analyze visual trace (if available)
            visual_analysis = await self._analyze_visual_trace(episode.visual_trace)
            
            # Use LLM for comprehensive analysis
            llm_analysis = await self._analyze_with_llm(episode)
            
            # Generate improvement suggestions
            improvement_suggestions = await self._generate_improvement_suggestions(
                episode, execution_analysis, verification_analysis, visual_analysis
            )
            
            # Calculate performance metrics
            performance_metrics = self._calculate_performance_metrics(
                episode, execution_analysis, verification_analysis
            )
            
            analysis_result = {
                "episode_summary": {
                    "goal": episode.goal,
                    "duration": episode.end_time - episode.start_time if episode.end_time > 0 else time.time() - episode.start_time,
                    "steps_executed": len(episode.execution_trace),
                    "verifications_performed": len(episode.verification_results),
                    "final_status": episode.final_status
                },
                "execution_analysis": execution_analysis,
                "verification_analysis": verification_analysis,
                "visual_analysis": visual_analysis,
                "llm_analysis": llm_analysis,
                "improvement_suggestions": improvement_suggestions,
                "performance_metrics": performance_metrics
            }
            
            return analysis_result
            
        except Exception as e:
            self.logger.error(f"Error performing episode analysis: {e}")
            return {
                "error": str(e),
                "partial_analysis": True
            }
    
    def _analyze_execution_trace(self, execution_trace: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze execution trace for patterns and issues"""
        try:
            if not execution_trace:
                return {
                    "total_steps": 0,
                    "success_rate": 0.0,
                    "average_execution_time": 0.0,
                    "common_failures": [],
                    "performance_issues": []
                }
            
            total_steps = len(execution_trace)
            successful_steps = sum(1 for step in execution_trace 
                                 if step.get("status") == "success")
            
            success_rate = successful_steps / total_steps if total_steps > 0 else 0.0
            
            # Calculate average execution time
            execution_times = [step.get("execution_time", 0.0) for step in execution_trace]
            average_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0.0
            
            # Identify common failure patterns
            failures = [step for step in execution_trace if step.get("status") == "failed"]
            failure_reasons = {}
            for failure in failures:
                reason = failure.get("error", "Unknown error")
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
            
            common_failures = [{"reason": reason, "count": count} 
                             for reason, count in failure_reasons.items()]
            common_failures.sort(key=lambda x: x["count"], reverse=True)
            
            # Identify performance issues
            performance_issues = []
            slow_steps = [step for step in execution_trace 
                         if step.get("execution_time", 0.0) > 5.0]
            if slow_steps:
                performance_issues.append({
                    "type": "slow_execution",
                    "count": len(slow_steps),
                    "description": f"{len(slow_steps)} steps took longer than 5 seconds"
                })
            
            return {
                "total_steps": total_steps,
                "successful_steps": successful_steps,
                "success_rate": success_rate,
                "average_execution_time": average_execution_time,
                "common_failures": common_failures,
                "performance_issues": performance_issues
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing execution trace: {e}")
            return {"error": str(e)}
    
    def _analyze_verification_results(
        self, 
        verification_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze verification results for accuracy and patterns"""
        try:
            if not verification_results:
                return {
                    "total_verifications": 0,
                    "pass_rate": 0.0,
                    "average_confidence": 0.0,
                    "bug_detection_rate": 0.0,
                    "common_issues": []
                }
            
            total_verifications = len(verification_results)
            
            # Count passes, fails, and bug detections
            passes = sum(1 for result in verification_results 
                        if result.get("verification_result") == "pass")
            fails = sum(1 for result in verification_results 
                       if result.get("verification_result") == "fail")
            bugs_detected = sum(1 for result in verification_results 
                              if result.get("verification_result") == "bug_detected")
            
            pass_rate = passes / total_verifications
            bug_detection_rate = bugs_detected / total_verifications
            
            # Calculate average confidence
            confidences = [result.get("confidence", 0.0) for result in verification_results]
            average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            # Collect common issues
            all_issues = []
            for result in verification_results:
                issues = result.get("issues_found", [])
                all_issues.extend(issues)
            
            issue_counts = {}
            for issue in all_issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1
            
            common_issues = [{"issue": issue, "count": count} 
                           for issue, count in issue_counts.items()]
            common_issues.sort(key=lambda x: x["count"], reverse=True)
            
            return {
                "total_verifications": total_verifications,
                "passes": passes,
                "fails": fails,
                "bugs_detected": bugs_detected,
                "pass_rate": pass_rate,
                "bug_detection_rate": bug_detection_rate,
                "average_confidence": average_confidence,
                "common_issues": common_issues[:5]  # Top 5 issues
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing verification results: {e}")
            return {"error": str(e)}
    
    async def _analyze_visual_trace(self, visual_trace: List[str]) -> Dict[str, Any]:
        """Analyze visual trace using LLM vision capabilities"""
        try:
            if not visual_trace:
                return {
                    "total_screenshots": 0,
                    "visual_analysis": "No visual trace available",
                    "ui_evolution": []
                }
            
            # For now, provide basic analysis
            # In a full implementation, this would use Gemini 2.5 vision capabilities
            
            total_screenshots = len(visual_trace)
            
            # Mock visual analysis
            ui_evolution = []
            for i, screenshot_path in enumerate(visual_trace):
                ui_evolution.append({
                    "step": i + 1,
                    "screenshot": screenshot_path,
                    "timestamp": time.time() + i,  # Mock timestamp
                    "analysis": f"UI state at step {i + 1}"
                })
            
            return {
                "total_screenshots": total_screenshots,
                "visual_analysis": f"Analyzed {total_screenshots} screenshots",
                "ui_evolution": ui_evolution,
                "visual_patterns": ["Mock pattern 1", "Mock pattern 2"]
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing visual trace: {e}")
            return {"error": str(e)}
    
    async def _analyze_with_llm(self, episode: TestEpisode) -> Dict[str, Any]:
        """Use LLM to analyze the complete episode"""
        try:
            # Create comprehensive analysis prompt
            prompt = self._build_episode_analysis_prompt(episode)
            
            response = await self.llm_client.generate_response(prompt)
            
            # Parse LLM response
            return self._parse_llm_episode_analysis(response)
            
        except Exception as e:
            self.logger.error(f"LLM episode analysis failed: {e}")
            return {
                "error": str(e),
                "analysis": "LLM analysis unavailable"
            }
    
    def _build_episode_analysis_prompt(self, episode: TestEpisode) -> str:
        """Build prompt for comprehensive episode analysis"""
        
        execution_summary = f"Executed {len(episode.execution_trace)} steps"
        verification_summary = f"Performed {len(episode.verification_results)} verifications"
        
        return f"""
You are an expert QA supervisor analyzing a complete test episode.

EPISODE OVERVIEW:
- Goal: {episode.goal}
- Duration: {episode.end_time - episode.start_time if episode.end_time > 0 else 'ongoing'} seconds
- Final Status: {episode.final_status}
- {execution_summary}
- {verification_summary}

EXECUTION TRACE (last 5 steps):
{json.dumps(episode.execution_trace[-5:], indent=2) if episode.execution_trace else 'No execution trace'}

VERIFICATION RESULTS:
{json.dumps(episode.verification_results, indent=2) if episode.verification_results else 'No verification results'}

ANALYSIS TASKS:
1. Evaluate the overall test execution quality
2. Identify patterns in failures and successes
3. Assess agent coordination effectiveness
4. Recommend specific improvements

Respond in JSON format:
{{
    "overall_assessment": "excellent|good|fair|poor",
    "key_findings": ["finding1", "finding2", "finding3"],
    "agent_performance": {{
        "planner": "assessment",
        "executor": "assessment", 
        "verifier": "assessment"
    }},
    "improvement_areas": ["area1", "area2"],
    "recommendations": ["rec1", "rec2", "rec3"]
}}

Respond only with JSON, no additional text.
"""
    
    def _parse_llm_episode_analysis(self, response: str) -> Dict[str, Any]:
        """Parse LLM episode analysis response"""
        try:
            # Clean response
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            
            return json.loads(clean_response)
            
        except Exception as e:
            self.logger.error(f"Error parsing LLM episode analysis: {e}")
            return {
                "overall_assessment": "inconclusive",
                "key_findings": ["LLM analysis parsing failed"],
                "agent_performance": {
                    "planner": "unable to assess",
                    "executor": "unable to assess",
                    "verifier": "unable to assess"
                },
                "improvement_areas": ["improve LLM integration"],
                "recommendations": ["fix analysis parsing"]
            }
    
    async def _generate_improvement_suggestions(
        self,
        episode: TestEpisode,
        execution_analysis: Dict[str, Any],
        verification_analysis: Dict[str, Any],
        visual_analysis: Dict[str, Any]
    ) -> List[str]:
        """Generate specific improvement suggestions"""
        try:
            suggestions = []
            
            # Based on execution analysis
            success_rate = execution_analysis.get("success_rate", 0.0)
            if success_rate < 0.8:
                suggestions.append(f"Improve execution success rate (currently {success_rate:.1%})")
            
            # Based on verification analysis
            pass_rate = verification_analysis.get("pass_rate", 0.0)
            if pass_rate < 0.7:
                suggestions.append(f"Enhance verification accuracy (currently {pass_rate:.1%})")
            
            average_confidence = verification_analysis.get("average_confidence", 0.0)
            if average_confidence < 0.6:
                suggestions.append(f"Increase verification confidence (currently {average_confidence:.2f})")
            
            # Based on common failures
            common_failures = execution_analysis.get("common_failures", [])
            if common_failures:
                top_failure = common_failures[0]
                suggestions.append(f"Address most common failure: {top_failure['reason']}")
            
            # Based on performance issues
            performance_issues = execution_analysis.get("performance_issues", [])
            if performance_issues:
                suggestions.append("Optimize execution performance for slow steps")
            
            # Generic improvements
            if episode.final_status == "failed":
                suggestions.append("Implement better error recovery mechanisms")
                suggestions.append("Add more robust fallback strategies")
            
            if len(episode.verification_results) < len(episode.execution_trace):
                suggestions.append("Ensure all execution steps are verified")
            
            return suggestions
            
        except Exception as e:
            self.logger.error(f"Error generating improvement suggestions: {e}")
            return ["Unable to generate specific suggestions due to analysis error"]
    
    def _calculate_performance_metrics(
        self,
        episode: TestEpisode,
        execution_analysis: Dict[str, Any],
        verification_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate performance metrics for the episode"""
        try:
            # Basic metrics
            total_steps = len(episode.execution_trace)
            successful_steps = execution_analysis.get("successful_steps", 0)
            step_success_rate = successful_steps / total_steps if total_steps > 0 else 0.0
            
            # Verification metrics
            total_verifications = verification_analysis.get("total_verifications", 0)
            verification_pass_rate = verification_analysis.get("pass_rate", 0.0)
            bug_detection_rate = verification_analysis.get("bug_detection_rate", 0.0)
            
            # Time metrics
            duration = episode.end_time - episode.start_time if episode.end_time > 0 else time.time() - episode.start_time
            average_step_time = duration / total_steps if total_steps > 0 else 0.0
            
            # Overall success
            overall_success = 1.0 if episode.final_status == "success" else 0.0
            
            return {
                "step_success_rate": step_success_rate,
                "verification_pass_rate": verification_pass_rate,
                "bug_detection_rate": bug_detection_rate,
                "overall_success": overall_success,
                "total_duration": duration,
                "average_step_time": average_step_time,
                "efficiency_score": successful_steps / duration if duration > 0 else 0.0,
                "quality_score": (step_success_rate + verification_pass_rate) / 2
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating performance metrics: {e}")
            return {"error": str(e)}
    
    async def _generate_evaluation_report(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive evaluation report"""
        try:
            episodes_to_analyze = task.get("episodes", list(self.test_episodes.keys()))
            
            if not episodes_to_analyze:
                return {
                    "status": "error",
                    "error": "No episodes available for evaluation"
                }
            
            self.logger.info(f"Generating evaluation report for {len(episodes_to_analyze)} episodes")
            
            # Analyze all episodes
            episode_analyses = []
            for episode_id in episodes_to_analyze:
                if episode_id in self.test_episodes:
                    analysis = await self._perform_episode_analysis(self.test_episodes[episode_id])
                    episode_analyses.append(analysis)
            
            # Calculate aggregate metrics
            aggregate_metrics = self._calculate_aggregate_metrics(episode_analyses)
            
            # Generate improvement suggestions
            overall_suggestions = self._generate_overall_suggestions(episode_analyses)
            
            # Identify failure patterns
            failure_patterns = self._identify_failure_patterns(episode_analyses)
            
            # Create evaluation report
            report = EvaluationReport(
                report_id=f"report_{int(time.time())}",
                episodes_analyzed=episodes_to_analyze,
                bug_detection_accuracy=aggregate_metrics.get("bug_detection_accuracy", 0.0),
                agent_recovery_ability=aggregate_metrics.get("agent_recovery_ability", 0.0),
                supervisor_feedback_effectiveness=aggregate_metrics.get("supervisor_feedback_effectiveness", 0.0),
                improvement_suggestions=overall_suggestions,
                failure_patterns=failure_patterns,
                performance_metrics=aggregate_metrics,
                visual_analysis_results=[],  # Would be populated with visual analysis
                generated_at=time.time()
            )
            
            self.evaluation_reports.append(report)
            
            # Save report to file
            report_path = await self._save_evaluation_report(report)
            
            return {
                "status": "success",
                "report_id": report.report_id,
                "report_path": report_path,
                "episodes_analyzed": len(episodes_to_analyze),
                "key_metrics": {
                    "bug_detection_accuracy": report.bug_detection_accuracy,
                    "agent_recovery_ability": report.agent_recovery_ability,
                    "supervisor_feedback_effectiveness": report.supervisor_feedback_effectiveness
                },
                "improvement_suggestions": report.improvement_suggestions
            }
            
        except Exception as e:
            self.logger.error(f"Error generating evaluation report: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _calculate_aggregate_metrics(self, episode_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate aggregate metrics across all episodes"""
        try:
            if not episode_analyses:
                return {}
            
            # Collect metrics from all episodes
            success_rates = []
            verification_pass_rates = []
            bug_detection_rates = []
            quality_scores = []
            
            for analysis in episode_analyses:
                exec_analysis = analysis.get("execution_analysis", {})
                verif_analysis = analysis.get("verification_analysis", {})
                perf_metrics = analysis.get("performance_metrics", {})
                
                success_rates.append(exec_analysis.get("success_rate", 0.0))
                verification_pass_rates.append(verif_analysis.get("pass_rate", 0.0))
                bug_detection_rates.append(verif_analysis.get("bug_detection_rate", 0.0))
                quality_scores.append(perf_metrics.get("quality_score", 0.0))
            
            # Calculate averages
            avg_success_rate = sum(success_rates) / len(success_rates) if success_rates else 0.0
            avg_verification_pass_rate = sum(verification_pass_rates) / len(verification_pass_rates) if verification_pass_rates else 0.0
            avg_bug_detection_rate = sum(bug_detection_rates) / len(bug_detection_rates) if bug_detection_rates else 0.0
            avg_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
            
            return {
                "bug_detection_accuracy": avg_bug_detection_rate,
                "agent_recovery_ability": avg_success_rate,  # Proxy for recovery ability
                "supervisor_feedback_effectiveness": avg_quality_score,
                "overall_success_rate": avg_success_rate,
                "verification_accuracy": avg_verification_pass_rate,
                "episodes_analyzed": len(episode_analyses)
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating aggregate metrics: {e}")
            return {"error": str(e)}
    
    def _generate_overall_suggestions(self, episode_analyses: List[Dict[str, Any]]) -> List[str]:
        """Generate overall improvement suggestions"""
        all_suggestions = []
        
        for analysis in episode_analyses:
            suggestions = analysis.get("improvement_suggestions", [])
            all_suggestions.extend(suggestions)
        
        # Count suggestion frequency
        suggestion_counts = {}
        for suggestion in all_suggestions:
            suggestion_counts[suggestion] = suggestion_counts.get(suggestion, 0) + 1
        
        # Return most common suggestions
        sorted_suggestions = sorted(suggestion_counts.items(), key=lambda x: x[1], reverse=True)
        return [suggestion for suggestion, count in sorted_suggestions[:10]]  # Top 10
    
    def _identify_failure_patterns(self, episode_analyses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify common failure patterns across episodes"""
        failure_patterns = []
        
        # Collect all failures
        all_failures = []
        for analysis in episode_analyses:
            exec_analysis = analysis.get("execution_analysis", {})
            failures = exec_analysis.get("common_failures", [])
            all_failures.extend(failures)
        
        # Group by failure reason
        pattern_counts = {}
        for failure in all_failures:
            reason = failure.get("reason", "Unknown")
            pattern_counts[reason] = pattern_counts.get(reason, 0) + failure.get("count", 1)
        
        # Convert to pattern format
        for reason, total_count in pattern_counts.items():
            if total_count > 1:  # Only patterns that occur multiple times
                failure_patterns.append({
                    "pattern": reason,
                    "frequency": total_count,
                    "severity": "high" if total_count > 5 else "medium" if total_count > 2 else "low"
                })
        
        return sorted(failure_patterns, key=lambda x: x["frequency"], reverse=True)
    
    async def _save_evaluation_report(self, report: EvaluationReport) -> str:
        """Save evaluation report to file"""
        try:
            reports_dir = "outputs/reports"
            os.makedirs(reports_dir, exist_ok=True)
            
            report_filename = f"evaluation_report_{report.report_id}.json"
            report_path = os.path.join(reports_dir, report_filename)
            
            with open(report_path, 'w') as f:
                json.dump(report.to_dict(), f, indent=2)
            
            self.logger.info(f"Evaluation report saved to {report_path}")
            return report_path
            
        except Exception as e:
            self.logger.error(f"Error saving evaluation report: {e}")
            return ""
    
    async def _record_visual_trace(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Record visual trace (screenshot) for current step"""
        try:
            screenshot_data = task.get("screenshot_data")
            step_info = task.get("step_info", {})
            
            if not screenshot_data and not task.get("screenshot_path"):
                return {
                    "status": "error",
                    "error": "No screenshot data or path provided"
                }
            
            # Generate screenshot filename
            timestamp = int(time.time() * 1000)
            step_id = step_info.get("step_id", "unknown")
            screenshot_filename = f"trace_{step_id}_{timestamp}.png"
            screenshot_path = os.path.join(self.visual_traces_dir, screenshot_filename)
            
            if task.get("screenshot_path"):
                # Copy existing screenshot
                import shutil
                shutil.copy2(task["screenshot_path"], screenshot_path)
            else:
                # Save screenshot data
                with open(screenshot_path, 'wb') as f:
                    f.write(screenshot_data)
            
            # Add to current episode's visual trace
            if self.current_episode:
                self.current_episode.visual_trace.append(screenshot_path)
            
            return {
                "status": "success",
                "screenshot_path": screenshot_path,
                "message": "Visual trace recorded"
            }
            
        except Exception as e:
            self.logger.error(f"Error recording visual trace: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
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
    
    async def _handle_supervision_request(self, message: AgentMessage):
        """Handle supervision request"""
        try:
            content = message.content
            action = content.get("action", "")
            
            result = await self.execute_task(content)
            
            # Send response
            await self.send_message(
                receiver=message.sender,
                message_type=MessageType.SUPERVISION_RESPONSE,
                content=result,
                correlation_id=message.correlation_id
            )
            
        except Exception as e:
            self.logger.error(f"Error handling supervision request: {e}")
            await self._send_error_response(message, str(e))
    
    async def _handle_execution_response(self, message: AgentMessage):
        """Handle execution response for episode tracking"""
        try:
            if self.current_episode:
                execution_data = message.content
                self.current_episode.execution_trace.append(execution_data)
                
                self.logger.debug(f"Added execution data to episode {self.current_episode.episode_id}")
                
        except Exception as e:
            self.logger.error(f"Error handling execution response: {e}")
    
    async def _handle_verification_response(self, message: AgentMessage):
        """Handle verification response for episode tracking"""
        try:
            if self.current_episode:
                verification_data = message.content
                self.current_episode.verification_results.append(verification_data)
                
                self.logger.debug(f"Added verification data to episode {self.current_episode.episode_id}")
                
        except Exception as e:
            self.logger.error(f"Error handling verification response: {e}")
    
    def get_episodes_summary(self) -> Dict[str, Any]:
        """Get summary of all episodes"""
        if not self.test_episodes:
            return {
                "total_episodes": 0,
                "success_rate": 0.0,
                "average_duration": 0.0
            }
        
        total_episodes = len(self.test_episodes)
        successful_episodes = sum(1 for episode in self.test_episodes.values() 
                                if episode.final_status == "success")
        success_rate = successful_episodes / total_episodes
        
        durations = []
        for episode in self.test_episodes.values():
            if episode.end_time > 0:
                durations.append(episode.end_time - episode.start_time)
        
        average_duration = sum(durations) / len(durations) if durations else 0.0
        
        return {
            "total_episodes": total_episodes,
            "successful_episodes": successful_episodes,
            "success_rate": success_rate,
            "average_duration": average_duration,
            "episodes": [episode.episode_id for episode in self.test_episodes.values()]
        }
    
    def get_latest_evaluation_report(self) -> Optional[Dict[str, Any]]:
        """Get the latest evaluation report"""
        if not self.evaluation_reports:
            return None
        
        latest_report = max(self.evaluation_reports, key=lambda r: r.generated_at)
        return latest_report.to_dict()
