import pytest

from wand_collect.cli import main


def test_help_prints_usage(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    assert "usage: wand-collect" in capsys.readouterr().out
