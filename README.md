# Bodycam FlySky Bridge

Fly the FPV drone in **Bodycam** with a **FlySky FS-i6X** transmitter. The bridge reads the transmitter over USB and feeds the game a virtual Xbox 360 controller. It can also spawn a drone when you flip a switch on the transmitter.

## Features

- Maps the transmitter's sticks to a virtual Xbox 360 controller
- Guided calibration that detects axes, directions and stick ranges
- Flight mode switch, sent to the game as a short LB press
- Drone spawn switch, which presses `5` and then left-clicks (only while the game is the foreground window)
- Cuts the throttle if the transmitter disconnects, then waits for it to reconnect
- English and Turkish interface

## Requirements

- Windows
- Python 3
- A FlySky FS-i6X connected over USB and recognized as a game controller (USB ID `284E:79A1`)
- The [`vgamepad`](https://pypi.org/project/vgamepad/) Python package, which relies on the ViGEmBus driver

## Installation

1. Download or clone this repository.
2. Install the dependency:

   ```
   pip install vgamepad
   ```

   If Windows prompts you to install ViGEmBus, accept it. If it doesn't and the bridge can't create the virtual controller, install ViGEmBus manually.

3. **Delete the included `flysky_config.json`.** It holds the calibration of the author's transmitter. Without it, the bridge guides you through your own calibration on first launch.

## Getting started

1. Connect the transmitter and turn it on.
2. Double-click `Baslat.bat` to start the bridge and follow the calibration prompts.
3. Start Bodycam and leave the bridge window open while you play.
4. Press `Ctrl+C` in the bridge window to stop.

### Scripts

| File | Meaning | What it does |
| --- | --- | --- |
| `Baslat.bat` | "Start" | Runs the bridge |
| `Kalibrasyon.bat` | "Calibration" | Repeats the full calibration |
| `Drone_Anahtari_Ata.bat` | "Assign drone switch" | Changes only the drone spawn switch |

## Calibration

The calibration assumes **Mode 1**: the right stick controls throttle and roll, and the left stick controls pitch and yaw. A beep counts down each step, and you hold the stick in position until it finishes.

1. Release the left stick and move the throttle all the way down.
2. Hold each requested position: roll right, pitch up, yaw right, throttle up.
3. Rotate both sticks in full circles through the corners for 10 seconds.
4. Release the sticks and lower the throttle.
5. Within 6 seconds, flip the switch you want for **flight mode**. To skip it, touch nothing.
6. Within 6 seconds, flip a different switch for **drone spawn**. To skip it, touch nothing.

If you skip the drone spawn switch, the bridge asks again the next time it starts.

## Controls

| Transmitter | Game |
| --- | --- |
| Throttle and yaw | Left stick |
| Pitch and roll | Right stick |
| Flight mode switch, either direction | LB |
| Drone spawn switch, either direction | `5`, a 0.6 second wait, then left click |

Use a 2-position switch (SWA, SWB or SWD) for these functions. The 3-position SWC can trigger them repeatedly from its middle position.

The spawn macro ignores flips made while it is already running (about 0.65 seconds) or while another window is in front.

## Language

The interface is in English by default. To switch language, run one of these commands from the project folder. The choice is saved.

```
python flysky_bridge.py --lang tr
python flysky_bridge.py --lang en
```

Each command also starts the bridge.

## Command-line options

| Option | Description |
| --- | --- |
| `--calibrate` | Run calibration only |
| `--assign-spawn` | Assign the drone spawn switch only |
| `--lang en\|tr` | Set and save the language |
| `--seconds N` | Run for N seconds, then exit (for testing) |

## Troubleshooting

| Problem | Try this |
| --- | --- |
| "Controller not found" | Check the USB cable and make sure the transmitter is on. Other FlySky models need a different `VID, PID` value in `flysky_bridge.py`. |
| "No movement detected" or "Not enough movement" | Repeat the step and push the stick fully to its limit. |
| The game doesn't respond to the sticks | Check that the bridge window is still running, then look at the game's controller settings. |
| A stick moves the wrong way or the wrong axis | Run `Kalibrasyon.bat` and follow each step exactly. |
| The drone spawn clicks too early | Increase `SPAWN_CLICK_DELAY_S` in `flysky_bridge.py`. |
| The drone spawn does nothing | Make sure the game is in front, then reassign the switch with `Drone_Anahtari_Ata.bat`. |

## Note on online play

The drone spawn switch sends simulated keyboard and mouse input to the game. Check the game's rules before using it in online matches.
