# Chapter 7: Testing without a simulator

**Tag:** [`chapter-07`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-07) · [Index](README.md) · Previous: [Chapter 6](06-main-loop.md) · Next: [Chapter 8](08-to-real-rig.md)

**What it teaches:** how the layer rules pay off: almost everything is testable on a laptop with no
CARLA and no window.

## Read in this order

1. [`tests/conftest.py`](../tests/conftest.py) and [`tests/fake_carla.py`](../tests/fake_carla.py):
   the fake `carla` is installed before any test imports project code, so the real client is never loaded.
2. [`tests/test_keyboard_ramp.py`](../tests/test_keyboard_ramp.py): testing the pure input math, and
   a test that checks in a clean interpreter that the input layer never imports `carla`.
3. [`tests/test_controller.py`](../tests/test_controller.py): blinker auto-cancel scenarios and
   light-bit mapping against a fake vehicle.
4. [`tests/test_config.py`](../tests/test_config.py): each validation rule has a test that breaks it.
5. [`tests/test_main_smoke.py`](../tests/test_main_smoke.py): the real loop and HUD run for four
   ticks against a fake sim with SDL's dummy video driver.

## Try it

```bash
pytest -v
```

Then break something on purpose (for example drop the `state.clamped()` call in
`VehicleController.apply`, or remove the direction check in `BlinkerAutoCancel`) and see which test catches it.
