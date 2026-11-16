# Tutorial

A reading order for the code. The comments in the source do the explaining; these pages tell you
**which files to open, in which order, and which comments to grep for**.

Each chapter has a git tag on the commit that introduced it, so you can see the code as it was
built up step by step:

```bash
git checkout chapter-03      # code as of chapter 3
git checkout main            # back to the latest
```

The tags are a snapshot of history. A few comments were tidied in later chapters (for example the
`# WHY:` tags were normalised in chapter 8), so read the latest code on `main` and use the tags to
see what each step added (`git diff chapter-02 chapter-03`).

| # | Chapter | What it teaches | Tag |
|---|---|---|---|
| 1 | [Scaffold](01-scaffold.md) | Repo layout, why the client version is pinned by hand | [`chapter-01`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-01) |
| 2 | [Contracts and config](02-contracts-and-config.md) | Layers talk only through two dataclasses; every tunable lives in YAML and is validated | [`chapter-02`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-02) |
| 3 | [The CARLA session](03-sim-session.md) | Why synchronous mode, and why cleanup must always run | [`chapter-03`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-03) |
| 4 | [Input](04-input.md) | One interface for every device; simulating analog pedals with a keyboard | [`chapter-04`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-04) |
| 5 | [Control and output](05-control-and-output.md) | Blinker auto-cancel, light bits, drawing the HUD, logging without stalling | [`chapter-05`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-05) |
| 6 | [The main loop](06-main-loop.md) | The 8 steps of one tick, frame matching, real-time pacing and overruns | [`chapter-06`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-06) |
| 7 | [Testing without a simulator](07-testing.md) | Faking `carla`, pure functions, a headless smoke test of the loop | [`chapter-07`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-07) |
| 8 | [From PoC to real rig](08-to-real-rig.md) | Following the `SWAP[...]` tags to a wheel, a stalk and multiple monitors | [`chapter-08`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-08) |

## Comment tags used throughout

| Tag | Meaning | Find them |
|---|---|---|
| `# WHY:` | A non-obvious decision, explained | `grep -rn "# WHY:" src/` |
| `# TUNE:` | A value you'll likely adjust, with its config key | `grep -rn "# TUNE:" src/` |
| `# SWAP[hardware]:` | Where real wheel / pedals / stalk / gauge replace PoC code | `grep -rn "SWAP\[hardware\]" src/` |
| `# SWAP[multi-monitor]:` | Where multi-screen changes go | `grep -rn "SWAP\[multi-monitor\]" src/` |
| `# RESEARCH:` | Where experiment-specific logic goes | `grep -rn "RESEARCH:" src/` |
