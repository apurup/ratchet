"""
Test: Research Skill with Playwright MCP

Run: python ratchet/skills/test_research.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratchet.skills.research import ResearchSkill
from ratchet.models import MiniMaxClient
from ratchet.curator import Curator


async def main():
    print("="*60)
    print("RATCHET RESEARCH SKILL TEST")
    print("Using Playwright MCP for browser automation")
    print("="*60)
    
    # Initialize
    research_skill = ResearchSkill()
    model = MiniMaxClient()
    curator = Curator(storage_path="/workspace/ratchet/data/research_curator.json")
    
    # Research a topic
    topic = "What is Databricks Unity Catalog"
    
    try:
        lesson = await research_skill.execute(
            topic=topic,
            curator=curator,
            model=model,
            max_pages=2,
        )
        
        print(f"\n✅ Research complete!")
        print(f"\nTopic: {lesson.topic}")
        print(f"\nKey Points:")
        for i, point in enumerate(lesson.key_points, 1):
            print(f"  {i}. {point}")
        
        print(f"\nSources:")
        for source in lesson.sources:
            print(f"  - {source}")
        
        print(f"\nCurator lessons: {len(curator.lessons)}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        research_skill.close()


if __name__ == "__main__":
    asyncio.run(main())
