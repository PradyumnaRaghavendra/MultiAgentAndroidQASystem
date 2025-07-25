#!/usr/bin/env python3
"""
Android-in-the-Wild Bonus Section Test Script
"""

import asyncio
import sys
import os

# Add paths
sys.path.insert(0, '.')

from src.evaluation.android_wild_evaluator import AndroidWildEvaluator
from src.agents.planner_agent import PlannerAgent
from src.agents.executor_agent import ExecutorAgent
from src.agents.verifier_agent import VerifierAgent
from src.agents.supervisor_agent import SupervisorAgent
from src.core.message_bus import MessageBus

async def run_complete_bonus_implementation():
    """Run the complete Android-in-the-Wild bonus section"""
    print("🏆 QUALGENT CHALLENGE - BONUS SECTION")
    print("Android-in-the-Wild Dataset Integration")
    print("=" * 70)
    
    # Configuration
    llm_config = {
        "provider": "mock",
        "model": "gpt-4"
    }
    
    # Initialize evaluator
    evaluator = AndroidWildEvaluator(llm_config)
    
    # Create realistic sessions
    sessions = evaluator.create_realistic_sessions(num_sessions=5)
    
    print(f"✅ Created {len(sessions)} realistic sessions")
    for i, session in enumerate(sessions, 1):
        print(f"  {i}. {session.session_id}: {session.inferred_task}")
    
    # Initialize agents
    message_bus = MessageBus()
    planner = PlannerAgent("aitw_planner", llm_config, message_bus)
    android_config = {"task_name": "settings_wifi", "device_config": {}}
    executor = ExecutorAgent("aitw_executor", llm_config, android_config, message_bus)
    verifier = VerifierAgent("aitw_verifier", llm_config, message_bus)
    supervisor = SupervisorAgent("aitw_supervisor", llm_config, message_bus)
    
    await planner.start()
    await executor.start()
    await verifier.start()
    await supervisor.start()
    
    print("✅ All agents started for AITW evaluation")
    
    # Reproduce sessions
    agents = {"planner": planner, "executor": executor, "verifier": verifier, "supervisor": supervisor}
    reproduction_results = []
    
    for session in sessions:
        result = await evaluator.reproduce_with_agents(session, agents)
        reproduction_results.append(result)
    
    # Generate report
    report = await evaluator.generate_comprehensive_report(reproduction_results)
    
    if "error" not in report:
        metrics = report["performance_metrics"]
        print(f"🏆 BONUS SECTION COMPLETE!")
        print(f"📊 Overall Score: {metrics['overall_score']:.1%}")
        print(f"📁 Report: outputs/reports/android_wild_comprehensive_evaluation.json")
    
    # Cleanup
    await planner.stop()
    await executor.stop()
    await verifier.stop()
    await supervisor.stop()

if __name__ == "__main__":
    asyncio.run(run_complete_bonus_implementation())