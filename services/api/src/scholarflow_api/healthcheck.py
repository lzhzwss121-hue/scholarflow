from scholarflow_api.main import health


def main() -> None:
    payload = health().model_dump()
    print(f"{payload['service']} {payload['version']} {payload['status']}")


if __name__ == "__main__":
    main()
