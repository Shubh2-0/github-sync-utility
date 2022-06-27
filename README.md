# Developer Graph Sync Utility

A lightweight background data utility to synchronize developer connections, compile graph nodes, and manage local metadata indexing caches. 

## Features

- **Automated Reconciler:** Periodically fetches nodes from developer source profiles to populate a localized cache.
- **Node Validation:** Checks active connection targets to verify communication status.
- **Cache Pruning:** Prunes stale connection caches and unlinked graph elements automatically.
- **Automated Workflow:** Integrates with GitHub Actions workflow runners to compile insights logs directly inside the repository database.

## Architecture

```
                 +-------------------+
                 |  GitHub API Base  |
                 +---------+---------+
                           | (Fetch node arrays)
                           v
+-------------+      +-----+-----+      +-------------+
| TARGET LIST | ---> |  sync.py  | ---> | sync_cache  |
+-------------+      +-----------+      +-------------+
```

## Running Locally

To index node entries locally:

```bash
python sync.py
```
