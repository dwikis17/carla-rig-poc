# Chapter 1: Scaffold

**Tag:** [`chapter-01`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-01) · [Index](README.md) · Next: [Chapter 2](02-contracts-and-config.md)

**What it teaches:** how the repo is laid out by layer, and why the `carla` client version is the
one dependency you must set by hand.

## Read in this order

1. [`requirements.txt`](../requirements.txt): `carla` is commented out on purpose. The client must
   be **exactly** the server's version, and only some Python versions have a wheel for each release.
2. [`src/carla_rig/__init__.py`](../src/carla_rig/__init__.py): the data-flow diagram of one tick.
3. The folder names under [`src/carla_rig/`](../src/carla_rig/): `input/`, `control/`, `sim/`,
   `output/`, `utils/`. Each folder is one layer; later chapters fill them in.
4. [`pyproject.toml`](../pyproject.toml): `pythonpath = ["src"]` lets `pytest` find the package
   without installing it.

## Try it

```bash
git show --stat chapter-01
```
