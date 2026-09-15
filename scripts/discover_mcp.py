"""Read-only capability discovery; writes no models and executes no DAX."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from powerbi_agent.adapters import ModelingMCPAdapter
from powerbi_agent.core import write_json

if __name__ == "__main__":
    result = asyncio.run(ModelingMCPAdapter().discover())
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/mcp-tools.json")
    write_json(target, result)
    print(f"Discovered {len(result)} tools; schemas saved to {target}")
