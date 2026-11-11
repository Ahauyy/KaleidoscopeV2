"""Example Python integration script importing KaleidoscopeV2 cleanly."""

from pathlib import Path

from kaleidoscope import FlowHeadlessBot, load_settings


def main() -> None:
    settings = load_settings()

    tasks = [
        {
            "name": "guardian_golem",
            "preset": "character",
            "prompt": "Stylized low-poly crystal stone guardian golem with moss shoulders and glowing amber core",
        },
        {
            "name": "arcane_greatsword",
            "preset": "weapon",
            "prompt": "Ornate gold and rose-quartz magical greatsword with feathered hilt wings",
        },
    ]

    with FlowHeadlessBot(settings=settings) as bot:
        bot.navigate()
        bot.verify_authenticated()

        for task in tasks:
            result = bot.generate_asset(
                name=task["name"],
                prompt=task["prompt"],
                preset=task["preset"],
                output_dir=Path(settings.output_dir),
            )
            print(f"[{result['name']}] Composite: {result['composite']}")
            for view_path in result["views"]:
                print(f"  View: {view_path.name}")


if __name__ == "__main__":
    main()
