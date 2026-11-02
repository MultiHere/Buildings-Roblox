"""Budget hook: owner's cap for this chat is CAP USD. Spend is summed from the transcript at Opus 5.5 list prices
(an over-estimate when the chat runs on Sonnet, so the cap is safe either way).

PostToolUse: tells the model the spend at each new whole dollar, and on every tool call from WARN on.
PreToolUse: from STOP on, denies everything except git, AskUserQuestion and writing docs/STATUS.md.
Test: python budget.py --test <transcript.jsonl>
"""
import json
import os
import sys
import tempfile

PER_MTOK = {"input": 4.0, "write_5m": 5.0, "write_1h": 8.0, "read": 0.20, "output": 20.0}
CAP = 10.0
WARN, STOP = CAP * 0.75, CAP * 0.9


def spend(path):
    # One API message can span several transcript lines; the last line of each id holds its final usage.
    usage = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") != "assistant":
                continue
            msg = entry.get("message") or {}
            if msg.get("usage"):
                usage[msg.get("id") or len(usage)] = msg["usage"]
    total = 0.0
    for u in usage.values():
        split = u.get("cache_creation") or {}
        w5 = split.get("ephemeral_5m_input_tokens", 0)
        w1 = split.get("ephemeral_1h_input_tokens", 0)
        if not split:
            w1 = u.get("cache_creation_input_tokens", 0)  # no split: count at the dearer price
        total += (u.get("input_tokens", 0) * PER_MTOK["input"] + w5 * PER_MTOK["write_5m"] + w1 * PER_MTOK["write_1h"]
                  + u.get("cache_read_input_tokens", 0) * PER_MTOK["read"]
                  + u.get("output_tokens", 0) * PER_MTOK["output"]) / 1e6
    return total


def allowed_when_over(tool, tool_input):
    if tool == "AskUserQuestion":
        return True
    if tool == "Bash":
        return tool_input.get("command", "").lstrip().startswith("git ")
    if tool in ("Write", "Edit"):
        return tool_input.get("file_path", "").replace("\\", "/").endswith("docs/STATUS.md")
    return False


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--test":
        print(f"{spend(sys.argv[2]):.2f} USD")
        return
    data = json.load(sys.stdin)
    try:
        used = spend(data["transcript_path"])
    except (KeyError, OSError):
        return
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        if used >= STOP and not allowed_when_over(data.get("tool_name", ""), data.get("tool_input") or {}):
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Budget reached: {used:.2f} of {CAP:.0f} USD. Commit and push with git, write "
                                            "docs/STATUS.md, then AskUserQuestion. Nothing else is allowed.",
            }}))
        return
    state = os.path.join(tempfile.gettempdir(), f"budget_{data.get('session_id', 'x')}")
    try:
        with open(state, encoding="utf-8") as f:
            last = int(f.read() or 0)
    except (OSError, ValueError):
        last = 0
    if used >= WARN or int(used) > last:
        with open(state, "w", encoding="utf-8") as f:
            f.write(str(int(used)))
        note = f"Budget: {used:.2f} of {CAP:.0f} USD used. Hard stop at {STOP:.2f}."
        if used >= WARN:
            note += " Finish what you are on, run the check, commit and push now."
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}}))


if __name__ == "__main__":
    main()
