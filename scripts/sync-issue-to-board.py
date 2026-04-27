#!/usr/bin/env python3
"""GitHub Actions workflow script: Sync a single issue to the Broville Roadmap board.

Triggered by GitHub Actions on issue events (opened, reopened, labeled, unlabeled, closed).
Adds the issue to the board if not present, then sets Status, Project, Priority, Deploy Stage.

Environment variables (set by GitHub Actions):
  GITHUB_TOKEN: GitHub App installation token (from echo-agent)
  ISSUE_NODE_ID: The node_id of the issue
  REPO_NAME: The repository name (e.g. "second-brain")
  ISSUE_NUMBER: The issue number
  ISSUE_STATE: "open" or "closed"
  LABELS: Comma-separated label names

Usage: python3 sync-issue-to-board.py
"""

import os, json, urllib.request, sys

PROJECT_ID = "PVT_kwDOEGI00s4BUgG0"

STATUS_FIELD = "PVTSSF_lADOEGI00s4BUgG0zhBnyZQ"
PROJECT_FIELD = "PVTSSF_lADOEGI00s4BUgG0zhBny54"
PRIORITY_FIELD = "PVTSSF_lADOEGI00s4BUgG0zhBny6w"
DEPLOY_FIELD = "PVTSSF_lADOEGI00s4BUgG0zhBpM3c"

STATUS = {"Backlog": "fe1c9b79", "Todo": "5e774a90", "In Progress": "915a2d40", "In Review": "885b0f1c", "Done": "dcd789f0"}
PROJECTS = {"Second Brain": "e5802239", "Hermes": "0b64c446", "Infrastructure": "1d2e1dce", "Command Center": "c653420c", "Homestead": "de150716", "Backlog Companion": "1c58f79a", "PodWave": "55440c93", "Nibble": "e3a9c2d8"}
PRIORITIES = {"P0 - Critical": "402a085e", "P1 - High": "f2192c64", "P2 - Medium": "1ae2c050", "P3 - Low": "2588bf33"}
DEPLOYS = {"Not Deployed": "3b2f36cb", "Local Dev": "2bf382c1", "Canary": "a9da2a7a", "Production": "64afe0c5", "Promoted": "2e78c806"}

REPO_TO_PROJECT = {
    "second-brain": "Second Brain",
    "second-brain-user-vault": "Second Brain",
    "pages": "Infrastructure",
    "homestead": "Homestead",
    "command-center": "Command Center",
    "backlog-companion": "Backlog Companion",
    "nibble": "Nibble",
    "podwave": "PodWave",
    "aegischat": "Hermes",
}


def api_graphql(query, token, variables=None):
    data = {"query": query}
    if variables:
        data["variables"] = variables
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_priority(labels):
    for l in labels:
        if l in ("priority:critical", "P0"): return "P0 - Critical"
        if l in ("priority:high", "P1"): return "P1 - High"
        if l in ("priority:medium", "P2"): return "P2 - Medium"
        if l in ("priority:low", "P3"): return "P3 - Low"
    return None


def get_status(state, labels):
    if state == "closed": return "Done"
    if "agent:canary" in labels or "agent:awaiting-feedback" in labels: return "In Review"
    if "agent:working" in labels: return "In Progress"
    return "Backlog"


def get_deploy(state, labels):
    if "agent:canary" in labels: return "Canary"
    if state == "closed" and "agent:canary" not in labels: return "Production"
    return "Not Deployed"


def main():
    token = os.environ["GITHUB_TOKEN"]
    issue_node_id = os.environ["ISSUE_NODE_ID"]
    repo_name = os.environ["REPO_NAME"]
    issue_number = os.environ["ISSUE_NUMBER"]
    issue_state = os.environ["ISSUE_STATE"]
    labels = [l.strip() for l in os.environ.get("LABELS", "").split(",") if l.strip()]

    key = f"{repo_name}#{issue_number}"
    print(f"Syncing {key} (state={issue_state}, labels={labels})")

    # Step 1: Check if issue is already on the board
    board_q = """query($pid: ID!) {
      node(id: $pid) {
        ... on ProjectV2 {
          items(first: 100) {
            nodes {
              id
              content {
                ... on Issue { number repository { name } }
              }
            }
          }
        }
      }
    }"""
    board = api_graphql(board_q, token, {"pid": PROJECT_ID})
    item_id = None
    for node in board["data"]["node"]["items"]["nodes"]:
        c = node.get("content")
        if c and isinstance(c, dict) and "number" in c:
            bkey = f"{c.get('repository',{}).get('name','')}#{c['number']}"
            if bkey == key:
                item_id = node["id"]
                break

    # Step 2: Add to board if not present
    if not item_id:
        print(f"  Adding {key} to board...")
        add_m = """mutation($pid: ID!, $cid: ID!) {
          addProjectV2ItemById(input: {projectId: $pid, contentId: $cid}) {
            item { id }
          }
        }"""
        r = api_graphql(add_m, token, {"pid": PROJECT_ID, "cid": issue_node_id})
        if "errors" in r:
            print(f"  ❌ ADD FAILED: {r['errors'][0].get('message','?')}")
            sys.exit(1)
        item_id = r["data"]["addProjectV2ItemById"]["item"]["id"]
        print(f"  ✅ Added (item: {item_id[:12]}...)")
    else:
        print(f"  Already on board (item: {item_id[:12]}...)")

    # Step 3: Set field values
    status = get_status(issue_state, labels)
    project = REPO_TO_PROJECT.get(repo_name)
    priority = get_priority(labels)
    deploy = get_deploy(issue_state, labels)

    if not project:
        print(f"  ⚠️ No Project mapping for repo '{repo_name}' — skipping Project field")

    for field_id, option_val, option_map in [
        (STATUS_FIELD, status, STATUS),
        (PROJECT_FIELD, project, PROJECTS),
        (PRIORITY_FIELD, priority, PRIORITIES),
        (DEPLOY_FIELD, deploy, DEPLOYS),
    ]:
        if option_val and option_map.get(option_val):
            update_m = """mutation($pid: ID!, $iid: ID!, $fid: ID!, $oid: String!) {
              updateProjectV2ItemFieldValue(input: {
                projectId: $pid, itemId: $iid, fieldId: $fid,
                value: { singleSelectOptionId: $oid }
              }) { projectV2Item { id } }
            }"""
            r = api_graphql(update_m, token, {"pid": PROJECT_ID, "iid": item_id, "fid": field_id, "oid": option_map[option_val]})
            if "errors" in r:
                print(f"  ⚠️ Field {option_val} failed: {r['errors'][0].get('message','?')}")
            else:
                print(f"  ✅ Set {option_val}")

    print(f"  Done: Status={status}, Project={project or '(unmapped)'}, Priority={priority}, Deploy={deploy}")


if __name__ == "__main__":
    main()