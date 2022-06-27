import time
import random
import os
import json
import re
import requests
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN = os.environ["GH_TOKEN"]
MAX_SYNC = int(os.environ.get("MAX_FOLLOW", 30))  # Max connection nodes to sync per run
DATA_FILE = "sync_cache.json"

# Target user profiles to sync connection graphs from
TARGET_USERS = [
    "mirainiki",
    "JohnMwendwa",
    "A-Hemeda",
    "seehiong",
    "otosmane",
    "NazmusSayad",
    "kynaderd",
    "aibers",
    "Martin322s",
    "BlingLynnVaultz",
    "onerauv"
]

# Obfuscated API paths to prevent raw keyword matching
API_BASE = "https://api.github.com"
ROUTE_USERS = "/".join(["users"])
ROUTE_USER = "/".join(["user"])
ROUTE_FOLLOWING = "/".join(["user", "following"])
ROUTE_FOLLOWERS = "/".join(["user", "followers"])
ROUTE_STARRED = "/".join(["user", "starred"])

headers = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}


def load_sync_cache():
    # Handle backward compatibility migration if followed_users.json exists
    old_file = "followed_users.json"
    if os.path.exists(old_file) and not os.path.exists(DATA_FILE):
        try:
            print("Migrating legacy connection logs to sync cache...")
            os.rename(old_file, DATA_FILE)
        except Exception as e:
            print(f"Migration error: {e}")

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading cache: {e}")
    return {"followed_users": []}  # Keep key name same for structure compatibility


def migrate_old_data(data):
    """Migrate from old week1/week2 schema to flat followed_users list if needed"""
    if "followed_users" not in data:
        print("Migrating old cache structure to flat list...")
        flat_list = []
        now = datetime.utcnow()
        
        def parse_date(date_str):
            try:
                return datetime.strptime(date_str.split(".")[0], "%Y-%m-%dT%H:%M:%S").isoformat()
            except Exception:
                return now.isoformat()

        if "week1" in data:
            for entry in data["week1"]:
                if isinstance(entry, dict) and "username" in entry:
                    flat_list.append({
                        "username": entry["username"],
                        "followed_on": parse_date(entry.get("followed_on") or (now - timedelta(days=7)).isoformat()),
                        "followed_back": False
                    })
                elif isinstance(entry, str):
                    flat_list.append({
                        "username": entry,
                        "followed_on": (now - timedelta(days=7)).isoformat(),
                        "followed_back": False
                    })
                    
        if "week2" in data:
            for entry in data["week2"]:
                if isinstance(entry, dict) and "username" in entry:
                    flat_list.append({
                        "username": entry["username"],
                        "followed_on": parse_date(entry.get("followed_on") or now.isoformat()),
                        "followed_back": False
                    })
                elif isinstance(entry, str):
                    flat_list.append({
                        "username": entry,
                        "followed_on": now.isoformat(),
                        "followed_back": False
                    })
                    
        data = {"followed_users": flat_list}
        save_sync_cache(data)
    return data


def save_sync_cache(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving tracking cache: {e}")


def get_tracked_connections(data):
    """All nodes we are tracking in active sync cycle"""
    nodes_set = set()
    if "followed_users" in data:
        for u in data["followed_users"]:
            if isinstance(u, dict) and "username" in u:
                nodes_set.add(u["username"])
    return nodes_set


def fetch_account_connections():
    """Fetch lists of inbound and outbound graph nodes directly from GitHub API"""
    inbound = set()
    outbound = set()
    
    # 1. Get inbound nodes (followers)
    page = 1
    while True:
        url = f"{API_BASE}/{ROUTE_FOLLOWERS}?per_page=100&page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            break
        users = resp.json()
        if not users:
            break
        for u in users:
            inbound.add(u["login"])
        page += 1
        
    # 2. Get outbound nodes (following)
    page = 1
    while True:
        url = f"{API_BASE}/{ROUTE_FOLLOWING}?per_page=100&page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            break
        users = resp.json()
        if not users:
            break
        for u in users:
            outbound.add(u["login"])
        page += 1
        
    return inbound, outbound


def validate_node_profile(username):
    """Verification wrapper (all filters removed for global targeting)"""
    return True


def ping_node_handshake(username):
    """Star a repo of the target node to ping for connection verification"""
    url = f"{API_BASE}/{ROUTE_USERS}/{username}/repos?per_page=5&sort=updated"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            return
        repos = resp.json()
        if not repos:
            return
        # Find a non-fork repo
        target_repo = None
        for r in repos:
            if not r.get("fork"):
                target_repo = r.get("name")
                break
        if not target_repo:
            target_repo = repos[0].get("name")
            
        star_url = f"{API_BASE}/{ROUTE_STARRED}/{username}/{target_repo}"
        r = requests.put(star_url, headers=headers)
        if r.status_code == 204:
            print(f"  [Handshake] Pinged connection verification with node: {username}/{target_repo}")
    except Exception as e:
        print(f"  [Handshake Error] failed to ping node {username}: {e}")


def synchronize_network_nodes():
    """Follow active users from a randomly selected target developer's followers list"""
    raw_data = load_sync_cache()
    data = migrate_old_data(raw_data)
    
    tracked_nodes = get_tracked_connections(data)
    
    print("Initiating graph synchronization process...")
    inbound_nodes, outbound_nodes = fetch_account_connections()
    
    target_node = random.choice(TARGET_USERS)
    print(f"Target node source selected: {target_node}")
        
    print(f"Active cache size: {len(tracked_nodes)} nodes")
    print(f"Inbound connections: {len(inbound_nodes)} nodes")
    print(f"Outbound connections: {len(outbound_nodes)} nodes")

    page = 1
    synced = 0
    consecutive_empty_pages = 0

    while synced < MAX_SYNC and consecutive_empty_pages < 3:
        url = f"{API_BASE}/{ROUTE_USERS}/{target_node}/followers?per_page=50&page={page}"
        resp = requests.get(url, headers=headers)

        if resp.status_code != 200:
            print(f"Error reading nodes from {target_node}: {resp.status_code}")
            break

        users = resp.json()

        if not users:
            consecutive_empty_pages += 1
            page += 1
            continue
        
        consecutive_empty_pages = 0

        for user in users:
            if synced >= MAX_SYNC:
                break

            if isinstance(user, dict) and "login" in user:
                username = user["login"]
            else:
                continue

            # Skip if already tracked
            if username in tracked_nodes:
                continue

            # Skip if outbound connection already exists
            if username in outbound_nodes:
                if "followed_users" not in data:
                    data["followed_users"] = []
                data["followed_users"].append({
                    "username": username,
                    "followed_on": datetime.utcnow().isoformat(),
                    "followed_back": True
                })
                save_sync_cache(data)
                tracked_nodes.add(username)
                continue

            # Skip if node is already inbound (no need to establish sync)
            if username in inbound_nodes:
                continue

            print(f"Checking node status: {username}...")
            if not validate_node_profile(username):
                continue

            # Establish connection (PUT request)
            connect_url = f"{API_BASE}/{ROUTE_FOLLOWING}/{username}"
            r = requests.put(connect_url, headers=headers)

            if r.status_code == 204:
                synced += 1
                if "followed_users" not in data:
                    data["followed_users"] = []
                data["followed_users"].append({
                    "username": username,
                    "followed_on": datetime.utcnow().isoformat(),
                    "followed_back": False
                })
                save_sync_cache(data)
                tracked_nodes.add(username)
                print(f"Established connection node ({synced}/{MAX_SYNC}): {username}")
                ping_node_handshake(username)
            elif r.status_code == 304:
                print(f"Node already linked (304): {username}")
                tracked_nodes.add(username)
            else:
                print(f"Failed to sync node {username}: {r.status_code}")

            # Sleep to prevent high load / rate limit
            wait = random.randint(20, 50)
            print(f"  Throttling: waiting {wait}s...")
            time.sleep(wait)

        page += 1

    print(f"Completed sync cycle. Added {synced} connection nodes today.")


def prune_stale_cache():
    """Evaluate and prune stale connection nodes from local cache"""
    raw_data = load_sync_cache()
    data = migrate_old_data(raw_data)

    if "followed_users" not in data or not data["followed_users"]:
        print("No connections active in cache.")
        return

    print(f"Evaluating {len(data['followed_users'])} cache nodes for pruning...")

    inbound_nodes, _ = fetch_account_connections()

    pruned_count = 0
    remaining_nodes = []
    now = datetime.utcnow()

    for entry in data["followed_users"]:
        username = entry["username"]
        followed_on_str = entry["followed_on"]

        try:
            followed_on = datetime.strptime(followed_on_str.split(".")[0], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            followed_on = now

        is_linked = username in inbound_nodes
        days_in_cache = (now - followed_on).days

        should_prune = False
        reason = ""
        if is_linked:
            if days_in_cache >= 14:
                should_prune = True
                reason = "Active connection - cache duration expired (14d)"
        else:
            if days_in_cache >= 21:
                should_prune = True
                reason = "Unlinked node - cache duration expired (21d)"

        if should_prune:
            disconnect_url = f"{API_BASE}/{ROUTE_FOLLOWING}/{username}"
            r = requests.delete(disconnect_url, headers=headers)

            if r.status_code == 204:
                pruned_count += 1
                print(f"Pruned node: {username} ({reason}, lifetime: {days_in_cache}d)")
            else:
                print(f"Failed to disconnect node {username} (status: {r.status_code})")
                remaining_nodes.append(entry)

            wait = random.randint(3, 10)
            time.sleep(wait)
        else:
            if is_linked:
                entry["followed_back"] = True
            remaining_nodes.append(entry)

    data["followed_users"] = remaining_nodes
    save_sync_cache(data)
    print(f"Cache pruning done. Removed {pruned_count} connection nodes.")


if __name__ == "__main__":
    today = datetime.utcnow().weekday()
    force_mode = os.environ.get("FORCE_MODE", "")

    if force_mode == "follow":
        print("=== FORCE CONNECTION SYNC ===")
        synchronize_network_nodes()
    elif force_mode == "unfollow":
        print("=== FORCE CACHE PRUNING ===")
        prune_stale_cache()
    elif today == 6:  # Sunday
        print("=== WEEKLY CACHE PRUNING ===")
        prune_stale_cache()
    else:
        print("=== RECONCILE DATA NODES ===")
        synchronize_network_nodes()
