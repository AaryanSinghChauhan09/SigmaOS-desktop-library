    # SigmaOS-desktop-library

    Shared desktop library (settings, icons, xapp glue)

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/linuxmint/cinnamon-desktop

    ## Design principles applied
    - **Abstraction**
- **Defensive Programming**
- **Fail-Fast**
- **Separation of Concerns**
- **KISS**
- **Deterministic Testing**

    ## Usage
    Verbs: `settings-get, settings-set, icon-theme, monitor-plan`

    ```
    $ sigma-desktop settings-get org.sigma.desktop.icon-theme
Mint-Y
$ sigma-desktop settings-set org.sigma.desktop.clock-format 12h
org.sigma.desktop.clock-format = 12h
$ sigma-desktop icon-theme --list
$ sigma-desktop monitor-plan --monitor eDP-1:1920x1080 --monitor HDMI-1:2560x1440@1.5 --primary eDP-1
xrandr --output eDP-1 --mode 1920x1080 --pos 0x0 --scale 1.0x1.0 --primary
xrandr --output HDMI-1 --mode 2560x1440 --pos 1920x0 --scale 1.5x1.5

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
