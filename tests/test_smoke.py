import importlib.metadata


def test_package_imports():
    import discord_acp_kiro  # noqa: F401
    from discord_acp_kiro import bot

    assert callable(bot.main)


def test_console_script_registered():
    eps = importlib.metadata.entry_points(group="console_scripts")
    names = {ep.name for ep in eps}
    assert "discord-acp-kiro-bot-bot" in names
