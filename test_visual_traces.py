#!/usr/bin/env python3
"""
Test Visual Trace Generation
Tests that visual traces (PNG files) are properly generated in outputs/visual_traces/
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
sys.path.insert(0, '.')

load_dotenv()

from src.agents.planner_agent import PlannerAgent
from src.agents.executor_agent import ExecutorAgent
from src.agents.supervisor_agent import SupervisorAgent
from src.core.message_bus import MessageBus

async def test_visual_trace_generation():
    """Test that visual traces are actually generated"""
    print("🎬 Testing Visual Trace Generation")
    print("=" * 50)
    
    # LLM config (using your real Gemini API)
    llm_config = {
        "provider": "google",
        "model": "gemini-1.5-flash",
        "api_key": os.getenv("GOOGLE_API_KEY")
    }
    
    # Android config
    android_config = {
        "task_name": "settings_wifi"
    }
    
    print("🔧 Initializing agents...")
    
    # Initialize message bus and agents
    message_bus = MessageBus()
    
    supervisor = SupervisorAgent("supervisor_agent", llm_config, message_bus)
    executor = ExecutorAgent("executor_agent", llm_config, android_config, message_bus)
    planner = PlannerAgent("planner_agent", llm_config, message_bus)
    
    # Start all agents
    await supervisor.start()
    await executor.start()
    await planner.start()
    
    print(" All agents started successfully")
    
    # Check initial state of visual traces directory
    visual_traces_dir = "outputs/visual_traces"
    print(f"\n Visual traces directory: {visual_traces_dir}")
    
    if os.path.exists(visual_traces_dir):
        initial_files = os.listdir(visual_traces_dir)
        print(f"   Initial files: {len(initial_files)}")
    else:
        print("   Directory doesn't exist yet (will be created)")
        initial_files = []
    
    # Start episode tracking
    print("\n🎬 Starting episode tracking...")
    episode_result = await supervisor.execute_task({
        "action": "start_episode",
        "goal": "Test Wi-Fi toggle with visual traces",
        "episode_id": "visual_trace_test_001"
    })
    
    print(f" Episode started: {episode_result['status']}")
    
    # Create a plan using real Gemini
    print("\n Creating plan with real Gemini...")
    plan_result = await planner.execute_task({
        "goal": "Test turning Wi-Fi on and off",
        "context": {"device": "android", "app": "settings"}
    })
    
    if plan_result["status"] == "success":
        plan = plan_result["plan"]
        steps = plan["steps"]
        print(f" Plan created with {len(steps)} steps")
        
        # Show the plan
        for i, step in enumerate(steps, 1):
            print(f"   {i}. {step['description']}")
        
        # Execute first few steps to generate visual traces
        print("\n Executing steps to generate visual traces...")
        
        max_steps = min(3, len(steps))  # Execute max 3 steps for testing
        for i, step in enumerate(steps[:max_steps]):
            print(f"\n   Step {i+1}/{max_steps}: {step['description']}")
            
            try:
                result = await executor._execute_single_step(step)
                print(f"   Status: {result['status']}")
                
                if result.get("screenshot_path"):
                    print(f"    Screenshot: {os.path.basename(result['screenshot_path'])}")
                else:
                    print("     No screenshot generated")
                
                # Small delay between steps
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f"   ❌ Step execution failed: {e}")
        
        # Check if visual traces were created
        print("\n Checking visual trace generation results...")
        
        if os.path.exists(visual_traces_dir):
            current_files = os.listdir(visual_traces_dir)
            new_files = [f for f in current_files if f not in initial_files]
            
            print(f"    Total files in directory: {len(current_files)}")
            print(f"    New files generated: {len(new_files)}")
            
            if new_files:
                print("    SUCCESS: Visual traces are being generated!")
                print("    New visual trace files:")
                for trace_file in sorted(new_files):
                    print(f"      • {trace_file}")
            else:
                print("    FAILURE: No new visual traces found")
                print("    Check if Executor → Supervisor communication is working")
                
            # Show all files in visual traces directory
            if current_files:
                print(f"\n    All files in {visual_traces_dir}:")
                for file in sorted(current_files):
                    file_path = os.path.join(visual_traces_dir, file)
                    size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    print(f"      • {file} ({size} bytes)")
            
        else:
            print("    FAILURE: Visual traces directory was never created")
            print("    Check Supervisor Agent initialization")
        
        # Also check screenshots directory
        screenshots_dir = "outputs/screenshots"
        if os.path.exists(screenshots_dir):
            screenshot_files = os.listdir(screenshots_dir)
            print(f"\n   📸 Screenshots directory has {len(screenshot_files)} files")
            if screenshot_files:
                print("    Screenshots are being generated by AndroidEnvWrapper")
            else:
                print("     No screenshots found - check AndroidEnvWrapper")
        else:
            print(f"\n    Screenshots directory {screenshots_dir} doesn't exist")
    
    else:
        print(f" Plan creation failed: {plan_result.get('error', 'Unknown error')}")
        print(" Check your Gemini API key and network connection")
    
    # End episode
    print("\n Ending episode...")
    end_result = await supervisor.execute_task({
        "action": "end_episode",
        "final_status": "completed"
    })
    print(f" Episode ended: {end_result['status']}")
    
    # Stop agents
    print("\n Stopping agents...")
    await supervisor.stop()
    await executor.stop()
    await planner.stop()
    print(" All agents stopped")
    
    # Final summary
    print("\n" + "=" * 50)
    print(" VISUAL TRACE TEST SUMMARY:")
    print("=" * 50)
    
    if os.path.exists(visual_traces_dir):
        final_files = os.listdir(visual_traces_dir)
        if final_files:
            print(f" SUCCESS: {len(final_files)} visual trace files found")
            print(" Visual traces are working correctly!")
            print("\n Next steps:")
            print("   1. Visual traces are now being generated")
            print("   2. Run your existing test.py for accuracy measurement")
            print("   3. Both PNG traces and JSON reports will be available")
        else:
            print(" FAILURE: No visual trace files found")
            print("\n Troubleshooting:")
            print("   1. Check if executor_agent.py was updated correctly")
            print("   2. Verify message bus communication")
            print("   3. Check supervisor agent initialization")
    else:
        print(" FAILURE: Visual traces directory not created")
        print("\n Troubleshooting:")
        print("   1. Check supervisor agent is running")
        print("   2. Verify visual_traces_dir creation in SupervisorAgent")
    
    print("\n Visual trace test completed!")

if __name__ == "__main__":
    print(" Starting Visual Trace Generation Test...")
    print("This will test if PNG files are generated in outputs/visual_traces/")
    print()
    
    try:
        asyncio.run(test_visual_trace_generation())
    except KeyboardInterrupt:
        print("\n Test interrupted by user")
    except Exception as e:
        print(f"\n Test failed with error: {e}")
        import traceback
        traceback.print_exc()