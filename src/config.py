MODEL_ID = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
MEMORY_ID = "DesignAgentMemory-oBupukC2Dp"
CACHE_FOLDER = "cache"
with open("instructions.txt", "r") as f:
    SYSTEM_PROMPT = f.read()
