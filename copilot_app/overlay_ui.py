"""Desktop overlay entry point. The working UI remains in overlay_copilot."""

from overlay_copilot import Overlay, install_mss_if_needed, load_local_env


def main() -> None:
    load_local_env()
    install_mss_if_needed()
    Overlay().run()


if __name__ == "__main__":
    main()
