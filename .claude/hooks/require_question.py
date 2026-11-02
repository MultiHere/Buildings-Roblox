"""Stop hook: a turn must end with AskUserQuestion (owner rule: never stop without asking).

Blocks the stop once with a reason when the last tool call of the turn was not AskUserQuestion.
Lets the stop through only when the hook already blocked once (stop_hook_active). Waiting on background
work is no excuse (owner 2026-10-29): ask instead.
"""
import json
import sys

IGNORE = {"mcp__ccd_turn__wrap_up", "mcp__ccd_turn__update_plan", "TodoWrite"}


def is_human(entry):
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        kinds = {b.get("type") for b in content if isinstance(b, dict)}
        return "tool_result" not in kinds and "text" in kinds
    return False


def last_tool(path):
    last = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if is_human(entry):
                last = None
            elif entry.get("type") == "assistant":
                for b in entry.get("message", {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") not in IGNORE:
                        last = b
    return last


def main():
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        return
    try:
        tool = last_tool(data["transcript_path"])
    except (KeyError, OSError):
        return
    if tool and tool.get("name") == "AskUserQuestion":
        return
    print(json.dumps({
        "decision": "block",
        "reason": "Owner rule: never stop without asking. End this turn with AskUserQuestion "
                  "(recommendation first). If a task or milestone just closed, write the status/next-session "
                  "note first, then ask.",
    }))


if __name__ == "__main__":
    main()
