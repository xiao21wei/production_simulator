import argparse


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Start the simulator web service. Select a dataset and start "
            "the simulation from the browser."
        )
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the simulator JSON config file.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help="Override the visualization/simulation speed.",
    )
    parser.add_argument(
        "--time-step",
        type=float,
        default=None,
        help="Override the real time step from the JSON config.",
    )
    parser.add_argument("--web-host", default=None)
    parser.add_argument("--web-port", type=int, default=None)
    realtime_group = parser.add_mutually_exclusive_group()
    realtime_group.add_argument(
        "--realtime",
        dest="realtime",
        action="store_true",
        help="Enable real-time waiting regardless of the JSON config.",
    )
    realtime_group.add_argument(
        "--fast-forward",
        dest="realtime",
        action="store_false",
        help="Disable real-time waiting regardless of the JSON config.",
    )
    parser.set_defaults(realtime=None)
    return parser.parse_args()


def main():
    args = parse_arguments()

    from simulator.config import DEFAULT_CONFIG_PATH
    from web_app import serve_dashboard

    serve_dashboard(
        config_path=args.config or DEFAULT_CONFIG_PATH,
        host=args.web_host,
        port=args.web_port,
        speed=args.speed,
        real_time_step=args.time_step,
        realtime=args.realtime,
    )


if __name__ == "__main__":
    main()
