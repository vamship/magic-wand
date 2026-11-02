from wand_core.casing import camel_keys, snake_keys, to_camel, to_snake


def test_name_conversion():
    assert to_snake("hueCenter") == "hue_center"
    assert to_snake("endHoldS") == "end_hold_s"
    assert to_camel("hue_center") == "hueCenter"
    assert to_camel("pre_s") == "preS"
    assert to_camel("fps") == "fps"


def test_nested_keys_converted_values_untouched():
    data = {
        "clipPadding": {"preS": 1},
        "items": [{"someKey": "too_long"}, 3],
        "reason": "keepThis",
    }
    snake = snake_keys(data)
    assert snake == {
        "clip_padding": {"pre_s": 1},
        "items": [{"some_key": "too_long"}, 3],
        "reason": "keepThis",
    }
    assert camel_keys(snake) == data
