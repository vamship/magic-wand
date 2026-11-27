import pytest

from wand_train.cli import COMMANDS, main


def test_commands_are_the_documented_ones():
    assert list(COMMANDS) == [
        "training-data",
        "explore",
        "show",
        "train",
        "index",
    ]


@pytest.mark.parametrize("command", list(COMMANDS))
def test_command_is_a_shell(command, capsys):
    assert main([command]) == 2
    assert "not implemented yet" in capsys.readouterr().err


@pytest.mark.parametrize("command", list(COMMANDS))
def test_command_help_works(command, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([command, "--help"])
    assert exit_info.value.code == 0
    assert command in capsys.readouterr().out


def test_no_command_prints_usage(capsys):
    assert main([]) == 2
    assert "usage: wand-train" in capsys.readouterr().out
